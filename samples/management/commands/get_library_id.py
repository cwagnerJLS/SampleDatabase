import requests
import logging
from django.core.management.base import BaseCommand
from samples.CreateOppFolderSharepoint import get_access_token

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Returns the SharePoint library ID for the 'salesengineering' site."

    def handle(self, *args, **options):
        access_token = get_access_token()
        site_url = "https://graph.microsoft.com/v1.0/sites/jlsautomation.sharepoint.com:/sites/salesengineering"
        headers = {"Authorization": f"Bearer {access_token}"}

        # Get the site details
        site_resp = requests.get(site_url, headers=headers)
        if site_resp.status_code != 200:
            self.stderr.write(f"Failed to get site info: {site_resp.status_code} - {site_resp.text}")
            return

        site_data = site_resp.json()
        site_id = site_data["id"]

        # Fetch all drives (document libraries) for this site
        drives_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives"
        drives_resp = requests.get(drives_url, headers=headers)
        if drives_resp.status_code != 200:
            self.stderr.write(f"Failed to get drives: {drives_resp.status_code} - {drives_resp.text}")
            return

        # Print all drive names and IDs
        drives_data = drives_resp.json().get("value", [])
        for drive in drives_data:
            self.stdout.write(f"Drive Name: {drive['name']}, ID: {drive['id']}")
