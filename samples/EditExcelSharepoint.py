import requests
from msal import PublicClientApplication
import os

# Configuration

def get_cell_value(access_token, library_id, file_id, worksheet_name, cell_address):
    endpoint = (
        f"https://graph.microsoft.com/v1.0/drives/{library_id}/items/{file_id}"
        f"/workbook/worksheets/{worksheet_name}/range(address='{cell_address}')"
    )
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(endpoint, headers=headers)

    if response.status_code == 200:
        data = response.json()
        values = data.get('values', [[]])
        if values and values[0]:
            return values[0][0]
    else:
        print(f"Failed to get cell value: {response.status_code}, {response.text}")
    return None

def get_existing_ids_from_workbook(access_token, library_id, file_id, worksheet_name, start_row=8):
    range_address = f"A{start_row}:B5000"
    endpoint = (
        f"https://graph.microsoft.com/v1.0/drives/{library_id}/items/{file_id}"
        f"/workbook/worksheets/{worksheet_name}/range(address='{range_address}')"
    )
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(endpoint, headers=headers)

    existing_ids = set()
    if response.status_code == 200:
        data = response.json()
        values = data.get('values', [])
        for row in values:
            if row and len(row) > 0:
                existing_ids.add(str(row[0]))
    else:
        print(f"Failed to get existing IDs: {response.status_code}, {response.text}")
    return existing_ids

def append_rows_to_workbook(access_token, library_id, file_id, worksheet_name, start_cell, rows):
    endpoint = (
        f"https://graph.microsoft.com/v1.0/drives/{library_id}/items/{file_id}"
        f"/workbook/worksheets/{worksheet_name}/range(address='{start_cell}')/insert"
    )
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    data = {
        "shift": "Down",
        "values": rows
    }
    response = requests.post(endpoint, headers=headers, json=data)
    if response.status_code == 200:
        print(f"Rows appended successfully.")
    else:
        print(f"Failed to append rows: {response.status_code}, {response.text}")
CLIENT_ID = "a6122249-68bf-479a-80b8-68583aba0e91"  # Azure AD App Client ID
TENANT_ID = "f281e9a3-6598-4ddc-adca-693183c89477"  # Azure AD Tenant ID
USERNAME = "cwagner@jlsautomation.com"             # Service Account Email
TOKEN_CACHE_FILE = "token_cache.json"

def load_token_cache():
    """
    Load the token cache from a JSON file.
    """
    from msal import SerializableTokenCache
    cache = SerializableTokenCache()
    if os.path.exists(TOKEN_CACHE_FILE):
        with open(TOKEN_CACHE_FILE, "r") as f:
            cache.deserialize(f.read())
    return cache

def save_token_cache(cache):
    """
    Save the token cache to a JSON file.
    """
    if cache.has_state_changed:
        with open(TOKEN_CACHE_FILE, "w") as f:
            f.write(cache.serialize())

def get_access_token():
    """
    Acquire an access token using MSAL with a token cache and device code flow.
    """
    cache = load_token_cache()

    app = PublicClientApplication(
        CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        token_cache=cache
    )

    # Required scopes for accessing SharePoint/Excel
    scopes = ["Sites.ReadWrite.All", "Files.ReadWrite.All"]

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

    print(flow["message"])
    result = app.acquire_token_by_device_flow(flow)

    if "access_token" in result:
        save_token_cache(app.token_cache)
        return result["access_token"]

    raise Exception("Authentication failed.")

def find_excel_file(access_token, library_id, opportunity_number):
    """
    Find the Excel file for a specific opportunity number in the Test Engineering library.
    The folder name matches the 4-digit opportunity number, and the file is named
    'Documentation_<OpportunityNumber>.xlsm'.

    Args:
        access_token (str): Access token from Microsoft Graph.
        library_id (str): The ID (drive ID) of the Test Engineering library.
        opportunity_number (str): The 4-digit opportunity number.

    Returns:
        str or None: The item ID of the Excel file if found, else None.
    """
    folder_path = opportunity_number
    endpoint = f"https://graph.microsoft.com/v1.0/drives/{library_id}/root:/{folder_path}:/children"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(endpoint, headers=headers)

    if response.status_code == 200:
        items = response.json().get("value", [])
        print(f"Items in folder '{folder_path}':")
        for item in items:
            item_name = item['name']
            item_id = item['id']
            is_folder = "Folder" if item.get('folder') else "File"
            print(f"- {item_name} (ID: {item_id}, Type: {is_folder})")

            expected_filename = f"Documentation_{opportunity_number}.xlsm"
            if item_name == expected_filename:
                print(f"Found Excel file: {item_name} (ID: {item_id})")
                return item_id

        print(f"No Excel file named 'Documentation_{opportunity_number}.xlsm' found in folder '{folder_path}'.")
    else:
        print(f"Failed to access folder '{folder_path}': {response.status_code}, {response.text}")

    return None

def list_worksheets(access_token, library_id, file_id):
    """
    List worksheets in an Excel file to confirm it's recognized by the Microsoft Graph Excel API.

    Args:
        access_token (str): Access token from Microsoft Graph.
        library_id (str): The ID (drive ID) of the Test Engineering library.
        file_id (str): The item ID of the Excel file within that drive.

    Returns:
        list or None: List of worksheets (dicts with 'id' and 'name') if successful, else None.
    """
    endpoint = f"https://graph.microsoft.com/v1.0/drives/{library_id}/items/{file_id}/workbook/worksheets"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(endpoint, headers=headers)

    if response.status_code == 200:
        data = response.json()
        worksheets = data.get("value", [])
        print("Worksheets found:")
        for ws in worksheets:
            print(f"- {ws['name']} (ID: {ws['id']})")
        return worksheets
    else:
        print(f"Failed to list worksheets: {response.status_code}, {response.text}")
        return None

def update_cell_value(access_token, library_id, file_id, worksheet_name, cell_address, value):
    """
    Update a specific cell in an Excel worksheet using the Microsoft Graph Excel API.
    For a basic sheet name like 'Sheet1' (no spaces or special chars), do NOT surround it with quotes.

    Args:
        access_token (str): Access token from Microsoft Graph.
        library_id (str): Drive (library) ID for "Test Engineering".
        file_id (str): The ID of the Excel file (item ID within that drive).
        worksheet_name (str): The name of the worksheet to edit (e.g., "Sheet1").
        cell_address (str): The address of the cell to edit (e.g., "A8").
        value (str): The value to write to the cell.
    """
    endpoint = (
        f"https://graph.microsoft.com/v1.0/drives/{library_id}/items/{file_id}/workbook/"
        f"worksheets/{worksheet_name}/range(address='{cell_address}')"
    )
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    body = {
        "values": [[value]]  # Graph API expects a 2D array for Excel values
    }

    response = requests.patch(endpoint, headers=headers, json=body)
    if response.status_code == 200:
        print(f"Cell {cell_address} updated successfully to '{value}'.")
    else:
        print(f"Failed to update cell {cell_address}: {response.status_code}, {response.text}")

if __name__ == "__main__":
    try:
        # 1. Acquire an access token
        token = get_access_token()

        # 2. Specify the library (drive) ID for "Test Engineering"
        library_id = "b!X3Eb6X7EmkGXMLnZD4j_mJuFfGH0APlLs0IrZrwqabH6SO1yJ5v6TYCHXT-lTWgj"

        # 3. Define the opportunity number
        opportunity_number = "7124"

        # 4. Locate the Excel file (item ID)
        excel_file_id = find_excel_file(token, library_id, opportunity_number)
        if not excel_file_id:
            print("Excel file not found. Cannot proceed.")
            exit()

        # 5. List worksheets to confirm the file is recognized as an Excel workbook
        worksheets = list_worksheets(token, library_id, excel_file_id)
        if not worksheets:
            print("No worksheets found or file not recognized by the Excel API.")
            exit()

        # For demonstration, we assume "Sheet1" is the correct worksheet name
        worksheet_name = "Sheet1"

        # 6. Update cell A8 to "5678"
        update_cell_value(
            access_token=token,
            library_id=library_id,
            file_id=excel_file_id,
            worksheet_name=worksheet_name,
            cell_address="A8",
            value="5678"
        )

    except Exception as e:
        print(f"Error: {e}")
