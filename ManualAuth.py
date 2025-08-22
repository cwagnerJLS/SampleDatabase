#!/usr/bin/env python3

import os
import sys
from pathlib import Path

# Add the project root to path and setup Django
sys.path.append(str(Path(__file__).resolve().parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.settings')

import django
django.setup()

from msal import PublicClientApplication
from samples.token_cache_utils import get_token_cache
from samples.sharepoint_config import (
    AZURE_CLIENT_ID as CLIENT_ID,
    AZURE_TENANT_ID as TENANT_ID,
    AZURE_USERNAME as USERNAME,
    AZURE_AUTHORITY,
    SHAREPOINT_SCOPES,
    is_configured
)


def manual_authenticate():
    """
    Authenticate manually and update the token cache if successful.
    """
    # Check if environment variables are configured
    if not is_configured():
        print("ERROR: Required environment variables are not set!")
        print("Please ensure all required environment variables are configured.")
        print("See .env.example for the list of required variables.")
        return None
    
    # Initialize token cache
    cache = get_token_cache()

    # Create the MSAL application instance
    app = PublicClientApplication(
        CLIENT_ID,
        authority=AZURE_AUTHORITY,
        token_cache=cache
    )

    # Required scopes for accessing Microsoft Graph resources
    scopes = SHAREPOINT_SCOPES

    # Attempt silent token acquisition first
    accounts = app.get_accounts(username=USERNAME)
    if accounts:
        result = app.acquire_token_silent(scopes, account=accounts[0])
        if result and "access_token" in result:
            print("Token successfully acquired silently.")
            return result["access_token"]

    # If silent acquisition fails, initiate device code flow
    flow = app.initiate_device_flow(scopes=scopes)
    if "user_code" not in flow:
        raise Exception("Device flow initiation failed. Check your app registration.")

    print("Please complete the authentication process:")
    print(flow["message"])

    result = app.acquire_token_by_device_flow(flow)

    if "access_token" in result:
        print("Authentication successful. Token saved to cache.")
        return result["access_token"]

    raise Exception("Authentication failed.")

if __name__ == "__main__":
    try:
        token = manual_authenticate()
        print("Access token:", token)
    except Exception as e:
        print(f"Error: {e}")

    # Wait for user input before closing
    input("Press Enter to exit...")
