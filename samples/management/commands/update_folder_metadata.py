"""
Management command to update SharePoint folder metadata for opportunities.
Useful for updating metadata after adding new columns or fixing missing metadata.
"""
import logging
from django.core.management.base import BaseCommand
from samples.models import Opportunity
from samples.sharepoint_config import TEST_ENGINEERING_LIBRARY_ID, GRAPH_API_URL
from samples.services.auth_service import get_sharepoint_token
from samples.utils.sharepoint_api import GraphAPIClient
from samples.utils.folder_utils import get_sharepoint_folder_name

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Update SharePoint folder metadata for opportunities'

    def add_arguments(self, parser):
        parser.add_argument(
            '--opportunity',
            type=str,
            help='Update metadata for a specific opportunity number',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )

    def handle(self, *args, **options):
        specific_opp = options.get('opportunity')
        dry_run = options.get('dry_run', False)
        
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
            folder_name = get_sharepoint_folder_name(opportunity)
            
            self.stdout.write(f'\n[{opp_num}] Processing folder: {folder_name}')
            
            try:
                # Find the folder
                search_url = f"{GRAPH_API_URL}/drives/{TEST_ENGINEERING_LIBRARY_ID}/root/children"
                result = GraphAPIClient.get(search_url, access_token, raise_on_error=False)
                
                if not result:
                    self.stdout.write(self.style.ERROR(f'  Failed to list folders'))
                    error_count += 1
                    continue
                
                # Find the folder with matching name
                folder_id = None
                for item in result.get('value', []):
                    # Check both old and new naming formats
                    if (item.get('name') == opp_num or item.get('name') == folder_name) and 'folder' in item:
                        folder_id = item['id']
                        actual_name = item.get('name')
                        break
                
                if not folder_id:
                    self.stdout.write(self.style.WARNING(f'  Folder not found on SharePoint'))
                    skip_count += 1
                    continue
                
                self.stdout.write(f'  Found folder: {actual_name} (ID: {folder_id})')
                
                if dry_run:
                    self.stdout.write(self.style.SUCCESS('  Would update metadata:'))
                    self.stdout.write(f'    Customer: {opportunity.customer}')
                    self.stdout.write(f'    RSM: {opportunity.rsm}')
                    self.stdout.write(f'    OpportunityNumber: {opportunity.opportunity_number}')
                    self.stdout.write(f'    Description: {opportunity.description}')
                    success_count += 1
                    continue
                
                # Update metadata
                update_url = f"{GRAPH_API_URL}/drives/{TEST_ENGINEERING_LIBRARY_ID}/items/{folder_id}/listItem/fields"
                
                # Build metadata fields
                metadata = {}
                
                # Always include these if they have values
                if opportunity.customer:
                    metadata['Customer'] = opportunity.customer
                if opportunity.rsm:
                    metadata['RSM'] = opportunity.rsm
                
                # Store opportunity number in the Description field (since folder name has the description)
                metadata['_ExtendedDescription'] = opportunity.opportunity_number
                
                # Try to update metadata
                update_result = GraphAPIClient.patch(update_url, access_token, json_data=metadata, raise_on_error=False)
                
                if update_result:
                    self.stdout.write(self.style.SUCCESS(f'  Successfully updated metadata'))
                    success_count += 1
                else:
                    self.stdout.write(self.style.ERROR(f'  Failed to update metadata'))
                    error_count += 1
                        
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  Error: {str(e)}'))
                error_count += 1
        
        # Summary
        self.stdout.write('\n' + '='*50)
        self.stdout.write(self.style.SUCCESS(f'Successfully updated: {success_count}'))
        self.stdout.write(self.style.WARNING(f'Skipped: {skip_count}'))
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f'Errors: {error_count}'))
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\nDRY RUN COMPLETE - No changes were made'))
        else:
            self.stdout.write(self.style.SUCCESS('\nMetadata update complete!'))