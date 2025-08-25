import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.settings')
import requests
from django.conf import settings
from samples.sharepoint_config import (
    EMAIL_SENDER,
    EMAIL_DOMAIN,
    TEST_MODE_EMAIL,
    TEST_LAB_GROUP_EMAILS,
    GRAPH_API_URL,
    AZURE_USERNAME,
    is_configured
)
from samples.services.auth_service import get_email_token
from samples.exceptions import (
    EmailAuthenticationError,
    EmailSendError,
    ConfigurationError
)
import logging

logger = logging.getLogger(__name__)

# Nicknames mapping
NICKNAMES = {
    'Peter DeSuno': 'Pete',
    'Michael R. Newcome': 'Mike',
    # Add other mappings as needed
}

# Test Lab Group emails - now loaded from config
TEST_LAB_GROUP = TEST_LAB_GROUP_EMAILS


def get_access_token():
    """
    Acquire an access token using the Device Code Flow with token caching.
    Returns:
        str: The access token.
    Raises:
        Exception: If token acquisition fails.
    """
    # Use the centralized authentication service
    return get_email_token()

def send_email(subject, body, recipient_email, cc_emails=None):
    """
    Sends an email using the Microsoft Graph API.
    Args:
        subject (str): Subject of the email.
        body (str): HTML content of the email.
        recipient_email (str): Recipient's email address.
    """
    logger.info(f"send_email called with subject: {subject}, recipient: {recipient_email}")
    access_token = get_access_token()
    logger.info(f"Got access token: {access_token[:20]}..." if access_token else "No token received")

    # Check if TEST_MODE is enabled
    if getattr(settings, 'TEST_MODE', False):
        logger.info(f"TEST_MODE is enabled. Overriding recipient email to {TEST_MODE_EMAIL}.")
        recipient_email = TEST_MODE_EMAIL
        cc_emails = None  # Do not CC Test Lab group in TEST_MODE

    # Define the endpoint for sending mail
    endpoint = f"{GRAPH_API_URL}/users/{AZURE_USERNAME}/sendMail"

    # Set up the headers with the access token
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # Create the email payload with the 'from' field
    email_msg = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": "HTML",
                "content": body
            },
            "toRecipients": [
                {
                    "emailAddress": {
                        "address": recipient_email
                    }
                }
            ],
            "ccRecipients": [
                {
                    "emailAddress": {
                        "address": email
                    }
                } for email in cc_emails
            ] if cc_emails else [],
            "from": {  # Specify the 'from' address
                "emailAddress": {
                    "address": EMAIL_SENDER  # Shared Mailbox Address from config
                }
            }
        }
    }

    # Send the POST request to the Graph API
    logger.info(f"Sending POST request to {endpoint}")
    response = requests.post(endpoint, headers=headers, json=email_msg)
    logger.info(f"Response status code: {response.status_code}")

    # Check the response status
    if response.status_code == 202:
        logger.info("Email sent successfully!")
    else:
        logger.error(f"Failed to send email: {response.status_code}, {response.text}")
        raise EmailSendError(f"Failed to send email: HTTP {response.status_code} - {response.text}")

def generate_email(full_name):
    # List of common suffixes to ignore
    suffixes = ["Jr.", "Sr.", "III", "IV", "V"]

    parts = full_name.strip().split()

    # If the last chunk is a known suffix, remove it
    if parts and parts[-1] in suffixes:
        parts = parts[:-1]

    if len(parts) < 2:
        logger.error(f"Invalid full name provided: '{full_name}'. Cannot generate email.")
        return None  # Or handle this appropriately

    # First name is the first element
    first_name = parts[0]
    # Last name is the last element
    last_name = parts[-1]

    # Construct the email address
    email = f"{first_name[0].lower()}{last_name.lower()}@{EMAIL_DOMAIN}"
    return email

def get_rsm_email(rsm_full_name):
    """
    Constructs the RSM's email address based on their full name.
    Args:
        rsm_full_name (str): The full name of the RSM.
    Returns:
        str or None: The constructed email address or None if invalid name.
    """
    email = generate_email(rsm_full_name)
    if email:
        return email
    else:
        # Return a default email or handle the error as needed
        return TEST_MODE_EMAIL  # Use test mode email as fallback
