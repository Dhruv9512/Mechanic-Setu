from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.contrib.auth import authenticate
from django.core.cache import cache  
from .authentication import generate_otp,user_key,CookieJWTAuthentication
from .tasks import Otp_Verification
from django.contrib.auth.models import User
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
        if cached_otp is None:
            return Response({"error": "Invalid email or OTP."}, status=status.HTTP_401_UNAUTHORIZED)

        if not cached_otp == otp:
            return Response({"error": "Invalid email or OTP."}, status=status.HTTP_401_UNAUTHORIZED)

        # OTP is valid, activate the user
        user = User.objects.filter(email=email).first()
        if user is None:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)
    
        # ✅ JWT Token generation
        refresh = RefreshToken.for_user(user)
        access_token = refresh.access_token
        # ✅ Return fast response
        response =Response({
            "message": "Login successful!",
            "satus": "true",
        }, status=status.HTTP_200_OK)

        response.set_cookie(
            key="access",
            value=str(access_token),
            httponly=True,
            secure=True,
            samesite="None",
            max_age=15*60  # 15 minutes
        )
        response.set_cookie(
            key="refresh",
            value=str(refresh),
            httponly=True,
            secure=True,
            samesite="None",
            max_age=7*24*60*60  # 7 days
        )

        return Response({"message": "OTP verified successfully."}, status=status.HTTP_200_OK)


# Manual Login View
class LoginView(APIView):
    permission_classes = [AllowAny] 
    def post(self, request):
        
        # Get email
        email = request.data.get('email')

        # Here, you would typically authenticate the user
        user=authenticate(request, email=email)
        if user is None:
            return Response({"error": "Invalid email"}, status=status.HTTP_401_UNAUTHORIZED)
        
        if not user.is_active:
            return Response({"error": "You are not verified yet. Please check your email or try later."}, status=status.HTTP_403_FORBIDDEN)

        cache_key = f"otp_{email}"
        otp=generate_otp()
        cache.set(cache_key, otp, timeout=300)

        user_data = {}
        try:
            
            user_data["otp"] = otp
            user_data["email"] = email
            Otp_Verification.apply_async(args=[user_data])
        except Exception as e:
                logger.warning(f"Email sending failed during registration: {str(e)}")
        return Response({"Email":email}, status=status.HTTP_200_OK)


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
