import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.settings')
import requests
from django.conf import settings
from msal import PublicClientApplication
from samples.token_cache_utils import get_token_cache
import logging

logger = logging.getLogger(__name__)

# Nicknames mapping
NICKNAMES = {
    'Peter DeSuno': 'Pete',
    'Michael R. Newcome': 'Mike',
    # Add other mappings as needed
}

# Test Lab Group emails
TEST_LAB_GROUP = [
    "cwagner@jlsautomation.com",
    "ndekker@jlsautomation.com",
    "cwentz@jlsautomation.com",
    "mmooney@jlsautomation.com",
    "kharding@jlsautomation.com",
    "msmith@jlsautomation.com",
    # Add other emails as needed in the future
]
CLIENT_ID = "a6122249-68bf-479a-80b8-68583aba0e91"         # Your Azure AD App Client ID
TENANT_ID = "f281e9a3-6598-4ddc-adca-693183c89477"         # Your Azure AD Tenant ID
USERNAME = "cwagner@jlsautomation.com"             # Your Service Account Email


def get_access_token():
    """
    Acquire an access token using the Device Code Flow with token caching.
    Returns:
        str: The access token.
    Raises:
        Exception: If token acquisition fails.
    """
    # Load existing token cache
    cache = get_token_cache()

    # Initialize the MSAL PublicClientApplication
    app = PublicClientApplication(
        CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        token_cache=cache
    )

    # Define the scopes required
    scopes = ["Mail.Send"]

    # Attempt to acquire token silently
    accounts = app.get_accounts(username=USERNAME)
    if accounts:
        result = app.acquire_token_silent(scopes, account=accounts[0])
        if result and "access_token" in result:
            print("Access token acquired from cache.")
            return result["access_token"]

    # If silent acquisition fails, use Device Code Flow
    flow = app.initiate_device_flow(scopes=scopes)
    if "user_code" not in flow:
        raise Exception("Failed to create device flow. Check your app registration.")

    print(flow["message"])  # Instructs the user to authenticate

    # Poll for the access token
    result = app.acquire_token_by_device_flow(flow)  # This function blocks until authentication is complete

    if "access_token" in result:
        print("Access token acquired via Device Code Flow.")
        return result["access_token"]
    else:
        error = result.get("error")
        error_description = result.get("error_description")
        raise Exception(f"Could not obtain access token: {error} - {error_description}")

def send_email(subject, body, recipient_email, cc_emails=None):
    """
    Sends an email using the Microsoft Graph API.
    Args:
        subject (str): Subject of the email.
        body (str): HTML content of the email.
        recipient_email (str): Recipient's email address.
    """
    access_token = get_access_token()

    # Check if TEST_MODE is enabled
    if getattr(settings, 'TEST_MODE', False):
        logger.info("TEST_MODE is enabled. Overriding recipient email to cwagner@jlsautomation.com.")
        recipient_email = 'cwagner@jlsautomation.com'
        cc_emails = None  # Do not CC Test Lab group in TEST_MODE

    # Define the endpoint for sending mail
    endpoint = f"https://graph.microsoft.com/v1.0/users/{USERNAME}/sendMail"

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
                    "address": "test-engineering@JLSAutomation.com"  # Shared Mailbox Address
                }
            }
        }
    }

    # Send the POST request to the Graph API
    response = requests.post(endpoint, headers=headers, json=email_msg)

    # Check the response status
    if response.status_code == 202:
        print("Email sent successfully!")
    else:
        print(f"Failed to send email: {response.status_code}, {response.text}")

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
    email = f"{first_name[0].lower()}{last_name.lower()}@jlsautomation.com"
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
        return 'cwagner@jlsautomation.com'
