#!/usr/bin/env python3

import os
import json
import requests
from msal import PublicClientApplication, SerializableTokenCache

# =============================================================================
# CONFIGURATION - REPLACE THESE WITH YOUR ACTUAL VALUES
# =============================================================================
CLIENT_ID = "a6122249-68bf-479a-80b8-68583aba0e91"         # Your Azure AD App Client ID
TENANT_ID = "f281e9a3-6598-4ddc-adca-693183c89477"         # Your Azure AD Tenant ID
USERNAME = "cwagner@jlsautomation.com"             # Your Service Account Email

# Token cache file path
TOKEN_CACHE_FILE = "token_cache.json"

# =============================================================================
# FUNCTION TO LOAD TOKEN CACHE
# =============================================================================
def load_token_cache():
    """
    Load the token cache from a JSON file.
    Returns:
        SerializableTokenCache: The loaded token cache.
    """
    cache = SerializableTokenCache()
    if os.path.exists(TOKEN_CACHE_FILE):
        with open(TOKEN_CACHE_FILE, "r") as f:
            cache.deserialize(f.read())
    return cache

# =============================================================================
# FUNCTION TO SAVE TOKEN CACHE
# =============================================================================
def save_token_cache(cache):
    """
    Save the token cache to a JSON file.
    Args:
        cache (SerializableTokenCache): The token cache to save.
    """
    if cache.has_state_changed:
        with open(TOKEN_CACHE_FILE, "w") as f:
            f.write(cache.serialize())

# =============================================================================
# FUNCTION TO GET ACCESS TOKEN USING DEVICE CODE FLOW WITH CACHE
# =============================================================================
def get_access_token():
    """
    Acquire an access token using the Device Code Flow with token caching.
    Returns:
        str: The access token.
    Raises:
        Exception: If token acquisition fails.
    """
    # Load existing token cache
    cache = load_token_cache()

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
            save_token_cache(app.token_cache)
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
        save_token_cache(app.token_cache)
        return result["access_token"]
    else:
        error = result.get("error")
        error_description = result.get("error_description")
        raise Exception(f"Could not obtain access token: {error} - {error_description}")

# =============================================================================
# FUNCTION TO SEND EMAIL VIA Microsoft Graph API
# =============================================================================
def send_email(subject, body, recipient_email, access_token):
    """
    Sends an email using the Microsoft Graph API.
    Args:
        subject (str): Subject of the email.
        body (str): HTML content of the email.
        recipient_email (str): Recipient's email address.
        access_token (str): Access token for authentication.
    """
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

# =============================================================================
# MAIN EXECUTION - SEND A TEST EMAIL
# =============================================================================
if __name__ == "__main__":
    try:
        # Step 1: Get access token (from cache or Device Code Flow)
        access_token = get_access_token()

        # Step 2: Define email details with variables
        RSM = "Jeremy"
        Date_Received = "12/15/2023"
        Opportunity_Number = "8739"
        Customer = "JF Martin"
        Quantity = 4

        # Construct the subject and body using the variables
        subject = f'{Opportunity_Number} ({Customer}) Samples Received'
        body = f"""
        <html>
            <body>
                <p>Hello {RSM},</p>
                <p>{Quantity} samples for opportunity number {Opportunity_Number} ({Customer}) were received on {Date_Received}. They will be documented and uploaded to the opportunity folder on Sharepoint shortly. Thanks,</p>
                <p>-Test Lab</p>
            </body>
        </html>
        """

        test_recipient = "cwagner@jlsautomation.com"  # Replace with your recipient email

        # Step 3: Send the test email
        send_email(subject, body, test_recipient, access_token)

    except Exception as e:
        print(f"An error occurred: {e}")
