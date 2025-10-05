from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed
import random
from hashlib import md5
import logging

logger = logging.getLogger(__name__)

ACCESS_COOKIE = "access"


class CookieJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        raw_token = request.COOKIES.get(ACCESS_COOKIE)
        if raw_token is None:
            return None

        try:
            validated_token = self.get_validated_token(raw_token)
        except Exception as e:
            raise AuthenticationFailed("Token Validation Error: " + str(e))

        try:
            user = self.get_user(validated_token)
        except Exception as e:
            raise AuthenticationFailed("User Retrieval Error: " + str(e))

        return (user, validated_token)


def generate_otp():
    """
    Generate a random 6-digit OTP as a string.
    """
    return f"{random.randint(100000, 999999)}"

