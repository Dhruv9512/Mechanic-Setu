from MechanicSetu.settings import EMAIL_HOST_USER
from celery import shared_task
from django.template.loader import render_to_string
from django.core.mail import send_mail
import logging

logger = logging.getLogger(__name__)

DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

def _send_templated_email(*, subject: str, to_email: str, html_template: str, context: dict, plain_fallback: str):
    html_message = render_to_string(html_template, context or {})
    plain_message = plain_fallback
    send_mail(
        subject=subject,
        message=plain_message,
        from_email=DEFAULT_FROM_EMAIL,
        recipient_list=[to_email],
        html_message=html_message,
        fail_silently=False,
    )

@shared_task
def Otp_Verification(user_data):
    try:
        email = (user_data or {}).get("email")
        otp = (user_data or {}).get("otp")
        if not email or not otp:
            logger.error("OTP email task missing required fields: email or otp")
            return

        _send_templated_email(
            subject="Your OTP for Mechanic Setu",
            to_email=email,
            html_template="Otp_Verification.html",
            context={"otp": otp},
            plain_fallback=f"Your OTP is {otp}",
        )
        logger.info("OTP email sent to %s", email)
    except Exception as e:
        logger.error("Error sending OTP email: %s", str(e), exc_info=True)

@shared_task
def send_login_success_email(user_data):
    try:
        email = (user_data or {}).get("email")
        first_name = (user_data or {}).get("first_name", "") or ""
        last_name = (user_data or {}).get("last_name", "") or ""
        if not email:
            logger.error("Login success email task missing required field: email")
            return

        context = {"first_name": first_name, "last_name": last_name}
        _send_templated_email(
            subject="Login Successful - Mechanic Setu",
            to_email=email,
            html_template="Login_Successful.html",
            context=context,
            plain_fallback=f"Hi {first_name} {last_name}, you have successfully logged in!",
        )
        logger.info("Login success email sent to %s", email)
    except Exception as e:
        logger.error("Error sending login success email: %s", str(e), exc_info=True)
