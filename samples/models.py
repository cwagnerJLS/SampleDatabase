import os
import re
import random
import logging
from datetime import datetime, timedelta
from django.utils import timezone
from django.utils.deconstruct import deconstructible
from celery import chain

# Configure logging
logger = logging.getLogger(__name__)
from django.db import models
from django.core.files.storage import FileSystemStorage
from django.conf import settings
from samples.services.opportunity_service import OpportunityService

class Opportunity(models.Model):
    opportunity_number = models.CharField(max_length=255, unique=True)
    new = models.BooleanField(default=False)
    sample_ids = models.TextField(blank=True)  # Do not set null=True
    update = models.BooleanField(default=True)
    
    # Add these fields:
    customer = models.CharField(max_length=255, blank=True, null=True)
    rsm = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    date_received = models.DateField(blank=True, null=True)
    sample_info_url = models.URLField(blank=True, null=True)
    sample_info_id = models.CharField(max_length=255, blank=True, null=True)
    
    # Export tracking fields
    export_count = models.IntegerField(default=0)
    last_export_date = models.DateTimeField(blank=True, null=True)
    first_export_date = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return self.opportunity_number

    def get_sample_ids(self):
        return list(Sample.objects.filter(opportunity_number=self.opportunity_number).values_list('unique_id', flat=True))

@deconstructible
class CustomFileSystemStorage(FileSystemStorage):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('location', settings.MEDIA_ROOT)
        kwargs.setdefault('base_url', settings.MEDIA_URL)
        super().__init__(*args, **kwargs)

    def get_valid_name(self, name):
        import os
        dir_name, base_name = os.path.split(name)
        s = str(base_name).strip().replace(' ', '_')
        base_name = re.sub(r'(?u)[^-\w.()]+', '', s)
        return os.path.join(dir_name, base_name)

class FullSizeImageStorage(CustomFileSystemStorage):
    def __init__(self, *args, **kwargs):
        kwargs['location'] = settings.MEDIA_ROOT
        kwargs['base_url'] = settings.MEDIA_URL
        super().__init__(*args, **kwargs)

def generate_unique_id():
    return random.randint(1000, 9999)

class Sample(models.Model):
    unique_id = models.PositiveIntegerField(unique=True, editable=False)
    date_received = models.DateField()
    customer = models.CharField(max_length=255)
    opportunity_number = models.CharField(max_length=255)
    rsm = models.CharField(max_length=255)
    storage_location = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        choices=[
            ('Cooler #2', 'Cooler #2'),
            ('Freezer #5', 'Freezer #5'),
            ('Freezer #9', 'Freezer #9'),
            ('Walk-in Fridge', 'Walk-in Fridge'),
            ('Walk-in Freezer', 'Walk-in Freezer'),
            ('Dry Food Storage', 'Dry Food Storage'),
            ('Empty Case Storage', 'Empty Case Storage'),
        ]
    )
    quantity = models.IntegerField(default=1)
    description = models.TextField(default="No description")
    audit = models.BooleanField(default=False)
    apps_eng = models.CharField(max_length=255, blank=True, null=True, default="")
    
    # Audit tracking fields
    location_assigned_date = models.DateTimeField(blank=True, null=True)
    audit_due_date = models.DateField(blank=True, null=True)
    last_audit_date = models.DateTimeField(blank=True, null=True)
    
    # User tracking fields
    created_by = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    modified_by = models.CharField(max_length=100, blank=True, null=True)
    modified_at = models.DateTimeField(auto_now=True, null=True)

    def calculate_audit_due_date(self, from_date=None):
        """Calculate audit due date based on storage location"""
        if not self.storage_location:
            return None
            
        if from_date is None:
            from_date = timezone.now()
            
        # Define audit periods for each location type
        audit_periods = {
            'Cooler #2': timedelta(weeks=3),
            'Test Lab Fridge': timedelta(weeks=3),  # Legacy support
            'Walk-in Fridge': timedelta(weeks=3),
            'Freezer #5': timedelta(weeks=8),
            'Freezer #9': timedelta(weeks=8),
            'Test Lab Freezer': timedelta(weeks=8),  # Legacy support
            'Walk-in Freezer': timedelta(weeks=8),
            'Dry Food Storage': timedelta(weeks=8),
            'Empty Case Storage': timedelta(weeks=8),
        }
        
        period = audit_periods.get(self.storage_location)
        if period:
            return (from_date + period).date()
        return None

    def update_location_tracking(self):
        """Update location tracking dates when location changes"""
        if self.storage_location:
            # Set location assigned date to now
            self.location_assigned_date = timezone.now()
            # Calculate audit due date
            self.audit_due_date = self.calculate_audit_due_date()
        else:
            # Clear dates if no location
            self.location_assigned_date = None
            self.audit_due_date = None

    def perform_audit(self):
        """Mark sample as audited and reset audit due date"""
        self.last_audit_date = timezone.now()
        self.audit = True
        # Reset audit due date from today
        if self.storage_location:
            self.audit_due_date = self.calculate_audit_due_date()

    def is_audit_overdue(self):
        """Check if audit is overdue"""
        if not self.audit_due_date:
            return False
        return timezone.now().date() > self.audit_due_date

    def days_until_audit(self):
        """Calculate days until audit is due (negative if overdue)"""
        if not self.audit_due_date:
            return None
        delta = self.audit_due_date - timezone.now().date()
        return delta.days

    def save(self, *args, **kwargs):
        # Get existing sample IDs from the Opportunity
        try:
            opportunity = Opportunity.objects.get(opportunity_number=self.opportunity_number)
            existing_sample_ids = opportunity.sample_ids.split(',') if opportunity.sample_ids else []
        except Opportunity.DoesNotExist:
            existing_sample_ids = []

        if not self.unique_id:
            for _ in range(100):
                self.unique_id = generate_unique_id()
                if (
                    not Sample.objects.filter(unique_id=self.unique_id).exists() and
                    str(self.unique_id) not in existing_sample_ids
                ):
                    break
            else:
                raise ValueError("Could not generate a unique ID after 100 attempts.")
        is_new = self.pk is None  # Check if the sample is new
        super().save(*args, **kwargs)

        # Update Opportunity's sample_ids field after the sample has been saved
        opportunity, created = Opportunity.objects.get_or_create(
            opportunity_number=self.opportunity_number
        )

        if created:
            opportunity.new = True  # Set 'new' to True
            opportunity.sample_ids = str(self.unique_id)
            opportunity.update = True
            opportunity.save()
        else:
            # Use the service to add the sample ID
            OpportunityService.add_sample_ids(opportunity, [str(self.unique_id)])

    def delete(self, *args, update_opportunity=True, **kwargs):
        opportunity_number = self.opportunity_number  # Store before deletion

        sample_unique_id = str(self.unique_id)  # Store the unique_id as a string

        # Delete the sample from the database
        super().delete(*args, **kwargs)

        if update_opportunity:
            try:
                opportunity = Opportunity.objects.get(opportunity_number=opportunity_number)

                # Use the service to remove the sample ID
                OpportunityService.remove_sample_id(opportunity, sample_unique_id)

                # Check if the opportunity should be archived
                if OpportunityService.should_archive(opportunity):

                    # Import tasks locally to avoid circular import
                    from .tasks import (
                        update_documentation_excels,
                        move_documentation_to_archive_task,
                        set_opportunity_update_false
                    )
                    from celery import chain

                    # Chain the tasks to ensure sequential execution
                    logger.info(f"Initiating task chain for opportunity {opportunity_number}")
                    task_chain = chain(
                        update_documentation_excels.si(opportunity_number),
                        move_documentation_to_archive_task.si(opportunity_number),
                        set_opportunity_update_false.si(opportunity_number)
                    )
                    task_chain.delay()
                else:
                    # If samples remain, update the documentation and reset the update flag
                    from .tasks import update_documentation_excels, set_opportunity_update_false
                    from celery import chain

                    # Create a task chain to update documentation and reset the update flag
                    logger.info(f"Updating documentation for opportunity {opportunity_number} after deleting sample.")
                    task_chain = chain(
                        update_documentation_excels.si(opportunity_number),
                        set_opportunity_update_false.si(opportunity_number)
                    )
                    task_chain.delay()
            except Opportunity.DoesNotExist:
                pass

def get_image_upload_path(instance, filename):
    opportunity_number = str(instance.sample.opportunity_number)
    return os.path.join('Thumbnails', opportunity_number, filename)

def get_full_size_image_upload_path(instance, filename):
    opportunity_number = str(instance.sample.opportunity_number)
    return os.path.join('Full Size Images', opportunity_number, filename)

class SampleImage(models.Model):
    sample = models.ForeignKey(Sample, related_name='images', on_delete=models.SET_NULL, null=True, blank=True)
    # Thumbnail image field
    image = models.ImageField(
        upload_to=get_image_upload_path,  # Correct function for thumbnails
        storage=CustomFileSystemStorage()
    )
    # Full-size image field
    full_size_image = models.ImageField(
        upload_to=get_full_size_image_upload_path,  # Correct function for full-size images
        storage=FullSizeImageStorage(),
        null=True,  # Allow null for existing records
        blank=True
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def delete(self, *args, **kwargs):
        # Ensure the local thumbnail file is removed
        if self.image and self.image.storage.exists(self.image.name):
            self.image.delete(save=False)
        # Ensure the local full-size file is removed
        if self.full_size_image and self.full_size_image.storage.exists(self.full_size_image.name):
            self.full_size_image.delete(save=False)

        super().delete(*args, **kwargs)

        # Optionally remove empty directories, like in remove_from_inventory()
        thumbnail_dir = os.path.dirname(self.image.path) if self.image else None
        full_size_dir = os.path.dirname(self.full_size_image.path) if self.full_size_image else None

        def remove_if_empty(directory):
            if directory and os.path.isdir(directory) and not os.listdir(directory):
                os.rmdir(directory)

        remove_if_empty(thumbnail_dir)
        remove_if_empty(full_size_dir)


class ActivityLog(models.Model):
    """Model to track all user activities in the system"""
    
    # Action type choices
    ACTION_CHOICES = [
        # Sample operations
        ('SAMPLE_CREATE', 'Sample Created'),
        ('SAMPLE_UPDATE', 'Sample Updated'),
        ('SAMPLE_DELETE', 'Sample Deleted'),
        ('SAMPLE_REMOVE', 'Sample Removed from Inventory'),
        ('SAMPLE_AUDIT', 'Sample Audited'),
        ('LOCATION_CHANGE', 'Location Changed'),
        
        # Bulk operations
        ('BULK_AUDIT', 'Bulk Audit'),
        ('BULK_DELETE', 'Bulk Delete'),
        ('BULK_LOCATION', 'Bulk Location Update'),
        ('BULK_REMOVE', 'Bulk Remove from Inventory'),
        
        # Document operations
        ('IMAGE_UPLOAD', 'Image Uploaded'),
        ('IMAGE_DELETE', 'Image Deleted'),
        ('EXPORT', 'Data Exported'),
        ('PRINT_LABEL', 'Label Printed'),
        
        # System events
        ('USER_LOGIN', 'User Identified'),
        ('PAGE_VIEW', 'Page Viewed'),
        ('SEARCH', 'Search Performed'),
        ('ERROR', 'Operation Failed'),
    ]
    
    STATUS_CHOICES = [
        ('SUCCESS', 'Success'),
        ('FAILED', 'Failed'),
        ('PARTIAL', 'Partial Success'),
    ]
    
    # Core fields
    user = models.CharField(max_length=100, db_index=True)
    action = models.CharField(max_length=50, choices=ACTION_CHOICES, db_index=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='SUCCESS')
    
    # Request information
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)
    
    # Object reference (generic to handle different object types)
    object_type = models.CharField(max_length=50, blank=True, null=True)
    object_id = models.CharField(max_length=100, blank=True, null=True)
    
    # Sample-related information
    customer = models.CharField(max_length=200, blank=True, null=True, db_index=True)
    opportunity = models.CharField(max_length=50, blank=True, null=True, db_index=True)
    
    # Detailed information
    changes = models.JSONField(blank=True, null=True)  # Store before/after values
    details = models.TextField(blank=True, null=True)  # Human-readable description
    error_message = models.TextField(blank=True, null=True)
    
    # Additional context
    affected_count = models.IntegerField(default=1)  # For bulk operations
    session_id = models.CharField(max_length=100, blank=True, null=True)
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['-timestamp', 'user']),
            models.Index(fields=['action', '-timestamp']),
            models.Index(fields=['object_type', 'object_id']),
        ]
        verbose_name = 'Activity Log'
        verbose_name_plural = 'Activity Logs'
    
    def __str__(self):
        return f"{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')} | {self.user} | {self.get_action_display()}"
    
    def get_object_link(self):
        """Generate a link to the affected object if possible"""
        if self.object_type == 'Sample' and self.object_id:
            return f"/manage_sample/{self.object_id}/"
        return None
    
    @classmethod
    def cleanup_old_logs(cls, days=90):
        """Remove logs older than specified days"""
        cutoff_date = timezone.now() - timedelta(days=days)
        return cls.objects.filter(timestamp__lt=cutoff_date).delete()
