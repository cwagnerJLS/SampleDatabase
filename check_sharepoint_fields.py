#!/usr/bin/env python
"""
Script to check SharePoint column internal names
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.settings')
django.setup()

from samples.sharepoint_config import TEST_ENGINEERING_LIBRARY_ID, GRAPH_API_URL
from samples.services.auth_service import get_sharepoint_token
from samples.utils.sharepoint_api import GraphAPIClient
import json

def check_column_fields():
    """Check the internal field names of SharePoint columns"""
    
    # Get access token
    access_token = get_sharepoint_token()
    if not access_token:
        print("Failed to get access token")
        return
    
    # Get list columns
    list_url = f"{GRAPH_API_URL}/drives/{TEST_ENGINEERING_LIBRARY_ID}/list/columns"
    result = GraphAPIClient.get(list_url, access_token, raise_on_error=False)
    
    if not result:
        print("Failed to get columns")
        return
    
    columns = result.get('value', [])
    print(f"Found {len(columns)} columns\n")
    
    # Look for our custom columns
    custom_columns = ['Customer', 'RSM', 'Description', 'Opportunity', 'OpportunityNumber', '_ExtendedDescription']
    
    print("Custom columns found:")
    print("-" * 60)
    
    for column in columns:
        display_name = column.get('displayName', '')
        internal_name = column.get('name', '')
        
        # Check if this is one of our columns
        if any(name.lower() in display_name.lower() or name.lower() in internal_name.lower() 
               for name in custom_columns):
            print(f"Display Name: {display_name}")
            print(f"Internal Name: {internal_name}")
            print(f"Type: {column.get('text', {}) if 'text' in column else column.get('type', 'Unknown')}")
            print("-" * 60)
    
    # Also test updating a folder with the current field name
    print("\nTesting field update with '_ExtendedDescription'...")
    
    # Get a test folder (first one we find)
    folders_url = f"{GRAPH_API_URL}/drives/{TEST_ENGINEERING_LIBRARY_ID}/root/children"
    folders_result = GraphAPIClient.get(folders_url, access_token, raise_on_error=False)
    
    if folders_result:
        folders = folders_result.get('value', [])
        for folder in folders:
            if 'folder' in folder:
                folder_id = folder['id']
                folder_name = folder['name']
                print(f"Testing on folder: {folder_name}")
                
                # Try to read current metadata
                metadata_url = f"{GRAPH_API_URL}/drives/{TEST_ENGINEERING_LIBRARY_ID}/items/{folder_id}/listItem/fields"
                metadata = GraphAPIClient.get(metadata_url, access_token, raise_on_error=False)
                
                if metadata:
                    print("Current metadata fields:")
                    if 'Customer' in metadata:
                        print(f"  Customer: {metadata['Customer']}")
                    if 'RSM' in metadata:
                        print(f"  RSM: {metadata['RSM']}")
                    if '_ExtendedDescription' in metadata:
                        print(f"  _ExtendedDescription: {metadata['_ExtendedDescription']}")
                    if 'OpportunityNumber' in metadata:
                        print(f"  OpportunityNumber: {metadata['OpportunityNumber']}")
                    if 'Description' in metadata:
                        print(f"  Description: {metadata['Description']}")
                
                break

if __name__ == "__main__":
    check_column_fields()