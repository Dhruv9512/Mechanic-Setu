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
            if message_type == 'join_job_room':
                await self.join_job_room(data)
            
            elif message_type == 'location_update':
                await self.handle_location_update(data)

            # (You can add more handlers here like 'send_chat_message', etc.)
            
            else:
                logger.warning(f"[WS-RECEIVE] Unknown message type '{message_type}' from user {self.user_id}.")

        except json.JSONDecodeError:
            logger.error(f"[WS-RECEIVE] Failed to parse JSON from message: {text_data}")
        except Exception as e:
            logger.error(f"[WS-RECEIVE] Error processing received message: {e}", exc_info=True)


    # --- Handlers for Client-Side Events ---

    async def join_job_room(self, event):
        """
        Adds the user/mechanic to a private room for a specific job.
        """
        job_id = event.get('job_id')
        if job_id:
            self.job_room_name = f"job_{job_id}"
            await self.channel_layer.group_add(
                self.job_room_name,
                self.channel_name
            )
            logger.info(f"User {self.user_id} joined room '{self.job_room_name}'")
            # Optional: Send a confirmation back to the client
            await self.send(text_data=json.dumps({
                'type': 'room_joined_confirmation',
                'job_id': job_id,
                'message': f"Successfully joined room for job {job_id}."
            }))

    async def handle_location_update(self, data):
        """
        Handles a mechanic's location update and broadcasts it to the job room.
        """
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        job_id = data.get('job_id') # Client MUST now send the job_id

        if latitude and longitude and job_id:
            # Update location in DB (good practice)
            await self.update_mechanic_location(self.user_id, latitude, longitude)
            
            # Broadcast the location to the private job room
            job_room = f"job_{job_id}"
            await self.channel_layer.group_send(
                job_room,
                {
                    'type': 'mechanic_location', # New handler type for the group
                    'latitude': latitude,
                    'longitude': longitude,
                    'mechanic_id': self.user_id,
                }
            )

    # --- Handlers for Server-Side Group Events ---

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

    async def mechanic_accepted(self, event):
        """
        Informs the user that their request has been accepted and provides the job_id.
        """
        logger.info(f"[HANDLER] 'mechanic_accepted' handler triggered for user {self.user_id}.")
        await self.send(text_data=json.dumps({
            'type': 'mechanic_accepted',
            'mechanic_details': event.get('mechanic_details'),
            'job_id': event.get('job_id') # Pass the job_id to the client
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


    # --- Asynchronous Database Operations ---

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