from celery import shared_task
from django.core.files.base import ContentFile
import os
from .models import SampleImage, get_image_upload_path
from .email_utils import send_email, get_rsm_email, NICKNAMES  # Import NICKNAMES
import logging

logger = logging.getLogger(__name__)

@shared_task
def save_full_size_image(sample_image_id, temp_file_path):
    try:
        # Retrieve the SampleImage instance
        sample_image = SampleImage.objects.get(id=sample_image_id)
        sample = sample_image.sample

        # Extract the base filename from the thumbnail image name
        thumbnail_filename = os.path.basename(sample_image.image.name)

        # Use the same filename for the full-size image
        filename = thumbnail_filename

        # Read the binary data from the temporary file
        with open(temp_file_path, 'rb') as f:
            file_data = f.read()

        # Create a ContentFile from the binary data
        full_size_image_content = ContentFile(file_data)

        # Save the full-size image using just the filename
        sample_image.full_size_image.save(filename, full_size_image_content)
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

@shared_task
def test_task():
    logger.info("Test task executed successfully.")
    return "Success"

@shared_task
def send_sample_received_email(rsm_full_name, date_received, opportunity_number, customer, quantity):
    try:
        # Extract the first name from the full name
        first_name = rsm_full_name.strip().split()[0]

        # Determine the greeting name (use nickname if available)
        greeting_name = NICKNAMES.get(rsm_full_name, first_name)
        subject = f'{opportunity_number} ({customer}) Samples Received'
        
        body = f"""
        <html>
            <body>
                <p>Hello {greeting_name},</p>
                <p>{quantity} sample(s) for opportunity number {opportunity_number} ({customer}) were received on {date_received}. They will be documented and uploaded to the opportunity folder on Sharepoint shortly. Thanks,</p>
                <p>-Test Lab</p>
            </body>
        </html>
        """
        recipient_email = get_rsm_email(rsm_full_name)
        if recipient_email:
            send_email(subject, body, recipient_email)
            logger.info(f"Email sent to {recipient_email} regarding samples for opportunity number {opportunity_number}")
        else:
            logger.error(f"Failed to generate email address for RSM '{rsm_full_name}'. Email not sent.")
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
