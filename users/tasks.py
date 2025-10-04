import os
from celery import shared_task
from django.template.loader import render_to_string
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
import logging
import pytz
from datetime import datetime

# Set up a logger for this module
logger = logging.getLogger(__name__)

# Function to return the current time as a string in HH:MM:SS format
def get_current_datetime():
    ist = pytz.timezone('Asia/Kolkata')
    return datetime.now(ist).strftime("%Y-%m-%d %I:%M %p")

# --- Brevo API Client Configuration ---
# This setup is done once when the Celery worker starts.

# It's best practice to define your "from" email here or get it from a specific env var.
# This email MUST be a verified sender in your Brevo account.
DEFAULT_FROM_EMAIL = os.getenv('BREVO_SENDER_EMAIL')

# Configure the Brevo API client
configuration = sib_api_v3_sdk.Configuration()
brevo_api_key = os.getenv('BREVO_API_KEY')
# 🚨 START: TEMPORARY DEBUGGING CODE 🚨
if brevo_api_key:
    logger.info(f"Found BREVO_API_KEY. Starts with: {brevo_api_key[:4]} and ends with {brevo_api_key[-4:]}")
else:
    logger.error("BREVO_API_KEY environment variable is NOT FOUND.")
# 🚨 END: TEMPORARY DEBUGGING CODE 🚨
if not brevo_api_key:
    logger.critical("FATAL: BREVO_API_KEY environment variable not found. Email sending will fail.")
else:
    configuration.api_key['api-key'] = brevo_api_key

# Create an API instance
api_client = sib_api_v3_sdk.ApiClient(configuration)
api_instance = sib_api_v3_sdk.TransactionalEmailsApi(api_client)


def _send_templated_email(*, subject: str, to_email: str, html_template: str, context: dict, plain_fallback: str, sender_name: str):
    """
    A helper function to render and send a transactional email using the Brevo API.
    """
    if not configuration.api_key.get('api-key'):
        raise ValueError("Cannot send email because Brevo API key is not configured.")

    # Render the HTML content from a Django template
    html_message = render_to_string(html_template, context or {})

    # Define the sender and recipient
    sender = {"name": sender_name, "email": DEFAULT_FROM_EMAIL}
    to = [{"email": to_email}]

    # Create the email object using the Brevo SDK
    send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
        to=to,
        sender=sender,
        subject=subject,
        html_content=html_message,
        text_content=plain_fallback
    )

    # Send the email via the Brevo API
    try:
        api_response = api_instance.send_transac_email(send_smtp_email)
        logger.info(f"Email '{subject}' sent to {to_email} via Brevo. Message ID: {api_response.message_id}")
    except ApiException as e:
        logger.error(f"Brevo API error when sending email to {to_email}: {e.body}")
        raise e


# --- USER FACING TASKS (Mechanic Setu) ---

@shared_task(name="Otp_Verification")
def Otp_Verification(user_data):
    """Celery task to send an OTP email to a regular user."""
    try:
        email = user_data.get("email")
        otp = user_data.get("otp")
        _send_templated_email(
            subject="Your OTP for Mechanic Setu",
            to_email=email,
            html_template="Otp_Verification.html",
            context={"otp": otp},
            plain_fallback=f"Your OTP is {otp}",
            sender_name="Mechanic Setu"
        )
    except Exception as e:
        logger.error(f"Error in Otp_Verification task for {user_data.get('email')}: {e}", exc_info=True)


@shared_task(name="send_login_success_email")
def send_login_success_email(user_data):
    """Celery task to send a login notification to a regular user."""
    try:
        email = user_data.get("email")
        context = {
            "first_name": user_data.get("first_name", ""),
            "last_name": user_data.get("last_name", "")
        }
        _send_templated_email(
            subject="Successful Login to Mechanic Setu",
            to_email=email,
            html_template="Login_Successful.html",
            context=context,
            plain_fallback=f"Hi {context['first_name']}, you have successfully logged in!",
            sender_name="Mechanic Setu"
        )
    except Exception as e:
        logger.error(f"Error in send_login_success_email task for {user_data.get('email')}: {e}", exc_info=True)


# --- MECHANIC FACING TASKS (Setu Partner) ---

@shared_task(name="Send_Mechanic_Otp_Verification")
def Send_Mechanic_Otp_Verification(user_data):
    """Celery task to send an OTP email to a mechanic."""
    try:
        email = user_data.get("email")
        otp = user_data.get("otp")
        _send_templated_email(
            subject="Your OTP for Setu Partner",
            to_email=email,
            html_template="Mechanic_Otp_Verification.html", # Assumes you have a specific template
            context={"otp": otp},
            plain_fallback=f"Your Setu Partner OTP is {otp}",
            sender_name="Setu Partner"
        )
    except Exception as e:
        logger.error(f"Error in Send_Mechanic_Otp_Verification task for {user_data.get('email')}: {e}", exc_info=True)


@shared_task(name="Send_Mechanic_Login_Successful_Email")
def Send_Mechanic_Login_Successful_Email(user_data):
    """Celery task to send a login notification to a mechanic."""
    try:
        email = user_data.get("email")
        context = {
            "first_name": user_data.get("first_name", ""),
            "last_name": user_data.get("last_name", "")
        }
        _send_templated_email(
            subject="Successful Login to Setu Partner",
            to_email=email,
            html_template="Mechanic_Login_Successful.html",
            context=context,
            plain_fallback=f"Hi {context['first_name']}, you have successfully logged into your Setu Partner dashboard!",
            sender_name="Setu Partner"
        )
    except Exception as e:
        logger.error(f"Error in Send_Mechanic_Login_Successful_Email task for {user_data.get('email')}: {e}", exc_info=True)

