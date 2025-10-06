from django.urls import path
from .views import CookieTokenRefreshView, MeApiView ,ExpiredCleanupView, GetWsTokenView

urlpatterns = [
    path("token/refresh/", CookieTokenRefreshView.as_view(), name="token_refresh"),
    path("me/", MeApiView.as_view(), name="me"),
    path('expiry-cleanup/', ExpiredCleanupView.as_view(), name='cache_cleanup'),
    path("ws-token/", GetWsTokenView.as_view(), name="ws_token"),
]
