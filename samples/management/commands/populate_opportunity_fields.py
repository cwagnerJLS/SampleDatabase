"""
Management command to populate missing opportunity fields from Apps_Database.xlsx
This will update customer, RSM, and description fields for all opportunities.
"""
import os
import pandas as pd
from django.core.management.base import BaseCommand
from django.conf import settings
from samples.models import Opportunity
from samples.sharepoint_config import get_apps_database_path

class Command(BaseCommand):
    help = 'Populate missing opportunity fields (customer, RSM, description) from Apps_Database.xlsx'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )
        parser.add_argument(
            '--opportunity',
            type=str,
            help='Update only a specific opportunity number',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        specific_opp = options.get('opportunity')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        # Load the Excel database
        apps_database_path = get_apps_database_path()
        if not os.path.exists(apps_database_path):
            self.stdout.write(self.style.ERROR(f'Apps_Database.xlsx not found at {apps_database_path}'))
            return
        
        self.stdout.write(f'Loading data from {apps_database_path}')
        df = pd.read_excel(apps_database_path)
        
        # Create a dictionary for quick lookup by opportunity number
        excel_data = {}
        for _, row in df.iterrows():
            opp_num = str(row.get('Opportunity #', '')).strip()
            if opp_num and opp_num.isdigit():
                excel_data[opp_num] = {
                    'customer': row.get('Customer', ''),
                    'rsm': row.get('RSM', ''),
                    'description': row.get('Description', ''),
                    'apps_engineer': row.get('Application Engineer', '')
                }
        
        self.stdout.write(f'Found {len(excel_data)} opportunities in Excel file')
        
        # Get opportunities to update
        if specific_opp:
            opportunities = Opportunity.objects.filter(opportunity_number=specific_opp)
            if not opportunities.exists():
                self.stdout.write(self.style.ERROR(f'Opportunity {specific_opp} not found in database'))
                return
        else:
            opportunities = Opportunity.objects.all()
        
        self.stdout.write(f'Processing {opportunities.count()} opportunities from database\n')
        
        # Track statistics
        updated_count = 0
        skipped_count = 0
        not_in_excel = 0
        
        for opportunity in opportunities:
            opp_num = opportunity.opportunity_number
            
            # Check if this opportunity exists in Excel
            if opp_num not in excel_data:
                self.stdout.write(self.style.WARNING(f'[{opp_num}] Not found in Excel file'))
                not_in_excel += 1
                continue
            
            excel_info = excel_data[opp_num]
            
            # Check what needs updating
            updates_needed = []
            
            # Check customer
            if not opportunity.customer or opportunity.customer == 'None':
                if excel_info['customer'] and str(excel_info['customer']) != 'nan':
                    updates_needed.append(('customer', excel_info['customer']))
            
            # Check RSM
            if not opportunity.rsm or opportunity.rsm == 'None':
                if excel_info['rsm'] and str(excel_info['rsm']) != 'nan':
                    updates_needed.append(('rsm', excel_info['rsm']))
            
            # Check description
            if not opportunity.description or opportunity.description == 'None' or opportunity.description == '':
                if excel_info['description'] and str(excel_info['description']) != 'nan':
                    updates_needed.append(('description', excel_info['description']))
            
            if updates_needed:
                self.stdout.write(f'\n[{opp_num}] Updates needed:')
                for field, value in updates_needed:
                    current_value = getattr(opportunity, field)
                    self.stdout.write(f'  {field}: "{current_value}" → "{value}"')
                
                if not dry_run:
                    # Apply updates
                    for field, value in updates_needed:
                        setattr(opportunity, field, value)
                    
                    # Also update the SharePoint folder name
                    from samples.utils.folder_utils import get_sharepoint_folder_name
                    opportunity.sharepoint_folder_name = get_sharepoint_folder_name(opportunity)
                    
                    opportunity.save()
                    self.stdout.write(self.style.SUCCESS(f'  ✓ Updated'))
                
                updated_count += 1
            else:
                # All fields are already populated
                self.stdout.write(f'[{opp_num}] Already complete - skipping')
                skipped_count += 1
        
        # Print summary
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS(f'Updated: {updated_count} opportunities'))
        self.stdout.write(f'Skipped (already complete): {skipped_count}')
        self.stdout.write(self.style.WARNING(f'Not in Excel: {not_in_excel}'))
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\nDRY RUN COMPLETE - No changes were made'))
            self.stdout.write('Run without --dry-run to apply changes')
        else:
            self.stdout.write(self.style.SUCCESS('\nAll opportunities updated successfully!'))
            
            # Remind about next steps
            if updated_count > 0:
                self.stdout.write('\nNext steps:')
                self.stdout.write('1. Run: python manage.py migrate_sharepoint_folders')
                self.stdout.write('2. Run: python manage.py update_folder_metadata')