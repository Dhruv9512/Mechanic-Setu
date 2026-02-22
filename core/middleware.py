# core/middleware.py

from channels.middleware import BaseMiddleware
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.contrib.auth import get_user_model

User = get_user_model()

@database_sync_to_async
def get_user_from_token(validated_token):
    try:
        # This matches the user_id payload sent from your Node app
        user_id = validated_token.get("user_id") 
        return User.objects.get(id=user_id)
    except User.DoesNotExist:
        return AnonymousUser()

class JWTAuthHeaderMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        # Extract headers from the WebSocket connection
        headers = dict(scope.get('headers', []))
        scope['user'] = AnonymousUser()

        # Check for the Authorization header
        if b'authorization' in headers:
            auth_header = headers[b'authorization'].decode('utf-8')
            
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
                
                try:
                    # UntypedToken automatically uses your settings.py SimpleJWT config
                    # to verify the token using your shared SIGNING_KEY and HS256!
                    validated_token = UntypedToken(token)
                    scope['user'] = await get_user_from_token(validated_token)
                except (InvalidToken, TokenError):
                    pass # Token is invalid, reject user

        return await super().__call__(scope, receive, send)