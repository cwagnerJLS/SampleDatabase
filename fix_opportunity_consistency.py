#!/usr/bin/env python
"""
Script to fix inconsistencies between SharePoint folders and the database.
This will:
1. Sync sample_ids fields with actual database counts
2. Archive folders that have no samples
3. Restore folders that have samples but are archived
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
from samples.services.opportunity_service import OpportunityService
from samples.tasks import (
    move_documentation_to_archive_task,
    restore_documentation_from_archive_task,
    update_documentation_excels,
    set_opportunity_update_false
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def fix_sample_count_mismatches(dry_run=False):
    """Fix opportunities where sample_ids doesn't match actual sample count."""
    print("\n" + "="*60)
    print("FIXING SAMPLE COUNT MISMATCHES")
    print("="*60)
    
    fixed_count = 0
    
    for opp in Opportunity.objects.all():
        # Get sample count from sample_ids field
        sample_ids = [id.strip() for id in opp.sample_ids.split(',') if id.strip()] if opp.sample_ids else []
        
        # Get actual samples from database
        actual_samples = list(Sample.objects.filter(
            opportunity_number=opp.opportunity_number
        ).values_list('unique_id', flat=True))
        
        # Check if they match
        if set(str(s) for s in sample_ids) != set(str(s) for s in actual_samples):
            print(f"\n{opp.opportunity_number}:")
            print(f"  Current sample_ids: {','.join(sample_ids) if sample_ids else '(empty)'}")
            print(f"  Actual samples: {','.join(str(s) for s in actual_samples) if actual_samples else '(empty)'}")
            
            if not dry_run:
                # Update the opportunity
                opp.sample_ids = ','.join(str(sid) for sid in actual_samples) if actual_samples else ''
                opp.save()
                print(f"  ✓ Fixed - Updated sample_ids")
            else:
                print(f"  [DRY RUN] Would update sample_ids")
            
            fixed_count += 1
    
    print(f"\nFixed {fixed_count} opportunities with sample count mismatches")
    return fixed_count


def archive_empty_opportunities(opportunities_to_archive, dry_run=False):
    """Archive opportunities that have no samples but are still in main library."""
    print("\n" + "="*60)
    print("ARCHIVING EMPTY OPPORTUNITIES")
    print("="*60)
    
    archived_count = 0
    
    for opp_num in opportunities_to_archive:
        try:
            opp = Opportunity.objects.get(opportunity_number=opp_num)
            print(f"\n{opp_num}: {opp.description or 'No description'}")
            
            if not dry_run:
                # Trigger the archive task chain
                task_chain = chain(
                    update_documentation_excels.si(opp_num),
                    move_documentation_to_archive_task.si(opp_num),
                    set_opportunity_update_false.si(opp_num)
                )
                task_chain.delay()
                print(f"  ✓ Archive task initiated")
            else:
                print(f"  [DRY RUN] Would initiate archive task")
            
            archived_count += 1
        except Opportunity.DoesNotExist:
            print(f"\n{opp_num}: Opportunity not found in database")
    
    print(f"\nInitiated archiving for {archived_count} opportunities")
    return archived_count


def restore_opportunities_with_samples(opportunities_to_restore, dry_run=False):
    """Restore opportunities that have samples but are in archive."""
    print("\n" + "="*60)
    print("RESTORING OPPORTUNITIES WITH SAMPLES")
    print("="*60)
    
    restored_count = 0
    
    for opp_num, sample_count in opportunities_to_restore:
        try:
            opp = Opportunity.objects.get(opportunity_number=opp_num)
            print(f"\n{opp_num}: {opp.description or 'No description'} ({sample_count} samples)")
            
            if not dry_run:
                # Trigger the restore task chain
                task_chain = chain(
                    restore_documentation_from_archive_task.si(opp_num),
                    update_documentation_excels.si(opp_num)
                )
                task_chain.delay()
                print(f"  ✓ Restore task initiated")
            else:
                print(f"  [DRY RUN] Would initiate restore task")
            
            restored_count += 1
        except Opportunity.DoesNotExist:
            print(f"\n{opp_num}: Opportunity not found in database")
    
    print(f"\nInitiated restoration for {restored_count} opportunities")
    return restored_count


def main():
    """Main function to fix consistency issues."""
    parser = argparse.ArgumentParser(description='Fix inconsistencies between SharePoint and database')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Show what would be done without making changes')
    parser.add_argument('--sample-counts', action='store_true',
                       help='Fix only sample count mismatches')
    parser.add_argument('--archive', action='store_true',
                       help='Archive only empty opportunities')
    parser.add_argument('--restore', action='store_true',
                       help='Restore only opportunities with samples')
    args = parser.parse_args()
    
    # If no specific action is requested, do all
    do_all = not (args.sample_counts or args.archive or args.restore)
    
    if args.dry_run:
        print("\n" + "="*60)
        print("DRY RUN MODE - No changes will be made")
        print("="*60)
    
    print("\n" + "="*60)
    print("SharePoint and Database Consistency Fixer")
    print("="*60)
    
    total_fixed = 0
    
    # Fix sample count mismatches
    if do_all or args.sample_counts:
        fixed = fix_sample_count_mismatches(args.dry_run)
        total_fixed += fixed
    
    # Archive empty opportunities
    if do_all or args.archive:
        # These are the opportunities identified from the check script
        opportunities_to_archive = [
            '8143', '7894', '8188', '8182', '8270', '8122', '8006'
        ]
        archived = archive_empty_opportunities(opportunities_to_archive, args.dry_run)
        total_fixed += archived
    
    # Restore opportunities with samples
    if do_all or args.restore:
        # Currently none identified, but keeping the function for future use
        opportunities_to_restore = []
        restored = restore_opportunities_with_samples(opportunities_to_restore, args.dry_run)
        total_fixed += restored
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    if args.dry_run:
        print(f"\nDRY RUN COMPLETE - {total_fixed} issues would be fixed")
        print("Run without --dry-run to apply changes")
    else:
        print(f"\n✓ Fixed {total_fixed} issues")
        if do_all or args.archive:
            print("\nNote: Archive tasks have been initiated.")
            print("Check Celery logs for task completion status:")
            print("  sudo journalctl -u celery-sampledb -f")
    
    print("="*60)


if __name__ == "__main__":
    main()