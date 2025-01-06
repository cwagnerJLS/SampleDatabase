import os
import requests
from msal import PublicClientApplication, SerializableTokenCache

# Load credentials from environment variables
CLIENT_ID = "a6122249-68bf-479a-80b8-68583aba0e91"         # Your Azure AD App Client ID
TENANT_ID = "f281e9a3-6598-4ddc-adca-693183c89477"         # Your Azure AD Tenant ID
USERNAME = "service_account@jlsautomation.com"             # Your Service Account Email

TOKEN_CACHE_FILE = "token_cache.json"

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

def save_token_cache(cache):
    """
    Save the token cache to a JSON file.
    Args:
        cache (SerializableTokenCache): The token cache to save.
    """
    if cache.has_state_changed:
        with open(TOKEN_CACHE_FILE, "w") as f:
            f.write(cache.serialize())

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

def send_email(subject, body, recipient_email):
    """
    Sends an email using the Microsoft Graph API.
    Args:
        subject (str): Subject of the email.
        body (str): HTML content of the email.
        recipient_email (str): Recipient's email address.
    """
    access_token = get_access_token()

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

def get_rsm_email(rsm):
    rsm_email_mapping = {
        'Jeremy': 'jeremy@example.com',
        # Add other RSMs here
    }
    return rsm_email_mapping.get(rsm, 'default@example.com')  # Provide a default email if needed
