import json
from urllib.parse import parse_qs
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from users.models import Mechanic, CustomUser
from rest_framework_simplejwt.tokens import AccessToken
from channels.db import database_sync_to_async
from .models import ServiceRequest
import logging
logger = logging.getLogger(__name__)


class JobNotificationConsumer(AsyncWebsocketConsumer):
    """
    Handles WebSocket connections for users and mechanics, facilitating real-time
    job notifications, job acceptances, and location tracking.
    """
    async def connect(self):
        # Extract user_id from the URL
        query_string = self.scope.get("query_string", b"").decode()
        query_params = parse_qs(query_string)
        token_key = query_params.get("token", [None])[0]

        self.user = await self.get_user_from_token(token_key)
        if not self.user:
            await self.close()
            return
        self.user_id = self.user.id
        self.room_group_name = f'Mechanic_{self.user_id}'
        # Add the user's channel to a group specific to their user_id
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        # Accept the WebSocket connection
        await self.accept()
        print(f"Accepted connection for user {self.user_id}")

    async def disconnect(self, close_code):
        # Remove the user's channel from their group upon disconnection
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        print(f"Disconnected user {self.user_id}")

    @database_sync_to_async
    def get_user_from_token(self, token_key):
        if not token_key:
            return None
        try:
            validated_token = AccessToken(token_key)
            user_id = validated_token["user_id"]
            return CustomUser.objects.only('id', 'username').get(id=user_id)
        except Exception as e:
            logger.error(f"[TOKEN ERROR] Invalid token: {e}", exc_info=True)
            return None
        
    async def receive(self, text_data):
        """
        Receives messages from the client WebSocket and routes them based on 'type'.
        """
        data = json.loads(text_data)
        message_type = data.get('type')

        # Route message to the appropriate handler
        if message_type == 'accept_job':
            service_request_id = data.get('service_request_id')
            mechanic_user_id = data.get('mechanic_user_id')
            await self.handle_job_acceptance(service_request_id, mechanic_user_id)
        
        elif message_type == 'location_update':
            latitude = data.get('latitude')
            longitude = data.get('longitude')
            if latitude and longitude:
                await self.update_mechanic_location(self.user_id, latitude, longitude)

    # --- Message Handlers ---

    async def handle_job_acceptance(self, service_request_id, mechanic_user_id):
        """
        Handles the logic when a mechanic accepts a job.
        """
        service_request, user_to_notify = await self.assign_mechanic_to_request(service_request_id, mechanic_user_id)

        if service_request and user_to_notify:
            # Notify the original user that a mechanic has accepted the job
            await self.channel_layer.group_send(
                f'user_{user_to_notify.id}',
                {
                    'type': 'mechanic.accepted', 
                    'mechanic_details': {
                        'name': service_request.mechanic.user.name,
                        'mobile_number': service_request.mechanic.user.mobile_number,
                        'shop_name': service_request.mechanic.shop_name,
                    }
                }
            )

    # --- Group Message Senders (called by server-side logic) ---

    async def new_job_notification(self, event):
        """
        Sends a new job notification to the connected mechanic.
        """
        await self.send(text_data=json.dumps({
            'type': 'new_job',
            'service_request': event['service_request']
        }))

    async def mechanic_accepted(self, event):
        """
        Informs the user that a mechanic has accepted their request.
        """
        await self.send(text_data=json.dumps({
            'type': 'mechanic_accepted',
            'mechanic_details': event['mechanic_details']
        }))

    # --- Asynchronous Database Operations ---

    @sync_to_async
    def assign_mechanic_to_request(self, service_request_id, mechanic_user_id):
        """
        Assigns a mechanic to a service request in the database.
        This runs in a separate thread to avoid blocking the event loop.
        """
        try:
            service_request = ServiceRequest.objects.get(id=service_request_id, mechanic__isnull=True)
            mechanic = Mechanic.objects.get(user_id=mechanic_user_id)

            # Assign the mechanic
            service_request.mechanic = mechanic
            service_request.save()

            return service_request, service_request.requested_by
        except (ServiceRequest.DoesNotExist, Mechanic.DoesNotExist):
            # Handles cases where the job was already taken or IDs are invalid
            return None, None

    @sync_to_async
    def update_mechanic_location(self, user_id, latitude, longitude):
        """
        Updates the mechanic's location in the database.
        This runs in a separate thread to avoid blocking the event loop.
        """
        try:
            rows_updated = Mechanic.objects.filter(user_id=user_id).update(
                shop_latitude=latitude,
                shop_longitude=longitude
            )
            if rows_updated > 0:
                print(f"Updated location for user {user_id} to {latitude}, {longitude}")
        except Exception as e:
            print(f"Error updating location for user {user_id}: {e}")