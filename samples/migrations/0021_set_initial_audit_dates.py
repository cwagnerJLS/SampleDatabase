from django.db import migrations
from django.utils import timezone
from datetime import timedelta

def set_initial_audit_dates(apps, schema_editor):
    Sample = apps.get_model('samples', 'Sample')
    
    # Define audit periods for each location type
    audit_periods = {
        'Test Lab Fridge': timedelta(weeks=3),
        'Walk-in Fridge': timedelta(weeks=3),
        'Test Lab Freezer': timedelta(weeks=8),
        'Walk-in Freezer': timedelta(weeks=8),
        'Dry Food Storage': timedelta(weeks=8),
        'Empty Case Storage': timedelta(weeks=8),
    }
    
    # Update all samples with storage locations but no audit dates
    for sample in Sample.objects.filter(storage_location__isnull=False, audit_due_date__isnull=True):
        if sample.storage_location in audit_periods:
            # Set location assigned date to now (or date_received if available)
            sample.location_assigned_date = timezone.now()
            
            # Calculate audit due date from today
            period = audit_periods[sample.storage_location]
            sample.audit_due_date = (timezone.now() + period).date()
            
            # If sample was already audited, set last audit date
            if sample.audit:
                sample.last_audit_date = timezone.now()
            
            sample.save()

def reverse_initial_audit_dates(apps, schema_editor):
    Sample = apps.get_model('samples', 'Sample')
    Sample.objects.update(
        location_assigned_date=None,
        audit_due_date=None,
        last_audit_date=None
    )

class Migration(migrations.Migration):

    dependencies = [
        ('samples', '0020_add_audit_date_fields'),
    ]

    operations = [
        migrations.RunPython(set_initial_audit_dates, reverse_initial_audit_dates),
    ]