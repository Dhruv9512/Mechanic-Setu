from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/job_notifications/$', consumers.JobNotificationConsumer.as_asgi()),
    re_path(r'ws/job/$', consumers.JobRoomConsumer.as_asgi())
]