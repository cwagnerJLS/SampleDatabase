#!/usr/bin/env python
"""
Script to remove redundant opportunity numbers from SharePoint folder names.
This will clean up folders that have the format "Description (####)" to just "Description"
since the description already starts with the opportunity number.

Example: "7000 - Company - Location (7000)" becomes "7000 - Company - Location"
"""
import os
import sys
import django
import argparse
import logging
import re

# Add the project directory to the Python path
sys.path.insert(0, '/home/jls/Desktop/SampleDatabase')

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.settings')
django.setup()

from samples.models import Opportunity
from samples.sharepoint_config import TEST_ENGINEERING_LIBRARY_ID, GRAPH_API_URL
from samples.services.auth_service import get_sharepoint_token
from samples.utils.sharepoint_api import GraphAPIClient
from django.db import transaction

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_all_folders(access_token, include_archive=True):
    """Get all folders from SharePoint, including those in _Archive if specified."""
    folders = []
    
    # Get main folders (from root)
    main_url = f"{GRAPH_API_URL}/drives/{TEST_ENGINEERING_LIBRARY_ID}/root/children"
    
    try:
        result = GraphAPIClient.get(main_url, access_token, raise_on_error=True)
        
        if result:
            for item in result.get('value', []):
                if 'folder' in item:  # Only folders, not files
                    folder_name = item.get('name', '')
                    # Skip system folders
                    if not folder_name.startswith('_') and not folder_name == 'Sample Info':
                        folders.append({
                            'name': folder_name,
                            'id': item.get('id', ''),
                            'location': 'main',
                            'webUrl': item.get('webUrl', '')
                        })
    except Exception as e:
        logger.error(f"Error listing main folders: {e}")
    
    # Get archive folders if requested
    if include_archive:
        archive_url = f"{GRAPH_API_URL}/drives/{TEST_ENGINEERING_LIBRARY_ID}/root:/_Archive:/children"
        
        try:
            result = GraphAPIClient.get(archive_url, access_token, raise_on_error=True)
            
            if result:
                for item in result.get('value', []):
                    if 'folder' in item:  # Only folders, not files
                        folders.append({
                            'name': item.get('name', ''),
                            'id': item.get('id', ''),
                            'location': 'archive',
                            'webUrl': item.get('webUrl', '')
                        })
        except Exception as e:
            logger.error(f"Error listing archive folders: {e}")
    
    return folders


def needs_cleanup(folder_name):
    """Check if a folder name needs cleanup (has redundant opportunity number)."""
    # Pattern to match folders ending with (####)
    pattern = r'^(.+)\s+\((\d+)\)$'
    match = re.match(pattern, folder_name)
    
    if match:
        description_part = match.group(1)
        opp_num_at_end = match.group(2)
        
        # Check if the description part starts with the same opportunity number
        if description_part.startswith(opp_num_at_end):
            return True, description_part
    
    return False, None


def rename_folder(folder_id, new_name, access_token, dry_run=False):
    """Rename a folder in SharePoint."""
    if dry_run:
        return True
    
    update_url = f"{GRAPH_API_URL}/drives/{TEST_ENGINEERING_LIBRARY_ID}/items/{folder_id}"
    update_data = {
        "name": new_name
    }
    
    try:
        result = GraphAPIClient.patch(update_url, access_token, json_data=update_data, raise_on_error=True)
        return result is not None
    except Exception as e:
        logger.error(f"  Error renaming folder: {e}")
        return False


def main():
    """Main function to clean up folder names."""
    parser = argparse.ArgumentParser(description='Remove redundant opportunity numbers from SharePoint folder names')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Show what would be done without making changes')
    parser.add_argument('--location', choices=['main', 'archive', 'all'], default='all',
                       help='Which folders to process (default: all)')
    parser.add_argument('--opportunity', type=str,
                       help='Process only a specific opportunity number')
    args = parser.parse_args()
    
    if args.dry_run:
        print("\n" + "="*60)
        print("DRY RUN MODE - No changes will be made")
        print("="*60)
    
    print("\n" + "="*60)
    print("SharePoint Folder Name Cleanup")
    print("="*60)
    
    # Get SharePoint access token
    access_token = get_sharepoint_token()
    if not access_token:
        logger.error('Failed to get SharePoint access token')
        return
    
    # Get all folders
    include_archive = args.location in ['archive', 'all']
    folders = get_all_folders(access_token, include_archive)
    
    if not folders:
        print("\nNo folders found or unable to retrieve them.")
        return
    
    # Filter by location if specified
    if args.location == 'main':
        folders = [f for f in folders if f['location'] == 'main']
    elif args.location == 'archive':
        folders = [f for f in folders if f['location'] == 'archive']
    
    # Filter by opportunity if specified
    if args.opportunity:
        filtered = []
        for folder in folders:
            # Check if folder name contains the opportunity number
            if args.opportunity in folder['name']:
                filtered.append(folder)
        folders = filtered
        if not folders:
            print(f"\nNo folders found for opportunity {args.opportunity}")
            return
    
    # Find folders that need cleanup
    folders_to_clean = []
    for folder in folders:
        needs_fix, clean_name = needs_cleanup(folder['name'])
        if needs_fix:
            folders_to_clean.append({
                **folder,
                'new_name': clean_name
            })
    
    if not folders_to_clean:
        print("\nNo folders need cleanup. All folder names are already correct.")
        return
    
    print(f"\nFound {len(folders_to_clean)} folders that need cleanup:\n")
    
    success_count = 0
    error_count = 0
    
    for folder in sorted(folders_to_clean, key=lambda x: x['name']):
        location = f"[{folder['location'].upper()}]"
        print(f"\n{location} Processing: {folder['name']}")
        print(f"  New name: {folder['new_name']}")
        
        if args.dry_run:
            print(f"  [DRY RUN] Would rename folder")
            success_count += 1
        else:
            # Rename the folder
            if rename_folder(folder['id'], folder['new_name'], access_token):
                print(f"  ✓ Successfully renamed")
                
                # Update the database record
                try:
                    # Extract opportunity number from the folder name
                    match = re.search(r'^(\d+)', folder['new_name'])
                    if match:
                        opp_num = match.group(1)
                        opportunity = Opportunity.objects.get(opportunity_number=opp_num)
                        with transaction.atomic():
                            opportunity.sharepoint_folder_name = folder['new_name']
                            opportunity.save()
                        print(f"  ✓ Updated database record")
                except Opportunity.DoesNotExist:
                    print(f"  ⚠ Could not update database - opportunity not found")
                except Exception as e:
                    print(f"  ⚠ Could not update database: {e}")
                
                success_count += 1
            else:
                print(f"  ✗ Failed to rename folder")
                error_count += 1
    
    # Summary
    print("\n" + "="*60)
    print("Cleanup Summary:")
    print(f"  Successfully cleaned: {success_count}")
    if error_count > 0:
        print(f"  Errors: {error_count}")
    
    if args.dry_run:
        print("\nDRY RUN COMPLETE - No changes were made")
        print("Run without --dry-run to apply changes")
    else:
        print("\nCleanup complete!")
    print("="*60)


if __name__ == "__main__":
    main()