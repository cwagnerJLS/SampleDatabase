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

# The Drive (document library) ID. For example:
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


# ====== Search for Folder in the Library ======
def search_folder(access_token, library_id, folder_name):
    """
    Search for a folder named `folder_name` in the drive (library) using the
    Graph search endpoint. Returns the folder's item ID if found.
    """
    url = f"https://graph.microsoft.com/v1.0/drives/{library_id}/root/search(q='{folder_name}')"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        items = response.json().get("value", [])
        for item in items:
            # Check if it's a folder with the exact matching name
            if item.get("name", "").lower() == folder_name.lower() and "folder" in item:
                return item["id"]
        logger.info(f"No exact match found for folder '{folder_name}'.")
    else:
        logger.error(f"Search error: {response.status_code}, {response.text}")
    return None


# ====== Update Folder Fields (Correct Endpoint) ======
def update_folder_fields(access_token, library_id, folder_id, customer, rsm, description):
    """
    Updates the custom fields (Customer, RSM, Description) for a folder item
    in the given library by PATCHing the 'listItem/fields' endpoint.
    """
    # NOTE the correct endpoint: /listItem/fields (not /fields)
    url = f"https://graph.microsoft.com/v1.0/drives/{library_id}/items/{folder_id}/listItem/fields"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    # Use your actual internal column names here. Display names might differ.
    data = {
        "Customer": customer,
        "RSM": rsm,
        "Description": description
    }

    response = requests.patch(url, headers=headers, json=data)
    if response.status_code == 200:
        print("Folder fields updated successfully.")
    else:
        logger.error(f"Failed to update folder fields: {response.status_code}, {response.text}")


# ====== Main Logic ======
def main():
    folder_name = "Test"  # The folder name you're looking for
    customer_value = "MyCustomer"
    rsm_value = "MyRSM"
    description_value = "This is a test folder"

    try:
        access_token = get_access_token()
        folder_id = search_folder(access_token, LIBRARY_ID, folder_name)

        if folder_id:
            logger.info(f"Folder '{folder_name}' found with ID: {folder_id}")
            update_folder_fields(
                access_token=access_token,
                library_id=LIBRARY_ID,
                folder_id=folder_id,
                customer=customer_value,
                rsm=rsm_value,
                description=description_value
            )
        else:
            logger.info(f"Folder '{folder_name}' not found in library.")
    except Exception as e:
        logger.error(f"An error occurred: {e}")


if __name__ == "__main__":
    main()
