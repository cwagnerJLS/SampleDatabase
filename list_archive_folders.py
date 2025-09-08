#!/usr/bin/env python
"""
Script to list all folders in the SharePoint _Archive folder.
This will help us understand what needs to be migrated.
"""
import os
import sys
import django

# Add the project directory to the Python path
sys.path.insert(0, '/home/jls/Desktop/SampleDatabase')

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.settings')
django.setup()

from samples.sharepoint_config import TEST_ENGINEERING_LIBRARY_ID, GRAPH_API_URL
from samples.services.auth_service import get_sharepoint_token
from samples.utils.sharepoint_api import GraphAPIClient
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def list_archive_folders():
    """List all folders in the _Archive folder."""
    
    # Get SharePoint access token
    access_token = get_sharepoint_token()
    if not access_token:
        logger.error('Failed to get SharePoint access token')
        return []
    
    # Get the _Archive folder
    archive_url = f"{GRAPH_API_URL}/drives/{TEST_ENGINEERING_LIBRARY_ID}/root:/_Archive:/children"
    
    try:
        result = GraphAPIClient.get(archive_url, access_token, raise_on_error=True)
        
        if not result:
            logger.error('Failed to retrieve archive folders')
            return []
        
        folders = []
        for item in result.get('value', []):
            if 'folder' in item:  # Only folders, not files
                folder_name = item.get('name', '')
                folder_id = item.get('id', '')
                folders.append({
                    'name': folder_name,
                    'id': folder_id
                })
        
        return folders
        
    except Exception as e:
        logger.error(f"Error listing archive folders: {e}")
        return []

def main():
    """Main function to list and analyze archive folders."""
    
    print("\n" + "="*60)
    print("SharePoint _Archive Folder Analysis")
    print("="*60)
    
    folders = list_archive_folders()
    
    if not folders:
        print("\nNo folders found in _Archive or unable to retrieve them.")
        return
    
    print(f"\nFound {len(folders)} folders in _Archive:\n")
    
    # Categorize folders by naming pattern
    old_format = []  # Just opportunity numbers
    new_format = []  # Description (OppNum) format
    unknown_format = []
    
    for folder in folders:
        name = folder['name']
        
        # Check if it's just a number (old format)
        if name.isdigit():
            old_format.append(folder)
        # Check if it ends with (####) pattern (new format)
        elif '(' in name and ')' in name and name.endswith(')'):
            new_format.append(folder)
        else:
            unknown_format.append(folder)
    
    # Display categorized results
    if old_format:
        print(f"\nOld Format (opportunity number only) - {len(old_format)} folders:")
        print("-" * 40)
        for folder in sorted(old_format, key=lambda x: x['name']):
            print(f"  {folder['name']}")
    
    if new_format:
        print(f"\nNew Format (description with number) - {len(new_format)} folders:")
        print("-" * 40)
        for folder in sorted(new_format, key=lambda x: x['name']):
            print(f"  {folder['name']}")
    
    if unknown_format:
        print(f"\nUnknown Format - {len(unknown_format)} folders:")
        print("-" * 40)
        for folder in sorted(unknown_format, key=lambda x: x['name']):
            print(f"  {folder['name']}")
    
    # Summary
    print("\n" + "="*60)
    print("Summary:")
    print(f"  Old format (needs migration): {len(old_format)}")
    print(f"  New format (already migrated): {len(new_format)}")
    print(f"  Unknown format: {len(unknown_format)}")
    print("="*60)
    
    return old_format, new_format, unknown_format

if __name__ == "__main__":
    main()