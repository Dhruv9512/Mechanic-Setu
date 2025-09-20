from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.contrib.auth import authenticate
from django.core.cache import cache  
from .authentication import generate_otp,user_key,CookieJWTAuthentication
from .tasks import Otp_Verification,send_login_success_email
from .models import CustomUser
from google.oauth2 import id_token  
import os
from google.auth.transport.requests import Request
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.permissions import IsAuthenticated
from .authentication import CookieJWTAuthentication, user_key


import logging
logger = logging.getLogger(__name__)

# Otp Verification View
class OtpVerificationView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        key = request.data.get('key')
        otp = request.data.get('otp')
        id = request.data.get('id')
        if not key or not otp:
            return Response(
                {"error": "Key and OTP are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Validate OTP
            cache_key = key
            cached_otp = cache.get(cache_key)

            if cached_otp != otp:
                return Response(
                    {"error": "Invalid key or OTP."},
                    status=status.HTTP_401_UNAUTHORIZED
                )

            # Validate user
            user = CustomUser.objects.filter(id=id).first()
            if not user:
                return Response(
                    {"error": "User not found."},
                    status=status.HTTP_404_NOT_FOUND
                )

            # Activate user if needed
            if not user.is_active:
                user.is_active = True
                user.save(update_fields=["is_active"])

            # Generate JWT tokens
            try:
                refresh = RefreshToken.for_user(user)
                access_token = refresh.access_token
            except Exception as e:
                logger.error(f"Token generation failed for {user.email}: {str(e)}")
                return Response(
                    {"error": "Failed to generate tokens."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            # Build response
            response = Response(
                {"message": "OTP verified successfully."},
                status=status.HTTP_200_OK
            )

            cookie_settings = {
                "httponly": True,
                "secure": True,
                "samesite": "None",
            }

            response.set_cookie(
                key="access",
                value=str(access_token),
                max_age=30 * 60,
                **cookie_settings
            )
            response.set_cookie(
                key="refresh",
                value=str(refresh),
                max_age=7 * 24 * 60 * 60,
                **cookie_settings
            )

            # Async email sending
            try:
                send_login_success_email.delay({
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                })
            except Exception as e:
                logger.warning(f"Email send failed for {user.email}: {str(e)}")

            return response

        except Exception as e:
            logger.exception(
                f"OTP verification failed , Error: {str(e)}"
            )
            return Response(
                {"error": "Something went wrong. Try again later."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# Manual Login View
class Login_SignUpView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response(
                {"error": "Email is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # ✅ Use get_or_create (1 DB call instead of 2)
            user, created = CustomUser.objects.get_or_create(
                email=email,
                defaults={"is_active": False},
            )
            status_message = "New User" if created else "Existing User"

            # ✅ Generate & cache OTP
            otp = generate_otp()
            key = user_key(user=user)
            cache.set(key, otp, timeout=140)

            # ✅ Fire async task (non-blocking)
            try:
                Otp_Verification.delay({"otp": otp, "email": email})
            except Exception as task_error:
                logger.warning(f"OTP async task enqueue failed for {email}: {task_error}")

            return Response(
                {"key": key, "id": user.id, "status": status_message},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            logger.exception(f"Login/Signup failed for email={email}: {e}")
            return Response(
                {"error": "Something went wrong. Try again later."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

# Logout View
class LogoutView(APIView):
    authentication_classes = [CookieJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.COOKIES.get('refresh')
            if not refresh_token:
                return Response({"error": "Refresh token missing"}, status=status.HTTP_401_UNAUTHORIZED)

            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except Exception as e:
                logger.warning(f"Invalid refresh token during logout for user {request.user.email}: {str(e)}")
                return Response({"error": "Invalid refresh token"}, status=status.HTTP_400_BAD_REQUEST)

            try:
                response = Response({"message": "Logged out successfully."}, status=status.HTTP_200_OK)
                response.delete_cookie('access')
                response.delete_cookie('refresh')
                cache.delete(user_key(user=request.user))
                return response
            except Exception as e:
                logger.exception(f"Error deleting cookies during logout for user {request.user.email}: {str(e)}")
                return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except Exception as e:
            logger.exception(f"Logout failed for user {request.user.email}: {str(e)}")
            return Response({"error": "Something went wrong. Try again later."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class Google_Login_SignupView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        token = request.data.get("token")
        if not token:
            return Response({"error": "Token not provided"}, status=status.HTTP_400_BAD_REQUEST)

        # ✅ Verify Google token
        try:
            idinfo = id_token.verify_oauth2_token(
                token,
                Request(),
                os.environ.get("GOOGLE_CLIENT_ID")
            )
        except ValueError:
            return Response({"error": "Invalid token"}, status=status.HTTP_400_BAD_REQUEST)

        email = idinfo.get("email")
        if not email:
            return Response({"error": "Invalid token"}, status=status.HTTP_400_BAD_REQUEST)

        # ✅ Blocklist certain users
        if email in {"forlaptop2626@gmail.com", "mitsuhamitsuha123@gmail.com"}:
            return Response({"error": "User not eligible"}, status=status.HTTP_403_FORBIDDEN)

        first_name = idinfo.get("given_name", "")
        last_name = idinfo.get("family_name", "")
        profile_pic = idinfo.get("picture", "")

        try:
            # ✅ One query: get_or_create
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

            # ✅ Update fields if changed (bulk)
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
            logger.exception(f"User fetch/create failed for {email}: {e}")
            return Response({"error": "User creation failed."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # ✅ Generate tokens
        try:
            refresh = RefreshToken.for_user(user)
            access_token = refresh.access_token
        except Exception as e:
            logger.error(f"JWT generation failed for {email}: {e}")
            return Response({"error": "Failed to generate tokens"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # ✅ Prepare response with cookies
        response = Response(
            {"message": "Login Successful", "status": status_message},
            status=status.HTTP_200_OK,
        )

        cookie_settings = {
            "httponly": True,
            "secure": True,
            "samesite": "None",
        }

        response.set_cookie("access", str(access_token), max_age=30 * 60, **cookie_settings)
        response.set_cookie("refresh", str(refresh), max_age=7 * 24 * 60 * 60, **cookie_settings)

        # ✅ Fire async email task (don’t block request)
        try:
            send_login_success_email.delay({
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
            })
        except Exception as e:
            logger.warning(f"Async email enqueue failed for {email}: {e}")

        return response
    

# Set the user other details

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

            # Update fields if provided
            if first_name:
                user.first_name = first_name
            if last_name:
                user.last_name = last_name
            if mobile_number:
                user.mobile_number = mobile_number
            if profile_pic:
                user.profile_pic = profile_pic

            user.save()

            return Response(
                {"message": "User details updated successfully"},
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.exception(f"User update failed: {e}")
            return Response(
                {"error": "User update failed"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )