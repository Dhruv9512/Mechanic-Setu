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

# --- Reusable Database Helper Functions (Moved to top-level for clarity) ---

@database_sync_to_async
def get_request_status_and_assignee(pk):
    """Checks the DB for the current status and assignee of a ServiceRequest."""
    try:
        req = ServiceRequest.objects.select_related('assigned_mechanic__user').get(pk=pk)
        assignee = req.assigned_mechanic.user.id if req.assigned_mechanic else None
        logger.debug(f"Checked status for job {pk}: Status is {req.status}, Assignee is {assignee}")
        return req.status, assignee
    except ServiceRequest.DoesNotExist:
        return None, None
    except Exception as e:
        logger.error(f"DB error checking status for job {pk}: {e}", exc_info=True)
        return None, None

@database_sync_to_async
def expire_request_if_pending(pk):
    """Atomically updates a PENDING request to EXPIRED."""
    try:
        updated_count = ServiceRequest.objects.filter(pk=pk, status='PENDING').update(status='EXPIRED')
        return updated_count > 0
    except Exception as e:
        logger.error(f"DB error expiring request {pk}: {e}", exc_info=True)
        return False

# --- Original Helper Functions (Unchanged) ---

def _get_nearby_mechanics(latitude, longitude, radius=15):
    # This function remains the same as in your original code.
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
    # This function remains the same.
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
    # This function remains the same.
    try:
        service_request = ServiceRequest.objects.get(id=request_id)
        serializer = JobDetailsForMechanicSerializer(service_request)
        return serializer.data
    except ServiceRequest.DoesNotExist:
        return None

# --- Refactored Broadcasting Logic ---

async def _execute_one_broadcast_pass(service_request, mechanic_user_ids, job_details):
    """
    Executes a single pass of broadcasting to all mechanics in batches.
    Returns True if the job is accepted during this pass, False otherwise.
    """
    channel_layer = get_channel_layer()
    batch_size = 5
    timeout = 30  # 30 seconds
    request_id = str(service_request.id)
    all_notified_mechanics_in_pass = []

    for i in range(0, len(mechanic_user_ids), batch_size):
        batch_ids = mechanic_user_ids[i:i + batch_size]
        all_notified_mechanics_in_pass.extend(batch_ids)

        logger.info(f"Broadcasting job {request_id} to batch {i//batch_size + 1}: {batch_ids}")
        for user_id in batch_ids:
            try:
                await channel_layer.group_send(f"user_{user_id}", {'type': 'new_job', 'service_request': job_details})
            except Exception as e:
                logger.error(f"Failed to send job notification for job {request_id} to user {user_id}: {e}", exc_info=True)

        logger.info(f"Waiting for {timeout} seconds for responses for job {request_id}...")
        await asyncio.sleep(timeout)

        current_status, assignee_id = await get_request_status_and_assignee(request_id)

        if current_status == 'ACCEPTED':
            logger.info(f"Job {request_id} was accepted by mechanic (user_id: {assignee_id}). Halting broadcast.")
            # Notify all mechanics who have seen the job so far that it's taken.
            for user_id in all_notified_mechanics_in_pass:
                if user_id != assignee_id:
                    try:
                        await channel_layer.group_send(
                            f"user_{user_id}",
                            {'type': 'job_taken_notification', 'job_id': request_id}
                        )
                    except Exception as e:
                        logger.error(f"Failed to send 'job taken' notification for job {request_id} to user {user_id}: {e}", exc_info=True)
            return True # Signal that the job was accepted.

        else: # Timeout for this batch, no one accepted yet.
            logger.info(f"Batch timeout for job {request_id}. Notifying mechanics in batch {batch_ids} of expiration.")
            for user_id in batch_ids:
                try:
                    await channel_layer.group_send(
                        f"user_{user_id}",
                        {'type': 'job_expired_notification', 'job_id': request_id}
                    )
                except Exception as e:
                    logger.error(f"Failed to send 'job expired' notification for job {request_id} to user {user_id}: {e}", exc_info=True)

    # If the entire loop completes, no mechanic accepted in this pass.
    logger.info(f"Broadcast pass for job {request_id} completed. No mechanic accepted.")
    return False

async def _manage_broadcast_attempts(service_request, mechanic_user_ids):
    """
    Manages the overall broadcasting process, including retries.
    Notifies the customer if no mechanic is found after all attempts.
    """
    max_attempts = 2
    request_id = str(service_request.id)
    job_details = await get_serialized_job_details(request_id)
    
    if not job_details:
        logger.error(f"Could not serialize job details for {request_id}. Aborting broadcast.")
        return

    for attempt in range(1, max_attempts + 1):
        logger.info(f"Starting broadcast attempt {attempt}/{max_attempts} for job {request_id}.")
        
        job_was_accepted = await _execute_one_broadcast_pass(service_request, mechanic_user_ids, job_details)

        if job_was_accepted:
            logger.info(f"Job {request_id} successfully assigned. Ending process.")
            return # Exit successfully

    # If the loop finishes without the job being accepted
    logger.warning(f"All {max_attempts} broadcast attempts for job {request_id} failed. No mechanic accepted.")
    
    # 1. Mark the service request as EXPIRED in the database.
    was_expired = await expire_request_if_pending(request_id)
    if was_expired:
        logger.info(f"Job {request_id} has been marked as EXPIRED.")
    else:
        logger.warning(f"Attempted to expire job {request_id}, but it was not in PENDING state or was not found.")

    # 2. Notify the original user (customer) that no one could be found.
    try:
        channel_layer = get_channel_layer()
        customer_user_id = service_request.user.id
        await channel_layer.group_send(
            f"user_{customer_user_id}",
            {
                'type': 'no_mechanic_found',
                'message': 'We are sorry, but we could not find an available mechanic for your request at this time.',
                'job_id': request_id
            }
        )
        logger.info(f"Sent 'no_mechanic_found' notification to customer user_{customer_user_id} for job {request_id}.")
    except Exception as e:
        logger.error(f"Failed to send 'no_mechanic_found' notification for job {request_id} to user {customer_user_id}: {e}", exc_info=True)


# --- Main Thread Task Function (Updated to call the new manager) ---

def find_and_notify_mechanics_thread_task(service_request_id):
    """
    This function runs in a separate thread to find and notify mechanics.
    """
    logger.info(f"[Thread Task] Starting for service_request_id: {service_request_id}")
    
    try:
        # Proactively fetch the related 'user' object to prevent lazy-loading issues.
        service_request = ServiceRequest.objects.select_related('user').get(id=service_request_id)
        
        mechanics = list(_get_nearby_mechanics(
            service_request.latitude,
            service_request.longitude
        ))
        
        if not mechanics:
            logger.warning(f"[Thread Task] No online or verified mechanics found for service request {service_request_id}.")
            # If no mechanics are found at all, expire immediately and notify the user.
            ServiceRequest.objects.filter(id=service_request_id, status='PENDING').update(status='EXPIRED')
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"user_{service_request.user.id}",
                {
                    'type': 'no_mechanic_found',
                    'message': 'We are sorry, but there are no mechanics available in your area right now.',
                    'job_id': str(service_request_id)
                }
            )
            return

        mechanic_user_ids = [m.user_id for m in mechanics]
        logger.info(f"[Thread Task] Found {len(mechanic_user_ids)} mechanics for request {service_request_id}: {mechanic_user_ids}")

        # `async_to_sync` correctly runs our new async manager from this sync thread.
        async_to_sync(_manage_broadcast_attempts)(service_request, mechanic_user_ids)
        
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