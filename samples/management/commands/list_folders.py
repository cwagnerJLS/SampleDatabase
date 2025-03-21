import requests
import logging
from django.core.management.base import BaseCommand
from samples.CreateOppFolderSharepoint import get_access_token

logger = logging.getLogger(__name__)

LIBRARY_ID = "b!AHIiPEiCJkSW7XmvcLmNUCmbMxhox6RHsHtOxuUGv88LSiuU7CeQS5URlOUmuH5w"

class Command(BaseCommand):
    help = "Lists all top-level folders in the SharePoint library."

    def handle(self, *args, **options):
        access_token = get_access_token()
        headers = {"Authorization": f"Bearer {access_token}"}

        # Get all child items in the root of the library
        root_children_url = f"https://graph.microsoft.com/v1.0/drives/{LIBRARY_ID}/root/children"
        response = requests.get(root_children_url, headers=headers)
        if response.status_code != 200:
            self.stderr.write(f"Failed to retrieve items: {response.status_code} - {response.text}")
            return

        items = response.json().get("value", [])
        if not items:
            self.stdout.write("No items found in the root of this library.")
            return

        # Print only items that are folders
        for item in items:
            if "folder" in item:
                folder_name = item.get("name", "UnnamedFolder")
                folder_id = item.get("id", "UnknownID")
                self.stdout.write(f"Folder Name: {folder_name}, ID: {folder_id}")
