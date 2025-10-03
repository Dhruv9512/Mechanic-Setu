from django.conf import settings
from django.contrib.auth import authenticate
from django.core.cache import cache
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from rest_framework_simplejwt.tokens import RefreshToken

from google.oauth2 import id_token
from google.auth.transport.requests import Request

from .authentication import generate_otp, user_key, CookieJWTAuthentication
from .tasks import Otp_Verification, send_login_success_email,Send_Mechanic_Login_Successful_Email,Send_Mechanic_Otp_Verification
from .models import CustomUser, Mechanic

import logging
import os

from .serializers import MechanicSerializer, UserSerializer

logger = logging.getLogger(__name__)

# -------------------------
# Constants / helpers
# -------------------------

ACCESS_COOKIE = "access"
REFRESH_COOKIE = "refresh"
ACCESS_MAX_AGE = 30 * 60                 # 30 minutes
REFRESH_MAX_AGE = 7 * 24 * 60 * 60       # 7 days
OTP_TTL_SECONDS = 140

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")


def jwt_cookie_opts():
    # SameSite=None requires Secure for modern browsers; use HTTPS in prod
    # Keep consistent with frontend withCredentials and CORS allow-credentials
    # to ensure cookies are accepted by browsers.
    # Refs: SameSite=None + Secure requirements
    return {
        "httponly": True,
        "secure": True,
        "samesite": "None",
    }


def set_auth_cookies(response: Response, access_token: str, refresh_token: str):
    opts = jwt_cookie_opts()
    response.set_cookie(ACCESS_COOKIE, access_token, max_age=ACCESS_MAX_AGE, **opts)
    response.set_cookie(REFRESH_COOKIE, refresh_token, max_age=REFRESH_MAX_AGE, **opts)


def clear_auth_cookies(response: Response):
    response.delete_cookie(ACCESS_COOKIE)
    response.delete_cookie(REFRESH_COOKIE)


def issue_tokens_for_user(user: CustomUser):
    refresh = RefreshToken.for_user(user)
    return str(refresh.access_token), str(refresh)


# -------------------------
# Views
# -------------------------

class OtpVerificationView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        key = request.data.get("key")
        otp = request.data.get("otp")
        user_id = request.data.get("id")

        if not key or not otp:
            return Response({"error": "Key and OTP are required."}, status=status.HTTP_400_BAD_REQUEST)

        # Validate OTP (string compare)
        cache_key = key
        cached_otp = cache.get(cache_key)
        if cached_otp != otp:
            return Response({"error": "Invalid key or OTP."}, status=status.HTTP_401_UNAUTHORIZED)

        # Validate user
        user = CustomUser.objects.filter(id=user_id).only("id", "is_active", "email", "first_name", "last_name").first()
        if not user:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        # Activate if needed
        if not user.is_active:
            CustomUser.objects.filter(pk=user.id, is_active=False).update(is_active=True)
            user.is_active = True

        # Generate tokens
        try:
            access_token, refresh_token = issue_tokens_for_user(user)
        except Exception as e:
            logger.error("Token generation failed for %s: %s", user.email, str(e))
            return Response({"error": "Failed to generate tokens."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Build response + set cookies
        response = Response({"message": "OTP verified successfully."}, status=status.HTTP_200_OK)
        set_auth_cookies(response, access_token, refresh_token)

        # Invalidate OTP
        cache.delete(cache_key)

        # Async email - best effort
        try:
            if user.is_mechanic:
                Send_Mechanic_Login_Successful_Email.delay({
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                })
            else:
                send_login_success_email.delay({
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                })
        except Exception as e:
            logger.warning("Email send failed for %s: %s", user.email, str(e))

        return response


class Login_SignUpView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email")
        if not email:
            return Response({"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Delete non-active stale accounts for same email
        CustomUser.objects.filter(email=email, is_active=False).delete()

        try:
            # get_or_create single round-trip
            user, created = CustomUser.objects.get_or_create(
                email=email,
                defaults={"is_active": False},
            )
            status_message = "New User" if created else "Existing User"

            # Generate & cache OTP
            otp = generate_otp()
            key = user_key(user=user)
            cache.set(key, otp, timeout=OTP_TTL_SECONDS)

            # Fire async task (non-blocking)
            try:
                if user.is_mechanic:
                    Send_Mechanic_Otp_Verification.delay({"otp": otp, "email": user.email})
                else:
                    Otp_Verification.delay({"otp": otp, "email": user.email})
            except Exception as task_error:
                logger.warning("OTP async task enqueue failed for %s: %s", email, task_error)

            return Response({"key": key, "id": user.id, "status": status_message}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception("Login/Signup failed for email=%s: %s", email, e)
            return Response({"error": "Something went wrong. Try again later."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class LogoutView(APIView):
    authentication_classes = [CookieJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.COOKIES.get(REFRESH_COOKIE)
        if not refresh_token:
            return Response({"error": "Refresh token missing"}, status=status.HTTP_401_UNAUTHORIZED)

        # Blacklist refresh token if enabled
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception as e:
            logger.warning("Invalid refresh token during logout for user %s: %s", getattr(request.user, "email", None), str(e))
            return Response({"error": "Invalid refresh token"}, status=status.HTTP_400_BAD_REQUEST)

        # Clear cookies + cache key
        try:
            response = Response({"message": "Logged out successfully."}, status=status.HTTP_200_OK)
            clear_auth_cookies(response)
            # Clear any OTP cache for this user key (best effort)
            try:
                cache.delete(user_key(user=request.user))
            except Exception:
                pass
            return response
        except Exception as e:
            logger.exception("Error deleting cookies during logout for user %s: %s", getattr(request.user, "email", None), str(e))
            return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class Google_Login_SignupView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        token_str = request.data.get("token")
        if not token_str:
            return Response({"error": "Token not provided"}, status=status.HTTP_400_BAD_REQUEST)

        # Verify Google token (per docs)
        try:
            idinfo = id_token.verify_oauth2_token(token_str, Request(), GOOGLE_CLIENT_ID)
        except ValueError:
            return Response({"error": "Invalid token"}, status=status.HTTP_400_BAD_REQUEST)

        email = idinfo.get("email")
        if not email:
            return Response({"error": "Invalid token"}, status=status.HTTP_400_BAD_REQUEST)

        # Delete non-active duplicates on same email
        CustomUser.objects.filter(email=email, is_active=False).delete()

        first_name = idinfo.get("given_name", "") or ""
        last_name = idinfo.get("family_name", "") or ""
        profile_pic = idinfo.get("picture", "") or ""

        try:
            user, created = CustomUser.objects.get_or_create(
                email=email,
                defaults={
                    "first_name": first_name,
                    "last_name": last_name,
                    "profile_pic": profile_pic,
                    "is_active": True,
                },
            )
            status_message = "New User" if created else "Existing User"

            # Apply differential updates
            updates = {}
            if user.first_name != first_name:
                updates["first_name"] = first_name
            if user.last_name != last_name:
                updates["last_name"] = last_name
            if user.profile_pic != profile_pic:
                updates["profile_pic"] = profile_pic

            if updates:
                CustomUser.objects.filter(pk=user.pk).update(**updates)
        except Exception as e:
            logger.exception("User fetch/create failed for %s: %s", email, e)
            return Response({"error": "User creation failed."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Generate tokens
        try:
            access_token, refresh_token = issue_tokens_for_user(user)
        except Exception as e:
            logger.error("JWT generation failed for %s: %s", email, e)
            return Response({"error": "Failed to generate tokens"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Response with cookies
        response = Response({"message": "Login Successful", "status": status_message}, status=status.HTTP_200_OK)
        set_auth_cookies(response, access_token, refresh_token)

        # Fire async email task (best effort)
        try:
            if user.is_mechanic:
                Send_Mechanic_Login_Successful_Email.delay({
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                })
            else:
                send_login_success_email.delay({
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                })
        except Exception as e:
            logger.warning("Async email enqueue failed for %s: %s", email, e)

        return response


class SetUsersDetail(APIView):
    authentication_classes = [CookieJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            user = request.user

            # Extract fields
            first_name = request.data.get("first_name")
            last_name = request.data.get("last_name")
            mobile_number = request.data.get("mobile_number")
            profile_pic = request.data.get("profile_pic")

            # Update conditionally to avoid unnecessary writes
            changed = False
            if first_name and user.first_name != first_name:
                user.first_name = first_name
                changed = True
            if last_name and user.last_name != last_name:
                user.last_name = last_name
                changed = True
            if mobile_number and user.mobile_number != mobile_number:
                user.mobile_number = mobile_number
                changed = True
            if profile_pic and user.profile_pic != profile_pic:
                user.profile_pic = profile_pic
                changed = True

            if changed:
                user.save(update_fields=["first_name", "last_name", "mobile_number", "profile_pic"])

            return Response({"message": "User details updated successfully"}, status=status.HTTP_200_OK)

        except Exception as e:
            logger.exception("User update failed: %s", e)
            return Response({"error": "User update failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ResendOtpView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        user_id = request.data.get("id")
        if not user_id:
            return Response({"error": "ID is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Delete prior OTP if provided key present
        key = request.data.get("key")
        if key:
            cache.delete(key)

        try:
            user = CustomUser.objects.filter(id=user_id).only("id", "email", "is_active").first()
            if not user:
                return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)
            if user.is_active:
                return Response({"error": "User is already active."}, status=status.HTTP_400_BAD_REQUEST)

            # Generate & cache OTP
            otp = generate_otp()
            new_key = user_key(user=user)
            cache.set(new_key, otp, timeout=OTP_TTL_SECONDS)

            # Fire async task
            try:
                if user.is_mechanic:
                    Send_Mechanic_Otp_Verification.delay({"otp": otp, "email": user.email})
                else:
                    Otp_Verification.delay({"otp": otp, "email": user.email})
            except Exception as task_error:
                logger.warning("OTP async task enqueue failed for %s: %s", user.email, task_error)

            return Response({"key": new_key, "id": user.id}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception("Resend OTP failed for id=%s: %s", user_id, e)
            return Response({"error": "Something went wrong. Try again later."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




# ---------------------------Mechanic Views---------------------------
# ---------------------------Mechanic Views---------------------------
class SetMechanicDetailView(APIView):
    authentication_classes = [CookieJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        first_name = request.data.get("first_name")
        last_name = request.data.get("last_name")
        mobile_number = request.data.get("mobile_number")
        profile_pic = request.FILES.get("profile_pic")
        shop_name = request.data.get("shop_name")
        shop_address = request.data.get("shop_address")
        shop_latitude = request.data.get("shop_latitude")
        shop_longitude = request.data.get("shop_longitude")

        CustomUser.objects.filter(pk=user.pk).update(first_name=first_name,
            last_name=last_name,
            mobile_number=mobile_number,
            profile_pic=profile_pic,
        )
    
        mechanic_serializer = MechanicSerializer(data={
                "shop_name": shop_name,
                "shop_address": shop_address,
                "shop_latitude": shop_latitude,
                "shop_longitude": shop_longitude
            })
        mechanic, created = Mechanic.objects.get_or_create(user=user, defaults=mechanic_serializer.validated_data)
        if created:
            return Response({"message": "Mechanic profile created successfully"}, status=status.HTTP_201_CREATED)
       
