import requests
from msal import PublicClientApplication
import os

# Reuse configurations
CLIENT_ID = "a6122249-68bf-479a-80b8-68583aba0e91"  # Azure AD App Client ID
TENANT_ID = "f281e9a3-6598-4ddc-adca-693183c89477"  # Azure AD Tenant ID
USERNAME = "cwagner@jlsautomation.com"  # Service Account Email
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


def get_access_token():
    """
    Acquire an access token.
    """
    cache = load_token_cache()

    app = PublicClientApplication(
        CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        token_cache=cache
    )

    scopes = ["Sites.ReadWrite.All", "Files.ReadWrite.All"]

    accounts = app.get_accounts(username=USERNAME)
    if accounts:
        result = app.acquire_token_silent(scopes, account=accounts[0])
        if result and "access_token" in result:
            save_token_cache(app.token_cache)
            return result["access_token"]

    flow = app.initiate_device_flow(scopes=scopes)
    if "user_code" not in flow:
        raise Exception("Device flow initiation failed. Check your app registration.")

    print(flow["message"])
    result = app.acquire_token_by_device_flow(flow)

    if "access_token" in result:
        save_token_cache(app.token_cache)
        return result["access_token"]

    raise Exception("Authentication failed.")


def query_sharepoint_site(access_token, hostname, path):
    """
    Queries the SharePoint site to ensure access.
    Args:
        access_token (str): Access token from Microsoft Graph.
        hostname (str): Hostname of the SharePoint site.
        path (str): Path to the specific site.
    """
    endpoint = f"https://graph.microsoft.com/v1.0/sites/{hostname}:/sites/{path}"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(endpoint, headers=headers)

    if response.status_code == 200:
        print("Access to SharePoint confirmed!")
        return response.json()
    else:
        print(f"Failed to query SharePoint site: {response.status_code}, {response.text}")
        return None

# Main
if __name__ == "__main__":
    try:
        token = get_access_token()
        site_info = query_sharepoint_site(
            token,
            hostname="jlsautomation.sharepoint.com",
            path="TestEngineering"
        )
        if site_info:
            print("Site Info:")
            print(site_info)
    except Exception as e:
        print(f"Error: {e}")

