import threading
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from core.authentication import CookieJWTAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ServiceRequest
from users.models import Mechanic
from core.cache import cache_per_user
from django.utils.decorators import method_decorator

from django.db import transaction
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .tasks import find_and_notify_mechanics_thread_task

from .serializers import MechanicDataForUserSerializer,JobDetailsForMechanicSerializer
import logging
logger = logging.getLogger(__name__)


# View to update the status of a mechanic.
class UpdateMechanicStatusView(APIView):
    """
    View to update the status of a mechanic.
    Only accessible by admin users.
    """
    authentication_classes = [CookieJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def put(self, request):
        
        user_id = request.user.id
        new_status = request.data.get('status')

        if not user_id or not new_status:
            return Response({"error": "user_id and status are required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            mechanic = Mechanic.objects.get(user_id=user_id)
            mechanic.status = new_status
            mechanic.save()
            return Response({"message": "Mechanic status updated successfully."}, status=status.HTTP_200_OK)
        except Mechanic.DoesNotExist:
            return Response({"error": "Mechanic not found."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        


# View to get the basic needs of a mechanic.
@method_decorator(cache_per_user(60 * 5), name='get')
class GetBasicNeedsView(APIView):
    """
    View to get the basic needs of a mechanic.
    Only accessible by authenticated users.
    """
    authentication_classes = [CookieJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user_id = getattr(request.user, 'id', None)
        logger.info(f"GetBasicNeedsView called by user_id: {user_id}")

        if not user_id:
            logger.warning("No user_id found in request.user")
            return Response({"error": "user_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            mechanic = Mechanic.objects.get(user_id=user_id)
            logger.info(f"Mechanic found for user_id {user_id}: {mechanic}")
            
            basic_needs = {
                "first_name": mechanic.user.first_name,
                "last_name": mechanic.user.last_name,
                "shop_name": mechanic.shop_name,
                "status": mechanic.status,
                "is_verified": mechanic.is_verified,
            }
            return Response({"basic_needs": basic_needs}, status=status.HTTP_200_OK)
        
        except Mechanic.DoesNotExist:
            logger.error(f"Mechanic not found for user_id: {user_id}")
            return Response({"error": "Mechanic not found."}, status=status.HTTP_404_NOT_FOUND)
        
        except Exception as e:
            logger.exception(f"Unexpected error for user_id {user_id}: {e}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        


# View to create a new service request.
class CreateServiceRequestView(APIView):
    # authentication_classes = [CookieJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            latitude = float(request.data.get('latitude'))
            longitude = float(request.data.get('longitude'))
            location = request.data.get('location', '')
            vehical_type = request.data.get('vehical_type', '')
            problem = request.data.get('problem', '')
            additional_details = request.data.get('additional_details', '')
        except (TypeError, ValueError):
            return Response({"error": "Invalid data provided for the service request."}, status=status.HTTP_400_BAD_REQUEST)

        service_request = ServiceRequest.objects.create(
            user=request.user,
            latitude=latitude,
            longitude=longitude,
            location=location,
            vehical_type=vehical_type,
            problem=problem,
            additional_details=additional_details,
            status='PENDING'
        )

        # Start a new thread to run the task
        thread = threading.Thread(
            target=find_and_notify_mechanics_thread_task,
            args=(service_request.id,) # The comma is important for a single-item tuple
        )
        # Setting daemon to True ensures the thread won't block the main process from exiting
        thread.daemon = True 
        thread.start()

        return Response({
            'message': 'Request sent successfully. We are finding a mechanic for you.',
            'request_id': service_request.id
        }, status=status.HTTP_201_CREATED)


class AcceptServiceRequestView(APIView):
    # authentication_classes = [CookieJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, request_id):
        try:
            with transaction.atomic():
                sr_locked = ServiceRequest.objects.select_for_update().get(id=request_id)
                
                if sr_locked.status == 'PENDING':
                    mechanic_profile = Mechanic.objects.select_for_update().get(user=request.user)
                    sr_locked.status = 'ACCEPTED'
                    sr_locked.assigned_mechanic = mechanic_profile
                    sr_locked.save()

                    serializer = MechanicDataForUserSerializer(mechanic_profile)
                    mechanic_data = serializer.data

                    channel_layer = get_channel_layer()
                    async_to_sync(channel_layer.group_send)(
                        f"user_{sr_locked.user.id}",
                        {
                            'type': 'mechanic_accepted',
                            'mechanic_details': mechanic_data,
                            'job_id': sr_locked.id,
                        }
                    )
                    return Response({'message': 'Request accepted!'}, status=status.HTTP_200_OK)
                else:
                    return Response({'error': 'This request is no longer available.'}, status=status.HTTP_409_CONFLICT)
        except ServiceRequest.DoesNotExist:
            return Response({'error': 'Service request not found.'}, status=status.HTTP_404_NOT_FOUND)
        




class CancelServiceRequestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, request_id):
        try:
            with transaction.atomic():
                service_request = ServiceRequest.objects.select_related('user', 'assigned_mechanic__user').get(id=request_id)
                cancellation_reason = request.data.get('cancellation_reason', '')

                is_customer = service_request.user == request.user
                is_mechanic = service_request.assigned_mechanic and service_request.assigned_mechanic.user == request.user

                if not is_customer and not is_mechanic:
                    return Response({'error': 'You are not authorized to cancel this request.'}, status=status.HTTP_403_FORBIDDEN)

                if service_request.status not in ['PENDING', 'ACCEPTED']:
                    return Response({'error': 'This request cannot be cancelled at its current stage.'}, status=status.HTTP_400_BAD_REQUEST)
                
                original_customer_id = service_request.user.id
                original_mechanic_id = service_request.assigned_mechanic.user.id if service_request.assigned_mechanic else None

                service_request.status = 'CANCELLED'
                service_request.cancellation_reason = cancellation_reason
                service_request.save()

                channel_layer = get_channel_layer()

                if is_mechanic:
                    mechanic_profile = service_request.assigned_mechanic
                    mechanic_profile.status = 'ONLINE'
                    mechanic_profile.save()
                    
                    target_room = f'user_{original_customer_id}'
                    message = f"The mechanic has cancelled job request {service_request.id}."
                    if cancellation_reason:
                        message += f" Reason: {cancellation_reason}"
                    
                    async_to_sync(channel_layer.group_send)(
                        target_room,
                        {
                            'type': 'job_cancelled_notification',
                            'job_id': service_request.id,
                            'message': message
                        }
                    )

                elif is_customer and original_mechanic_id:
                    target_room = f'user_{original_mechanic_id}'
                    message = f"The customer has cancelled job request {service_request.id}."
                    if cancellation_reason:
                        message += f" Reason: {cancellation_reason}"

                    async_to_sync(channel_layer.group_send)(
                        target_room,
                        {
                            'type': 'job_cancelled_notification',
                            'job_id': service_request.id,
                            'message': message
                        }
                    )

                return Response({'message': 'The service request has been successfully cancelled.'}, status=status.HTTP_200_OK)
        except ServiceRequest.DoesNotExist:
            return Response({'error': 'Service request not found.'}, status=status.HTTP_404_NOT_FOUND)



class CompleteServiceRequestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, request_id):
        try:
            with transaction.atomic():
                service_request = ServiceRequest.objects.select_related('user', 'assigned_mechanic__user').get(id=request_id)

                # Authorization check: Only the assigned mechanic can complete the job.
                if not (service_request.assigned_mechanic and service_request.assigned_mechanic.user == request.user):
                    return Response({'error': 'You are not authorized to complete this request.'}, status=status.HTTP_403_FORBIDDEN)

                # Status validation: The job must be in 'ACCEPTED' state to be completed.
                if service_request.status != 'ACCEPTED':
                    return Response({'error': 'This request cannot be completed at its current stage.'}, status=status.HTTP_400_BAD_REQUEST)

                 # Get the price from the request data
                try:
                    price = float(request.data.get('price'))
                except (TypeError, ValueError):
                    return Response({"error": "Invalid price provided."}, status=status.HTTP_400_BAD_REQUEST)


                # Update service request
                service_request.status = 'COMPLETED'
                service_request.price = price
                service_request.save()

                # Update mechanic's status to ONLINE
                mechanic_profile = service_request.assigned_mechanic
                mechanic_profile.status = 'ONLINE'
                mechanic_profile.save()

                # Broadcast notification to the customer
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    f"user_{service_request.user.id}",
                    {
                        'type': 'job_completed_notification',
                        'job_id': service_request.id,
                        'message': f"Your service request {service_request.id} has been completed by the mechanic."
                    }
                )

                return Response({'message': 'Job has been marked as completed.'}, status=status.HTTP_200_OK)
        except ServiceRequest.DoesNotExist:
            return Response({'error': 'Service request not found.'}, status=status.HTTP_404_NOT_FOUND)





class SyncActiveJobView(APIView):
    """
    Checks for and returns the currently active job for a user upon reconnection.
    This allows the frontend to sync its state.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        active_request = None
        is_mechanic_user = False

        try:
            mechanic_profile = user.mechanic_profile
            active_request = ServiceRequest.objects.filter(
                assigned_mechanic=mechanic_profile,
                status='ACCEPTED'
            ).select_related('user', 'assigned_mechanic__user').first()
            is_mechanic_user = True
        except Mechanic.DoesNotExist:
            active_request = ServiceRequest.objects.filter(
                user=user,
                status__in=['PENDING', 'ACCEPTED']
            ).select_related('user', 'assigned_mechanic__user').first()

        if active_request:
            # --- MODIFICATION: Manually build the response based on user role ---
            if is_mechanic_user:
                # This is a mechanic, send them the job and customer details
                serializer=JobDetailsForMechanicSerializer(active_request)
                job_details =serializer.data
                return Response(job_details, status=status.HTTP_200_OK)
            else:
                # This is a customer, send them the mechanic's details
                if active_request.assigned_mechanic:
                    mechanic_profile = active_request.assigned_mechanic
                    serializer = MechanicDataForUserSerializer(mechanic_profile)
                    mechanic_data = serializer.data
                    return Response(mechanic_data, status=status.HTTP_200_OK)
                else:
                    # The job is pending and has no mechanic assigned yet
                    pending_data = {
                        'job_id': active_request.id,
                        'status': 'PENDING',
                        'message': 'Waiting for a mechanic to accept your request.'
                    }
                    return Response(pending_data, status=status.HTTP_200_OK)
                    
                
        else:
            return Response({'message': 'No active job found.'}, status=status.HTTP_200_OK)