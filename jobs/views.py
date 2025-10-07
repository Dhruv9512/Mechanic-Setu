from uuid import uuid4
from django.conf import settings
from django.core.cache import cache
from vercel_blob import put
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
from django.db.models import F,ExpressionWrapper, fields
from django.db.models.functions import Radians, Sin, Cos, Sqrt, Power
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
import asyncio
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
            return Response({"error": "Invalid data provided."}, status=status.HTTP_400_BAD_REQUEST)

        # ORM calls are sync, so fine here
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

        mechanics = list(self._get_nearby_mechanics(latitude, longitude))
        mechanic_user_ids = [m.user.id for m in mechanics]

        # run async broadcast synchronously
        async_to_sync(self._broadcast_to_mechanics)(service_request, mechanic_user_ids)

        return Response({
            'message': 'Request sent successfully.',
            'request_id': service_request.id
        }, status=status.HTTP_201_CREATED)

    def _get_nearby_mechanics(self, latitude, longitude, radius=15):
        # This remains a synchronous method
        lat_r = Radians(latitude)
        lon_r = Radians(longitude)
        mechanics = Mechanic.objects.filter(
            status=Mechanic.StatusChoices.ONLINE, is_verified=True
        ).annotate(
            dlat=Radians(F('current_latitude')) - lat_r,
            dlon=Radians(F('current_longitude')) - lon_r,
            a=Power(Sin(F('dlat') / 2), 2) + Cos(lat_r) * Cos(Radians(F('current_latitude'))) * Power(Sin(F('dlon') / 2), 2),
            c=2 * Sqrt(F('a')),
            distance=6371 * F('c')
        ).filter(distance__lte=radius).order_by('distance')
        return mechanics

    async def _broadcast_to_mechanics(self, service_request, mechanic_user_ids):
        # This method is already async, which is correct
        channel_layer = get_channel_layer()
        batch_size = 5
        timeout = 30  # 30 seconds

        for i in range(0, len(mechanic_user_ids), batch_size):
            batch_ids = mechanic_user_ids[i:i + batch_size]
            
            job_details = {
            'id': str(service_request.id),
            'latitude': service_request.latitude,
            'longitude': service_request.longitude,
            'location': service_request.location,
            'vehical_type': service_request.vehical_type,
            'problem': service_request.problem,
            'additional_details': service_request.additional_details,
            }

            logger.info(f"Broadcasting job {service_request.id} to batch: {batch_ids}")
            for user_id in batch_ids:
                await channel_layer.group_send(f"user_{user_id}", {'type': 'new_job_notification', 'job': job_details})

            await asyncio.sleep(timeout)
            
            @database_sync_to_async
            def get_request_status_and_assignee(pk):
                req = ServiceRequest.objects.select_related('assigned_mechanic__user').get(pk=pk)
                return req.status, req.assigned_mechanic.user.id if req.assigned_mechanic else None

            current_status, assignee_id = await get_request_status_and_assignee(service_request.id)

            if current_status == 'ACCEPTED':
                logger.info(f"Job {service_request.id} was accepted. Halting broadcast.")
                all_notified_mechanics = mechanic_user_ids[:i + batch_size]
                for user_id in all_notified_mechanics:
                    if user_id != assignee_id:
                        await channel_layer.group_send(f"user_{user_id}", {'type': 'job_taken_notification', 'job_id': str(service_request.id)})
                return 

            else:
                logger.info(f"Batch timeout for job {service_request.id}. Notifying mechanics.")
                for user_id in batch_ids:
                    await channel_layer.group_send(f"user_{user_id}", {'type': 'job_expired_notification', 'job_id': str(service_request.id)})
        
        @database_sync_to_async
        def expire_request(pk):
            ServiceRequest.objects.filter(pk=pk, status='PENDING').update(status='EXPIRED')
        
        await expire_request(service_request.id)
        logger.info(f"Job {service_request.id} expired completely.")


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
                            'type': 'job_accepted_notification',
                            'job': { 'id': str(sr_locked.id), 'mechanic_name': mechanic.user.get_full_name() }
                        }
                    )
                    return Response({'message': 'Request accepted!'}, status=status.HTTP_200_OK)
                else:
                    return Response({'error': 'This request is no longer available.'}, status=status.HTTP_409_CONFLICT)
        except ServiceRequest.DoesNotExist:
            return Response({'error': 'Service request not found.'}, status=status.HTTP_404_NOT_FOUND)