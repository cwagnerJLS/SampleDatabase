import os
import re
import random
import shutil
import logging
from django.utils.deconstruct import deconstructible

# Configure logging
logger = logging.getLogger(__name__)
from django.db import models
from django.core.files.storage import FileSystemStorage
from django.conf import settings

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
            else:
                raise ValueError("Could not generate a unique ID after 100 attempts.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        opportunity_number = self.opportunity_number

        # Call the superclass delete method to delete the database record
        super().delete(*args, **kwargs)

        # Check if any samples remain with the same opportunity number
        if not Sample.objects.filter(opportunity_number=opportunity_number).exists():
            dir_path = os.path.join(settings.BASE_DIR, 'OneDrive_Sync', opportunity_number)
            if os.path.exists(dir_path):
                try:
                    shutil.rmtree(dir_path)
                    logger.debug(f"Deleted directory for opportunity number {opportunity_number}")
                except Exception as e:
                    logger.error(f"Error deleting directory {dir_path}: {e}")

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
