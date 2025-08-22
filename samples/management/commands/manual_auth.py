from django.core.management.base import BaseCommand
import logging
from msal import PublicClientApplication
from samples.token_cache_utils import get_token_cache
from samples.sharepoint_config import (
    AZURE_CLIENT_ID as CLIENT_ID,
    AZURE_TENANT_ID as TENANT_ID,
    AZURE_USERNAME as USERNAME,
    AZURE_AUTHORITY,
    SHAREPOINT_SCOPES,
    is_configured
)

# identical to the helper we used elsewhere
def manual_authenticate():
    if not is_configured():
        raise Exception("Configuration error: Required environment variables are not set")
    
    cache = get_token_cache()
    app = PublicClientApplication(
        CLIENT_ID,
        authority=AZURE_AUTHORITY,
        token_cache=cache,
    )
    scopes = SHAREPOINT_SCOPES
    accounts = app.get_accounts(username=USERNAME)
    if accounts:
        result = app.acquire_token_silent(scopes, account=accounts[0])
        if result and "access_token" in result:
            return result["access_token"]

    flow = app.initiate_device_flow(scopes=scopes)
    if "user_code" not in flow:
        raise Exception("Device-flow initiation failed.")
    print(flow["message"])
    result = app.acquire_token_by_device_flow(flow)
    if "access_token" in result:
        return result["access_token"]
    raise Exception("Authentication failed.")

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Manually obtain a new access token via device flow and save it to the token cache."

    def handle(self, *args, **options):
        try:
            token = manual_authenticate()
            self.stdout.write(self.style.SUCCESS(f"Access token: {token}"))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error: {str(e)}"))
