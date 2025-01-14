#!/usr/bin/env python3

import os
from msal import PublicClientApplication

# Configuration
CLIENT_ID = "a6122249-68bf-479a-80b8-68583aba0e91"  # Azure AD App Client ID
TENANT_ID = "f281e9a3-6598-4ddc-adca-693183c89477"  # Azure AD Tenant ID
USERNAME = "cwagner@jlsautomation.com"             # Service Account Email
TOKEN_CACHE_FILE = "token_cache.json"

def load_token_cache():
    """
    Load the token cache from a JSON file.
    """
    from msal import SerializableTokenCache
    cache = SerializableTokenCache()
    if os.path.exists(TOKEN_CACHE_FILE):
        with open(TOKEN_CACHE_FILE, "r") as f:
            cache.deserialize(f.read())
    return cache

def save_token_cache(cache):
    """
    Save the token cache to a JSON file.
    """
    if cache.has_state_changed:
        with open(TOKEN_CACHE_FILE, "w") as f:
            f.write(cache.serialize())

def manual_authenticate():
    """
    Authenticate manually and update the token cache if successful.
    """
    # Initialize token cache
    cache = load_token_cache()

    # Create the MSAL application instance
    app = PublicClientApplication(
        CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        token_cache=cache
    )

    # Required scopes for accessing Microsoft Graph resources
    scopes = ["Sites.ReadWrite.All", "Files.ReadWrite.All"]

    # Attempt silent token acquisition first
    accounts = app.get_accounts(username=USERNAME)
    if accounts:
        result = app.acquire_token_silent(scopes, account=accounts[0])
        if result and "access_token" in result:
            print("Token successfully acquired silently.")
            save_token_cache(app.token_cache)
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
        save_token_cache(app.token_cache)
        return result["access_token"]

    raise Exception("Authentication failed.")

if __name__ == "__main__":
    try:
        token = manual_authenticate()
        print("Access token:", token)
    except Exception as e:
        print(f"Error: {e}")
