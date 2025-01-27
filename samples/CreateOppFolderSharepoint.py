import os
import csv
import requests
import logging
from msal import PublicClientApplication, SerializableTokenCache
from django.conf import settings

# Define the path to Hyperlinks.csv using BASE_DIR
HYPERLINKS_CSV_FILE = os.path.join(settings.BASE_DIR, 'Hyperlinks.csv')

logger = logging.getLogger(__name__)

import os
import django
from django.conf import settings

if not settings.configured:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.settings')
    django.setup()
# 1) CONFIGURATION CONSTANTS
def create_subfolder(access_token, parent_folder_id, subfolder_name):
    """
    Creates a subfolder within the specified parent folder.
    """
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
        logger.info(f"Created subfolder '{subfolder_name}' in folder ID {parent_folder_id}")
    else:
        logger.error(f"Error creating subfolder '{subfolder_name}' in folder ID {parent_folder_id}: {resp.status_code}, {resp.text}")
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

def update_hyperlinks_csv(opportunity_number, web_url):
    """
    Updates the Hyperlinks.csv file with the opportunity number and web URL.
    If the opportunity number already exists, it updates the URL.
    """
    try:
        # Ensure the CSV file exists. If not, create it with headers.
        if not os.path.exists(HYPERLINKS_CSV_FILE):
            with open(HYPERLINKS_CSV_FILE, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['OpportunityNumber', 'Hyperlink'])

        # Read existing entries
        rows = []
        exists = False
        with open(HYPERLINKS_CSV_FILE, 'r', newline='', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile)
            for row in reader:
                if row and row[0] == opportunity_number:
                    # Update the URL if the opportunity number exists
                    rows.append([opportunity_number, web_url])
                    exists = True
                else:
                    rows.append(row)

        if not exists:
            # Add new entry
            rows.append([opportunity_number, web_url])

        # Write back to CSV
        with open(HYPERLINKS_CSV_FILE, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerows(rows)

        logger.info(f"Updated Hyperlinks.csv with opportunity '{opportunity_number}' and link '{web_url}'")

    except Exception as e:
        logger.error(f"Failed to update Hyperlinks.csv: {e}")

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

        # 4) Retrieve the web URL and update Hyperlinks.csv
        folder_url = f"https://graph.microsoft.com/v1.0/drives/{LIBRARY_ID}/items/{parent_folder_id}"
        headers = {"Authorization": f"Bearer {access_token}"}
        resp = requests.get(folder_url, headers=headers)
        if resp.status_code == 200:
            folder_info = resp.json()
            web_url = folder_info.get('webUrl')
            if web_url:
                update_hyperlinks_csv(opportunity_number, web_url)
            else:
                logger.error(f"Failed to retrieve webUrl for folder '{opportunity_number}'.")
        else:
            logger.error(f"Failed to retrieve folder info for '{opportunity_number}': {resp.status_code}, {resp.text}")
        create_subfolder(access_token, parent_folder_id, 'Samples')
        create_subfolder(access_token, parent_folder_id, 'Pics and Vids')
        create_subfolder(access_token, parent_folder_id, 'Modeling')

    except Exception as e:
        logger.error(f"SharePoint folder creation failed for {opportunity_number}: {e}")
        raise
    """
    Updates the Hyperlinks.csv file with the opportunity number and web URL.
    If the opportunity number already exists, it updates the URL.
    """
    try:
        # Ensure the CSV file exists. If not, create it with headers.
        if not os.path.exists(HYPERLINKS_CSV_FILE):
            with open(HYPERLINKS_CSV_FILE, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['OpportunityNumber', 'Hyperlink'])

        # Read existing entries
        rows = []
        exists = False
        with open(HYPERLINKS_CSV_FILE, 'r', newline='', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile)
            for row in reader:
                if row and row[0] == opportunity_number:
                    # Update the URL if the opportunity number exists
                    rows.append([opportunity_number, web_url])
                    exists = True
                else:
                    rows.append(row)

        if not exists:
            # Add new entry
            rows.append([opportunity_number, web_url])

        # Write back to CSV
        with open(HYPERLINKS_CSV_FILE, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerows(rows)

        logger.info(f"Updated Hyperlinks.csv with opportunity '{opportunity_number}' and link '{web_url}'")

    except Exception as e:
        logger.error(f"Failed to update Hyperlinks.csv: {e}")
