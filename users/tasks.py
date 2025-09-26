import os
from celery import shared_task
from django.template.loader import render_to_string
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
import logging

# Set up a logger for this module
logger = logging.getLogger(__name__)

DEFAULT_FROM_EMAIL = os.getenv("EMAIL_HOST_USER")

# Configure the Brevo API client
configuration = sib_api_v3_sdk.Configuration()
# Get the API key from the environment variable you set in Render
brevo_api_key = os.environ.get('BREVO_API_KEY')
if not brevo_api_key:
    logger.error("BREVO_API_KEY environment variable not set. Emails will fail to send.")
configuration.api_key['api-key'] = brevo_api_key

# Create an API instance
api_client = sib_api_v3_sdk.ApiClient(configuration)
api_instance = sib_api_v3_sdk.TransactionalEmailsApi(api_client)


def _send_templated_email(*, subject: str, to_email: str, html_template: str, context: dict, plain_fallback: str):
    """
    A helper function to render and send a transactional email using the Brevo API.
    This replaces the original function that used Django's SMTP-based send_mail.
    """
    # 1. Render the HTML content from a Django template
    html_message = render_to_string(html_template, context or {})

    # 2. Define the sender and recipient for the Brevo API
    # IMPORTANT: The sender email MUST be a verified sender in your Brevo account.
    sender = {"name": "Mechanic Setu", "email": DEFAULT_FROM_EMAIL}
    to = [{"email": to_email}]

    # 3. Create the email object using the Brevo SDK
    send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
        to=to,
        sender=sender,
        subject=subject,
        html_content=html_message,
        text_content=plain_fallback  # Use the plain text fallback
    )

    # 4. Send the email via the Brevo API
    try:
        api_response = api_instance.send_transac_email(send_smtp_email)
        logger.info(f"Email sent to {to_email} via Brevo. Response: {api_response.message_id}")
    except ApiException as e:
        logger.error(f"Brevo API error when sending email to {to_email}: {e}")
        # Re-raise the exception so the calling Celery task can handle it (e.g., retry)
        raise e


@shared_task(name="Otp_Verification")
def Otp_Verification(user_data):
    """Celery task to send an OTP verification email."""
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
        logger.info("OTP email task successfully queued for %s", email)
    except Exception as e:
        logger.error("Error in Otp_Verification task for %s: %s", email, str(e), exc_info=True)


@shared_task(name="send_login_success_email")
def send_login_success_email(user_data):
    """Celery task to send a notification after a successful login."""
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
        logger.info("Login success email task successfully queued for %s", email)
    except Exception as e:
        logger.error("Error in send_login_success_email task for %s: %s", email, str(e), exc_info=True)




@shared_task(name="Send_Mechanic_Login_Successful_Email")
def Send_Mechanic_Login_Successful_Email(user_data):
    """Celery task to send a notification after a successful login."""
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
            html_template="Mechanic_Login_Successful.html",
            context=context,
            plain_fallback=f"Hi {first_name} {last_name}, you have successfully logged in!",
        )
        logger.info("Login success email task successfully queued for %s", email)
    except Exception as e:
        logger.error("Error in send_login_success_email task for %s: %s", email, str(e), exc_info=True)


@shared_task(name="Send_Mechanic_Otp_Verification")
def Send_Mechanic_Otp_Verification(user_data):
    """Celery task to send an OTP verification email."""
    try:
        email = (user_data or {}).get("email")
        otp = (user_data or {}).get("otp")
        if not email or not otp:
            logger.error("OTP email task missing required fields: email or otp")
            return

        _send_templated_email(
            subject="Your OTP for Mechanic Setu",
            to_email=email,
            html_template="Mechanic_Otp_Verification.html",
            context={"otp": otp},
            plain_fallback=f"Your OTP is {otp}",
        )
        logger.info("OTP email task successfully queued for %s", email)
    except Exception as e:
        logger.error("Error in Otp_Verification task for %s: %s", email, str(e), exc_info=True)