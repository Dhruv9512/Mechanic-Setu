from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed
import random
from hashlib import md5
import logging
logger = logging.getLogger(__name__)


# Custom JWT Authentication to read token from cookies
class CookieJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        # Look for token in cookies instead of headers
        raw_token = request.COOKIES.get('access')
        if raw_token is None:
            return None
        try:
            validated_token = self.get_validated_token(raw_token)
        except Exception as e:
            raise AuthenticationFailed(f'Token Validation Error: ' + str(e))

        try:
            user = self.get_user(validated_token)
            return user, validated_token
        except Exception as e:
            raise AuthenticationFailed(f'User Retrieval Error: ' + str(e))
        


# OTP Generation function
def generate_otp():
    """Generate a random 6-digit OTP."""
    otp = str(random.randint(100000, 999999))
    return otp





# Cache key functions
def user_cache_key(request, key_prefix, cache_key):
    user_id = request.user.pk if request.user.is_authenticated else "anon"
    key = f"user_cache:{user_id}"
    return md5(key.encode("utf-8")).hexdigest()
# Cache key functions
def user_key(user):
    key = f"user_cache:{user.pk}"
    return md5(key.encode("utf-8")).hexdigest()

