from django.core.management.base import BaseCommand
import logging
from msal import PublicClientApplication
from samples.token_cache_utils import get_token_cache

CLIENT_ID  = "a6122249-68bf-479a-80b8-68583aba0e91"
TENANT_ID  = "f281e9a3-6598-4ddc-adca-693183c89477"
USERNAME   = "cwagner@jlsautomation.com"

# identical to the helper we used elsewhere
def manual_authenticate():
    cache = get_token_cache()
    app = PublicClientApplication(
        CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        token_cache=cache,
    )
    scopes = ["Sites.ReadWrite.All", "Files.ReadWrite.All"]
    accounts = app.get_accounts(username=USERNAME)
    if accounts:
        result = app.acquire_token_silent(scopes, account=accounts[0])
        if result and "access_token" in result:
            return result["access_token"]

    flow = app.initiate_device_flow(scopes=scopes)
    if "user_code" not in flow:
        raise Exception("Device-flow initiation failed.")
    self.stdout.write(flow["message"])
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
