#!/usr/bin/env python

import os
import logging
import requests
from msal import PublicClientApplication, SerializableTokenCache

# --------------------------------------------
# 1) DJANGO SETUP
#    Here we set DJANGO_SETTINGS_MODULE to 'inventory_system.settings'
# --------------------------------------------
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.settings')
import django
django.setup()

# Import your model(s)
from samples.models import Sample  # <--- Updated to match your 'samples' app's models.py

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# --------------------------------------------
# 2) MSAL / SHAREPOINT CONSTANTS
# --------------------------------------------
CLIENT_ID = "a6122249-68bf-479a-80b8-68583aba0e91"  # Azure AD App Client ID
TENANT_ID = "f281e9a3-6598-4ddc-adca-693183c89477"  # Azure AD Tenant ID
USERNAME = "cwagner@jlsautomation.com"             # Service Account Email
TOKEN_CACHE_FILE = "token_cache.json"

# The Drive (document library) ID
LIBRARY_ID = "b!X3Eb6X7EmkGXMLnZD4j_mJuFfGH0APlLs0IrZrwqabH6SO1yJ5v6TYCHXT-lTWgj"

# Internal SharePoint field names for your custom columns
FIELD_CUSTOMER = "Customer"
FIELD_RSM = "RSM"
FIELD_DESCRIPTION = "_ExtendedDescription"  # 'Description' column is '_ExtendedDescription' internally

# --------------------------------------------
# 3) DJANGO DATA ACCESS
# --------------------------------------------
def get_opportunity_details(opportunity_number):
    """
    Query the Sample model for a given opportunity_number.
    Return a dict with 'Customer', 'RSM', 'Description' or None if not found.
    """
    try:
        sample = Sample.objects.filter(opportunity_number=opportunity_number).first()
        if sample:
            return {
                "Customer": sample.customer or "",
                "RSM": sample.rsm or "",
                "Description": sample.description or "",
            }
        else:
            logger.info(f"No database record found for opportunity: {opportunity_number}")
            return None
    except Exception as e:
        logger.error(f"Database error for {opportunity_number}: {e}")
        return None

# --------------------------------------------
# 4) MSAL TOKEN CACHE LOGIC
# --------------------------------------------
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

# --------------------------------------------
# 5) LIST FOLDERS IN LIBRARY ROOT (WITH PAGINATION)
# --------------------------------------------
def list_all_folders_in_root(access_token, library_id):
    """
    Generator function to list folder items in the drive's root, handling pagination.
    """
    url = f"https://graph.microsoft.com/v1.0/drives/{library_id}/root/children"
    headers = {"Authorization": f"Bearer {access_token}"}

    while url:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            for item in data.get("value", []):
                # Only return folders
                if "folder" in item:
                    yield item
            url = data.get("@odata.nextLink")  # Go to next page if exists
        else:
            logger.error(f"Failed to list folders: {response.status_code}, {response.text}")
            break

# --------------------------------------------
# 6) UPDATE FOLDER FIELDS
# --------------------------------------------
def update_folder_fields(access_token, library_id, folder_id, customer, rsm, description):
    """
    PATCH the 'listItem/fields' endpoint with the correct internal names.
    """
    patch_url = f"https://graph.microsoft.com/v1.0/drives/{library_id}/items/{folder_id}/listItem/fields"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    data = {
        FIELD_CUSTOMER: customer,
        FIELD_RSM: rsm,
        FIELD_DESCRIPTION: description
    }

    resp = requests.patch(patch_url, headers=headers, json=data)
    if resp.status_code == 200:
        logger.info(
            f"Updated folder ID {folder_id} => "
            f"Customer='{customer}', RSM='{rsm}', Description='{description}'"
        )
    else:
        logger.error(f"Failed to update folder {folder_id}: {resp.status_code}, {resp.text}")

# --------------------------------------------
# 7) MAIN LOGIC
# --------------------------------------------
def main():
    try:
        access_token = get_access_token()
        folders = list_all_folders_in_root(access_token, LIBRARY_ID)

        for folder in folders:
            folder_name = folder["name"].strip()
            folder_id = folder["id"]

            logger.info(f"Processing folder: '{folder_name}' (ID: {folder_id})")

            # We assume folder_name matches opportunity_number in the DB
            details = get_opportunity_details(folder_name)
            if details:
                update_folder_fields(
                    access_token=access_token,
                    library_id=LIBRARY_ID,
                    folder_id=folder_id,
                    customer=details["Customer"],
                    rsm=details["RSM"],
                    description=details["Description"]
                )
            else:
                logger.info(f"No DB record for '{folder_name}'. Skipping update.")

    except Exception as e:
        logger.error(f"Error in main: {e}")

if __name__ == "__main__":
    main()
