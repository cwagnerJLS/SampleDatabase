import os
import re
import random
import logging
from django.utils.deconstruct import deconstructible
from celery import chain

def delete_documentation_from_sharepoint(opportunity_number):
    import subprocess
    import logging
    logger = logging.getLogger(__name__)

    # Construct the path to the opportunity directory on SharePoint
    # Remote name is 'TestLabSamples', folders are named after the opportunity number
    remote_folder_path = f"TestLabSamples:{opportunity_number}"

    # Command to delete the file using rclone
    try:
        subprocess.run(['rclone', 'purge', remote_folder_path], check=True)
        logger.info(f"Deleted opportunity directory from SharePoint: {remote_folder_path}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to delete opportunity directory from SharePoint: {e}")

def delete_local_opportunity_folder(opportunity_number):
    import shutil
    import logging
    logger = logging.getLogger(__name__)

    # Clean up thumbnails
    thumbnail_folder_path = os.path.join(settings.BASE_DIR, 'media', 'Thumbnails', opportunity_number)
    if os.path.exists(thumbnail_folder_path):
        try:
            shutil.rmtree(thumbnail_folder_path)
            logger.info(f"Deleted local thumbnail folder: {thumbnail_folder_path}")
        except Exception as e:
            logger.error(f"Failed to delete local thumbnail folder: {e}")
    else:
        logger.warning(f"Local thumbnail folder does not exist: {thumbnail_folder_path}")

    # Clean up full-size images
    fullsize_folder_path = os.path.join(settings.BASE_DIR, 'media', 'Full Size Images', opportunity_number)
    if os.path.exists(fullsize_folder_path):
        try:
            shutil.rmtree(fullsize_folder_path)
            logger.info(f"Deleted local full-size image folder: {fullsize_folder_path}")
        except Exception as e:
            logger.error(f"Failed to delete local full-size image folder: {e}")
    else:
        logger.warning(f"Local full-size image folder does not exist: {fullsize_folder_path}")

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
    
    # Add these fields:
    customer = models.CharField(max_length=255, blank=True, null=True)
    rsm = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    date_received = models.DateField(blank=True, null=True)

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
    apps_eng = models.CharField(max_length=255, blank=True, null=True, default="")

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
        else:
            # Append the new sample's unique_id to sample_ids
            sample_ids = opportunity.sample_ids.split(',') if opportunity.sample_ids else []
            if str(self.unique_id) not in sample_ids:
                sample_ids.append(str(self.unique_id))
                opportunity.sample_ids = ','.join(sample_ids)
        opportunity.update = True  # Set the 'update' field to True
        opportunity.save()

    def delete(self, *args, update_opportunity=True, **kwargs):
        opportunity_number = self.opportunity_number  # Store before deletion

        sample_unique_id = str(self.unique_id)  # Store the unique_id as a string

        # Delete the sample from the database
        super().delete(*args, **kwargs)

        if update_opportunity:
            try:
                opportunity = Opportunity.objects.get(opportunity_number=opportunity_number)

                # Retrieve the current sample_ids from the Opportunity
                sample_ids = opportunity.sample_ids.split(',') if opportunity.sample_ids else []

                # Remove the unique_id of the deleted sample from the list
                if sample_unique_id in sample_ids:
                    sample_ids.remove(sample_unique_id)

                # Update the sample_ids field
                opportunity.sample_ids = ','.join(sample_ids)

                # Mark the opportunity as needing an update
                opportunity.update = True

                opportunity.save()

                # If no samples remain, proceed to archive the opportunity
                if not sample_ids:

                    # Import tasks locally to avoid circular import
                    from .tasks import (
                        update_documentation_excels,
                        move_documentation_to_archive_task,
                        delete_local_opportunity_folder_task,
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

    def remove_from_inventory(self):
        # Capture the image names before deletion
        image_name = self.image.name if self.image else None
        full_size_image_name = self.full_size_image.name if self.full_size_image else None

        # Get the directory paths before deleting
        thumbnail_dir = os.path.dirname(self.image.path) if self.image else None
        full_size_dir = os.path.dirname(self.full_size_image.path) if self.full_size_image else None

        # Delete the thumbnail image from storage
        if self.image and self.image.storage.exists(self.image.name):
            self.image.delete(save=False)

        # Delete the full-size image from storage
        if self.full_size_image and self.full_size_image.storage.exists(self.full_size_image.name):
            self.full_size_image.delete(save=False)

        super().delete()

        # Function to check and delete directory if empty
        def remove_if_empty(directory):
            if directory and os.path.isdir(directory) and not os.listdir(directory):
                try:
                    os.rmdir(directory)
                    logger.info(f"Removed empty directory: {directory}")
                except Exception as e:
                    logger.error(f"Error removing directory {directory}: {e}")
                    logger.exception(e)

        # Remove directories if they are empty
        remove_if_empty(thumbnail_dir)
        remove_if_empty(full_size_dir)
