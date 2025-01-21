import os
import requests
import logging
from msal import PublicClientApplication, SerializableTokenCache

logger = logging.getLogger(__name__)

# ------------------------------------------------------------
# 1) CONFIGURATION CONSTANTS
# ------------------------------------------------------------
CLIENT_ID = "a6122249-68bf-479a-80b8-68583aba0e91"      # Azure AD App Client ID
TENANT_ID = "f281e9a3-6598-4ddc-adca-693183c89477"      # Azure AD Tenant ID
USERNAME = "cwagner@jlsautomation.com"                 # Service Account Email
TOKEN_CACHE_FILE = "token_cache.json"

# The Drive (document library) ID
LIBRARY_ID = "b!X3Eb6X7EmkGXMLnZD4j_mJuFfGH0APlLs0IrZrwqabH6SO1yJ5v6TYCHXT-lTWgj"

# Internal SharePoint field names for your custom columns
FIELD_CUSTOMER = "Customer"
FIELD_RSM = "RSM"
FIELD_DESCRIPTION = "_ExtendedDescription"  # 'Description' column is '_ExtendedDescription' internally

# ------------------------------------------------------------
# 2) TOKEN ACQUISITION
# ------------------------------------------------------------
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
    """
    Acquire an access token for Microsoft Graph using MSAL device flow.
    """
    cache = load_token_cache()
    app = PublicClientApplication(
        client_id=CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        token_cache=cache
    )
    scopes = ["Sites.ReadWrite.All"]  # Adjust if needed

    # Attempt silent token acquisition
    accounts = app.get_accounts(username=USERNAME)
    if accounts:
        result = app.acquire_token_silent(scopes, account=accounts[0])
        if result and "access_token" in result:
            save_token_cache(app.token_cache)
            return result["access_token"]

    # Fallback to device flow
    flow = app.initiate_device_flow(scopes=scopes)
    if "user_code" not in flow:
        raise Exception("Device flow initiation failed. Check your app registration.")

    print(flow["message"])
    result = app.acquire_token_by_device_flow(flow)
    if "access_token" in result:
        save_token_cache(app.token_cache)
        return result["access_token"]

    raise Exception("Authentication failed.")

# ------------------------------------------------------------
# 3) FOLDER OPERATIONS
# ------------------------------------------------------------
def search_folder(access_token, folder_name):
    """
    Search for a folder by exact name in the root of the given LIBRARY_ID.
    Returns the folder's item ID if found, else None.
    """
    url = f"https://graph.microsoft.com/v1.0/drives/{LIBRARY_ID}/root/search(q='{folder_name}')"
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        items = resp.json().get("value", [])
        for item in items:
            # Check if it's a folder with the exact matching name
            if item.get("name", "").strip().lower() == folder_name.strip().lower() and "folder" in item:
                return item["id"]
    else:
        logger.error(f"Search folder error: {resp.status_code}, {resp.text}")
    return None

def create_folder(access_token, folder_name):
    """
    Creates a folder in the root of the library. Returns its item ID if successful, else None.
    If the folder name already exists, it fails unless you change conflictBehavior.
    """
    url = f"https://graph.microsoft.com/v1.0/drives/{LIBRARY_ID}/root/children"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    data = {
        "name": folder_name,
        "folder": {},
        "@microsoft.graph.conflictBehavior": "fail"
    }
    resp = requests.post(url, headers=headers, json=data)
    if resp.status_code in (200, 201):
        folder_item = resp.json()
        return folder_item["id"]
    else:
        error_message = f"Error creating folder '{folder_name}': {resp.status_code}, {resp.text}"
        logger.error(error_message)
        raise Exception(error_message)

def update_folder_fields(access_token, folder_id, customer, rsm, description):
    """
    Updates the custom fields (Customer, RSM, _ExtendedDescription) of the folder's listItem.
    """
    url = f"https://graph.microsoft.com/v1.0/drives/{LIBRARY_ID}/items/{folder_id}/listItem/fields"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    data = {
        FIELD_CUSTOMER: customer,
        FIELD_RSM: rsm,
        FIELD_DESCRIPTION: description
    }
    resp = requests.patch(url, headers=headers, json=data)
    if resp.status_code == 200:
        logger.info(f"Updated SharePoint fields for folder ID {folder_id}")
    else:
        logger.error(f"Error updating folder fields ID {folder_id}: {resp.status_code}, {resp.text}")

def create_sharepoint_folder(opportunity_number, customer, rsm, description):
    """
    Ensures a folder named opportunity_number exists in the SharePoint library.
    If it doesn't, creates it and sets fields. Then creates a 'Samples' subfolder within it.
    """
    try:
        access_token = get_access_token()
        # 1) Check if the folder exists
        existing_folder_id = search_folder(access_token, opportunity_number)
        if existing_folder_id:
            logger.info(f"Folder '{opportunity_number}' already exists on SharePoint.")
            parent_folder_id = existing_folder_id
        else:
            # 2) Create the opportunity folder
            parent_folder_id = create_folder(access_token, opportunity_number)
            if parent_folder_id:
                # 3) Update the custom fields
                update_folder_fields(access_token, parent_folder_id, customer, rsm, description)
            else:
                logger.error(f"Failed to create opportunity folder '{opportunity_number}'.")
                raise Exception(f"Failed to create opportunity folder '{opportunity_number}'.")

        # 4) Create the 'Samples' subfolder within the opportunity folder
        create_subfolder(access_token, parent_folder_id, 'Samples')
        create_subfolder(access_token, parent_folder_id, 'Pics and Vids')
        create_subfolder(access_token, parent_folder_id, 'Modeling')

    except Exception as e:
        logger.error(f"SharePoint folder creation failed for {opportunity_number}: {e}")
        raise
def create_subfolder(access_token, parent_folder_id, subfolder_name):
    url = f"https://graph.microsoft.com/v1.0/drives/{LIBRARY_ID}/items/{parent_folder_id}/children"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    data = {
        "name": subfolder_name,
        "folder": {},
        "@microsoft.graph.conflictBehavior": "fail"
    }
    resp = requests.post(url, headers=headers, json=data)
    if resp.status_code in (200, 201):
        logger.info(f"Subfolder '{subfolder_name}' created successfully.")
    elif resp.status_code == 409:
        # Parse the error code and message
        error_info = resp.json().get("error", {})
        error_code = error_info.get("code")
        error_message = error_info.get("message")
        if error_code == "nameAlreadyExists":
            logger.info(f"Subfolder '{subfolder_name}' already exists. Proceeding without error.")
            # Do not raise an exception; treat as success
        else:
            # Handle other conflict errors
            logger.error(f"Conflict error creating subfolder '{subfolder_name}': {error_code}, {error_message}")
            raise Exception(f"Error creating subfolder '{subfolder_name}': {error_code}, {error_message}")
