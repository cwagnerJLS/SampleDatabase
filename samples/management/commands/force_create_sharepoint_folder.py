from django.core.management.base import BaseCommand, CommandError
from samples.CreateOppFolderSharepoint import create_sharepoint_folder

class Command(BaseCommand):
    help = "Force the creation of a SharePoint folder for the given opportunity number, with custom fields."

    def add_arguments(self, parser):
        parser.add_argument('opportunity_number', type=str, help="Opportunity number")
        parser.add_argument('--customer', '-c', type=str, default='', help="Optional customer name")
        parser.add_argument('--rsm', '-r', type=str, default='', help="Optional RSM name")
        parser.add_argument('--description', '-d', type=str, default='', help="Optional description")

    def handle(self, *args, **options):
        opportunity_number = options['opportunity_number']
        customer = options['customer']
        rsm = options['rsm']
        description = options['description']
        try:
            create_sharepoint_folder(opportunity_number, customer, rsm, description)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully created (or found) folder for '{opportunity_number}'."
                )
            )
        except Exception as e:
            raise CommandError(
                f"Error creating folder for '{opportunity_number}': {e}"
            )
