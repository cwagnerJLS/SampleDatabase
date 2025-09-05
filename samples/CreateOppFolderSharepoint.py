import os
from django.conf import settings
from samples.sharepoint_config import (
    TEST_ENGINEERING_LIBRARY_ID as LIBRARY_ID,
    GRAPH_API_URL,
    is_configured
)
from samples.services.auth_service import get_sharepoint_token
from samples.utils.sharepoint_api import GraphAPIClient
from samples.logging_config import get_logger

# Define the path to Hyperlinks.csv using BASE_DIR
HYPERLINKS_CSV_FILE = os.path.join(settings.BASE_DIR, 'Hyperlinks.csv')

logger = get_logger(__name__, 'sharepoint')

import django

if not settings.configured:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.settings')
    django.setup()

# Internal SharePoint field names for your custom columns
FIELD_CUSTOMER = "Customer"
FIELD_RSM = "RSM"
FIELD_DESCRIPTION = "_ExtendedDescription"  # Now stores the opportunity number
def create_subfolder(access_token, parent_folder_id, subfolder_name):
    """
    Creates a subfolder within the specified parent folder.
    """
    url = f"{GRAPH_API_URL}/drives/{LIBRARY_ID}/items/{parent_folder_id}/children"
    data = {
        "name": subfolder_name,
        "folder": {},
        "@microsoft.graph.conflictBehavior": "fail"
    }
    result = GraphAPIClient.post(url, access_token, json_data=data, raise_on_error=False)
    if result:
        logger.info(f"Created subfolder '{subfolder_name}' in folder ID {parent_folder_id}")
    else:
        logger.error(f"Error creating subfolder '{subfolder_name}' in folder ID {parent_folder_id}")

def get_access_token():
    """
    Acquire an access token for Microsoft Graph using MSAL device flow.
    """
    # Use the centralized authentication service
    return get_sharepoint_token()

# ------------------------------------------------------------
# 3) FOLDER OPERATIONS
# ------------------------------------------------------------
def search_folder(access_token, folder_name):
    """
    Search for a folder by exact name in the root of the given LIBRARY_ID.
    Returns the folder's item ID if found, else None.
    """
    url = f"{GRAPH_API_URL}/drives/{LIBRARY_ID}/root/search(q='{folder_name}')"
    result = GraphAPIClient.get(url, access_token, raise_on_error=False)
    if result:
        items = result.get("value", [])
        for item in items:
            # Check if it's a folder with the exact matching name
            if item.get("name", "").strip().lower() == folder_name.strip().lower() and "folder" in item:
                return item["id"]
    else:
        logger.error(f"Search folder error")
    return None

def create_folder(access_token, folder_name):
    """
    Creates a folder in the root of the library. Returns its item ID if successful, else None.
    If the folder name already exists, it fails unless you change conflictBehavior.
    """
    url = f"{GRAPH_API_URL}/drives/{LIBRARY_ID}/root/children"
    data = {
        "name": folder_name,
        "folder": {},
        "@microsoft.graph.conflictBehavior": "fail"
    }
    result = GraphAPIClient.post(url, access_token, json_data=data, raise_on_error=False)
    if result:
        return result.get("id")
    else:
        error_message = f"Error creating folder '{folder_name}'"
        logger.error(error_message)
        raise Exception(error_message)

def update_folder_fields(access_token, folder_id, customer, rsm, opportunity_number, description):
    """
    Updates the custom fields (Customer, RSM, _ExtendedDescription) of the folder's listItem.
    The Description field now stores the opportunity number since the folder name contains the description.
    """
    url = f"{GRAPH_API_URL}/drives/{LIBRARY_ID}/items/{folder_id}/listItem/fields"
    data = {
        FIELD_CUSTOMER: customer,
        FIELD_RSM: rsm,
        FIELD_DESCRIPTION: opportunity_number  # Store opportunity number in the Description field
    }
    result = GraphAPIClient.patch(url, access_token, json_data=data, raise_on_error=False)
    if result:
        logger.info(f"Updated SharePoint fields for folder ID {folder_id}")
    else:
        logger.error(f"Error updating folder fields ID {folder_id}")


def create_sharepoint_folder(opportunity_number, customer, rsm, description):
    """
    Creates a folder named after the description (with opportunity number appended) in the SharePoint library.
    If it doesn't exist, creates it and sets fields. Then creates subfolders within it.
    """
    try:
        # Import folder utilities
        from samples.utils.folder_utils import get_sharepoint_folder_name_simple
        
        access_token = get_access_token()
        
        # Generate folder name from description
        folder_name = get_sharepoint_folder_name_simple(description, opportunity_number)
        logger.info(f"Creating/checking SharePoint folder: '{folder_name}' for opportunity {opportunity_number}")
        
        # 1) Check if the folder exists
        existing_folder_id = search_folder(access_token, folder_name)
        if existing_folder_id:
            logger.info(f"Folder '{folder_name}' already exists on SharePoint.")
            parent_folder_id = existing_folder_id
        else:
            # 2) Create the opportunity folder with the new name
            parent_folder_id = create_folder(access_token, folder_name)
            if parent_folder_id:
                # 3) Update the custom fields (now includes opportunity number)
                update_folder_fields(access_token, parent_folder_id, customer, rsm, opportunity_number, description)
            else:
                logger.error(f"Failed to create opportunity folder '{folder_name}'.")
                raise Exception(f"Failed to create opportunity folder '{folder_name}'.")

        create_subfolder(access_token, parent_folder_id, 'Samples')
        create_subfolder(access_token, parent_folder_id, 'Pics and Vids')
        create_subfolder(access_token, parent_folder_id, 'Modeling')

    except Exception as e:
        logger.error(f"SharePoint folder creation failed for opportunity {opportunity_number}: {e}")
        raise
