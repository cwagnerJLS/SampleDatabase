from django.core.management.base import BaseCommand
from samples.models import SampleImage
from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image
import os
import logging
from io import BytesIO

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Generate missing thumbnails for SampleImages.'

    def handle(self, *args, **options):
        # Get all SampleImage instances
        sample_images = SampleImage.objects.all()

        for sample_image in sample_images:
            # Check if the thumbnail exists
            if not sample_image.image or not sample_image.image.storage.exists(sample_image.image.name):
                try:
                    # Generate the thumbnail
                    self.generate_thumbnail(sample_image)
                    logger.info(f"Generated thumbnail for SampleImage ID {sample_image.id}")
                except Exception as e:
                    logger.error(f"Failed to generate thumbnail for SampleImage ID {sample_image.id}: {e}")
            else:
                logger.debug(f"Thumbnail already exists for SampleImage ID {sample_image.id}")

    def generate_thumbnail(self, sample_image):
        # Ensure the full-size image exists
        if not sample_image.full_size_image or not sample_image.full_size_image.storage.exists(sample_image.full_size_image.name):
            raise FileNotFoundError("Full-size image not found.")

        # Open the full-size image
        full_size_path = sample_image.full_size_image.path
        with Image.open(full_size_path) as img:
            img = img.convert('RGB')  # Ensure image is in RGB mode

            # Create a thumbnail
            max_size = (200, 200)  # Desired thumbnail size
            img.thumbnail(max_size, resample=Image.LANCZOS)

            # Save the thumbnail to an in-memory file
            thumb_io = BytesIO()
            img.save(thumb_io, format='JPEG', quality=85)
            thumb_io.seek(0)  # Reset file pointer to the beginning

            # Create a ContentFile from the in-memory file
            thumbnail_content = ContentFile(thumb_io.read())

            # Define the thumbnail filename
            filename = os.path.basename(sample_image.full_size_image.name)

            # Save the thumbnail image to the `image` field
            sample_image.image.save(filename, thumbnail_content, save=False)

            # Save the SampleImage instance
            sample_image.save()
