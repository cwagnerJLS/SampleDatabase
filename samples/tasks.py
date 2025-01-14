from celery import shared_task
from django.core.files.base import ContentFile
import os
from .models import SampleImage, get_image_upload_path, Sample
from .email_utils import send_email, get_rsm_email, NICKNAMES, TEST_LAB_GROUP
import logging
from .EditExcelSharepoint import (
    get_access_token,
    find_excel_file,
    get_cell_value,
    update_cell_value,
    get_existing_ids_from_workbook,
    append_rows_to_workbook
)

logger = logging.getLogger(__name__)

@shared_task
def update_documentation_excels():
    logger.info("Starting update_documentation_excels task.")
    try:
        token = get_access_token()
        logger.debug(f"Access token acquired: {token}")
        if not token:
            logger.error("Failed to acquire access token.")
            return

        library_id = "b!X3Eb6X7EmkGXMLnZD4j_mJuFfGH0APlLs0IrZrwqabH6SO1yJ5v6TYCHXT-lTWgj"
        logger.debug(f"Using library_id: {library_id}")

        opportunity_numbers = Sample.objects.values_list('opportunity_number', flat=True).distinct()
        logger.info(f"Found opportunity_numbers: {list(opportunity_numbers)}")

        for opportunity_number in opportunity_numbers:
            logger.info(f"Processing opportunity number: {opportunity_number}")

            excel_file_id = find_excel_file(token, library_id, opportunity_number)
            logger.debug(f"Excel file ID for {opportunity_number}: {excel_file_id}")
            if not excel_file_id:
                logger.warning(f"No Excel file found for opportunity number {opportunity_number}. Skipping.")
                logger.info(f"No Excel file found for opportunity number {opportunity_number}. Skipping.")
                continue

            worksheet_name = 'Sheet1'

            cells_to_check = {
                'B1': 'customer',
                'B2': 'rsm',
                'B3': 'opportunity_number',
                'B4': 'description',
            }

            sample = Sample.objects.filter(opportunity_number=opportunity_number).first()
            if not sample:
                logger.warning(f"No samples found for opportunity number {opportunity_number}.")
                continue

            for cell_address, model_field in cells_to_check.items():
                cell_value = get_cell_value(token, library_id, excel_file_id, worksheet_name, cell_address)
                logger.debug(f"Cell {cell_address} current value: {cell_value}")
                if not cell_value:
                    value_to_write = getattr(sample, model_field)
                    update_cell_value(token, library_id, excel_file_id, worksheet_name, cell_address, value_to_write)
                    logger.info(f"Updated cell {cell_address} with value '{value_to_write}'.")
                    value_to_write = getattr(sample, model_field)
                    update_cell_value(token, library_id, excel_file_id, worksheet_name, cell_address, value_to_write)
                    logger.info(f"Updated cell {cell_address} with value '{value_to_write}'.")
                else:
                    logger.info(f"Cell {cell_address} already has value '{cell_value}'. Skipping.")

            existing_ids = get_existing_ids_from_workbook(token, library_id, excel_file_id, worksheet_name, start_row=8)
            logger.debug(f"Existing IDs in worksheet: {existing_ids}")

            samples = Sample.objects.filter(opportunity_number=opportunity_number)
            rows_to_append = []

            for s in samples:
                if str(s.unique_id) not in existing_ids:
                    row = [s.unique_id, s.date_received.strftime('%Y-%m-%d')]
                    rows_to_append.append(row)
                    logger.info(f"Prepared to append row: {row}")
                else:
                    logger.info(f"Sample ID {s.unique_id} already exists in worksheet. Skipping.")

            if rows_to_append:
                start_row = 8 + len(existing_ids)
                start_cell = f"A{start_row}"
                append_rows_to_workbook(token, library_id, excel_file_id, worksheet_name, start_cell, rows_to_append)
                logger.info(f"Appended {len(rows_to_append)} rows to the workbook.")
            else:
                logger.info("No new rows to append.")

    except Exception as e:
        logger.error(f"An error occurred in update_documentation_excels task: {e}")

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
            send_email(subject, body, recipient_email, cc_emails=TEST_LAB_GROUP)
            logger.info(f"Email sent to {recipient_email} regarding samples for opportunity number {opportunity_number}")
        else:
            logger.error(f"Failed to generate email address for RSM '{rsm_full_name}'. Email not sent.")
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
