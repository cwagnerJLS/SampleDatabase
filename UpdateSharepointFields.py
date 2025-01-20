import requests
import os
import logging
from msal import PublicClientApplication, SerializableTokenCache

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ====== Constants ======
CLIENT_ID = "a6122249-68bf-479a-80b8-68583aba0e91"  # Azure AD App Client ID
TENANT_ID = "f281e9a3-6598-4ddc-adca-693183c89477"  # Azure AD Tenant ID
USERNAME = "cwagner@jlsautomation.com"             # Service Account Email
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

# ====== 1. Search for the Folder by Name ======
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
            # Confirm exact name match and that the item is a folder
            if item.get("name", "").lower() == folder_name.lower() and "folder" in item:
                return item["id"]
        logger.info(f"No exact folder match for '{folder_name}'.")
    else:
        logger.error(f"Search error: {response.status_code}, {response.text}")

    return None

# ====== 2. Update the Folder Fields ======
def update_folder_fields(access_token, library_id, folder_id, customer_value, rsm_value, description_value):
    """
    Updates the custom fields (Customer, RSM, and _ExtendedDescription) for a folder item
    in the given library by PATCHing the 'listItem/fields' endpoint.
    """
    url = f"https://graph.microsoft.com/v1.0/drives/{library_id}/items/{folder_id}/listItem/fields"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # Use the correct internal names based on your column inspection:
    data = {
        "Customer": customer_value,
        "RSM": rsm_value,
        "_ExtendedDescription": description_value
    }

    response = requests.patch(url, headers=headers, json=data)
    if response.status_code == 200:
        print("Folder fields updated successfully.")
    else:
        logger.error(f"Failed to update folder fields: {response.status_code}, {response.text}")

# ====== Main Logic ======
def main():
    folder_name = "Test"  # The folder name to find
    # Set the new values you'd like
    new_customer = "Contoso"
    new_rsm = "Jane Doe"
    new_description = "Updated description for the Test folder."

    try:
        access_token = get_access_token()

        # 1. Find the folder by name
        folder_id = search_folder(access_token, LIBRARY_ID, folder_name)
        if not folder_id:
            print(f"Folder '{folder_name}' not found in library.")
            return

        logger.info(f"Found folder '{folder_name}' with ID: {folder_id}")

        # 2. Update the fields
        update_folder_fields(
            access_token=access_token,
            library_id=LIBRARY_ID,
            folder_id=folder_id,
            customer_value=new_customer,
            rsm_value=new_rsm,
            description_value=new_description
        )
    except Exception as e:
        logger.error(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
