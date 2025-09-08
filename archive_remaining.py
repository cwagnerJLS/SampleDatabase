#!/usr/bin/env python
"""
Manually trigger archive for remaining opportunities 8122 and 8188.
"""
import os
import sys
import django
from celery import chain

# Add the project directory to the Python path
sys.path.insert(0, '/home/jls/Desktop/SampleDatabase')

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'inventory_system.settings')
django.setup()

from samples.tasks import (
    move_documentation_to_archive_task,
    update_documentation_excels,
    set_opportunity_update_false
)

def archive_remaining():
    """Archive the two remaining opportunities."""
    remaining = ['8122', '8188']
    
    print("Archiving remaining opportunities...")
    for opp_num in remaining:
        print(f"\nProcessing {opp_num}...")
        
        # Directly call the archive task without the update_documentation_excels
        # since that seems to be skipping due to flags
        try:
            task = move_documentation_to_archive_task.delay(opp_num)
            print(f"  ✓ Archive task initiated directly (Task ID: {task.id})")
        except Exception as e:
            print(f"  ✗ Failed: {e}")
    
    print("\nDone! Check logs with: sudo journalctl -u celery-sampledb -f")

if __name__ == "__main__":
    archive_remaining()