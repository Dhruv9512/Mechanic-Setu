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
        self.room_group_name = f'user_{self.user_id}'
        
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()
        logger.info(f"[WS-CONNECT] Accepted connection for user {self.user_id} and added to group '{self.room_group_name}'.")
        

    async def disconnect(self, close_code):
        """
        Handles a WebSocket disconnection.
        """
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            logger.info(f"[WS-DISCONNECT] Disconnected user {getattr(self, 'user_id', 'N/A')}. Removed from group '{self.room_group_name}'. Code: {close_code}")
        else:
            logger.info(f"[WS-DISCONNECT] A user disconnected without being added to a group. Code: {close_code}")

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

            if message_type == 'accept_job':
                await self.handle_job_acceptance(
                    data.get('service_request_id'), 
                    data.get('mechanic_user_id')
                )
            
            elif message_type == 'location_update':
                latitude = data.get('latitude')
                longitude = data.get('longitude')
                if latitude and longitude:
                    await self.update_mechanic_location(self.user_id, latitude, longitude)
            else:
                logger.warning(f"[WS-RECEIVE] Unknown message type '{message_type}' from user {self.user_id}.")
        except json.JSONDecodeError:
            logger.error(f"[WS-RECEIVE] Failed to parse JSON from message: {text_data}")
        except Exception as e:
            logger.error(f"[WS-RECEIVE] Error processing received message: {e}", exc_info=True)


    # --- Handlers for Server-Side Events (from Celery) ---

    async def new_job_notification(self, event):
        """
        Handles the 'new_job_notification' event from the channel layer (Celery).
        """
        logger.info(f"[HANDLER] 'new_job_notification' handler triggered for user {self.user_id}.")
        job_details = event.get('job')
        if not job_details:
            logger.warning(f"[HANDLER] 'new_job_notification' event for user {self.user_id} was missing 'job' data.")
            return

        payload = {
            'type': 'new_job',
            'service_request': job_details
        }
        
        logger.info(f"[HANDLER] Sending 'new_job' payload to user {self.user_id} for job {job_details.get('id')}.")
        await self.send(text_data=json.dumps(payload))

    async def mechanic_accepted(self, event):
        """
        Informs the user that their request has been accepted.
        """
        logger.info(f"[HANDLER] 'mechanic_accepted' handler triggered for user {self.user_id}.")
        await self.send(text_data=json.dumps({
            'type': 'mechanic_accepted',
            'mechanic_details': event.get('mechanic_details')
        }))

    # --- Asynchronous Database Operations ---

    @sync_to_async
    def assign_mechanic_to_request(self, service_request_id, mechanic_user_id):
        """
        Assigns a mechanic to a request in the database.
        """
        try:
            service_request = ServiceRequest.objects.get(id=service_request_id, assigned_mechanic__isnull=True)
            mechanic = Mechanic.objects.get(user_id=mechanic_user_id)
            service_request.assigned_mechanic = mechanic
            service_request.status = 'ACCEPTED'
            service_request.save()
            logger.info(f"Successfully assigned mechanic {mechanic.user.id} to service request {service_request.id}")
            return service_request, service_request.user
        except (ServiceRequest.DoesNotExist, Mechanic.DoesNotExist) as e:
            logger.warning(f"Could not assign mechanic to request. Job may have already been taken. Error: {e}")
            return None, None
        except Exception as e:
            logger.error(f"Error in assign_mechanic_to_request: {e}", exc_info=True)
            return None, None


    @sync_to_async
    def update_mechanic_location(self, user_id, latitude, longitude):
        """
        Updates a mechanic's general location in the database.
        """
        try:
            rows_updated = Mechanic.objects.filter(user_id=user_id).update(
                current_latitude=latitude,
                current_longitude=longitude
            )
            if rows_updated > 0:
                logger.info(f"Updated location for user {user_id} to ({latitude}, {longitude})")
            else:
                logger.warning(f"Attempted to update location for non-existent mechanic user {user_id}")
        except Exception as e:
            logger.error(f"Error updating location for user {user_id}: {e}", exc_info=True)