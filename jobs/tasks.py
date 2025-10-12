import asyncio
import logging
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.db import database_sync_to_async
from django.db.models import F
from django.db.models.functions import Radians, Sin, Cos, Sqrt, Power

from .models import ServiceRequest
from users.models import Mechanic

import threading
from datetime import timedelta
from django.utils import timezone
from celery import shared_task

from .serializers import JobDetailsForMechanicSerializer
import logging

# Set up a specific logger for this module
logger = logging.getLogger(__name__)


# --- Helper functions (NO CHANGES NEEDED HERE) ---

def _get_nearby_mechanics(latitude, longitude, radius=15):
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
        return Mechanic.objects.none()

@database_sync_to_async
def get_mechanic_details(user_id):
    try:
        mechanic = Mechanic.objects.select_related('user').get(user_id=user_id)
        return mechanic.user.email, mechanic.shop_name
    except Mechanic.DoesNotExist:
        logger.warning(f"Mechanic with user_id {user_id} not found.")
        return None, None
    except Exception as e:
        logger.error(f"Error fetching details for mechanic {user_id}: {e}", exc_info=True)
        return None, None

@database_sync_to_async
def get_serialized_job_details(request_id):
    """
    Fetches a ServiceRequest and serializes it using the specific
    serializer for mechanics.
    """
    try:
        service_request = ServiceRequest.objects.get(id=request_id)
        serializer = JobDetailsForMechanicSerializer(service_request)
        return serializer.data
    except ServiceRequest.DoesNotExist:
        return None

async def _broadcast_to_mechanics(service_request, mechanic_user_ids):
    channel_layer = get_channel_layer()
    batch_size = 5
    timeout = 30  # 30 seconds
    all_notified_mechanics = []
    request_id = str(service_request.id)

    logger.info(f"Starting broadcast for job {request_id} to {len(mechanic_user_ids)} mechanics in batches of {batch_size}.")

    job_details = await get_serialized_job_details(request_id)

    for i in range(0, len(mechanic_user_ids), batch_size):
        batch_ids = mechanic_user_ids[i:i + batch_size]
        all_notified_mechanics.extend(batch_ids)

        logger.info(f"Broadcasting job {request_id} to batch {i//batch_size + 1}: {batch_ids}")
        for user_id in batch_ids:
            try:
                await channel_layer.group_send(f"user_{user_id}", {'type': 'new_job', 'service_request': job_details})
                email, shop_name = await get_mechanic_details(user_id)
                if email and shop_name:
                    logger.info(f"Mechanic details: Email={email}, Shop={shop_name}, UserID=user_{user_id}")
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
                return None, None
            except Exception as e_db:
                logger.error(f"DB error checking status for job {pk}: {e_db}", exc_info=True)
                return None, None

        current_status, assignee_id = await get_request_status_and_assignee(service_request.id)

        if current_status == 'ACCEPTED':
            logger.info(f"Job {request_id} was accepted by mechanic (user_id: {assignee_id}). Halting broadcast.")
            for user_id in all_notified_mechanics:
                if user_id != assignee_id:
                    try:
                        await channel_layer.group_send(
                            f"user_{user_id}", 
                            {'type': 'job_taken_notification', 'job_id': request_id}
                        )
                    except Exception as e:
                        logger.error(f"Failed to send 'job taken' notification for job {request_id} to user {user_id}: {e}", exc_info=True)
            return
        else:
            logger.info(f"Batch timeout for job {request_id}. Notifying mechanics in batch {batch_ids} of expiration.")
            for user_id in batch_ids:
                try:
                    await channel_layer.group_send(
                        f"user_{user_id}", 
                        {'type': 'job_expired_notification', 'job_id': request_id}
                    )
                except Exception as e:
                    logger.error(f"Failed to send 'job expired' notification for job {request_id} to user {user_id}: {e}", exc_info=True)

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


# --- Main Thread Task Function ---

def find_and_notify_mechanics_thread_task(service_request_id):
    """
    This function runs in a separate thread to find and notify mechanics.
    """
    logger.info(f"[Thread Task] Starting for service_request_id: {service_request_id}")
    
    try:
        # === FIX APPLIED HERE ===
        # Proactively fetch the related 'user' object to prevent lazy-loading
        # in the async context later on.
        service_request = ServiceRequest.objects.select_related('user').get(id=service_request_id)
        
        mechanics = list(_get_nearby_mechanics(
            service_request.latitude, 
            service_request.longitude
        ))
        
        if not mechanics:
            logger.warning(f"[Thread Task] No online or verified mechanics found for service request {service_request_id}. The request will expire.")
            ServiceRequest.objects.filter(id=service_request_id, status='PENDING').update(status='EXPIRED')
            return f"No mechanics found for request {service_request_id}."

        mechanic_user_ids = [m.user.id for m in mechanics]
        logger.info(f"[Thread Task] Found {len(mechanic_user_ids)} mechanics for request {service_request_id}: {mechanic_user_ids}")

        # `async_to_sync` correctly handles running async code from a sync thread
        async_to_sync(_broadcast_to_mechanics)(service_request, mechanic_user_ids)
        
        logger.info(f"[Thread Task] Broadcast process completed for service request {service_request_id}.")

    except ServiceRequest.DoesNotExist:
        logger.error(f"[Thread Task] ServiceRequest with ID {service_request_id} not found.")
    except Exception as e:
        logger.critical(f"[Thread Task] An unexpected critical error occurred: {e}", exc_info=True)
    finally:
        logger.info(f"[Thread Task] Task for service_request_id: {service_request_id} finished.")




logger = logging.getLogger(__name__)

# ... (other tasks like find_and_notify_mechanics_thread_task remain the same) ...

def cancel_inactive_jobs_thread_task():
    """
    This function contains the core logic and is designed to run in a separate thread.
    It finds and cancels jobs that have been inactive for too long.
    """
    logger.info("[INACTIVITY_CHECK] Running job inactivity cleanup in a new thread...")
    inactivity_threshold = timezone.now() - timedelta(minutes=15)

    inactive_requests = ServiceRequest.objects.filter(
        status='ACCEPTED',
        updated_at__lt=inactivity_threshold
    ).select_related('user', 'assigned_mechanic__user')

    if not inactive_requests.exists():
        logger.info("[INACTIVITY_CHECK] No inactive jobs found.")
        return

    logger.info(f"[INACTIVITY_CHECK] Found {inactive_requests.count()} inactive jobs to cancel.")

    for request in inactive_requests:
        mechanic_profile = request.assigned_mechanic
        
        # Update the service request status
        request.status = 'CANCELLED'
        request.cancellation_reason = 'Job automatically cancelled due to inactivity from both parties.'
        request.save()

        # Update the mechanic's status
        if mechanic_profile:
            mechanic_profile.status = 'ONLINE'
            mechanic_profile.save()

        # Broadcast the cancellation to both the user and the mechanic
        channel_layer = get_channel_layer()
        message = f"Job {request.id} was automatically cancelled due to inactivity."

        # Notify the user
        async_to_sync(channel_layer.group_send)(
            f"user_{request.user.id}",
            {
                'type': 'job_cancelled_notification',
                'job_id': request.id,
                'message': message
            }
        )

        # Notify the mechanic
        if mechanic_profile and mechanic_profile.user:
            async_to_sync(channel_layer.group_send)(
                f"user_{mechanic_profile.user.id}",
                {
                    'type': 'job_cancelled_notification',
                    'job_id': request.id,
                    'message': message
                }
            )
        logger.info(f"[INACTIVITY_CHECK] Cancelled job {request.id} and notified both parties.")


@shared_task(name="cancel_inactive_jobs")
def cancel_inactive_jobs():
    """
    Celery task that spawns a new thread to handle the cleanup of inactive jobs.
    This is the function that Celery Beat will schedule.
    """
    logger.info("[CELERY_TASK] Spawning a thread for cancel_inactive_jobs_thread_task.")
    thread = threading.Thread(target=cancel_inactive_jobs_thread_task)
    thread.daemon = True
    thread.start()