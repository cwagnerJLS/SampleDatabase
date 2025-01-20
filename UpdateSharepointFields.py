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

# Drive (document library) ID
LIBRARY_ID = "b!X3Eb6X7EmkGXMLnZD4j_mJuFfGH0APlLs0IrZrwqabH6SO1yJ5v6TYCHXT-lTWgj"

# Internal field names (from your library column listing)
FIELD_CUSTOMER = "Customer"
FIELD_RSM = "RSM"
FIELD_DESCRIPTION = "_ExtendedDescription"

# ====== Token Cache Utility Functions ======
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

# ====== Authentication ======
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
        raise Exception("Device flow initiation failed. Check your app registration.")

    print(flow["message"])
    result = app.acquire_token_by_device_flow(flow)

    if "access_token" in result:
        save_token_cache(app.token_cache)
        return result["access_token"]

    raise Exception("Authentication failed.")

# ====== 1. Search for Folder by Name ======
def search_folder(access_token, library_id, folder_name):
    """
    Returns the folder's item ID if found; else None.
    """
    url = f"https://graph.microsoft.com/v1.0/drives/{library_id}/root/search(q='{folder_name}')"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        items = response.json().get("value", [])
        for item in items:
            # Match exact name & confirm it's a folder
            if item.get("name", "").lower() == folder_name.lower() and "folder" in item:
                return item["id"]
        logger.info(f"No exact folder match for '{folder_name}'.")
    else:
        logger.error(f"Search error: {response.status_code}, {response.text}")

    return None

# ====== 2. Create Folder (if not found) ======
def create_folder(access_token, library_id, folder_name):
    """
    Create a new folder in the root of the given drive/library.
    Returns the new folder's item ID on success.
    """
    url = f"https://graph.microsoft.com/v1.0/drives/{library_id}/root/children"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    # @microsoft.graph.conflictBehavior = "fail"
    #   => This will fail if a folder with same name already exists
    data = {
        "name": folder_name,
        "folder": {},
        "@microsoft.graph.conflictBehavior": "fail"
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code in (200, 201):
        folder_item = response.json()
        logger.info(f"Folder '{folder_name}' created successfully.")
        return folder_item["id"]
    else:
        logger.error(f"Failed to create folder '{folder_name}': {response.status_code}, {response.text}")
        return None

# ====== 3. Update the Folder Fields ======
def update_folder_fields(access_token, library_id, folder_id, customer_value, rsm_value, description_value):
    """
    PATCH the 'listItem/fields' endpoint with the correct internal column names.
    """
    url = f"https://graph.microsoft.com/v1.0/drives/{library_id}/items/{folder_id}/listItem/fields"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    data = {
        FIELD_CUSTOMER: customer_value,
        FIELD_RSM: rsm_value,
        FIELD_DESCRIPTION: description_value
    }
    response = requests.patch(url, headers=headers, json=data)
    if response.status_code == 200:
        print("Folder fields updated successfully.")
    else:
        logger.error(f"Failed to update folder fields: {response.status_code}, {response.text}")

# ====== Main Logic ======
def main():
    folder_name = "Test"  # The folder to create/update
    new_customer = "New Customer"
    new_rsm = "Jeremy"
    new_description = "This is a test"

    try:
        access_token = get_access_token()

        # 1. Search for the folder
        folder_id = search_folder(access_token, LIBRARY_ID, folder_name)

        # 2. If not found, create it
        if not folder_id:
            folder_id = create_folder(access_token, LIBRARY_ID, folder_name)
            if not folder_id:
                logger.error("Unable to proceed without a valid folder ID.")
                return
        else:
            logger.info(f"Folder '{folder_name}' already exists with ID: {folder_id}")

        # 3. Update fields on the folder
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
