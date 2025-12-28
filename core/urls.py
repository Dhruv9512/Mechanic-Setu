from django.urls import path,include
from .views import CookieTokenRefreshView, MeApiView ,ExpiredCleanupView, GetWsTokenView,MapAdViewSet
from rest_framework.routers import DefaultRouter
router = DefaultRouter()
router.register(r'map-ads', MapAdViewSet, basename='map-ad')

urlpatterns = [
    path("token/refresh/", CookieTokenRefreshView.as_view(), name="token_refresh"),
    path("me/", MeApiView.as_view(), name="me"),
    path('expiry-cleanup/', ExpiredCleanupView.as_view(), name='cache_cleanup'),
    path("ws-token/", GetWsTokenView.as_view(), name="ws_token"),
    path("", include(router.urls))
]
