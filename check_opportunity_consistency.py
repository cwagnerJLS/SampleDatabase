#!/usr/bin/env python
"""
Script to check for inconsistencies between SharePoint folders and the database.
This identifies:
1. Opportunities with no samples that haven't been archived
2. Folders in main library that should be in archive
3. Folders in archive that should be in main library
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

from samples.models import Opportunity, Sample
from samples.utils.folder_utils import extract_opportunity_number_from_folder
from samples.sharepoint_config import TEST_ENGINEERING_LIBRARY_ID, GRAPH_API_URL
from samples.services.auth_service import get_sharepoint_token
from samples.utils.sharepoint_api import GraphAPIClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_all_sharepoint_folders(access_token):
    """Get all folders from both main library and archive."""
    folders = {'main': [], 'archive': []}
    
    # Get main folders
    main_url = f"{GRAPH_API_URL}/drives/{TEST_ENGINEERING_LIBRARY_ID}/root/children"
    
    try:
        result = GraphAPIClient.get(main_url, access_token, raise_on_error=True)
        
        if result:
            for item in result.get('value', []):
                if 'folder' in item:  # Only folders, not files
                    folder_name = item.get('name', '')
                    # Skip system folders
                    if not folder_name.startswith('_') and folder_name != 'Sample Info':
                        folders['main'].append({
                            'name': folder_name,
                            'id': item.get('id', ''),
                            'webUrl': item.get('webUrl', '')
                        })
    except Exception as e:
        logger.error(f"Error listing main folders: {e}")
    
    # Get archive folders
    archive_url = f"{GRAPH_API_URL}/drives/{TEST_ENGINEERING_LIBRARY_ID}/root:/_Archive:/children"
    
    try:
        result = GraphAPIClient.get(archive_url, access_token, raise_on_error=True)
        
        if result:
            for item in result.get('value', []):
                if 'folder' in item:  # Only folders, not files
                    folders['archive'].append({
                        'name': item.get('name', ''),
                        'id': item.get('id', ''),
                        'webUrl': item.get('webUrl', '')
                    })
    except Exception as e:
        logger.error(f"Error listing archive folders: {e}")
    
    return folders


def check_database_consistency():
    """Check database for opportunities and their sample counts."""
    opportunities = {}
    
    # Get all opportunities
    for opp in Opportunity.objects.all():
        # Get sample count from sample_ids field
        sample_ids = [id.strip() for id in opp.sample_ids.split(',') if id.strip()] if opp.sample_ids else []
        
        # Get actual sample count from database
        actual_samples = Sample.objects.filter(opportunity_number=opp.opportunity_number).count()
        
        opportunities[opp.opportunity_number] = {
            'opportunity': opp,
            'sample_ids_count': len(sample_ids),
            'actual_sample_count': actual_samples,
            'description': opp.description,
            'customer': opp.customer,
            'rsm': opp.rsm,
            'date_received': opp.date_received,
            'sharepoint_folder_name': opp.sharepoint_folder_name
        }
    
    return opportunities


def analyze_inconsistencies(db_opportunities, sharepoint_folders):
    """Analyze inconsistencies between database and SharePoint."""
    issues = {
        'main_should_archive': [],  # Folders in main that should be in archive
        'archive_should_restore': [],  # Folders in archive that should be in main
        'missing_from_sharepoint': [],  # Opportunities with no folder anywhere
        'unknown_folders': [],  # Folders with no matching opportunity
        'sample_count_mismatch': []  # Opportunities where sample_ids doesn't match actual count
    }
    
    # Create lookup for SharePoint folders by opportunity number
    main_folders_by_opp = {}
    archive_folders_by_opp = {}
    
    for folder in sharepoint_folders['main']:
        opp_num = extract_opportunity_number_from_folder(folder['name'])
        if opp_num:
            main_folders_by_opp[opp_num] = folder
    
    for folder in sharepoint_folders['archive']:
        opp_num = extract_opportunity_number_from_folder(folder['name'])
        if opp_num:
            archive_folders_by_opp[opp_num] = folder
    
    # Check each opportunity
    for opp_num, data in db_opportunities.items():
        has_samples = data['actual_sample_count'] > 0
        in_main = opp_num in main_folders_by_opp
        in_archive = opp_num in archive_folders_by_opp
        
        # Check for sample count mismatches
        if data['sample_ids_count'] != data['actual_sample_count']:
            issues['sample_count_mismatch'].append({
                'opportunity_number': opp_num,
                'sample_ids_count': data['sample_ids_count'],
                'actual_sample_count': data['actual_sample_count'],
                'description': data['description']
            })
        
        # Check folder location vs sample status
        if has_samples and in_archive and not in_main:
            # Has samples but folder is in archive
            issues['archive_should_restore'].append({
                'opportunity_number': opp_num,
                'folder': archive_folders_by_opp[opp_num],
                'sample_count': data['actual_sample_count'],
                'description': data['description']
            })
        elif not has_samples and in_main and not in_archive:
            # No samples but folder is in main
            issues['main_should_archive'].append({
                'opportunity_number': opp_num,
                'folder': main_folders_by_opp[opp_num],
                'description': data['description']
            })
        elif not in_main and not in_archive:
            # Opportunity exists but no folder anywhere
            issues['missing_from_sharepoint'].append({
                'opportunity_number': opp_num,
                'sample_count': data['actual_sample_count'],
                'description': data['description']
            })
    
    # Check for unknown folders (folders without matching opportunities)
    all_opportunity_numbers = set(db_opportunities.keys())
    
    for folder in sharepoint_folders['main']:
        opp_num = extract_opportunity_number_from_folder(folder['name'])
        if opp_num and opp_num not in all_opportunity_numbers:
            issues['unknown_folders'].append({
                'folder': folder,
                'location': 'main',
                'extracted_opp_num': opp_num
            })
    
    for folder in sharepoint_folders['archive']:
        opp_num = extract_opportunity_number_from_folder(folder['name'])
        if opp_num and opp_num not in all_opportunity_numbers:
            issues['unknown_folders'].append({
                'folder': folder,
                'location': 'archive',
                'extracted_opp_num': opp_num
            })
    
    return issues


def main():
    """Main function to check consistency."""
    parser = argparse.ArgumentParser(description='Check for inconsistencies between SharePoint and database')
    parser.add_argument('--fix', action='store_true', 
                       help='Attempt to fix issues (move folders to correct location)')
    args = parser.parse_args()
    
    print("\n" + "="*60)
    print("SharePoint and Database Consistency Check")
    print("="*60)
    
    # Get SharePoint access token
    access_token = get_sharepoint_token()
    if not access_token:
        logger.error('Failed to get SharePoint access token')
        return
    
    # Get all SharePoint folders
    print("\nFetching SharePoint folders...")
    sharepoint_folders = get_all_sharepoint_folders(access_token)
    print(f"  Found {len(sharepoint_folders['main'])} folders in main library")
    print(f"  Found {len(sharepoint_folders['archive'])} folders in archive")
    
    # Check database consistency
    print("\nChecking database...")
    db_opportunities = check_database_consistency()
    print(f"  Found {len(db_opportunities)} opportunities in database")
    
    # Analyze inconsistencies
    print("\nAnalyzing inconsistencies...")
    issues = analyze_inconsistencies(db_opportunities, sharepoint_folders)
    
    # Report findings
    print("\n" + "="*60)
    print("FINDINGS:")
    print("="*60)
    
    if issues['sample_count_mismatch']:
        print(f"\n❌ Sample Count Mismatches ({len(issues['sample_count_mismatch'])} opportunities):")
        print("   (sample_ids field doesn't match actual sample count)")
        for item in issues['sample_count_mismatch']:
            print(f"   - {item['opportunity_number']}: sample_ids={item['sample_ids_count']}, actual={item['actual_sample_count']}")
            if item['description']:
                print(f"     Description: {item['description']}")
    
    if issues['main_should_archive']:
        print(f"\n❌ Folders in Main Library that Should be Archived ({len(issues['main_should_archive'])} folders):")
        print("   (No samples but folder still in main library)")
        for item in issues['main_should_archive']:
            print(f"   - {item['opportunity_number']}: {item['folder']['name']}")
            if item['description']:
                print(f"     Description: {item['description']}")
    
    if issues['archive_should_restore']:
        print(f"\n❌ Folders in Archive that Should be Restored ({len(issues['archive_should_restore'])} folders):")
        print("   (Has samples but folder is in archive)")
        for item in issues['archive_should_restore']:
            print(f"   - {item['opportunity_number']}: {item['folder']['name']} ({item['sample_count']} samples)")
            if item['description']:
                print(f"     Description: {item['description']}")
    
    if issues['missing_from_sharepoint']:
        print(f"\n⚠️  Opportunities Missing from SharePoint ({len(issues['missing_from_sharepoint'])} opportunities):")
        print("   (Opportunity exists in database but no folder found)")
        for item in issues['missing_from_sharepoint']:
            print(f"   - {item['opportunity_number']} ({item['sample_count']} samples)")
            if item['description']:
                print(f"     Description: {item['description']}")
    
    if issues['unknown_folders']:
        print(f"\n⚠️  Unknown Folders in SharePoint ({len(issues['unknown_folders'])} folders):")
        print("   (Folders with no matching opportunity in database)")
        for item in issues['unknown_folders']:
            print(f"   - [{item['location'].upper()}] {item['folder']['name']} (extracted: {item['extracted_opp_num']})")
    
    # Summary
    total_issues = sum(len(v) for v in issues.values())
    if total_issues == 0:
        print("\n✅ No inconsistencies found! Everything is in sync.")
    else:
        print(f"\n\nTotal issues found: {total_issues}")
        
        if args.fix:
            print("\n" + "="*60)
            print("FIXING ISSUES:")
            print("="*60)
            print("\nAutomatic fixing is not yet implemented.")
            print("To fix these issues:")
            print("1. For 'main_should_archive': Run archive tasks for these opportunities")
            print("2. For 'archive_should_restore': Run restore tasks for these opportunities")
            print("3. For 'sample_count_mismatch': Use OpportunityService.sync_sample_ids()")
            print("4. For 'missing_from_sharepoint': May need to create folders manually")
            print("5. For 'unknown_folders': Investigate and possibly delete or create opportunities")
        else:
            print("\nRun with --fix flag to attempt automatic fixes")
    
    print("="*60)


if __name__ == "__main__":
    main()