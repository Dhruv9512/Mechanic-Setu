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


import logging
logger = logging.getLogger(__name__)

# Otp Verification View
class OtpVerificationView(APIView):
    permission_classes = [AllowAny]  

    def post(self, request):
        try:
            email = request.data.get('email')
            otp = request.data.get('otp')

            if not email or not otp:
                return Response({"error": "Email and OTP are required."}, status=status.HTTP_400_BAD_REQUEST)

            cache_key = f"otp_{email}"
            cached_otp = cache.get(cache_key)
            if cached_otp is None or cached_otp != otp:
                return Response({"error": "Invalid email or OTP."}, status=status.HTTP_401_UNAUTHORIZED)

            user = CustomUser.objects.filter(email=email).first()
            if user is None:
                return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

            user.is_active = True
            user.save()

            refresh = RefreshToken.for_user(user)
            access_token = refresh.access_token

            response = Response({
                "message": "OTP verified successfully."
            }, status=status.HTTP_200_OK)

            response.set_cookie(
                key="access",
                value=str(access_token),
                httponly=True,
                secure=True,
                samesite="None",
                max_age=30*60
            )
            response.set_cookie(
                key="refresh",
                value=str(refresh),
                httponly=True,
                secure=True,
                samesite="None",
                max_age=7*24*60*60
            )

            # Send Login Successful Email asynchronously
            try:
                user_data = {
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                }
                send_login_success_email.delay(user_data)
            except Exception as e:
                logger.warning(f"Email send failed for {user.email}: {str(e)}")

            return response

        except Exception as e:
            logger.exception(f"OTP verification failed for email: {request.data.get('email')}, Error: {str(e)}")
            return Response({"error": "Something went wrong. Try again later."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Manual Login View
class Login_SignUpView(APIView):
    permission_classes = [AllowAny] 

    def post(self, request):
        try:
            email = request.data.get('email')
            if not email:
                return Response({"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)

            user = authenticate(request, email=email)

            if user is None:
                user = CustomUser.objects.create_user(email=email)
                user.is_active = False
                user.save()
                status_message = "New User"
            else:
                if not user.is_active:
                    return Response({"error": "You are not verified yet."}, status=status.HTTP_403_FORBIDDEN)
                status_message = "Existing User"

            cache_key = f"otp_{email}"
            otp = generate_otp()
            cache.set(cache_key, otp, timeout=300)

            user_data = {"otp": otp, "email": email, "status": status_message}
            try:
                Otp_Verification.apply_async(args=[user_data])
            except Exception as e:
                logger.warning(f"OTP email sending failed: {str(e)}")

            return Response({"Email": email, "Status": status_message}, status=status.HTTP_200_OK)

        except Exception as e:
            logger.exception(f"Login/Signup failed for email: {request.data.get('email')}, Error: {str(e)}")
            return Response({"error": "Something went wrong. Try again later."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
        try:
            token = request.data.get('token')
            if not token:
                return Response({'error': 'Token not provided'}, status=status.HTTP_400_BAD_REQUEST)

            try:
                idinfo = id_token.verify_oauth2_token(
                    token,
                    Request(),
                    os.environ.get('GOOGLE_CLIENT_ID')
                )
            except ValueError:
                return Response({"error": "Invalid token"}, status=status.HTTP_400_BAD_REQUEST)

            email = idinfo.get('email')
            first_name = idinfo.get('given_name')
            last_name = idinfo.get('family_name')
            profile_pic = idinfo.get('picture')

            if not email:
                return Response({"error": "Invalid token"}, status=status.HTTP_400_BAD_REQUEST)

            if email in ["forlaptop2626@gmail.com", "mitsuhamitsuha123@gmail.com"]:
                return Response({"error": "User not eligible"}, status=status.HTTP_403_FORBIDDEN)

            user = CustomUser.objects.filter(email=email).first()

            if not user:
                user = CustomUser.objects.create(
                    email=email,
                    username=email.split("@")[0],
                    first_name=first_name or "",
                    last_name=last_name or "",
                    profile_pic=profile_pic or "",
                    is_active=True
                )
                status_message = "New User"
            else:
                if not user.is_active:
                    return Response({"error": "You are not verified yet."}, status=status.HTTP_403_FORBIDDEN)

                updated = False
                if user.first_name != first_name:
                    user.first_name = first_name or ""
                    updated = True
                if user.last_name != last_name:
                    user.last_name = last_name or ""
                    updated = True
                if user.profile_pic != profile_pic:
                    user.profile_pic = profile_pic or ""
                    updated = True
                if updated:
                    try:
                        user.save()
                    except Exception as e:
                        logger.warning(f"Failed to update user data for {user.email}: {str(e)}")

                status_message = "Existing User"

            try:
                refresh = RefreshToken.for_user(user)
                access_token = refresh.access_token
            except Exception as e:
                logger.error(f"JWT token generation failed for {user.email}: {str(e)}")
                return Response({"error": "Failed to generate tokens."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            response = Response({
                "message": "Login Successful",
                "status": status_message,
            }, status=status.HTTP_200_OK)

            response.set_cookie(
                key="access",
                value=str(access_token),
                httponly=True,
                secure=True,
                samesite="None",
                max_age=30 * 60
            )
            response.set_cookie(
                key="refresh",
                value=str(refresh),
                httponly=True,
                secure=True,
                samesite="None",
                max_age=7 * 24 * 60 * 60
            )

            try:
                user_data = {
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                }
                send_login_success_email.delay(user_data)
            except Exception as e:
                logger.warning(f"Email send failed for {user.email}: {str(e)}")

            return response

        except Exception as e:
            logger.exception(f"Google login failed: {str(e)}")
            return Response({"error": "Something went wrong. Try again later."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
