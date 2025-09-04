from django.db import migrations

def populate_customer_opportunity(apps, schema_editor):
    """Populate customer and opportunity fields for existing ActivityLog entries"""
    ActivityLog = apps.get_model('samples', 'ActivityLog')
    Sample = apps.get_model('samples', 'Sample')
    
    # Get all activity logs related to samples
    sample_logs = ActivityLog.objects.filter(object_type='Sample').exclude(object_id__isnull=True)
    
    updated_count = 0
    for log in sample_logs:
        try:
            # Try to find the sample
            sample = Sample.objects.filter(unique_id=log.object_id).first()
            if sample:
                # Update the log with customer and opportunity info
                log.customer = sample.customer
                log.opportunity = sample.opportunity_number
                log.save(update_fields=['customer', 'opportunity'])
                updated_count += 1
        except Exception as e:
            # Continue processing even if one fails
            print(f"Error processing log {log.id}: {e}")
            continue
    
    print(f"Updated {updated_count} activity log entries with customer and opportunity data")

def reverse_populate(apps, schema_editor):
    """Reverse migration - clear customer and opportunity fields"""
    ActivityLog = apps.get_model('samples', 'ActivityLog')
    ActivityLog.objects.update(customer=None, opportunity=None)

class Migration(migrations.Migration):

    dependencies = [
        ('samples', '0026_add_customer_opportunity_to_activitylog'),
    ]

    operations = [
        migrations.RunPython(populate_customer_opportunity, reverse_populate),
    ]