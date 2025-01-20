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

# This is the Drive (document library) ID, e.g. "b!X3Eb6X7EmkGXMLnZD4..."
LIBRARY_ID = "b!X3Eb6X7EmkGXMLnZD4j_mJuFfGH0APlLs0IrZrwqabH6SO1yJ5v6TYCHXT-lTWgj"


# ====== Token Cache Utility Functions ======
def load_token_cache():
    """
    Load the token cache from token_cache.json (if it exists).
    """
    cache = SerializableTokenCache()
    if os.path.exists(TOKEN_CACHE_FILE):
        with open(TOKEN_CACHE_FILE, "r") as f:
            cache.deserialize(f.read())
    return cache


def save_token_cache(cache):
    """
    Save the token cache to token_cache.json if it has changed.
    """
    if cache.has_state_changed:
        with open(TOKEN_CACHE_FILE, "w") as f:
            f.write(cache.serialize())


# ====== Authentication ======
def get_access_token():
    """
    Acquire an access token using MSAL with a token cache and device code flow.
    """
    cache = load_token_cache()

    app = PublicClientApplication(
        client_id=CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        token_cache=cache
    )

    # Required scopes for accessing SharePoint
    scopes = ["Sites.ReadWrite.All"]

    # Attempt silent token acquisition
    accounts = app.get_accounts(username=USERNAME)
    if accounts:
        result = app.acquire_token_silent(scopes, account=accounts[0])
        if result and "access_token" in result:
            save_token_cache(app.token_cache)
            return result["access_token"]

    # If silent acquisition fails, initiate device code flow
    flow = app.initiate_device_flow(scopes=scopes)
    if "user_code" not in flow:
        raise Exception("Device flow initiation failed. Check your app registration.")

    print(flow["message"])  # Instructs you to sign in with a provided code
    result = app.acquire_token_by_device_flow(flow)

    if "access_token" in result:
        save_token_cache(app.token_cache)
        return result["access_token"]

    raise Exception("Authentication failed.")


# ====== 1. Find the Folder by Name ======
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
        logger.info(f"No exact folder match for '{folder_name}'.")
    else:
        logger.error(f"Search error: {response.status_code}, {response.text}")

    return None


# ====== 2. Retrieve Folder's Fields (listItem) ======
def list_folder_fields(access_token, library_id, folder_id):
    """
    Retrieves and prints the folder's associated list item fields.
    Shows the actual fields that have values set (or have defaults).
    """
    # Expand the listItem with its fields
    url = f"https://graph.microsoft.com/v1.0/drives/{library_id}/items/{folder_id}/listItem?$expand=fields"
    headers = {"Authorization": f"Bearer {access_token}"}

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        list_item = response.json()
        fields = list_item.get("fields", {})

        print("=== Fields currently set on this folder's list item ===")
        for key, value in fields.items():
            print(f"{key}: {value}")
    else:
        logger.error(f"Failed to retrieve folder fields: {response.status_code}, {response.text}")


# ====== 3. Discover the Underlying List (and site) for the Library ======
def get_site_and_list_id(access_token, drive_id):
    """
    Expands the `list` property of the drive to get:
      - The list ID
      - The site ID (from parentReference)
    so we can then list all columns in the library.
    """
    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}?$expand=list"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        data = response.json()
        list_data = data.get("list", {})
        list_id = list_data.get("id")  # The library's list ID

        parent_reference = list_data.get("parentReference", {})
        site_id = parent_reference.get("siteId")  # e.g. "contoso.sharepoint.com,GUID,GUID"
        return site_id, list_id
    else:
        logger.error(f"Error expanding drive to find list: {response.status_code}, {response.text}")
        return None, None


# ====== 4. List All Columns in the Library (Including Blank) ======
def list_all_columns(access_token, site_id, list_id):
    """
    List all columns (fields) in the library, including their internal and display names.
    This is where you can see columns that might be blank/not set for your folder.
    """
    if not site_id or not list_id:
        logger.error("Site ID or List ID is missing. Cannot list columns.")
        return

    url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/lists/{list_id}/columns"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        columns = response.json().get("value", [])
        print("=== All columns defined on this library ===")
        for col in columns:
            internal_name = col.get("name")
            display_name = col.get("displayName")
            print(f"Internal Name: {internal_name}, Display Name: {display_name}")
    else:
        logger.error(f"Error listing columns: {response.status_code}, {response.text}")


# ====== Main Logic ======
def main():
    folder_name = "Test"  # The folder name you're looking for

    try:
        access_token = get_access_token()

        # 1. Search for the folder
        folder_id = search_folder(access_token, LIBRARY_ID, folder_name)
        if folder_id:
            logger.info(f"Found folder '{folder_name}' with ID: {folder_id}")

            # 2. List the folder's fields that are already set
            list_folder_fields(access_token, LIBRARY_ID, folder_id)
        else:
            logger.info(f"Folder '{folder_name}' not found in library.")

        # 3. Get the site ID + list ID behind the library
        site_id, list_id = get_site_and_list_id(access_token, LIBRARY_ID)
        if site_id and list_id:
            # 4. List all columns in that library (including ones that might be blank)
            list_all_columns(access_token, site_id, list_id)

    except Exception as e:
        logger.error(f"An error occurred: {e}")


if __name__ == "__main__":
    main()
