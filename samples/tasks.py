from celery import shared_task
from django.core.files.base import ContentFile
import os
from .models import SampleImage, get_image_upload_path, Sample, Opportunity
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
                continue

            # Fetch the Opportunity object
            try:
                opportunity = Opportunity.objects.get(opportunity_number=opportunity_number)
            except Opportunity.DoesNotExist:
                logger.warning(f"Opportunity with number {opportunity_number} not found. Skipping.")
                continue

            # Define worksheet_name
            worksheet_name = 'Sheet1'

            # Check if opportunity.new is True
            if opportunity.new:
                logger.info(f"Opportunity {opportunity_number} is new. Updating cells B1-B4.")

                # Fetch a sample associated with this opportunity
                sample = Sample.objects.filter(opportunity_number=opportunity_number).first()
                if not sample:
                    logger.warning(f"No samples found for opportunity number {opportunity_number}.")
                    continue

                # Update cells B1-B4 with sample data
                cells_to_update = {
                    'B1': sample.customer,
                    'B2': sample.rsm,
                    'B3': sample.opportunity_number,
                    'B4': sample.description,
                }

                for cell_address, value_to_write in cells_to_update.items():
                    update_cell_value(token, library_id, excel_file_id, worksheet_name, cell_address, value_to_write)
                    logger.info(f"Updated cell {cell_address} with value '{value_to_write}'.")

                # After updating, set opportunity.new = False and save
                opportunity.new = False
                opportunity.save()
                logger.info(f"Set opportunity.new to False for {opportunity_number}.")
            else:
                logger.info(f"Opportunity {opportunity_number}'s 'new' flag is False. Skipping updating cells B1-B4.")
            if opportunity.update:
                logger.info(f"Opportunity {opportunity_number} 'update' flag is True. Updating cells A8 onward.")

                excel_file_id = find_excel_file(token, library_id, opportunity_number)
                logger.debug(f"Excel file ID for {opportunity_number}: {excel_file_id}")
                if not excel_file_id:
                    logger.warning(f"No Excel file found for opportunity number {opportunity_number}. Skipping.")
                    continue

                worksheet_name = 'Sheet1'

                # Get existing IDs from Excel starting from row 8, along with their row numbers
                existing_ids = get_existing_ids_with_rows(token, library_id, excel_file_id, worksheet_name, start_row=8)
                logger.debug(f"Existing IDs in worksheet: {existing_ids}")

                # Get the list of sample IDs from opportunity.sample_ids
                sample_ids = set(opportunity.sample_ids.split(',')) if opportunity.sample_ids else set()
                logger.debug(f"Sample IDs from opportunity.sample_ids: {sample_ids}")

                # Determine IDs to add and IDs to remove
                ids_in_excel = set(existing_ids.keys())
                ids_to_add = sample_ids - ids_in_excel
                ids_to_remove = ids_in_excel - sample_ids

                logger.info(f"IDs to add: {ids_to_add}")
                logger.info(f"IDs to remove: {ids_to_remove}")

                # Remove IDs from Excel sheet
                if ids_to_remove:
                    rows_to_delete = [existing_ids[id_to_remove] for id_to_remove in ids_to_remove]
                    delete_rows_in_workbook(token, library_id, excel_file_id, worksheet_name, rows_to_delete)
                    logger.info(f"Removed IDs from rows: {rows_to_delete}")

                # Add new IDs to Excel sheet
                if ids_to_add:
                    # Find the next empty row in column A starting from row 8
                    existing_row_numbers = existing_ids.values()
                    if existing_row_numbers:
                        next_row = max(existing_row_numbers) + 1
                    else:
                        next_row = 8
                    for id_to_add in ids_to_add:
                        try:
                            sample = Sample.objects.get(unique_id=id_to_add)
                            date_received = sample.date_received.strftime('%Y-%m-%d')
                        except Sample.DoesNotExist:
                            logger.warning(f"Sample with unique_id {id_to_add} does not exist. Skipping.")
                            continue
                        # Prepare row data
                        row_data = [id_to_add, date_received]
                        # Append the row to the worksheet
                        start_cell = f"A{next_row}"
                        update_row_in_workbook(token, library_id, excel_file_id, worksheet_name, start_cell, row_data)
                        logger.info(f"Appended row starting at {start_cell}: {row_data}")
                        next_row += 1
                else:
                    logger.info("No new IDs to add.")

                # After updating, set opportunity.update = False
                opportunity.update = False
                opportunity.save()
                logger.info(f"Set opportunity.update to False for {opportunity_number}.")

            else:
                logger.info(f"Opportunity {opportunity_number} 'update' flag is False. Skipping update for cells A8 onward.")

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
