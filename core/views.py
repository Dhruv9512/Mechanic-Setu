from django.db import models
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.contrib.auth import get_user_model
from users.authentication import CookieJWTAuthentication
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
from django.utils.timezone import now
import logging

logger = logging.getLogger(__name__)



# Token Refresh View
class CookieTokenRefreshView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        raw_refresh = request.COOKIES.get("refresh")
        if not raw_refresh:
            logger.warning("Refresh token missing in cookies")
            return Response({"error": "Refresh token missing"}, status=401)

        try:
            refresh = RefreshToken(raw_refresh)
            
            # Get user from payload
            user_id = refresh.get("user_id")
            User = get_user_model()
            user = User.objects.get(id=user_id)

            logger.info(f"Refreshing tokens for user: {user.username}")

            new_access = str(refresh.access_token)

            # Blacklist old refresh (optional)
            try:
                refresh.blacklist()
                logger.info(f"Blacklisted old refresh token for {user.username}")
            except Exception:
                logger.debug("Token blacklist not configured")

            # Issue new refresh
            new_refresh = RefreshToken.for_user(user)

            response = Response({"message": "Tokens refreshed successfully"}, status=200)
            response.set_cookie("access", new_access, httponly=True, secure=True,
                                samesite="None", max_age=15*60)
            response.set_cookie("refresh", str(new_refresh), httponly=True, secure=True,
                                samesite="None", max_age=7*24*60*60)

            return response

        except Exception as e:
            logger.error(f"Refresh token error: {e}", exc_info=True)
            return Response({"error": "Invalid or expired refresh token"}, status=401)


# User Info View
class MeApiView(APIView):
    """
    Returns authenticated user's info.
    Requires a valid access token in HttpOnly cookie.
    """
    authentication_classes = [CookieJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        logger.info(f"User data requested: {user.username}")
        return Response({
            "username": user.username,
        }, status=status.HTTP_200_OK)


class ExpiredCleanupView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    def get(self, request):

        try:
            from django.core.cache import cache
            cache.clear_expired()
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        try:
             # ---------- 1. Cleanup expired outstanding tokens ----------
            expired_tokens = OutstandingToken.objects.filter(expires_at__lt=now())
            count_outstanding = expired_tokens.count()
            expired_tokens.delete()

            # ---------- 2. Cleanup expired blacklisted tokens ----------
            expired_blacklisted = BlacklistedToken.objects.filter(token__expires_at__lt=now())
            count_blacklisted = expired_blacklisted.count()
            expired_blacklisted.delete()
            return Response(
                {"detail": f"Deleted {count_outstanding} expired outstanding tokens and {count_blacklisted} expired blacklisted tokens and expired cache."},
                status=200
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

      