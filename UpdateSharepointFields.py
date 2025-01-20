import requests
import os
import logging
from msal import PublicClientApplication, SerializableTokenCache

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ====== Constants ======
CLIENT_ID = "a6122249-68bf-479a-80b8-68583aba0e91"  # Azure AD App Client ID
TENANT_ID = "f281e9a3-6598-4ddc-adca-693183c89477"  # Azure AD Tenant ID
USERNAME = "cwagner@jlsautomation.com"  # Service Account Email
TOKEN_CACHE_FILE = "token_cache.json"
LIBRARY_ID = "b!X3Eb6X7EmkGXMLnZD4j_mJuFfGH0APlLs0IrZrwqabH6SO1yJ5v6TYCHXT-lTWgj"


def load_token_cache():
    cache = SerializableTokenCache()
    if os.path.exists(TOKEN_CACHE_FILE):
        with open(TOKEN_CACHE_FILE, "r") as f:
            cache.deserialize(f.read())
    return cache


def save_token_cache(cache):
    if cache.has_state_changed:
        with open(TOKEN_CACHE_FILE, "w") as f:
            f.write(cache.serialize())


def get_access_token():
    cache = load_token_cache()
    app = PublicClientApplication(
        client_id=CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        token_cache=cache
    )
    scopes = ["Sites.ReadWrite.All"]

    accounts = app.get_accounts(username=USERNAME)
    if accounts:
        result = app.acquire_token_silent(scopes, account=accounts[0])
        if result and "access_token" in result:
            save_token_cache(app.token_cache)
            return result["access_token"]

    flow = app.initiate_device_flow(scopes=scopes)
    if "user_code" not in flow:
        raise Exception("Device flow initiation failed.")

    print(flow["message"])
    result = app.acquire_token_by_device_flow(flow)
    if "access_token" in result:
        save_token_cache(app.token_cache)
        return result["access_token"]

    raise Exception("Authentication failed.")


def search_folder(access_token, library_id, folder_name):
    """
    Search for a folder named `folder_name` in the drive (library) using
    the Graph search endpoint. Returns the folder's item ID if found.
    """
    url = f"https://graph.microsoft.com/v1.0/drives/{library_id}/root/search(q='{folder_name}')"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        items = response.json().get("value", [])
        for item in items:
            if item.get("name", "").lower() == folder_name.lower() and "folder" in item:
                return item["id"]
        logger.info(f"No exact match found for folder '{folder_name}'.")
    else:
        logger.error(f"Search error: {response.status_code}, {response.text}")
    return None


def list_folder_fields(access_token, library_id, folder_id):
    """
    Retrieves and prints the folder's associated list item fields.
    Shows the actual internal field names and current values.
    """
    url = f"https://graph.microsoft.com/v1.0/drives/{library_id}/items/{folder_id}/listItem?$expand=fields"
    headers = {"Authorization": f"Bearer {access_token}"}

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        list_item = response.json()
        fields = list_item.get("fields", {})

        print("=== Fields for this folder's list item ===")
        for key, value in fields.items():
            print(f"{key}: {value}")
    else:
        logger.error(f"Failed to retrieve folder fields: {response.status_code}, {response.text}")


def main():
    folder_name = "Test"  # Replace with the folder name in your library

    try:
        access_token = get_access_token()
        folder_id = search_folder(access_token, LIBRARY_ID, folder_name)
        if folder_id:
            logger.info(f"Found folder '{folder_name}' with ID: {folder_id}")
            list_folder_fields(access_token, LIBRARY_ID, folder_id)
        else:
            logger.info(f"Folder '{folder_name}' not found.")
    except Exception as e:
        logger.error(f"An error occurred: {e}")


if __name__ == "__main__":
    main()
