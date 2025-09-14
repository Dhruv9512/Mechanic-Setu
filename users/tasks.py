from MechanicSetu.settings import EMAIL_HOST_USER
from celery import shared_task
from django.template.loader import render_to_string
from django.core.mail import send_mail
import logging

logger = logging.getLogger(__name__)

# OTP Verification Task
@shared_task(bind=True, max_retries=3)
def Otp_Verification(self, user_data):
    try:
        subject = "Your OTP for Mechanic Setu"
        from_email = EMAIL_HOST_USER
        recipient_list = [user_data.get("email")]

        context = {"otp": user_data.get("otp")}

        # Render HTML + plain text
        html_message = render_to_string("Otp_Verification.html", context)
        plain_message = f"Your OTP is {user_data.get('otp')}"

        send_mail(
            subject,
            plain_message,   # Fallback text
            from_email,
            recipient_list,
            fail_silently=False,
            html_message=html_message,
        )
        logger.info(f"OTP email sent to {recipient_list[0]}")

    except Exception as e:
        logger.error(f"Error sending OTP email: {str(e)}")
        raise self.retry(exc=e, countdown=30)  # Retry after 30s


@shared_task(bind=True, max_retries=3)
def send_login_success_email(self, user_data):
    try:
        subject = "Login Successful - Mechanic Setu"
        from_email = EMAIL_HOST_USER
        recipient_list = [user_data.get("email")]

        context = {
            "first_name": user_data.get("first_name", ""),
            "last_name": user_data.get("last_name", ""),
        }

        html_message = render_to_string("Login_Successful.html", context)
        plain_message = f"Hi {context['first_name']} {context['last_name']}, you have successfully logged in!"

        send_mail(
            subject,
            plain_message,
            from_email,
            recipient_list,
            fail_silently=False,
            html_message=html_message,
        )
        logger.info(f"Login success email sent to {recipient_list[0]}")

    except Exception as e:
        logger.error(f"Error sending login success email: {str(e)}")
        raise self.retry(exc=e, countdown=30)  # Retry after 30s
