#!/usr/bin/env python
"""
Script to migrate SharePoint _Archive folders from old naming convention (opportunity number only)
to new naming convention (description with opportunity number).

This script will:
1. Find all folders in _Archive that use the old naming convention
2. Look up the corresponding opportunity in the database
3. Generate the new folder name using the same logic as the main folders
4. Rename the folders in SharePoint
5. Update metadata if needed
"""
import os
import sys
import django
import argparse
import logging

# Add the project directory to the Python path
sys.path.insert(0, '/home/jls/Desktop/SampleDatabase')

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.settings')
django.setup()

from samples.models import Opportunity
from samples.utils.folder_utils import get_sharepoint_folder_name
from samples.sharepoint_config import TEST_ENGINEERING_LIBRARY_ID, GRAPH_API_URL
from samples.services.auth_service import get_sharepoint_token
from samples.utils.sharepoint_api import GraphAPIClient
from django.db import transaction

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_archive_folders(access_token):
    """Get all folders in the _Archive folder."""
    archive_url = f"{GRAPH_API_URL}/drives/{TEST_ENGINEERING_LIBRARY_ID}/root:/_Archive:/children"
    
    try:
        result = GraphAPIClient.get(archive_url, access_token, raise_on_error=True)
        
        if not result:
            logger.error('Failed to retrieve archive folders')
            return []
        
        folders = []
        for item in result.get('value', []):
            if 'folder' in item:  # Only folders, not files
                folders.append({
                    'name': item.get('name', ''),
                    'id': item.get('id', ''),
                    'webUrl': item.get('webUrl', '')
                })
        
        return folders
        
    except Exception as e:
        logger.error(f"Error listing archive folders: {e}")
        return []


def rename_archive_folder(folder_id, new_name, access_token, dry_run=False):
    """Rename a folder in SharePoint."""
    if dry_run:
        logger.info(f"  [DRY RUN] Would rename folder to: {new_name}")
        return True
    
    update_url = f"{GRAPH_API_URL}/drives/{TEST_ENGINEERING_LIBRARY_ID}/items/{folder_id}"
    update_data = {
        "name": new_name
    }
    
    try:
        result = GraphAPIClient.patch(update_url, access_token, json_data=update_data, raise_on_error=True)
        if result:
            logger.info(f"  Successfully renamed to: {new_name}")
            return True
        else:
            logger.error(f"  Failed to rename folder")
            return False
    except Exception as e:
        logger.error(f"  Error renaming folder: {e}")
        return False


def update_folder_metadata(folder_id, opportunity, access_token, dry_run=False):
    """Update folder metadata (Customer, RSM, opportunity number in Description field)."""
    if dry_run:
        logger.info(f"  [DRY RUN] Would update metadata: Customer={opportunity.customer}, RSM={opportunity.rsm}, Description={opportunity.opportunity_number}")
        return True
    
    # Get list item ID for the folder
    list_item_url = f"{GRAPH_API_URL}/drives/{TEST_ENGINEERING_LIBRARY_ID}/items/{folder_id}/listItem"
    
    try:
        # Get the list item
        list_item = GraphAPIClient.get(list_item_url, access_token, raise_on_error=True)
        
        if not list_item:
            logger.warning("  Could not get list item for metadata update")
            return False
        
        # Update the metadata
        update_url = f"{GRAPH_API_URL}/drives/{TEST_ENGINEERING_LIBRARY_ID}/items/{folder_id}/listItem/fields"
        update_data = {
            "Customer": opportunity.customer or "",
            "RSM": opportunity.rsm or "",
            "_ExtendedDescription": opportunity.opportunity_number  # Store opp number in Description field
        }
        
        result = GraphAPIClient.patch(update_url, access_token, json_data=update_data, raise_on_error=False)
        
        if result:
            logger.info(f"  Updated metadata: Customer={opportunity.customer}, RSM={opportunity.rsm}")
            return True
        else:
            logger.warning("  Could not update metadata (this is non-critical)")
            return True  # Return True anyway as this is non-critical
            
    except Exception as e:
        logger.warning(f"  Could not update metadata: {e} (this is non-critical)")
        return True  # Return True anyway as this is non-critical


def main():
    """Main function to migrate archive folders."""
    parser = argparse.ArgumentParser(description='Migrate SharePoint archive folders to new naming convention')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Show what would be done without making changes')
    parser.add_argument('--opportunity', type=str,
                       help='Migrate only a specific opportunity number')
    args = parser.parse_args()
    
    if args.dry_run:
        print("\n" + "="*60)
        print("DRY RUN MODE - No changes will be made")
        print("="*60)
    
    print("\n" + "="*60)
    print("SharePoint _Archive Folder Migration")
    print("="*60)
    
    # Get SharePoint access token
    access_token = get_sharepoint_token()
    if not access_token:
        logger.error('Failed to get SharePoint access token')
        return
    
    # Get all folders in archive
    folders = get_archive_folders(access_token)
    
    if not folders:
        print("\nNo folders found in _Archive or unable to retrieve them.")
        return
    
    # Filter to only old format folders (just numbers)
    old_format_folders = [f for f in folders if f['name'].isdigit()]
    
    if args.opportunity:
        old_format_folders = [f for f in old_format_folders if f['name'] == args.opportunity]
        if not old_format_folders:
            print(f"\nOpportunity {args.opportunity} not found in archive with old naming format.")
            return
    
    print(f"\nFound {len(old_format_folders)} folders to migrate\n")
    
    success_count = 0
    skip_count = 0
    error_count = 0
    
    for folder in sorted(old_format_folders, key=lambda x: x['name']):
        opp_num = folder['name']
        folder_id = folder['id']
        
        print(f"\n[{opp_num}] Processing...")
        
        try:
            # Look up the opportunity in the database
            opportunity = Opportunity.objects.get(opportunity_number=opp_num)
            
            # Generate the new folder name
            new_folder_name = get_sharepoint_folder_name(opportunity)
            
            print(f"  Current name: {opp_num}")
            print(f"  New name: {new_folder_name}")
            
            # Check if it's already using the new naming (shouldn't happen but check anyway)
            if folder['name'] == new_folder_name:
                print(f"  Already migrated")
                skip_count += 1
                continue
            
            # Rename the folder
            if rename_archive_folder(folder_id, new_folder_name, access_token, args.dry_run):
                # Update metadata
                update_folder_metadata(folder_id, opportunity, access_token, args.dry_run)
                
                # Update the opportunity model if not in dry run
                if not args.dry_run:
                    with transaction.atomic():
                        opportunity.sharepoint_folder_name = new_folder_name
                        opportunity.save()
                
                success_count += 1
            else:
                error_count += 1
                
        except Opportunity.DoesNotExist:
            print(f"  ERROR: Opportunity not found in database")
            print(f"  Skipping - cannot generate new name without opportunity data")
            error_count += 1
        except Exception as e:
            print(f"  ERROR: {str(e)}")
            error_count += 1
    
    # Summary
    print("\n" + "="*60)
    print("Migration Summary:")
    print(f"  Successfully migrated: {success_count}")
    print(f"  Skipped: {skip_count}")
    if error_count > 0:
        print(f"  Errors: {error_count}")
    
    if args.dry_run:
        print("\nDRY RUN COMPLETE - No changes were made")
        print("Run without --dry-run to apply changes")
    else:
        print("\nMigration complete!")
    print("="*60)


if __name__ == "__main__":
    main()