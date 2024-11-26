from celery import shared_task
from django.core.files.base import ContentFile
import os
from .models import SampleImage, get_image_upload_path
import logging

logger = logging.getLogger(__name__)

@shared_task
def save_full_size_image(sample_image_id, temp_file_path):
    try:
        # Retrieve the SampleImage instance
        sample_image = SampleImage.objects.get(id=sample_image_id)
        sample = sample_image.sample

        # Generate the filename using the same convention
        image_count = SampleImage.objects.filter(sample=sample).count()
        filename = f"{sample.unique_id}({image_count}).jpg"

        # Determine the upload path
        upload_path = get_image_upload_path(sample_image, filename)

        # Read the binary data from the temporary file
        with open(temp_file_path, 'rb') as f:
            file_data = f.read()

        # Create a ContentFile from the binary data
        full_size_image_content = ContentFile(file_data)

        # Save the full-size image using the storage backend
        sample_image.full_size_image.save(upload_path, full_size_image_content)
        sample_image.save()

        logger.info(f"Full-size image saved for SampleImage ID {sample_image_id}")

    except SampleImage.DoesNotExist:
        logger.error(f"SampleImage with ID {sample_image_id} does not exist.")
    except Exception as e:
        logger.error(f"Error saving full-size image for SampleImage ID {sample_image_id}: {e}")
    finally:
        # Delete the temporary file
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
            logger.info(f"Temporary file {temp_file_path} deleted.")
