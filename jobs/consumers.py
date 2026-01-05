import json
from urllib.parse import parse_qs
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from users.models import Mechanic, CustomUser
from rest_framework_simplejwt.tokens import AccessToken
from channels.db import database_sync_to_async
from .models import ServiceRequest
import logging

# Set up a specific logger for this module
logger = logging.getLogger(__name__)


class JobNotificationConsumer(AsyncWebsocketConsumer):
    """
    Handles WebSocket connections for users and mechanics, facilitating real-time
    job notifications, job acceptances, and location tracking.
    """

    # --- Connection Management ---
    
    async def connect(self):
        """
        Handles an incoming WebSocket connection.
        """
        logger.info("[WS-CONNECT] Attempting to connect...")
        
        query_string = self.scope.get("query_string", b"").decode()
        query_params = parse_qs(query_string)
        token_key = query_params.get("token", [None])[0]

        if not token_key:
            logger.warning("[WS-CONNECT] Connection rejected: No token provided.")
            await self.close()
            return

        self.user = await self.get_user_from_token(token_key)
        if not self.user:
            logger.warning("[WS-CONNECT] Connection rejected: Invalid token.")
            await self.close()
            return

        self.user_id = self.user.id
        self.personal_room_name = f'user_{self.user_id}'
        self.job_room_name = None # To store the job-specific room name
        
        await self.channel_layer.group_add(
            self.personal_room_name,
            self.channel_name
        )

        await self.accept()
        logger.info(f"[WS-CONNECT] Accepted connection for user {self.user_id} and added to group '{self.personal_room_name}'.")
        

    async def disconnect(self, close_code):
        """
        Handles a WebSocket disconnection.
        """
        # Discard from personal group
        if hasattr(self, 'personal_room_name'):
            await self.channel_layer.group_discard(
                self.personal_room_name,
                self.channel_name
            )
        
        # Discard from job-specific group if connected
        if hasattr(self, 'job_room_name') and self.job_room_name:
            await self.channel_layer.group_discard(
                self.job_room_name,
                self.channel_name
            )

        logger.info(f"[WS-DISCONNECT] Disconnected user {getattr(self, 'user_id', 'N/A')}. Code: {close_code}")


    @database_sync_to_async
    def get_user_from_token(self, token_key):
        """
        Validates the JWT and retrieves the user from the database.
        """
        logger.debug(f"Attempting to validate token...")
        try:
            validated_token = AccessToken(token_key)
            user_id = validated_token["user_id"]
            user = CustomUser.objects.only('id', 'email').get(id=user_id)
            logger.debug(f"Token validation successful for user_id: {user.id}")
            return user
        except Exception as e:
            logger.error(f"[TOKEN ERROR] Invalid token provided. Error: {e}", exc_info=False)
            return None
            
    # --- Incoming Message Router ---

    async def receive(self, text_data):
        """
        Called whenever a message is received from a client.
        """
        logger.info(f"[WS-RECEIVE] Received raw message from user {self.user_id}: {text_data}")
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            logger.info(f"[WS-RECEIVE] Parsed message type: '{message_type}'")

            # --- ROUTER LOGIC UPDATED ---
            if message_type == 'location_update':
                await self.handle_location_update(data)

            # --- ADD THIS CONDITION ---
            elif message_type == 'user_heartbeat':
                await self.handle_user_heartbeat(data)
            
            else:
                logger.warning(f"[WS-RECEIVE] Unknown message type '{message_type}' from user {self.user_id}.")

        except json.JSONDecodeError:
            logger.error(f"[WS-RECEIVE] Failed to parse JSON from message: {text_data}")
        except Exception as e:
            logger.error(f"[WS-RECEIVE] Error processing received message: {e}", exc_info=True)

    # --- Handlers for Server-Side Group Events ---
    async def no_mechanic_found(self, event):
        """
        Receives the 'no_mechanic_found' event from the backend task
        and forwards it to the connected client (frontend).
        
        The 'event' dictionary contains the data sent from the backend:
        {
            'type': 'no_mechanic_found',
            'message': 'We are sorry, but we could not find...',
            'job_id': '...'
        }
        """
        print(f"Received 'no_mechanic_found' for user {self.user.id}, job {event.get('job_id')}")
        
        # Send the message payload directly to the WebSocket client (frontend).
        await self.send(text_data=json.dumps({
            'type': 'no_mechanic_found', 
            'message': event['message'],
            'job_id': event['job_id']
        }))

    async def new_job(self, event):
        """
        Handles the 'new_job' event from the channel layer.
        """
        logger.info(f"[HANDLER] 'new_job' handler triggered for user {self.user_id}.")
        job_details = event.get('service_request')
        if not job_details:
            logger.warning(f"[HANDLER] 'new_job' event was missing 'service_request' data.")
            return

        payload = {
            'type': 'new_job',
            'service_request': job_details
        }
        
        await self.send(text_data=json.dumps(payload))


    async def job_expired_notification(self, event):
        """
        Handles the 'job_expired_notification' event from the channel layer.
        Informs the mechanic that a job they were notified about has timed out.
        """
        job_id = event.get('job_id')
        logger.info(f"[HANDLER] 'job_expired_notification' triggered for user {self.user_id} regarding job {job_id}.")
        
        await self.send(text_data=json.dumps({
            'type': 'job_expired', # The type your frontend will look for
            'job_id': job_id,
            'message': f"The job request {job_id} has expired."
        }))

    # --- ADDED THIS NEW HANDLER ---
    async def job_taken_notification(self, event):
        """
        Handles the 'job_taken_notification' event. This tells other mechanics
        that a job they were offered has been accepted by someone else.
        """
        job_id = event.get('job_id')
        logger.info(f"[HANDLER] 'job_taken_notification' triggered for user {self.user_id} regarding job {job_id}.")
        
        await self.send(text_data=json.dumps({
            'type': 'job_taken',  # The type your frontend will look for
            'job_id': job_id,
            'message': f"The job request {job_id} has been taken by another mechanic."
        }))


    async def mechanic_accepted(self, event):
        """
        Informs the user that their request has been accepted and provides the job_id.
        """
        logger.info(f"[HANDLER] 'mechanic_accepted' handler triggered for user {self.user_id}.")
        await self.send(text_data=json.dumps({
            'type': 'mechanic_accepted',
            'mechanic_details': event.get('mechanic_details'),
            'job_id': event.get('job_id')
        }))

    async def mechanic_location(self, event):
        """
        Receives a location from the group and sends it to the client (the user).
        """
        await self.send(text_data=json.dumps({
            'type': 'mechanic_location_update',
            'latitude': event.get('latitude'),
            'longitude': event.get('longitude'),
            'mechanic_id': event.get('mechanic_id'),
        }))

    async def job_cancelled_notification(self, event):
        """
        Handles the 'job_cancelled_notification' event.
        Informs the user/mechanic that a job has been cancelled.
        """
        job_id = event.get('job_id')
        message = event.get('message')
        logger.info(f"[HANDLER] 'job_cancelled_notification' triggered for user {self.user_id} regarding job {job_id}.")

        await self.send(text_data=json.dumps({
            'type': 'job_cancelled', # The type frontend will look for
            'job_id': job_id,
            'message': message
        }))

    async def mechanic_arrived_notification(self, event):
        """
        Handles the 'mechanic_arrived_notification' event.
        Informs the user that the mechanic has arrived.
        """
        job_id = event.get('job_id')
        price = event.get('price')
        message = event.get('message')
        logger.info(f"[HANDLER] 'mechanic_arrived_notification' triggered for user {self.user_id} regarding job {job_id}.")

        await self.send(text_data=json.dumps({
            'type': 'mechanic_arrived', 
            'job_id': job_id,
            'price': price,
            'message': message
        }))

    async def job_completed_notification(self, event):
        """
        Handles the 'job_completed_notification' event.
        Informs the user that their job has been completed.
        """
        job_id = event.get('job_id')
        message = event.get('message')
        logger.info(f"[HANDLER] 'job_completed_notification' triggered for user {self.user_id} regarding job {job_id}.")

        await self.send(text_data=json.dumps({
            'type': 'job_completed', # The type frontend will look for
            'job_id': job_id,
            'message': message
        }))


    async def handle_location_update(self, data):
        """
        Handles location updates. Always updates the DB.
        Only sends to the customer if the mechanic is 'working' AND a job_id is provided.
        """
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        job_id = data.get('job_id') # Will be None if not sent by client
        
        logger.info(f"Location update from Machanic {self.user_id}: lat={latitude}, lon={longitude}, job_id={job_id}")
        # This check handles the case where job_id is missing.
        if not all([latitude, longitude]):
            logger.warning(f"Incomplete location data from user {self.user_id}.")
            return

        # 1. Always update the mechanic's location in the database.
        await self.update_mechanic_location(self.user_id, latitude, longitude)
        
        logger.debug(f"Mechanic {self.user_id} location updated in DB: lat={latitude}, lon={longitude}.")
        # 2. Only proceed to send a notification if there is a job_id.
        if not job_id:
            logger.info(f"Mechanic {self.user_id} has no active job. DB location updated.")
            return # Exit early

        # 3. Check the mechanic's status.
        mechanic_is_working = await self.is_mechanic_working(self.user_id)

        logger.info(f"Mechanic {self.user_id} is {'working' if mechanic_is_working else 'not working'}.")
        # 4. If they are working, send the notification.
        if mechanic_is_working:

            customer_id = await self.get_customer_id_for_job(job_id, self.user)
            await self.update_service_request_timestamp(job_id)
            if customer_id:
                target_room = f'user_{customer_id}'
                logger.info(f"Sending mechanic location update to customer {customer_id} for job {job_id}.")
                # This line will NOT cause an error if the customer is offline.
                await self.channel_layer.group_send(
                    target_room,
                    {
                        'type': 'mechanic_location',
                        'latitude': latitude,
                        'longitude': longitude,
                        'mechanic_id': self.user_id,
                        'job_id': job_id
                    }
                )
    async def handle_user_heartbeat(self, data):
        """
        Handles heartbeat messages from the user to keep a job active.
        """
        job_id = data.get('job_id')
        if job_id:
            await self.update_service_request_timestamp(job_id)
       
    # --- Asynchronous Database Operations ---
    @database_sync_to_async
    def get_customer_id_for_job(self, job_id, mechanic_user):
        """
        Securely retrieves the customer's user ID for a given job.
        """
        try:
            job = ServiceRequest.objects.select_related('user', 'mechanic__user').get(
                id=job_id, 
                mechanic__user=mechanic_user
            )
            return job.user.id
        except ServiceRequest.DoesNotExist:
            return None
        

    @database_sync_to_async
    def is_mechanic_working(self, user_id):
        """
        Checks the database to see if the mechanic is marked as 'working'.
        Returns True if the mechanic exists and is working, otherwise False.
        """
        try:
            mechanic = Mechanic.objects.get(user_id=user_id)
            if mechanic.status==mechanic.StatusChoices.WORKING:
                return True
            else:
                return False
        except Mechanic.DoesNotExist:
            return False
    
    @database_sync_to_async
    def update_service_request_timestamp(self, job_id):
        """
        Updates the 'updated_at' field for a given service request.
        """
        try:
            service_request = ServiceRequest.objects.get(id=job_id)
            service_request.save() # This will automatically update the updated_at field
            logger.info(f"Updated timestamp for service request {job_id}")
        except ServiceRequest.DoesNotExist:
            logger.warning(f"Could not update timestamp for non-existent service request {job_id}")


    @sync_to_async
    def update_mechanic_location(self, user_id, latitude, longitude):
        """
        Updates a mechanic's current location in the database.
        Using .get() and .save() to ensure signals are triggered.
        """
        try:
            mechanic = Mechanic.objects.get(user_id=user_id)
            mechanic.current_latitude = latitude
            mechanic.current_longitude = longitude
            mechanic.save(update_fields=['current_latitude', 'current_longitude'])
            
            logger.info(f"Updated location for user {user_id} to ({latitude}, {longitude})")

        except Mechanic.DoesNotExist:
            logger.warning(f"Attempted to update location for non-existent mechanic user {user_id}")
        except Exception as e:
            logger.error(f"Error updating location for user {user_id}: {e}", exc_info=True)


