import requests
from msal import PublicClientApplication
import os
import logging

logger = logging.getLogger(__name__)

# Constants
CLIENT_ID = "a6122249-68bf-479a-80b8-68583aba0e91"  # Azure AD App Client ID
TENANT_ID = "f281e9a3-6598-4ddc-adca-693183c89477"  # Azure AD Tenant ID
USERNAME = "cwagner@jlsautomation.com"             # Service Account Email
TOKEN_CACHE_FILE = "token_cache.json"
LIBRARY_ID = "b!X3Eb6X7EmkGXMLnZD4j_mJuFfGH0APlLs0IrZrwqabH6SO1yJ5v6TYCHXT-lTWgj"

# Token management functions
def load_token_cache():
    from msal import SerializableTokenCache
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
        CLIENT_ID,
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

# Find a folder by name in the document library
def find_folder(access_token, library_id):
    url = f"https://graph.microsoft.com/v1.0/drives/{library_id}/root/children"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        items = response.json().get("value", [])
        print("Items in library:")
        for item in items:
            print(f"Name: {item['name']}, ID: {item['id']}")
            if "folder" in item:
                return item["id"]
    else:
        print(f"Error: {response.status_code}, {response.text}")
    return None


# Update custom fields for a folder
def update_folder_fields(access_token, library_id, folder_id, customer, rsm, description):
    url = f"https://graph.microsoft.com/v1.0/sites/root/drives/{library_id}/items/{folder_id}/fields"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
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

# Main logic
def main():
    folder_name = "Test"  # Replace with the folder name
    customer = "Updated Customer"
    rsm = "Updated RSM"
    description = "Updated Description"

    try:
        access_token = get_access_token()
        folder_id = find_folder(access_token, LIBRARY_ID, folder_name)
        if folder_id:
            logger.info(f"Found folder: {folder_id}")
            update_folder_fields(access_token, LIBRARY_ID, folder_id, customer, rsm, description)
        else:
            print(f"Folder '{folder_name}' not found.")
    except Exception as e:
        logger.error(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
