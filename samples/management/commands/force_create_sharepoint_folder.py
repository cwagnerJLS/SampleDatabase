from django.core.management.base import BaseCommand, CommandError
from samples.CreateOppFolderSharepoint import create_sharepoint_folder
import logging

logger = logging.getLogger(__name__)
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
        logger.debug("Reading Excel file from: %s", excel_file)
        if not os.path.exists(excel_file):
            raise CommandError(f"Excel file not found at {excel_file}")

        # Read the Excel file without assuming headers, then rename columns
        df = pd.read_excel(excel_file, header=None)
        # A=Customer, B=RSM, C=OpportunityNumber, D=Description, E=AppsEng
        df.columns = ['Customer','RSM','OpportunityNumber','Description','AppsEng']

        # Filter rows matching the opportunity_number in col C
        row = df.loc[df['OpportunityNumber'] == opportunity_number]
        logger.debug("OpportunityNumber=%s: Found row => %s", opportunity_number, row.to_dict('records'))
        if row.empty:
            raise CommandError(f"No matching row for '{opportunity_number}' in the Excel file.")

        customer = str(row.iloc[0]['Customer'])
        rsm = str(row.iloc[0]['RSM'])
        description = str(row.iloc[0]['Description'])
        apps_eng = str(row.iloc[0]['AppsEng'])  # This is column E, adjust usage as desired
        logger.debug("Customer=%s, RSM=%s, Description=%s, AppsEng=%s", customer, rsm, description, apps_eng)
        try:
            logger.debug("Calling create_sharepoint_folder with arguments: (%s, %s, %s, %s)",
                         opportunity_number, customer, rsm, description)
            create_sharepoint_folder(opportunity_number, customer, rsm, description)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully created (or found) folder for '{opportunity_number}'."
                )
            )
        except Exception as e:
            logger.exception("Exception occurred while creating folder")
            raise CommandError(
                f"Error creating folder for '{opportunity_number}': {e}"
            )
