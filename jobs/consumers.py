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

    # --- Connection Management ---

    async def connect(self):
        """
        This method is called when a client (a user's browser or app)
        tries to establish a WebSocket connection.
        """
        # 1. Authenticate the user from the token in the URL.
        #    The frontend will send its JWT token in the WebSocket URL's query string.
        #    Example URL: ws://.../?token=...
        query_string = self.scope.get("query_string", b"").decode()
        query_params = parse_qs(query_string)
        token_key = query_params.get("token", [None])[0]

        self.user = await self.get_user_from_token(token_key)
        if not self.user:
            # If the token is invalid, the connection is rejected.
            await self.close()
            return

        self.user_id = self.user.id
        # 2. Define a unique "room" or "group" name for this user. This acts
        #    as their private channel for receiving direct notifications.
        self.room_group_name = f'user_{self.user_id}'
        
        # 3. Add this user's connection to their private group.
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        # 4. Accept the connection.
        await self.accept()
        print(f"Accepted connection for user {self.user_id}")
        

    async def disconnect(self, close_code):
        """
        Called automatically when the connection is closed.
        """
        # Clean up by removing the user from their group.
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        print(f"Disconnected user {self.user_id}")

    @database_sync_to_async
    def get_user_from_token(self, token_key):
        """
        Validates the JWT and retrieves the user from the database.
        The decorator `@database_sync_to_async` is crucial because database
        operations are synchronous, but this consumer is asynchronous. This
        decorator runs the database query safely in a separate thread.
        """
        if not token_key:
            return None
        try:
            validated_token = AccessToken(token_key)
            user_id = validated_token["user_id"]
            return CustomUser.objects.only('id', 'email').get(id=user_id)
        except Exception as e:
            logger.error(f"[TOKEN ERROR] Invalid token: {e}", exc_info=True)
            return None
            
    # --- Incoming Message Router ---

    async def receive(self, text_data):
        """
        Called whenever a message is received from a client. It routes the
        message to the correct handler based on its 'type'.
        """
        data = json.loads(text_data)
        message_type = data.get('type')

        if message_type == 'accept_job':
            # This logic is now handled by the `AcceptServiceRequestView` for better
            # reliability, but the consumer could also handle it like this.
            await self.handle_job_acceptance(
                data.get('service_request_id'), 
                data.get('mechanic_user_id')
            )
        
        elif message_type == 'location_update':
            # This is for the mechanic to update their general location while idle.
            latitude = data.get('latitude')
            longitude = data.get('longitude')
            if latitude and longitude:
                await self.update_mechanic_location(self.user_id, latitude, longitude)

    # --- Handlers for Server-Side Actions ---

    async def new_job_notification(self, event):
        """
        This method is triggered by the backend (e.g., from `CreateServiceRequestView`).
        It sends the 'new_job' message to this specific client's WebSocket.
        """
        await self.send(text_data=json.dumps({
            'type': 'new_job',
            'service_request': event['service_request']
        }))

    async def mechanic_accepted(self, event):
        """
        This method is triggered by the backend to inform this client (the user)
        that their request has been successfully accepted by a mechanic.
        """
        await self.send(text_data=json.dumps({
            'type': 'mechanic_accepted',
            'mechanic_details': event['mechanic_details']
        }))

    # --- Asynchronous Database Operations ---

    @sync_to_async
    def assign_mechanic_to_request(self, service_request_id, mechanic_user_id):
        """
        Assigns a mechanic to a request in the database.
        The `@sync_to_async` decorator allows this database code to be called from
        an async method like `handle_job_acceptance`.
        """
        try:
            # Note: This check isn't atomic. It's safer to use a view with
            # `select_for_update` to prevent two mechanics from accepting the same job.
            service_request = ServiceRequest.objects.get(id=service_request_id, mechanic__isnull=True)
            mechanic = Mechanic.objects.get(user_id=mechanic_user_id)
            service_request.mechanic = mechanic
            service_request.save()
            return service_request, service_request.requested_by
        except (ServiceRequest.DoesNotExist, Mechanic.DoesNotExist):
            return None, None

    @sync_to_async
    def update_mechanic_location(self, user_id, latitude, longitude):
        """
        Updates a mechanic's general location in the database while they are online
        and waiting for jobs.
        """
        try:
            Mechanic.objects.filter(user_id=user_id).update(
                current_latitude=latitude,
                current_longitude=longitude
            )
        except Exception as e:
            print(f"Error updating location for user {user_id}: {e}")