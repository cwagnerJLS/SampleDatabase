import os
import re
import random
import shutil
import logging
import subprocess
from django.utils.deconstruct import deconstructible

# Configure logging
logger = logging.getLogger(__name__)
from django.db import models
from django.core.files.storage import FileSystemStorage
from django.conf import settings

class Opportunity(models.Model):
    opportunity_number = models.CharField(max_length=255, unique=True)
    new = models.BooleanField(default=False)
    sample_ids = models.TextField(blank=True)  # Do not set null=True
    update = models.BooleanField(default=True)

    def __str__(self):
        return self.opportunity_number

    def get_sample_ids(self):
        return list(Sample.objects.filter(opportunity_number=self.opportunity_number).values_list('unique_id', flat=True))

@deconstructible
class CustomFileSystemStorage(FileSystemStorage):
    def get_valid_name(self, name):
        import os  # Add this import at the top if not already present
        # Split the path into directory and filename
        dir_name, base_name = os.path.split(name)
        # Sanitize the base filename
        s = str(base_name).strip().replace(' ', '_')
        base_name = re.sub(r'(?u)[^-\w.()]+', '', s)
        # Reconstruct the full path
        return os.path.join(dir_name, base_name)

class FullSizeImageStorage(CustomFileSystemStorage):
    def __init__(self, *args, **kwargs):
        location = os.path.join(settings.BASE_DIR, 'OneDrive_Sync')
        base_url = '/onedrive_media/'
        super().__init__(location=location, base_url=base_url, *args, **kwargs)

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
            ('Test Lab Fridge', 'Test Lab Fridge'),
            ('Test Lab Freezer', 'Test Lab Freezer'),
            ('Walk-in Fridge', 'Walk-in Fridge'),
            ('Walk-in Freezer', 'Walk-in Freezer'),
            ('Dry Food Storage', 'Dry Food Storage'),
            ('Empty Case Storage', 'Empty Case Storage'),
        ]
    )
    quantity = models.IntegerField(default=1)
    description = models.TextField(default="No description")
    audit = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.unique_id:
            for _ in range(100):
                self.unique_id = generate_unique_id()
                if not Sample.objects.filter(unique_id=self.unique_id).exists():
                    break
                opportunity.update = True  # Set 'update' to True
            else:
                raise ValueError("Could not generate a unique ID after 100 attempts.")
        is_new = self.pk is None  # Check if the sample is new
        if not self.unique_id:
            for _ in range(100):
                self.unique_id = generate_unique_id()
                if not Sample.objects.filter(unique_id=self.unique_id).exists():
                    break
            else:
                raise ValueError("Could not generate a unique ID after 100 attempts.")
        super().save(*args, **kwargs)

        # Update Opportunity's sample_ids field after the sample has been saved
        opportunity, created = Opportunity.objects.get_or_create(
            opportunity_number=self.opportunity_number
        )

        if created:
            opportunity.new = True  # Set 'new' to True
            opportunity.sample_ids = str(self.unique_id)
        else:
            # Append the new sample's unique_id to sample_ids
            sample_ids = opportunity.sample_ids.split(',') if opportunity.sample_ids else []
            if str(self.unique_id) not in sample_ids:
                sample_ids.append(str(self.unique_id))
                opportunity.sample_ids = ','.join(sample_ids)
        opportunity.update = True  # Set the 'update' field to True
        opportunity.update = True  # Set 'update' to True
        opportunity.update = True  # Set 'update' to True
        opportunity.save()

    def delete(self, *args, **kwargs):
        opportunity_number = self.opportunity_number
        super().delete(*args, **kwargs)

        # Update Opportunity's sample_ids field
        try:
            opportunity = Opportunity.objects.get(opportunity_number=opportunity_number)
            # Retrieve all unique IDs associated with this opportunity
            sample_ids = Sample.objects.filter(
                opportunity_number=opportunity_number
            ).values_list('unique_id', flat=True)

            if sample_ids:
                # Update the sample_ids field
                opportunity.sample_ids = ','.join(map(str, sample_ids))
                opportunity.save()
            else:
                # If no samples remain, delete the Opportunity entry
                opportunity.delete()
                opportunity = None  # Set opportunity to None since it's deleted
        except Opportunity.DoesNotExist:
            pass  # Opportunity might have been deleted already
            opportunity = None  # Opportunity might have been deleted already
            pass  # Opportunity might have been deleted already

        # Update Opportunity's sample_ids field
        try:
            opportunity = Opportunity.objects.get(opportunity_number=opportunity_number)
            # Retrieve all unique IDs associated with this opportunity
            sample_ids = Sample.objects.filter(
                opportunity_number=opportunity_number
            ).values_list('unique_id', flat=True)

            if sample_ids:
                # Update the sample_ids field
                opportunity.sample_ids = ','.join(map(str, sample_ids))
                opportunity.save()
            else:
                # If no samples remain, delete the Opportunity entry
                opportunity.delete()
        except Opportunity.DoesNotExist:
            pass  # Opportunity might have been deleted already

def get_image_upload_path(instance, filename):
    opportunity_number = str(instance.sample.opportunity_number)
    return os.path.join(opportunity_number, filename)

def get_full_size_image_upload_path(instance, filename):
    opportunity_number = str(instance.sample.opportunity_number)
    return os.path.join(opportunity_number, filename)

class SampleImage(models.Model):
    sample = models.ForeignKey(Sample, related_name='images', on_delete=models.CASCADE)
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
        # Get the directory paths for both images before deleting
        thumbnail_dir = os.path.dirname(self.image.path) if self.image else None
        full_size_dir = os.path.dirname(self.full_size_image.path) if self.full_size_image else None

        # Delete the thumbnail image from storage
        if self.image and self.image.storage.exists(self.image.name):
            self.image.delete(save=False)
        # Delete the full-size image from storage
        if self.full_size_image and self.full_size_image.storage.exists(self.full_size_image.name):
            self.full_size_image.delete(save=False)

        # Call the superclass delete method to delete the database record
        super().delete(*args, **kwargs)

        # Function to check and delete directory if empty
        def remove_if_empty(directory):
            if directory and os.path.isdir(directory) and not os.listdir(directory):
                try:
                    os.rmdir(directory)
                except Exception:
                    pass  # You might want to log this exception

        # Remove directories if they are empty
        remove_if_empty(thumbnail_dir)
        remove_if_empty(full_size_dir)
