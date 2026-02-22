# In MechanicSetu/asgi.py

import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from core.middleware import JWTAuthHeaderMiddleware
import django

# Set the settings module environment variable
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MechanicSetu.settings')


django.setup()

# Import your routing module AFTER Django is initialized
import jobs.routing

application = ProtocolTypeRouter({
    "http": get_asgi_application(),  # Use the initialized app for HTTP
    "websocket": JWTAuthHeaderMiddleware(
        URLRouter(
            jobs.routing.websocket_urlpatterns
        )
    ),
})