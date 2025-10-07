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
from .tasks import find_and_notify_mechanics

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
    authentication_classes = [CookieJWTAuthentication]
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

        # Create the service request object
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

        # *** CHANGE: Trigger the background task and respond immediately ***
        find_and_notify_mechanics.delay(service_request.id)

        return Response({
            'message': 'Request sent successfully. We are finding a mechanic for you.',
            'request_id': service_request.id
        }, status=status.HTTP_201_CREATED)

class AcceptServiceRequestView(APIView):
    authentication_classes = [CookieJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, request_id):
        try:
            with transaction.atomic():
                sr_locked = ServiceRequest.objects.select_for_update().get(id=request_id)
                
                if sr_locked.status == 'PENDING':
                    mechanic_profile = Mechanic.objects.select_for_update().get(user=request.user)
                    mechanic = mechanic_profile
                    sr_locked.status = 'ACCEPTED'
                    sr_locked.assigned_mechanic = mechanic
                    sr_locked.save()

                    channel_layer = get_channel_layer()
                    async_to_sync(channel_layer.group_send)(
                        f"user_{sr_locked.user.id}",
                        {
                            'type': 'mechanic.accepted',  # FIX: Change to 'mechanic.accepted'
                            'mechanic_details': {
                                'name': mechanic.user.get_full_name(),
                                'shop_name': mechanic.shop_name,
                                # Add any other details you want to send to the user
                            }
                        }
                    )
                    return Response({'message': 'Request accepted!'}, status=status.HTTP_200_OK)
                else:
                    return Response({'error': 'This request is no longer available.'}, status=status.HTTP_409_CONFLICT)
        except ServiceRequest.DoesNotExist:
            return Response({'error': 'Service request not found.'}, status=status.HTTP_404_NOT_FOUND)