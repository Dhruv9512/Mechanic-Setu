from django.utils.timezone import now
from django.contrib.auth import get_user_model
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken

from core.authentication import CookieJWTAuthentication
from django.conf import settings
from django.core.management import call_command
from django.db import connections, transaction
import logging

logger = logging.getLogger(__name__)

# -------------------------
# Constants / helpers
# -------------------------

ACCESS_COOKIE = "access"
REFRESH_COOKIE = "refresh"
ACCESS_MAX_AGE = 30 * 60            # 30 minutes (kept as provided)
REFRESH_MAX_AGE = 7 * 24 * 60 * 60  # 7 days

COOKIE_OPTS = {
    "httponly": True,
    "secure": True,
    "samesite": "None",
}

HTTP_200 = status.HTTP_200_OK
HTTP_401 = status.HTTP_401_UNAUTHORIZED
HTTP_500 = status.HTTP_500_INTERNAL_SERVER_ERROR


def set_auth_cookies(response: Response, access_value: str, refresh_value: str):
    response.set_cookie(ACCESS_COOKIE, access_value, max_age=ACCESS_MAX_AGE, **COOKIE_OPTS)
    response.set_cookie(REFRESH_COOKIE, refresh_value, max_age=REFRESH_MAX_AGE, **COOKIE_OPTS)


def clear_auth_cookies(response: Response):
    response.delete_cookie(ACCESS_COOKIE)
    response.delete_cookie(REFRESH_COOKIE)


def issue_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return str(refresh.access_token), str(refresh)


# -------------------------
# Views
# -------------------------

class CookieTokenRefreshView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        raw_refresh = request.COOKIES.get(REFRESH_COOKIE)
        if not raw_refresh:
            logger.warning("Refresh token missing in cookies")
            return Response({"error": "Refresh token missing"}, status=HTTP_401)

        try:
            refresh = RefreshToken(raw_refresh)
        except Exception as e:
            logger.error("Refresh token parse error: %s", e, exc_info=True)
            return Response({"error": "Invalid or expired refresh token"}, status=HTTP_401)

        # Extract user; errors handled explicitly
        try:
            user_id = refresh.get("user_id")
            User = get_user_model()
            user = User.objects.get(id=user_id)
        except Exception as e:
            logger.error("Failed to load user from refresh token: %s", e, exc_info=True)
            return Response({"error": "Invalid or expired refresh token"}, status=HTTP_401)

        logger.info("Refreshing tokens for user: %s", getattr(user, "username", user_id))

        # Use access from current refresh (keeps logic intact)
        new_access = str(refresh.access_token)

        # Optional blacklist of the used refresh (kept as-is)
        try:
            refresh.blacklist()
            logger.info("Blacklisted old refresh token for %s", getattr(user, "username", user_id))
        except Exception:
            logger.debug("Token blacklist not configured or already blacklisted")

        # Issue a new refresh for rotation
        try:
            new_refresh = RefreshToken.for_user(user)
        except Exception as e:
            logger.error("Failed to issue new refresh token: %s", e, exc_info=True)
            return Response({"error": "Invalid or expired refresh token"}, status=HTTP_401)

        response = Response({"message": "Tokens refreshed successfully"}, status=HTTP_200)
        set_auth_cookies(response, new_access, str(new_refresh))
        return response


class MeApiView(APIView):
    """
    Returns authenticated user's info.
    Requires a valid access token in HttpOnly cookie.
    """
    authentication_classes = [CookieJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        logger.info("User data requested: %s", getattr(user, "username", None))
        return Response({"username": user.id}, status=HTTP_200)


class ExpiredCleanupView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):

        details = {}

        # Purge only expired cache rows for DatabaseCache
        try:
            conf = settings.CACHES.get("default", {})
            if conf.get("BACKEND") == "django.core.cache.backends.db.DatabaseCache":
                table = conf["LOCATION"]
                with connections["default"].cursor() as cursor, transaction.atomic():
                    cursor.execute(f"DELETE FROM {table} WHERE expires < %s", [now()])
                    details["cache_deleted"] = cursor.rowcount
            else:
                details["cache_status"] = "Non-DB cache; backend TTL handles expiry"
        except Exception as e:
            logger.error("Cache purge failed: %s", e, exc_info=True)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Flush expired SimpleJWT tokens
        try:
            call_command("flushexpiredtokens")
            details["jwt_status"] = "flushexpiredtokens executed"
        except Exception as e:
            logger.error("flushexpiredtokens failed: %s", e, exc_info=True)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"detail": details}, status=status.HTTP_200_OK)
