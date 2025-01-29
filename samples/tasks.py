from celery import shared_task
from django.core.files.base import ContentFile
import os
from .models import SampleImage, get_image_upload_path, Sample, Opportunity
from .email_utils import send_email, get_rsm_email, NICKNAMES, TEST_LAB_GROUP
import logging
from .CreateOppFolderSharepoint import create_sharepoint_folder
from .utils import create_documentation_on_sharepoint
import subprocess
import shutil
import os

from .EditExcelSharepoint import (
    get_access_token,
    find_excel_file,
    get_cell_value,
    update_cell_value,
    append_rows_to_workbook,
    get_existing_ids_with_rows,
    clear_range_in_workbook,
    update_range_in_workbook,
    update_row_in_workbook,
    delete_rows_in_workbook
)

logger = logging.getLogger(__name__)

@shared_task
def create_sharepoint_folder_task(opportunity_number, customer, rsm, description):
    logger.info(f"Starting create_sharepoint_folder_task for opportunity {opportunity_number}")
    try:
        create_sharepoint_folder(
            opportunity_number=opportunity_number,
            customer=customer,
            rsm=rsm,
            description=description
        )
        logger.info(f"Successfully created SharePoint folder for opportunity {opportunity_number}")
    except Exception as e:
        logger.error(f"Error creating SharePoint folder for opportunity {opportunity_number}: {e}")

@shared_task
def create_documentation_on_sharepoint_task(opportunity_number):
    logger.info(f"Starting create_documentation_on_sharepoint_task for opportunity {opportunity_number}")
    try:
        create_documentation_on_sharepoint(opportunity_number)
        logger.info(f"Successfully copied documentation template to SharePoint for opportunity {opportunity_number}")
    except Exception as e:
        logger.error(f"Error copying documentation template to SharePoint for opportunity {opportunity_number}: {e}")
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

        opportunity_numbers = Opportunity.objects.values_list('opportunity_number', flat=True)
        logger.info(f"Found opportunity_numbers from Opportunity model: {list(opportunity_numbers)}")

        for opportunity_number in opportunity_numbers:
            logger.info(f"Processing opportunity number: {opportunity_number}")

            # Fetch the Opportunity object
            try:
                opportunity = Opportunity.objects.get(opportunity_number=opportunity_number)
            except Opportunity.DoesNotExist:
                logger.warning(f"Opportunity with number {opportunity_number} not found. Skipping.")
                continue

            # Check if either opportunity.new or opportunity.update is True
            if not opportunity.new and not opportunity.update:
                logger.info(
                    f"Opportunity {opportunity_number} has neither 'new' nor 'update' flags set. Skipping."
                )
                continue  # Skip to the next opportunity_number

            # Now, since either 'new' or 'update' is True, proceed to find the Excel file
            excel_file_id = find_excel_file(token, library_id, opportunity_number)
            logger.debug(f"Excel file ID for {opportunity_number}: {excel_file_id}")
            if not excel_file_id:
                logger.warning(f"No Excel file found for opportunity number {opportunity_number}. Skipping.")
                continue

            # Define worksheet_name
            worksheet_name = 'Sheet1'

            # Check if opportunity.new is True
            if opportunity.new:
                logger.info(f"Opportunity {opportunity_number} is new. Updating cells B1-B4.")

                # Use Opportunity data to update cells B1-B4
                cells_to_update = {
                    'B1': opportunity.customer or '',
                    'B2': opportunity.rsm or '',
                    'B3': opportunity.opportunity_number,
                    'B4': opportunity.description or '',
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
                sample_ids = set(filter(None, [s.strip() for s in opportunity.sample_ids.split(',')])) if opportunity.sample_ids else set()
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
                    # Build the list of rows to write to Excel sheet
                    rows_to_write = []
                    for sample_id in sorted(sample_ids):
                        try:
                            sample = Sample.objects.get(unique_id=sample_id)
                            date_received = sample.date_received.strftime('%Y-%m-%d')
                        except Sample.DoesNotExist:
                            logger.warning(f"Sample with unique_id {sample_id} does not exist. Skipping.")
                            continue
                        row = [sample_id, date_received]
                        rows_to_write.append(row)

                    # Clear existing data from Excel
                    start_row = 8
                    end_row = start_row + max(len(existing_ids), len(rows_to_write)) + 100  # Clear extra rows to be safe
                    range_to_clear = f"A{start_row}:B{end_row}"
                    clear_range_in_workbook(token, library_id, excel_file_id, worksheet_name, range_to_clear)
                    logger.info(f"Cleared existing data in range {range_to_clear}")

                    # Write the new data to Excel
                    if rows_to_write:
                        update_range_in_workbook(token, library_id, excel_file_id, worksheet_name, start_row, rows_to_write)
                        logger.info(f"Updated Excel sheet with new data starting from row {start_row}")
                    else:
                        logger.info("No data to write to Excel.")

                # Clear existing data if no sample IDs
                if not sample_ids:
                    start_row = 8
                    end_row = start_row + max(len(existing_ids), 100)  # Adjust the number as needed
                    range_to_clear = f"A{start_row}:B{end_row}"
                    clear_range_in_workbook(token, library_id, excel_file_id, worksheet_name, range_to_clear)
                    logger.info(f"Cleared existing data in range {range_to_clear} because there are no sample IDs.")

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
        
        url = f"https://jlsautomation.sharepoint.com/sites/TestEngineering/Test%20Engineering/{opportunity_number}/Samples"
        body = f"""
        <html>
            <body>
                <p>Hello {greeting_name},</p>
                <p>{quantity} sample(s) for opportunity number {opportunity_number} ({customer}) were received on {date_received}. They will be documented and uploaded to the opportunity folder on SharePoint shortly. You can access the sample documentation <a href="{url}">here</a>.</p>
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
@shared_task
def upload_full_size_images_to_sharepoint(sample_image_ids):
    logger.info(f"Environment variables in Celery worker: {os.environ}")
    path_env = os.environ.get('PATH', '')
    logger.info(f"Celery worker PATH environment variable: {path_env}")

    # Attempt to find rclone in PATH
    rclone_path = shutil.which('rclone')
    logger.info(f"rclone found at: {rclone_path}")
    if not rclone_path:
        logger.error("rclone executable not found in PATH.")

    rclone_executable = rclone_path or '/usr/local/bin/rclone'  # Replace with the actual path to rclone
        try:
            # Retrieve the SampleImage instance
            sample_image = SampleImage.objects.get(id=sample_image_id)

            # Define source and destination paths
            source_path = sample_image.full_size_image.path
            # Construct the destination path in SharePoint using the same relative path
            # Assuming 'TestLabSamples' is the rclone remote name
            destination_path = f"TestLabSamples:{sample_image.full_size_image.name}"

            # Log the paths
            logger.info(f"Uploading image {sample_image_id} from {source_path} to {destination_path}")

            # Copy the full-size image to SharePoint
            result = subprocess.run(
                [rclone_executable, 'copy', source_path, destination_path],
                check=True,
                capture_output=True,
                text=True,
                env=os.environ
            )
            if result.stdout:
                logger.debug(f"rclone stdout: {result.stdout}")
            if result.stderr:
                logger.error(f"rclone stderr: {result.stderr}")
            subprocess.run(['rclone', 'copy', source_path, destination_path], check=True)
            logger.info(f"Copied full-size image {sample_image_id} to SharePoint: {destination_path}")

        except Exception as e:
            logger.error(f"Failed to upload image {sample_image_id} to SharePoint: {e}")
