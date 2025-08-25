import os
import requests
import logging
from django.conf import settings
from samples.sharepoint_config import (
    TEST_ENGINEERING_LIBRARY_ID as LIBRARY_ID,
    GRAPH_API_URL,
    is_configured
)
from samples.services.auth_service import get_sharepoint_token

# Define the path to Hyperlinks.csv using BASE_DIR
HYPERLINKS_CSV_FILE = os.path.join(settings.BASE_DIR, 'Hyperlinks.csv')

logger = logging.getLogger(__name__)

import django

if not settings.configured:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.settings')
    django.setup()

# Internal SharePoint field names for your custom columns
FIELD_CUSTOMER = "Customer"
FIELD_RSM = "RSM"
FIELD_DESCRIPTION = "_ExtendedDescription"  # 'Description' column is '_ExtendedDescription' internally
def create_subfolder(access_token, parent_folder_id, subfolder_name):
    """
    Creates a subfolder within the specified parent folder.
    """
    url = f"{GRAPH_API_URL}/drives/{LIBRARY_ID}/items/{parent_folder_id}/children"
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
        logger.info(f"Created subfolder '{subfolder_name}' in folder ID {parent_folder_id}")
    else:
        logger.error(f"Error creating subfolder '{subfolder_name}' in folder ID {parent_folder_id}: {resp.status_code}, {resp.text}")

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
    url = f"{GRAPH_API_URL}/drives/{LIBRARY_ID}/root/children"
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
    url = f"{GRAPH_API_URL}/drives/{LIBRARY_ID}/items/{folder_id}/listItem/fields"
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

        create_subfolder(access_token, parent_folder_id, 'Samples')
        create_subfolder(access_token, parent_folder_id, 'Pics and Vids')
        create_subfolder(access_token, parent_folder_id, 'Modeling')

    except Exception as e:
        logger.error(f"SharePoint folder creation failed for {opportunity_number}: {e}")
        raise
