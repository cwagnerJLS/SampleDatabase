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
from .logging_config import get_logger

logger = get_logger(__name__, 'email')

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
        recipient_email (str or list): Recipient's email address(es).
        cc_emails (list): Optional list of CC email addresses.
    """
    # Handle both single recipient and list of recipients
    if isinstance(recipient_email, list):
        recipients = recipient_email
        logger.info(f"send_email called with subject: {subject}, recipients: {recipients}")
    else:
        recipients = [recipient_email]
        logger.info(f"send_email called with subject: {subject}, recipient: {recipient_email}")
    
    access_token = get_access_token()
    logger.info(f"Got access token: {access_token[:20]}..." if access_token else "No token received")

    # Check if TEST_MODE is enabled
    if getattr(settings, 'TEST_MODE', False):
        logger.info(f"TEST_MODE is enabled. Overriding recipients to {TEST_MODE_EMAIL}.")
        recipients = [TEST_MODE_EMAIL]
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
                        "address": email
                    }
                } for email in recipients
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

def build_opportunity_cc_list(opportunity_number):
    """
    Build CC list for opportunity emails including apps engineers and test lab group.
    
    Args:
        opportunity_number (str): The opportunity number
        
    Returns:
        list: List of email addresses for CC field
    """
    from .models import Sample
    
    apps_eng_values = Sample.objects.filter(
        opportunity_number=opportunity_number
    ).values_list('apps_eng', flat=True).distinct()
    
    cc_list = TEST_LAB_GROUP.copy()
    for apps_eng_name in apps_eng_values:
        if apps_eng_name:
            apps_eng_email = generate_email(apps_eng_name)
            if apps_eng_email and apps_eng_email not in cc_list:
                cc_list.append(apps_eng_email)
    
    logger.debug(f"Built CC list for opportunity {opportunity_number}: {cc_list}")
    return cc_list

def get_greeting_name(full_name):
    """
    Get the appropriate greeting name (nickname or first name).
    
    Args:
        full_name (str): The person's full name
        
    Returns:
        str: The greeting name to use in emails
    """
    if not full_name:
        return ""
    
    first_name = full_name.strip().split()[0] if full_name.strip() else ""
    return NICKNAMES.get(full_name, first_name)

def get_opportunity_email_context(opportunity_number):
    """
    Get common email context for opportunity-based emails.
    
    Args:
        opportunity_number (str): The opportunity number
        
    Returns:
        dict: Context containing opportunity, greeting_name, rsm_email, and cc_list
        None: If opportunity doesn't exist or has no RSM
    """
    from .models import Opportunity
    
    try:
        opp = Opportunity.objects.get(opportunity_number=opportunity_number)
        if not opp.rsm:
            logger.warning(f"No RSM name for opportunity {opportunity_number}")
            return None
            
        return {
            'opportunity': opp,
            'greeting_name': get_greeting_name(opp.rsm),
            'rsm_email': get_rsm_email(opp.rsm),
            'cc_list': build_opportunity_cc_list(opportunity_number),
            'customer': opp.customer or 'Unknown Customer'
        }
    except Opportunity.DoesNotExist:
        logger.error(f"No Opportunity found with number {opportunity_number}")
        return None
