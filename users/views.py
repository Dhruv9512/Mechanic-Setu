from django.conf import settings
from django.core.cache import cache
from pytz import timezone
from vercel_blob import put
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
from django.template.loader import render_to_string
from io import BytesIO 
from xhtml2pdf import pisa 

# --- IMPORT THE NEW SERIALIZERS ---
from .serializers import (
    UserSerializer, 
    MechanicSerializer, 
    SetUsersDetailsSerializer, 
    SetMechanicDetailViewSerializer
)

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

        cached_otp = cache.get(key)
        if cached_otp != otp:
            return Response({"error": "Invalid key or OTP."}, status=status.HTTP_401_UNAUTHORIZED)

        user = CustomUser.objects.filter(id=user_id).first()
        if not user:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        if not user.is_active:
            user.is_active = True
            user.save(update_fields=['is_active'])

        try:
            access_token, refresh_token = issue_tokens_for_user(user)
        except Exception as e:
            logger.error("Token generation failed for %s: %s", user.email, str(e))
            return Response({"error": "Failed to generate tokens."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Invalidate OTP
        cache.delete(key)

        response_data = {
            "message": "OTP verified successfully."
        }
        response = Response(response_data, status=status.HTTP_200_OK)
        set_auth_cookies(response, access_token, refresh_token)

        try:
            if user.is_mechanic:
                Send_Mechanic_Login_Successful_Email.delay({"email": user.email, "first_name": user.first_name})
            else:
                send_login_success_email.delay({"email": user.email, "first_name": user.first_name})
        except Exception as e:
            logger.warning("Email send failed for %s: %s", user.email, str(e))

        return response


class Login_SignUpView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email")
        is_mechanic = request.data.get("is_mechanic", False)
        if not email:
            return Response({"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)

        CustomUser.objects.filter(email=email, is_active=False).delete()

        try:
            user, created = CustomUser.objects.get_or_create(
                email=email,
                defaults={"is_active": False},
            )
            status_message = "New User" if created else "Existing User"

            otp = generate_otp()
            key = user_key(user=user)
            cache.set(key, otp, timeout=OTP_TTL_SECONDS)

            try:
                if is_mechanic:
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
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except Exception as e:
                logger.warning("Invalid refresh token during logout for user %s: %s", getattr(request.user, "email", "N/A"), str(e))
        
        response = Response({"message": "Logged out successfully."}, status=status.HTTP_200_OK)
        clear_auth_cookies(response)
        try:
            cache.delete(user_key(user=request.user))
        except Exception:
            pass # Fails silently if user key doesn't exist
        return response


class Google_Login_SignupView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        token_str = request.data.get("token")
        if not token_str:
            return Response({"error": "Token not provided"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            idinfo = id_token.verify_oauth2_token(token_str, Request(), GOOGLE_CLIENT_ID)
        except ValueError:
            return Response({"error": "Invalid token"}, status=status.HTTP_400_BAD_REQUEST)
        is_mechanic = request.data.get("is_mechanic", False)
        email = idinfo.get("email")
        if not email:
            return Response({"error": "Invalid token"}, status=status.HTTP_400_BAD_REQUEST)

        CustomUser.objects.filter(email=email, is_active=False).delete()

        user_defaults = {
            "first_name": idinfo.get("given_name", ""),
            "last_name": idinfo.get("family_name", ""),
            "profile_pic": idinfo.get("picture", ""),
            "is_active": True,
        }
        
        try:
            user, created = CustomUser.objects.update_or_create(
                email=email, defaults=user_defaults
            )
            status_message = "New User" if created else "Existing User"
        except Exception as e:
            logger.exception("User fetch/create failed for %s: %s", email, e)
            return Response({"error": "User creation failed."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        try:
            access_token, refresh_token = issue_tokens_for_user(user)
        except Exception as e:
            logger.error("JWT generation failed for %s: %s", email, e)
            return Response({"error": "Failed to generate tokens"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # --- MODIFICATION: Return user data along with the success message ---
        response_data = {
            "message": "Login Successful",
            "status": status_message,
        }
        response = Response(response_data, status=status.HTTP_200_OK)
        set_auth_cookies(response, access_token, refresh_token)

        try:
            if is_mechanic:
                Send_Mechanic_Login_Successful_Email.delay({"email": user.email, "first_name": user.first_name})
            else:
                send_login_success_email.delay({"email": user.email, "first_name": user.first_name})
        except Exception as e:
            logger.warning("Async email enqueue failed for %s: %s", email, e)

        return response

# --- REFACTORED VIEW ---
class SetUsersDetail(APIView):
    authentication_classes = [CookieJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Handles updating user profile details using a serializer.
        This approach replaces manual field checking with robust validation.
        """

        user = request.user
        # `partial=True` allows for updating only a subset of fields.
        serializer = SetUsersDetailsSerializer(user, data=request.data, partial=True)
        
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ResendOtpView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        user_id = request.data.get("id")
        if not user_id:
            return Response({"error": "ID is required"}, status=status.HTTP_400_BAD_REQUEST)

        if key := request.data.get("key"):
            cache.delete(key)
        is_mechanic = request.data.get("is_mechanic", False)
        try:
            user = CustomUser.objects.filter(id=user_id, is_active=False).first()
            if not user:
                return Response({"error": "User not found or is already active."}, status=status.HTTP_404_NOT_FOUND)

            otp = generate_otp()
            new_key = user_key(user=user)
            cache.set(new_key, otp, timeout=OTP_TTL_SECONDS)

            try:
                if is_mechanic:
                    Send_Mechanic_Otp_Verification.delay({"otp": otp, "email": user.email})
                else:
                    Otp_Verification.delay({"otp": otp, "email": user.email})
            except Exception as task_error:
                logger.warning("OTP async task enqueue failed for %s: %s", user.email, task_error)

            return Response({"key": new_key, "id": user.id}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception("Resend OTP failed for id=%s: %s", user_id, e)
            return Response({"error": "Something went wrong."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



# ---------------------------Mechanic Views---------------------------
class SetMechanicDetailView(APIView):
    authentication_classes = [CookieJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Handles creation/update of a mechanic's profile.
        This view now uses two serializers to handle the user part and the mechanic part separately.
        It also uses `update_or_create` for robustly handling both new and existing mechanic profiles.
        """
        user = request.user
        mutable_data = request.data.copy()

        # 1. Handle profile picture upload
        profile_pic = request.FILES.get('profile_pic')
        if profile_pic:
            try:
                path = f"Mechanic_Profile/{profile_pic.name}"
                blob = put(path, profile_pic.read())
                mutable_data['profile_pic'] = blob["url"]
            except Exception as e:
                logger.error(f"File upload failed: {e}")
                return Response({"error": "File upload failed."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        first_name = mutable_data.pop('first_name', None)
        last_name = mutable_data.pop('last_name', None)
        mobile_number = mutable_data.pop('mobile_number', None)
    
        user_serializer = SetUsersDetailsSerializer(user, data={
            "first_name": first_name or user.first_name,
            "last_name": last_name or user.last_name,
            "mobile_number": mobile_number or user.mobile_number,
            "profile_pic": profile_pic or user.profile_pic,
        }, partial=True)
        if not user_serializer.is_valid():
            return Response(user_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        user_serializer.save()

        mechanic_serializer = SetMechanicDetailViewSerializer(data=mutable_data, partial=True)
        if not mechanic_serializer.is_valid():
            return Response(mechanic_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        # 3. Create or update the mechanic profile linked to the user
        mechanic, created = Mechanic.objects.update_or_create(
            user=user,
            defaults=mechanic_serializer.validated_data
        )

         # --- START: PDF GENERATION LOGIC ---
         # --- START: UPDATED PDF GENERATION LOGIC for xhtml2pdf ---
        try:
            # 1. Prepare context (same as before)
            context = {
                'user': user,
                'mechanic': mechanic,
                'timestamp': timezone.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            # 2. Render the HTML template to a string (same as before)
            html_string = render_to_string('mechanic_agreement.html', context)
            
            # 3. Generate PDF in memory
            result = BytesIO() # Create an in-memory binary file
            pdf = pisa.CreatePDF(BytesIO(html_string.encode("UTF-8")), dest=result)

            if not pdf.err:
                # 4. Upload the generated PDF
                pdf_path = f"Mechanic_Agreements/agreement-{user.id}-{mechanic.id}.pdf"
                # Use result.getvalue() to get the byte content of the PDF
                pdf_blob = put(pdf_path, result.getvalue())
                pdf_url = pdf_blob.get("url")

                # 5. Save the PDF URL to the mechanic's profile
                mechanic.agreement_document = pdf_url
                mechanic.save(update_fields=['agreement_document'])
                logger.info(f"Successfully generated agreement for mechanic {mechanic.id} with xhtml2pdf")
            else:
                logger.error(f"xhtml2pdf error for mechanic {mechanic.id}: {pdf.err}")

        except Exception as e:
            logger.error(f"Failed to generate agreement PDF for mechanic {mechanic.id}: {e}")
        # --- END: UPDATED PDF GENERATION LOGIC ---

        status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        message = "Mechanic profile created successfully." if created else "Mechanic profile updated successfully."
    
        return Response({
            "message": message,
        }, status=status_code)