from celery import shared_task
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.db import database_sync_to_async
from django.db.models import F
from django.db.models.functions import Radians, Sin, Cos, Sqrt, Power
import asyncio
import logging

from .models import ServiceRequest
from users.models import Mechanic

logger = logging.getLogger(__name__)

# --- Helper functions moved from views.py ---

def _get_nearby_mechanics(latitude, longitude, radius=15):
    """
    Finds verified, online mechanics within a given radius.
    This is now a standalone function.
    """
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

async def _broadcast_to_mechanics(service_request, mechanic_user_ids):
    """
    Notifies batches of mechanics about a new service request.
    This is now a standalone async function.
    """
    channel_layer = get_channel_layer()
    batch_size = 5
    timeout = 30  # 30 seconds

    all_notified_mechanics = []

    for i in range(0, len(mechanic_user_ids), batch_size):
        batch_ids = mechanic_user_ids[i:i + batch_size]
        all_notified_mechanics.extend(batch_ids)

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
            try:
                req = ServiceRequest.objects.select_related('assigned_mechanic__user').get(pk=pk)
                assignee = req.assigned_mechanic.user.id if req.assigned_mechanic else None
                return req.status, assignee
            except ServiceRequest.DoesNotExist:
                return None, None

        current_status, assignee_id = await get_request_status_and_assignee(service_request.id)

        if current_status == 'ACCEPTED':
            logger.info(f"Job {service_request.id} was accepted by {assignee_id}. Halting broadcast.")
            for user_id in all_notified_mechanics:
                if user_id != assignee_id:
                    await channel_layer.group_send(
                        f"user_{user_id}", 
                        {'type': 'job_taken_notification', 'job_id': str(service_request.id)}
                    )
            return 

        else:
            logger.info(f"Batch timeout for job {service_request.id}. Notifying mechanics.")
            for user_id in batch_ids:
                await channel_layer.group_send(
                    f"user_{user_id}", 
                    {'type': 'job_expired_notification', 'job_id': str(service_request.id)}
                )
    
    @database_sync_to_async
    def expire_request(pk):
        updated_count = ServiceRequest.objects.filter(pk=pk, status='PENDING').update(status='EXPIRED')
        return updated_count > 0

    was_expired = await expire_request(service_request.id)
    if was_expired:
        logger.info(f"Job {service_request.id} expired completely after notifying all batches.")


# --- Celery Task ---

@shared_task(name="find_and_notify_mechanics")
def find_and_notify_mechanics(service_request_id):
    """
    Celery task to find and notify mechanics, now using the local helper functions.
    """
    logger.info(f"Starting task for request ID: {service_request_id}")
    try:
        service_request = ServiceRequest.objects.get(id=service_request_id)
        
        # 1. Find mechanics using the local helper function
        mechanics = list(_get_nearby_mechanics(
            service_request.latitude, 
            service_request.longitude
        ))
        mechanic_user_ids = [m.user.id for m in mechanics]
        
        logger.info(f"Found {len(mechanic_user_ids)} mechanics for request {service_request_id}.")

        # 2. Broadcast using the local async helper function
        if mechanic_user_ids:
            async_to_sync(_broadcast_to_mechanics)(service_request, mechanic_user_ids)
        else:
            logger.warning(f"No online mechanics found for service request {service_request_id}.")

    except ServiceRequest.DoesNotExist:
        logger.error(f"ServiceRequest with ID {service_request_id} not found.")
    except Exception as e:
        logger.error(f"An error occurred in find_and_notify_mechanics task: {e}", exc_info=True)