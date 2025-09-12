from django.contrib.auth.backends import ModelBackend
from .models import CustomUser


class EmailBackend(ModelBackend):
    """
    Authenticate using email only (no password required).
    Used for OTP-based authentication.
    """
    def authenticate(self, request, email=None, password=None, **kwargs):
        if email is None:
            return None
        try:
            return CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            return None
