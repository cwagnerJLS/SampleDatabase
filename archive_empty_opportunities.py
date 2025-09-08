#!/usr/bin/env python
"""
Script to archive opportunities that have no current samples in inventory.
This preserves the historical sample_ids field while moving folders to _Archive
for opportunities with no active samples.
"""
import os
import sys
import django
import argparse
import logging
from celery import chain

# Add the project directory to the Python path
sys.path.insert(0, '/home/jls/Desktop/SampleDatabase')

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.settings')
django.setup()

from samples.models import Opportunity, Sample
from samples.tasks import (
    move_documentation_to_archive_task,
    update_documentation_excels,
    set_opportunity_update_false
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def find_opportunities_to_archive():
    """Find opportunities with no current samples that haven't been archived."""
    opportunities_to_archive = []
    
    # These are the opportunities identified as being in main library with no samples
    # Found by the check_opportunity_consistency.py script
    known_empty_in_main = ['8143', '7894', '8188', '8182', '8270', '8122', '8006']
    
    for opp_num in known_empty_in_main:
        try:
            opp = Opportunity.objects.get(opportunity_number=opp_num)
            
            # Double-check that there are no current samples
            current_sample_count = Sample.objects.filter(opportunity_number=opp_num).count()
            
            if current_sample_count == 0:
                opportunities_to_archive.append({
                    'opportunity_number': opp_num,
                    'description': opp.description,
                    'historical_samples': opp.sample_ids,  # Preserve this for display
                    'customer': opp.customer,
                    'rsm': opp.rsm
                })
            else:
                logger.warning(f"Opportunity {opp_num} now has {current_sample_count} samples - skipping")
        
        except Opportunity.DoesNotExist:
            logger.error(f"Opportunity {opp_num} not found in database")
    
    return opportunities_to_archive


def archive_opportunities(opportunities_to_archive, dry_run=False):
    """Archive opportunities that have no current samples."""
    archived_count = 0
    failed_count = 0
    
    for opp_data in opportunities_to_archive:
        opp_num = opp_data['opportunity_number']
        
        print(f"\n{opp_num}: {opp_data['description'] or 'No description'}")
        print(f"  Customer: {opp_data['customer'] or 'N/A'}")
        print(f"  RSM: {opp_data['rsm'] or 'N/A'}")
        print(f"  Historical samples: {opp_data['historical_samples'] or 'None recorded'}")
        
        if not dry_run:
            try:
                # Trigger the archive task chain
                # This will:
                # 1. Update the Excel documentation
                # 2. Move the folder to _Archive
                # 3. Reset the update flag
                task_chain = chain(
                    update_documentation_excels.si(opp_num),
                    move_documentation_to_archive_task.si(opp_num),
                    set_opportunity_update_false.si(opp_num)
                )
                result = task_chain.delay()
                print(f"  ✓ Archive task initiated (Task ID: {result.id})")
                archived_count += 1
            except Exception as e:
                print(f"  ✗ Failed to initiate archive task: {e}")
                failed_count += 1
        else:
            print(f"  [DRY RUN] Would initiate archive task")
            archived_count += 1
    
    return archived_count, failed_count


def main():
    """Main function to archive empty opportunities."""
    parser = argparse.ArgumentParser(
        description='Archive opportunity folders with no current samples to _Archive folder'
    )
    parser.add_argument('--dry-run', action='store_true', 
                       help='Show what would be done without making changes')
    args = parser.parse_args()
    
    if args.dry_run:
        print("\n" + "="*60)
        print("DRY RUN MODE - No changes will be made")
        print("="*60)
    
    print("\n" + "="*60)
    print("Archive Empty Opportunities")
    print("="*60)
    print("\nThis script will archive opportunity folders that have")
    print("no current samples in inventory. The historical sample_ids")
    print("field will be preserved for record-keeping.")
    
    # Find opportunities to archive
    print("\n" + "-"*60)
    print("Finding opportunities to archive...")
    opportunities = find_opportunities_to_archive()
    
    if not opportunities:
        print("\n✓ No opportunities need to be archived")
        return
    
    print(f"\nFound {len(opportunities)} opportunities to archive")
    
    # Archive them
    print("\n" + "-"*60)
    print("Archiving opportunities...")
    archived, failed = archive_opportunities(opportunities, args.dry_run)
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    if args.dry_run:
        print(f"\nDRY RUN COMPLETE")
        print(f"Would archive {archived} opportunities")
        print("\nRun without --dry-run to apply changes")
    else:
        print(f"\n✓ Successfully initiated archiving for {archived} opportunities")
        if failed > 0:
            print(f"✗ Failed to archive {failed} opportunities")
        
        print("\nNote: Archive tasks are running in the background.")
        print("Check task status with:")
        print("  sudo journalctl -u celery-sampledb -f")
        print("\nOr check SharePoint directly to confirm folders have moved to _Archive")
    
    print("="*60)


if __name__ == "__main__":
    main()