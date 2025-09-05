"""
Management command to migrate SharePoint folder names from opportunity numbers to descriptions.
This will rename existing folders and update the Opportunity model with the new folder names.
"""
import logging
from django.core.management.base import BaseCommand
from django.db import transaction
from samples.models import Opportunity
from samples.utils.folder_utils import get_sharepoint_folder_name
from samples.sharepoint_config import TEST_ENGINEERING_LIBRARY_ID, GRAPH_API_URL
from samples.services.auth_service import get_sharepoint_token
from samples.utils.sharepoint_api import GraphAPIClient

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Migrate SharePoint folders from opportunity number naming to description naming'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )
        parser.add_argument(
            '--opportunity',
            type=str,
            help='Migrate only a specific opportunity number',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        specific_opp = options.get('opportunity')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        # Get opportunities to process
        if specific_opp:
            opportunities = Opportunity.objects.filter(opportunity_number=specific_opp)
            if not opportunities.exists():
                self.stdout.write(self.style.ERROR(f'Opportunity {specific_opp} not found'))
                return
        else:
            opportunities = Opportunity.objects.all()
        
        self.stdout.write(f'Found {opportunities.count()} opportunities to process')
        
        # Get SharePoint access token
        access_token = get_sharepoint_token()
        if not access_token:
            self.stdout.write(self.style.ERROR('Failed to get SharePoint access token'))
            return
        
        success_count = 0
        skip_count = 0
        error_count = 0
        
        for opportunity in opportunities:
            opp_num = opportunity.opportunity_number
            
            # Generate the new folder name
            new_folder_name = get_sharepoint_folder_name(opportunity)
            
            # Check if it's already using the new naming
            if opportunity.sharepoint_folder_name == new_folder_name:
                self.stdout.write(f'  [{opp_num}] Already migrated to "{new_folder_name}"')
                skip_count += 1
                continue
            
            self.stdout.write(f'\n[{opp_num}] Processing...')
            self.stdout.write(f'  Current name: {opp_num}')
            self.stdout.write(f'  New name: {new_folder_name}')
            
            if dry_run:
                self.stdout.write(self.style.SUCCESS('  Would rename folder'))
                success_count += 1
                continue
            
            try:
                # Find the current folder
                search_url = f"{GRAPH_API_URL}/drives/{TEST_ENGINEERING_LIBRARY_ID}/root/children"
                result = GraphAPIClient.get(search_url, access_token, raise_on_error=False)
                
                if not result:
                    self.stdout.write(self.style.ERROR(f'  Failed to list folders'))
                    error_count += 1
                    continue
                
                # Find the folder with matching name
                folder_id = None
                for item in result.get('value', []):
                    if item.get('name') == opp_num and 'folder' in item:
                        folder_id = item['id']
                        break
                
                if not folder_id:
                    # Try with the new name in case it was already renamed
                    for item in result.get('value', []):
                        if item.get('name') == new_folder_name and 'folder' in item:
                            folder_id = item['id']
                            self.stdout.write(self.style.WARNING(f'  Folder already renamed to "{new_folder_name}"'))
                            # Update the model
                            opportunity.sharepoint_folder_name = new_folder_name
                            opportunity.save()
                            skip_count += 1
                            break
                    
                    if not folder_id:
                        self.stdout.write(self.style.WARNING(f'  Folder not found on SharePoint'))
                        skip_count += 1
                    continue
                
                # Rename the folder
                update_url = f"{GRAPH_API_URL}/drives/{TEST_ENGINEERING_LIBRARY_ID}/items/{folder_id}"
                update_data = {
                    "name": new_folder_name
                }
                
                update_result = GraphAPIClient.patch(update_url, access_token, json_data=update_data, raise_on_error=False)
                
                if update_result:
                    # Update the opportunity model
                    with transaction.atomic():
                        opportunity.sharepoint_folder_name = new_folder_name
                        opportunity.save()
                    
                    self.stdout.write(self.style.SUCCESS(f'  Successfully renamed to "{new_folder_name}"'))
                    success_count += 1
                else:
                    self.stdout.write(self.style.ERROR(f'  Failed to rename folder'))
                    error_count += 1
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  Error: {str(e)}'))
                error_count += 1
        
        # Summary
        self.stdout.write('\n' + '='*50)
        self.stdout.write(self.style.SUCCESS(f'Successfully migrated: {success_count}'))
        self.stdout.write(self.style.WARNING(f'Skipped: {skip_count}'))
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f'Errors: {error_count}'))
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\nDRY RUN COMPLETE - No changes were made'))
        else:
            self.stdout.write(self.style.SUCCESS('\nMigration complete!'))