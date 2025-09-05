#!/usr/bin/env python
"""
Script to force rename specific SharePoint folders
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.settings')
django.setup()

from samples.models import Opportunity
from samples.utils.folder_utils import get_sharepoint_folder_name
from samples.sharepoint_config import TEST_ENGINEERING_LIBRARY_ID, GRAPH_API_URL
from samples.services.auth_service import get_sharepoint_token
from samples.utils.sharepoint_api import GraphAPIClient

def rename_folders():
    """Force rename specific folders"""
    
    # Opportunities to rename
    opp_numbers = ['7894', '7942', '8143', '8158']
    
    # Get access token
    access_token = get_sharepoint_token()
    if not access_token:
        print("Failed to get access token")
        return
    
    # Get all folders from SharePoint
    list_url = f"{GRAPH_API_URL}/drives/{TEST_ENGINEERING_LIBRARY_ID}/root/children"
    result = GraphAPIClient.get(list_url, access_token, raise_on_error=False)
    
    if not result:
        print("Failed to list SharePoint folders")
        return
    
    folders = result.get('value', [])
    print(f"Found {len(folders)} items in SharePoint library\n")
    
    for opp_num in opp_numbers:
        print(f"\nProcessing {opp_num}:")
        
        # Get opportunity from database
        try:
            opp = Opportunity.objects.get(opportunity_number=opp_num)
            new_name = get_sharepoint_folder_name(opp)
            print(f"  Should be named: {new_name}")
        except Opportunity.DoesNotExist:
            print(f"  Not found in database")
            continue
        
        # Find the folder on SharePoint
        folder_id = None
        current_name = None
        
        for folder in folders:
            if 'folder' in folder:  # It's a folder
                name = folder.get('name', '')
                # Check if it's our folder (by number or by new name)
                if name == opp_num or opp_num in name:
                    folder_id = folder['id']
                    current_name = name
                    break
        
        if not folder_id:
            print(f"  Not found on SharePoint")
            continue
        
        print(f"  Current name on SharePoint: {current_name}")
        
        if current_name == new_name:
            print(f"  Already correctly named")
            continue
        
        # Rename the folder
        print(f"  Renaming to: {new_name}")
        update_url = f"{GRAPH_API_URL}/drives/{TEST_ENGINEERING_LIBRARY_ID}/items/{folder_id}"
        update_data = {"name": new_name}
        
        update_result = GraphAPIClient.patch(update_url, access_token, json_data=update_data, raise_on_error=False)
        
        if update_result:
            print(f"  ✓ Successfully renamed")
            
            # Update the opportunity record
            opp.sharepoint_folder_name = new_name
            opp.save()
        else:
            print(f"  ✗ Failed to rename")
    
    # Now update metadata for all these folders
    print("\n" + "="*50)
    print("Updating metadata for all renamed folders...")
    
    for opp_num in opp_numbers:
        try:
            opp = Opportunity.objects.get(opportunity_number=opp_num)
            folder_name = get_sharepoint_folder_name(opp)
            
            # Find the folder again (with new name)
            folder_id = None
            for folder in folders:
                if 'folder' in folder and folder.get('name') == folder_name:
                    folder_id = folder['id']
                    break
            
            if folder_id:
                # Update metadata
                metadata_url = f"{GRAPH_API_URL}/drives/{TEST_ENGINEERING_LIBRARY_ID}/items/{folder_id}/listItem/fields"
                metadata = {
                    'Customer': opp.customer,
                    'RSM': opp.rsm,
                    '_ExtendedDescription': opp.opportunity_number  # Opportunity number in Description field
                }
                
                result = GraphAPIClient.patch(metadata_url, access_token, json_data=metadata, raise_on_error=False)
                if result:
                    print(f"  {opp_num}: Metadata updated")
                else:
                    print(f"  {opp_num}: Failed to update metadata")
        except:
            pass

if __name__ == "__main__":
    rename_folders()