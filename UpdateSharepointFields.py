import json
import requests
from msal import PublicClientApplication

# Constants
CLIENT_ID = "a6122249-68bf-479a-80b8-68583aba0e91"  # Azure AD App Client ID
TENANT_ID = "f281e9a3-6598-4ddc-adca-693183c89477"  # Azure AD Tenant ID
USERNAME = "cwagner@jlsautomation.com"  # Service Account Email
TOKEN_CACHE_FILE = "token_cache.json"  # Token cache file
GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
LIBRARY_ID = "b!X3Eb6X7EmkGXMLnZD4j_mJuFfGH0APlLs0IrZrwqabH6SO1yJ5v6TYCHXT-lTWgj"


# Function to authenticate and get an access token
def get_access_token():
    app = PublicClientApplication(
        client_id=CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        token_cache=TOKEN_CACHE_FILE
    )

    accounts = app.get_accounts()
    result = None

    if accounts:
        # Use the existing cached account
        result = app.acquire_token_silent(["https://graph.microsoft.com/.default"], account=accounts[0])

    if not result:
        print("Please authenticate with Microsoft")
        flow = app.initiate_device_flow(scopes=["https://graph.microsoft.com/.default"])
        print(flow["message"])
        result = app.acquire_token_by_device_flow(flow)

    if "access_token" not in result:
        raise Exception("Authentication failed")

    return result["access_token"]


# Function to find a folder in the document library
def find_folder(folder_name, access_token):
    url = f"{GRAPH_API_BASE}/drives/{LIBRARY_ID}/root/children"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        items = response.json().get("value", [])
        for item in items:
            if item["name"].lower() == folder_name.lower() and "folder" in item:
                return item["id"]  # Return the folder ID
    else:
        print(f"Error finding folder: {response.status_code} {response.text}")

    return None


# Function to update custom fields for a folder
def update_folder_fields(folder_id, access_token, customer, rsm, description):
    url = f"{GRAPH_API_BASE}/sites/root/drives/{LIBRARY_ID}/items/{folder_id}/fields"
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
        print(f"Error updating folder fields: {response.status_code} {response.text}")


# Main function
def main():
    folder_name = "Test"  # Replace with the name of the folder you want to update
    customer = "Customer Name"
    rsm = "RSM Name"
    description = "Updated Description"

    try:
        # Get access token
        access_token = get_access_token()

        # Find the folder
        folder_id = find_folder(folder_name, access_token)
        if folder_id:
            print(f"Folder found: {folder_id}")
            # Update the custom fields
            update_folder_fields(folder_id, access_token, customer, rsm, description)
        else:
            print("Folder not found.")
    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    main()
