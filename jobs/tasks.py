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

# Set up a specific logger for this module
logger = logging.getLogger(__name__)

# --- Helper functions ---

def _get_nearby_mechanics(latitude, longitude, radius=15):
    """
    Finds verified, online mechanics within a given radius.
    """
    logger.info(f"Searching for mechanics near (lat: {latitude}, lon: {longitude}) within {radius}km.")
    lat_r = Radians(latitude)
    lon_r = Radians(longitude)
    
    try:
        mechanics = Mechanic.objects.filter(
            status=Mechanic.StatusChoices.ONLINE, is_verified=True
        ).annotate(
            dlat=Radians(F('current_latitude')) - lat_r,
            dlon=Radians(F('current_longitude')) - lon_r,
            a=Power(Sin(F('dlat') / 2), 2) + Cos(lat_r) * Cos(Radians(F('current_latitude'))) * Power(Sin(F('dlon') / 2), 2),
            c=2 * Sqrt(F('a')),
            distance=6371 * F('c')
        ).filter(distance__lte=radius).order_by('distance')
        logger.info(f"Found {mechanics.count()} nearby mechanics.")
        return mechanics
    except Exception as e:
        logger.error(f"Error while querying for nearby mechanics: {e}", exc_info=True)
        return Mechanic.objects.none() # Return an empty queryset on error

async def _broadcast_to_mechanics(service_request, mechanic_user_ids):
    """
    Notifies batches of mechanics about a new service request.
    """
    channel_layer = get_channel_layer()
    batch_size = 5
    timeout = 30  # 30 seconds
    all_notified_mechanics = []
    request_id = str(service_request.id)

    logger.info(f"Starting broadcast for job {request_id} to {len(mechanic_user_ids)} mechanics in batches of {batch_size}.")

    job_details = {
        'id': request_id,
        'latitude': service_request.latitude,
        'longitude': service_request.longitude,
        'location': service_request.location,
        'vehical_type': service_request.vehical_type,
        'problem': service_request.problem,
        'additional_details': service_request.additional_details,
    }

    for i in range(0, len(mechanic_user_ids), batch_size):
        batch_ids = mechanic_user_ids[i:i + batch_size]
        all_notified_mechanics.extend(batch_ids)

        logger.info(f"Broadcasting job {request_id} to batch {i//batch_size + 1}: {batch_ids}")
        for user_id in batch_ids:
            try:
                await channel_layer.group_send(f"user_{user_id}", {'type': 'new_job_notification', 'job': job_details})
                logger.debug(f"mechanic email and shop name: {Mechanic.objects.get(user_id=user_id).user.email}, {Mechanic.objects.get(user_id=user_id).shop_name}")
            except Exception as e:
                logger.error(f"Failed to send job notification for job {request_id} to user {user_id}: {e}", exc_info=True)

        logger.info(f"Waiting for {timeout} seconds for responses for job {request_id}...")
        await asyncio.sleep(timeout)
        
        @database_sync_to_async
        def get_request_status_and_assignee(pk):
            try:
                req = ServiceRequest.objects.select_related('assigned_mechanic__user').get(pk=pk)
                assignee = req.assigned_mechanic.user.id if req.assigned_mechanic else None
                logger.debug(f"Checked status for job {pk}: Status is {req.status}, Assignee is {assignee}")
                return req.status, assignee
            except ServiceRequest.DoesNotExist:
                logger.warning(f"ServiceRequest {pk} not found during status check.")
                return None, None
            except Exception as e_db:
                logger.error(f"DB error checking status for job {pk}: {e_db}", exc_info=True)
                return None, None

        current_status, assignee_id = await get_request_status_and_assignee(service_request.id)

        if current_status == 'ACCEPTED':
            logger.info(f"Job {request_id} was accepted by mechanic (user_id: {assignee_id}). Halting broadcast.")
            # Notify other mechanics in the broadcast that the job is taken
            for user_id in all_notified_mechanics:
                if user_id != assignee_id:
                    try:
                        await channel_layer.group_send(
                            f"user_{user_id}", 
                            {'type': 'job_taken_notification', 'job_id': request_id}
                        )
                        
                    except Exception as e:
                        logger.error(f"Failed to send 'job taken' notification for job {request_id} to user {user_id}: {e}", exc_info=True)
            return  # Exit the broadcast loop

        else:
            logger.info(f"Batch timeout for job {request_id}. Notifying mechanics in batch {batch_ids} of expiration.")
            # Notify the current batch that their specific notification has expired
            for user_id in batch_ids:
                try:
                    await channel_layer.group_send(
                        f"user_{user_id}", 
                        {'type': 'job_expired_notification', 'job_id': request_id}
                    )
                except Exception as e:
                    logger.error(f"Failed to send 'job expired' notification for job {request_id} to user {user_id}: {e}", exc_info=True)

    # If the loop completes without the job being accepted
    @database_sync_to_async
    def expire_request(pk):
        try:
            updated_count = ServiceRequest.objects.filter(pk=pk, status='PENDING').update(status='EXPIRED')
            return updated_count > 0
        except Exception as e:
            logger.error(f"DB error expiring request {pk}: {e}", exc_info=True)
            return False

    was_expired = await expire_request(service_request.id)
    if was_expired:
        logger.info(f"Job {request_id} has been marked as EXPIRED after notifying all mechanics.")
    else:
        logger.warning(f"Attempted to expire job {request_id}, but it was not in PENDING state or was not found.")

# --- Celery Task ---

@shared_task(bind=True, name="find_and_notify_mechanics")
def find_and_notify_mechanics(self, service_request_id):
    """
    Celery task to find and notify mechanics.
    """
    task_id = self.request.id
    logger.info(f"[Task ID: {task_id}] Starting task for service_request_id: {service_request_id}")
    
    try:
        service_request = ServiceRequest.objects.get(id=service_request_id)
        
        # 1. Find mechanics
        mechanics = list(_get_nearby_mechanics(
            service_request.latitude, 
            service_request.longitude
        ))
        
        if not mechanics:
            logger.warning(f"[Task ID: {task_id}] No online or verified mechanics found for service request {service_request_id}. The request will expire.")
            ServiceRequest.objects.filter(id=service_request_id, status='PENDING').update(status='EXPIRED')
            return f"No mechanics found for request {service_request_id}."

        mechanic_user_ids = [m.user.id for m in mechanics]
        logger.info(f"[Task ID: {task_id}] Found {len(mechanic_user_ids)} mechanics for request {service_request_id}: {mechanic_user_ids}")

        # 2. Broadcast to mechanics
        async_to_sync(_broadcast_to_mechanics)(service_request, mechanic_user_ids)
        
        logger.info(f"[Task ID: {task_id}] Broadcast process completed for service request {service_request_id}.")

    except ServiceRequest.DoesNotExist:
        logger.error(f"[Task ID: {task_id}] ServiceRequest with ID {service_request_id} not found.")
    except Exception as e:
        logger.critical(f"[Task ID: {task_id}] An unexpected critical error occurred in find_and_notify_mechanics task for request {service_request_id}: {e}", exc_info=True)
        # Depending on your celery setup, you might want to retry the task
        # self.retry(exc=e, countdown=60)
    finally:
        logger.info(f"[Task ID: {task_id}] Task for service_request_id: {service_request_id} finished.")

    return f"Task for request {service_request_id} completed."