from django.core.management.base import BaseCommand, CommandError
from samples.CreateOppFolderSharepoint import create_sharepoint_folder
import os
import pandas as pd
from django.conf import settings

class Command(BaseCommand):
    help = "Force the creation of a SharePoint folder for the given opportunity number, with custom fields."

    def add_arguments(self, parser):
        parser.add_argument('opportunity_number', type=str, help="Opportunity number")

    def handle(self, *args, **options):
        opportunity_number = options['opportunity_number']
        # Load Apps_Database.xlsx
        excel_file = os.path.join(settings.BASE_DIR, 'Apps_Database.xlsx')
        if not os.path.exists(excel_file):
            raise CommandError(f"Excel file not found at {excel_file}")

        # Read the Excel file without assuming headers, then rename columns
        df = pd.read_excel(excel_file, header=None)
        # A=Customer, B=Unused, C=OpportunityNumber, D=Description
        df.columns = ['Customer','_unused','OpportunityNumber','Description']

        # Filter rows matching the opportunity_number in col C
        row = df.loc[df['OpportunityNumber'] == opportunity_number]
        if row.empty:
            raise CommandError(f"No matching row for '{opportunity_number}' in the Excel file.")

        customer = str(row.iloc[0]['Customer'])
        description = str(row.iloc[0]['Description'])
        # We have no RSM column, so just pass an empty string
        rsm = ''
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
