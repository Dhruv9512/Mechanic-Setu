from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.contrib.auth import authenticate
from django.core.cache import cache  
from .authentication import generate_otp,user_key,CookieJWTAuthentication
from .tasks import Otp_Verification
from .models import CustomUser
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.permissions import IsAuthenticated

import logging
logger = logging.getLogger(__name__)

# Otp Verification View
class OtpVerificationView(APIView):
    permission_classes = [AllowAny]  

    def post(self, request):
        email = request.data.get('email')
        otp = request.data.get('otp')

        if not email or not otp:
            return Response({"error": "Email and OTP are required."}, status=status.HTTP_400_BAD_REQUEST)

        cache_key = f"otp_{email}"
        cached_otp = cache.get(cache_key)
        if cached_otp is None or cached_otp != otp:
            return Response({"error": "Invalid email or OTP."}, status=status.HTTP_401_UNAUTHORIZED)

        from .models import CustomUser
        user = CustomUser.objects.filter(email=email).first()
        if user is None:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        
        user.is_active = True
        user.save()

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        access_token = refresh.access_token

        # ✅ Return response with cookies
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
        return response


# Manual Login View
class Login_SignUpView(APIView):
    permission_classes = [AllowAny] 

    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Authenticate user using custom backend
        from django.contrib.auth import authenticate
        user = authenticate(request, email=email)

        if user is None:
            # Create a new user
            from .models import CustomUser
            user = CustomUser.objects.create_user(email=email)
            user.is_active = False
            user.save()
            status_message = "New User"
        else:
            if not user.is_active:
                return Response({"error": "You are not verified yet."}, status=status.HTTP_403_FORBIDDEN)
            status_message = "Existing User"

        # Generate OTP and cache it
        cache_key = f"otp_{email}"
        otp = generate_otp()
        cache.set(cache_key, otp, timeout=300)

        # Send OTP asynchronously
        user_data = {"otp": otp, "email": email, "status": status_message}
        try:
            Otp_Verification.apply_async(args=[user_data])
        except Exception as e:
            logger.warning(f"Email sending failed: {str(e)}")

        return Response({"Email": email, "Status": status_message}, status=status.HTTP_200_OK)


# Logout View
class LogoutView(APIView):

    authentication_classes = [CookieJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):

        refresh_token = request.COOKIES.get('refresh')
        if not refresh_token:
            return Response({"error": "Refresh token missing"}, status=status.HTTP_401_UNAUTHORIZED)

        # Blacklist the refresh token
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception as e:
            logger.warning(f"Invalid refresh token during logout: {str(e)}")
            return Response({"error": "Invalid refresh token"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            response = Response({"message": "Logged out successfully."}, status=status.HTTP_200_OK)
            response.delete_cookie('access')
            response.delete_cookie('refresh')
            cache.delete(user_key(user=request.user))
            return response
        except Exception as e:
            logger.exception("Error during logout.")
            return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
