import requests
from msal import PublicClientApplication
from samples.token_cache_utils import get_token_cache
import os
import logging

logger = logging.getLogger(__name__)

# Configuration

def get_cell_value(access_token, library_id, file_id, worksheet_name, cell_address):
    endpoint = (
        f"https://graph.microsoft.com/v1.0/drives/{library_id}/items/{file_id}"
        f"/workbook/worksheets/{worksheet_name}/range(address='{cell_address}')"
    )
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(endpoint, headers=headers)

    if response.status_code == 200:
        logger.info(f"Cell {cell_address} updated successfully.")
        data = response.json()
        values = data.get('values', [[]])
        if values and values[0]:
            return values[0][0]
    else:
        print(f"Failed to get cell value: {response.status_code}, {response.text}")
    return None

def get_existing_ids_with_rows(access_token, library_id, file_id, worksheet_name, start_row=8):
    range_address = f"A{start_row}:B5000"
    endpoint = (
        f"https://graph.microsoft.com/v1.0/drives/{library_id}/items/{file_id}"
        f"/workbook/worksheets/{worksheet_name}/range(address='{range_address}')"
    )
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(endpoint, headers=headers)

    existing_ids = {}
    if response.status_code == 200:
        data = response.json()
        values = data.get('values', [])
        for idx, row in enumerate(values):
            current_row_number = start_row + idx
            if row and len(row) > 0 and row[0]:  # Check if the cell is not empty or None
                existing_ids[str(row[0])] = current_row_number
    else:
        print(f"Failed to get existing IDs: {response.status_code}, {response.text}")
    return existing_ids

import re

def delete_rows_in_workbook(access_token, library_id, file_id, worksheet_name, row_numbers):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    for row_num in sorted(row_numbers, reverse=True):  # Process rows in reverse order
        range_address = f"A{row_num}:B{row_num}"
        endpoint = (
            f"https://graph.microsoft.com/v1.0/drives/{library_id}/items/{file_id}"
            f"/workbook/worksheets/{worksheet_name}/range(address='{range_address}')/clear"
        )
        data = {
            "applyTo": "contents"
        }
        response = requests.post(endpoint, headers=headers, json=data)
        if response.status_code == 200:
            logger.info(f"Cleared cells in range {range_address}.")
        else:
            logger.error(f"Failed to clear range {range_address}: {response.status_code}, {response.text}")

def append_rows_to_workbook(access_token, library_id, file_id, worksheet_name, start_cell, rows):
    """
    Update a specific range in an Excel worksheet with the provided rows.
    """
    # Calculate the end cell based on the number of rows and columns
    num_rows = len(rows)
    num_cols = len(rows[0]) if rows else 0
    if num_cols == 0:
        logger.error("No columns to append.")
        return

    # Get start cell row and column
    match = re.match(r"([A-Z]+)(\d+)", start_cell)
    if not match:
        logger.error(f"Invalid start cell address: {start_cell}")
        return
    start_col_letters, start_row_number = match.groups()
    start_row_number = int(start_row_number)

    # Compute end row number
    end_row_number = start_row_number + num_rows - 1

    # Compute end column letter(s)
    def col_num_to_letters(n):
        result = ''
        while n > 0:
            n, remainder = divmod(n - 1, 26)
            result = chr(65 + remainder) + result
        return result

    # Convert start column letters to number
    start_col_num = sum(
        [(ord(char) - ord('A') + 1) * (26 ** idx)
         for idx, char in enumerate(reversed(start_col_letters))]
    )
    end_col_num = start_col_num + num_cols - 1
    end_col_letters = col_num_to_letters(end_col_num)

    # Build the range address
    range_address = f"{start_col_letters}{start_row_number}:{end_col_letters}{end_row_number}"
    logger.debug(f"Calculated range address: {range_address}")

    endpoint = (
        f"https://graph.microsoft.com/v1.0/drives/{library_id}/items/{file_id}"
        f"/workbook/worksheets/{worksheet_name}/range(address='{range_address}')"
    )

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    data = {
        "values": rows
    }

    response = requests.patch(endpoint, headers=headers, json=data)

    if response.status_code == 200:
        logger.info(f"Rows appended successfully to range {range_address}.")
    else:
        logger.error(f"Failed to append rows: {response.status_code}, {response.text}")
        logger.debug(f"Response content: {response.content}")
CLIENT_ID = "a6122249-68bf-479a-80b8-68583aba0e91"  # Azure AD App Client ID
TENANT_ID = "f281e9a3-6598-4ddc-adca-693183c89477"  # Azure AD Tenant ID
USERNAME = "cwagner@jlsautomation.com"             # Service Account Email

def get_access_token():
    """
    Acquire an access token using MSAL with a token cache and device code flow.
    """
    logger.debug("Attempting to acquire access token.")
    cache = get_token_cache()

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
            return result["access_token"]

    # If silent acquisition fails, initiate device code flow
    flow = app.initiate_device_flow(scopes=scopes)
    if "user_code" not in flow:
        raise Exception("Device flow initiation failed. Check your app registration.")

    print(flow["message"])
    result = app.acquire_token_by_device_flow(flow)

    if "access_token" in result:
        logger.debug("Access token acquired successfully.")
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
    logger.debug(f"Finding Excel file for opportunity_number: {opportunity_number}")
    folder_path = f"{opportunity_number}/Samples"
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
        value (ystr): The value to write to the cell.
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

def clear_range_in_workbook(access_token, library_id, file_id, worksheet_name, range_address):
    endpoint = (
        f"https://graph.microsoft.com/v1.0/drives/{library_id}/items/{file_id}"
        f"/workbook/worksheets/{worksheet_name}/range(address='{range_address}')/clear"
    )
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    data = {
        "applyTo": "contents"
    }
    response = requests.post(endpoint, headers=headers, json=data)

    if response.status_code == 200:
        logger.info(f"Cleared range {range_address} successfully.")
    else:
        logger.error(f"Failed to clear range {range_address}: {response.status_code}, {response.text}")

def update_range_in_workbook(access_token, library_id, file_id, worksheet_name, start_row, values, row_numbers=None):
    num_rows = len(values)
    num_cols = len(values[0]) if values else 0
    if num_cols == 0:
        logger.error("No columns to update.")
        return

    end_row = start_row + num_rows - 1
    end_col_letter = chr(ord('A') + num_cols - 1)  # Assuming columns A-Z

    range_address = f"A{start_row}:{end_col_letter}{end_row}"
    logger.debug(f"Calculated range address for update: {range_address}")

    endpoint = (
        f"https://graph.microsoft.com/v1.0/drives/{library_id}/items/{file_id}"
        f"/workbook/worksheets/{worksheet_name}/range(address='{range_address}')"
    )

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    data = {
        "values": values
    }

    response = requests.patch(endpoint, headers=headers, json=data)

    if response.status_code == 200:
        logger.info(f"Range {range_address} updated successfully.")
    else:
        logger.error(f"Failed to update range {range_address}: {response.status_code}, {response.text}")
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    if row_numbers is None:
        row_numbers = []
    for row_num in sorted(row_numbers, reverse=True):  # Process rows in reverse order
        range_address = f"A{row_num}:B{row_num}"
        endpoint = (
            f"https://graph.microsoft.com/v1.0/drives/{library_id}/items/{file_id}"
            f"/workbook/worksheets/{worksheet_name}/range(address='{range_address}')/clear"
        )
        data = {
            "applyTo": "contents"
        }
        response = requests.post(endpoint, headers=headers, json=data)
        if response.status_code == 200:
            logger.info(f"Cleared cells in range {range_address}.")
        else:
            logger.error(f"Failed to clear range {range_address}: {response.status_code}, {response.text}")
def update_row_in_workbook(access_token, library_id, file_id, worksheet_name, start_cell, row_data):
    num_cols = len(row_data)
    end_col_letter = chr(ord('A') + num_cols - 1)  # Assuming columns start at 'A'
    row_number = re.findall(r'\d+', start_cell)[0]

    range_address = f"A{row_number}:{end_col_letter}{row_number}"
    logger.debug(f"Updating row at range: {range_address}")

    endpoint = (
        f"https://graph.microsoft.com/v1.0/drives/{library_id}/items/{file_id}"
        f"/workbook/worksheets/{worksheet_name}/range(address='{range_address}')"
    )

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    data = {
        "values": [row_data]
    }

    response = requests.patch(endpoint, headers=headers, json=data)
    if response.status_code == 200:
        logger.info(f"Row updated successfully at range {range_address}.")
    else:
        logger.error(f"Failed to update row at range {range_address}: {response.status_code}, {response.text}")
