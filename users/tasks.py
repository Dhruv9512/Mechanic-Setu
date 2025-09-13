from MechanicSetu.settings import EMAIL_HOST_USER
from celery import shared_task
from django.template.loader import render_to_string
from django.core.mail import send_mail
import logging
logger = logging.getLogger(__name__)






# OTP Verification Task
@shared_task
def Otp_Verification(user_data):
    
    try:
        subject = "Your OTP for Mechanic Setu"
        from_email = EMAIL_HOST_USER
        recipient_list = [user_data.get("email")]
        context = {
            'otp': user_data.get("otp"),
        }
        message =  render_to_string('Otp_Verification.html', context)
        
       
        send_mail(subject, message, from_email, recipient_list, fail_silently=False, html_message=message)
    except Exception as e:
        logger.error(f"Error sending registration email: {str(e)}")


@shared_task
def send_login_success_email(user_data):
    try:
        subject = "Login Successful - Mechanic Setu"
        from_email = EMAIL_HOST_USER
        recipient_list = [user_data.get("email")]

        context = {
            "first_name": user_data.get("first_name", ""),
            "last_name": user_data.get("last_name", ""),
        }

        # ✅ Use a template for HTML email
        message = render_to_string("Login_Successful.html", context)

        send_mail(
            subject,
            message,  # fallback plain-text
            from_email,
            recipient_list,
            fail_silently=False,
            html_message=message
        )
        logger.info(f"Login success email sent to {recipient_list[0]}")

    except Exception as e:
        logger.error(f"Error sending login success email: {str(e)}")