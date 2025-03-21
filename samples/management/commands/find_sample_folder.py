import requests
import logging
from collections import deque
from django.core.management.base import BaseCommand
from samples.CreateOppFolderSharepoint import get_access_token, LIBRARY_ID

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Finds the 'Sample Info' folder for a given customer/opportunity inside the lettered folder structure."

    def add_arguments(self, parser):
        parser.add_argument('--customer_name', required=True, help='Customer name (e.g. "Campbell Snacks")')
        parser.add_argument('--opportunity_number', required=True, help='4-digit opportunity number (e.g. "8076")')

    def handle(self, *args, **options):
        customer_name = options['customer_name']
        opportunity_number = options['opportunity_number']

        # Use the first letter of the customer name (uppercase)
        letter_folder_name = customer_name[0].upper()

        access_token = get_access_token()
        headers = {"Authorization": f"Bearer {access_token}"}

        # 1) Find the letter folder in the root
        letter_folder_id = self.find_folder_by_name(LIBRARY_ID, None, letter_folder_name, headers)
        if not letter_folder_id:
            self.stderr.write(f"Folder '{letter_folder_name}' not found in the root of this library.")
            return

        # 2) Within the letter folder, find a folder containing the opportunity_number, possibly nested
        opp_folder_id = self.find_folder_containing(LIBRARY_ID, letter_folder_id, opportunity_number, headers)
        if not opp_folder_id:
            self.stderr.write(f"No folder found containing '{opportunity_number}' within '{letter_folder_name}'!")
            return

        # 3) Inside that folder, find "1 Info", then "Sample Info"
        info_folder_id = self.find_folder_by_name(LIBRARY_ID, opp_folder_id, "1 Info", headers)
        if not info_folder_id:
            self.stderr.write(f"No '1 Info' folder found inside folder containing '{opportunity_number}'.")
            return

        sample_info_folder_id = self.find_folder_by_name(LIBRARY_ID, info_folder_id, "Sample Info", headers)
        if not sample_info_folder_id:
            self.stderr.write(f"No 'Sample Info' folder found inside '1 Info'.")
            return

        # 4) Retrieve the webUrl for the found folder
        folder_details_url = f"https://graph.microsoft.com/v1.0/drives/{LIBRARY_ID}/items/{sample_info_folder_id}"
        resp = requests.get(folder_details_url, headers=headers)
        if resp.status_code != 200:
            self.stderr.write(f"Failed to get folder details: {resp.status_code} - {resp.text}")
            return
        folder_data = resp.json()
        web_url = folder_data.get("webUrl", "No URL provided")

        self.stdout.write(f"Found 'Sample Info' folder at: {web_url}")

    def find_folder_by_name(self, drive_id, parent_id, folder_name, headers):
        """
        Searches only the direct children of the specified folder (or root if parent_id is None)
        for a folder with an exact matching name. Returns the folder ID if found, else None.
        """
        if parent_id:
            children_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{parent_id}/children"
        else:
            # Root
            children_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root/children"

        resp = requests.get(children_url, headers=headers)
        if resp.status_code != 200:
            logger.error(f"Failed to get children for folder {parent_id}: {resp.status_code}, {resp.text}")
            return None

        items = resp.json().get("value", [])
        for item in items:
            if "folder" in item and item.get("name", "").strip().lower() == folder_name.strip().lower():
                return item["id"]
        return None

    def find_folder_containing(self, drive_id, start_folder_id, substring, headers):
        """
        Performs a BFS search from start_folder_id looking for a folder whose name contains substring.
        Returns the first matching folder ID found, or None if not found.
        """
        queue = deque([start_folder_id])
        while queue:
            current_folder_id = queue.popleft()

            # Get children of the current folder
            url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{current_folder_id}/children"
            resp = requests.get(url, headers=headers)
            if resp.status_code != 200:
                logger.error(f"Failed to get children of {current_folder_id}: {resp.status_code}, {resp.text}")
                continue

            children = resp.json().get("value", [])
            for child in children:
                if "folder" in child:
                    # Check if child name contains the substring
                    name_lower = child.get("name", "").lower()
                    if substring.lower() in name_lower:
                        return child["id"]
                    # Otherwise, add folder to the queue to keep searching
                    queue.append(child["id"])
        return None
