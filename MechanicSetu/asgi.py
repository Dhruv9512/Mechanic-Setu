import os
import django
from django.core.asgi import get_asgi_application

# 1. Set the environment variable first
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MechanicSetu.settings')

# 2. Call django.setup() BEFORE importing anything else related to Django
django.setup()

# 3. NOW it is safe to import Channels, routing, and your middleware
from channels.routing import ProtocolTypeRouter, URLRouter
import jobs.routing
from core.middleware import JWTAuthHeaderMiddleware

# 4. Define your application
application = ProtocolTypeRouter({
    "http": get_asgi_application(), 
    "websocket": JWTAuthHeaderMiddleware(
        URLRouter(
            jobs.routing.websocket_urlpatterns
        )
    ),
})