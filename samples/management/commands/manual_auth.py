from django.core.management.base import BaseCommand
import logging
from ManualAuth import manual_authenticate

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Manually obtain a new access token via device flow and save it to the token cache."

    def handle(self, *args, **options):
        try:
            token = manual_authenticate()
            self.stdout.write(self.style.SUCCESS(f"Access token: {token}"))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error: {str(e)}"))
