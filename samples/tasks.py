from celery import shared_task
from django.core.files.base import ContentFile
from .email_utils import send_email, get_rsm_email, NICKNAMES, TEST_LAB_GROUP
import logging
from .CreateOppFolderSharepoint import create_sharepoint_folder
from .utils import create_documentation_on_sharepoint
import subprocess
import shutil
import os
from django.conf import settings
from .sharepoint_config import (
    TEST_ENGINEERING_LIBRARY_ID,
    SALES_ENGINEERING_LIBRARY_ID,
    GRAPH_API_URL,
    get_library_url
)

from .models import SampleImage

from .EditExcelSharepoint import (
    get_access_token,
    find_excel_file,
    update_cell_value,
    get_existing_ids_with_rows,
    clear_range_in_workbook,
    update_range_in_workbook,
    delete_rows_in_workbook
)

logger = logging.getLogger(__name__)

@shared_task
def create_sharepoint_folder_task(opportunity_number, customer, rsm, description):
    logger.info(f"Starting create_sharepoint_folder_task for opportunity {opportunity_number}")
    try:
        # Import models locally
        from .models import Opportunity

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
def delete_image_from_sharepoint(full_size_image_name, opportunity_number):
    logger.info(f"Starting task to delete image from SharePoint: {full_size_image_name}")
    if full_size_image_name:
        try:
            sharepoint_image_path = f"TestLabSamples:{opportunity_number}/Samples/{os.path.basename(full_size_image_name)}"
            rclone_executable = settings.RCLONE_EXECUTABLE
            logger.info(f"Using rclone executable at: {rclone_executable}")
            result = subprocess.run(
                [rclone_executable, 'delete', sharepoint_image_path],
                check=True,
                capture_output=True,
                text=True,
                env=os.environ
            )
            if result.stdout:
                logger.debug(f"rclone stdout: {result.stdout}")
            if result.stderr:
                logger.error(f"rclone stderr: {result.stderr}")
            logger.info(f"Deleted image from SharePoint: {sharepoint_image_path}")
        except Exception as e:
            logger.error(f"Failed to delete image from SharePoint: {e}")
            logger.exception(e)
    else:
        logger.error("No full_size_image_name provided to delete_image_from_sharepoint task")

@shared_task
def update_documentation_excels(opportunity_number=None):
    logger.info(f"Starting update_documentation_excels task for opportunity {opportunity_number if opportunity_number else 'all opportunities'}.")
    try:
        # Import models locally
        from .models import Opportunity, Sample

        token = get_access_token()
        logger.debug(f"Access token acquired: {token}")
        if not token:
            logger.error("Failed to acquire access token.")
            send_missing_sample_info_folder_email.delay(opportunity_number)
            return

        library_id = TEST_ENGINEERING_LIBRARY_ID
        logger.debug(f"Using library_id: {library_id}")

        if opportunity_number:
            # Process only the specified opportunity
            opportunity_numbers = [opportunity_number]
        else:
            # Process all opportunities
            opportunity_numbers = Opportunity.objects.values_list('opportunity_number', flat=True)

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

                # Build rows_to_write with *all* sample_ids, not just the new ones
                rows_to_write = []
                for sample_id in sorted(sample_ids):
                    try:
                        sample = Sample.objects.get(unique_id=sample_id)
                        date_received = sample.date_received.strftime('%Y-%m-%d')
                        rows_to_write.append([sample_id, date_received])
                    except Sample.DoesNotExist:
                        logger.warning(f"Sample with unique_id {sample_id} does not exist. Skipping.")


                # After that, append only the newly added IDs (ids_to_add) at the end
                if ids_to_add:
                    # Find the last used row in existing_ids (or 7 if there are none yet)
                    last_used_row = max(existing_ids.values()) if existing_ids else 7
                    start_row_for_new = last_used_row + 1

                    # Build rows_to_write with only the new IDs
                    rows_to_write = []
                    for sample_id in sorted(ids_to_add):
                        try:
                            sample = Sample.objects.get(unique_id=sample_id)
                            date_received = sample.date_received.strftime('%Y-%m-%d')
                            rows_to_write.append([sample_id, date_received])
                        except Sample.DoesNotExist:
                            logger.warning(f"Sample with unique_id {sample_id} does not exist. Skipping.")

                    if rows_to_write:
                        update_range_in_workbook(
                            token,
                            library_id,
                            excel_file_id,
                            worksheet_name,
                            start_row_for_new,
                            rows_to_write
                        )
                        logger.info(f"Appended {len(rows_to_write)} new rows starting at row {start_row_for_new}.")
                    else:
                        logger.info("No new rows to append.")


                # Set opportunity.update to False after updating documentation
                opportunity.update = False
                opportunity.save()
                logger.info(f"Set opportunity.update to False for {opportunity_number} after updating documentation.")

                # ONLY clear rows if there are no sample IDs left
                if not sample_ids:
                    start_row = 8
                    end_row = start_row + max(len(existing_ids), 100)
                    range_to_clear = f"A{start_row}:B{end_row}"
                    clear_range_in_workbook(token, library_id, excel_file_id, worksheet_name, range_to_clear)
                    logger.info(f"Cleared existing data in range {range_to_clear} because there are no sample IDs.")
                else:
                    logger.info("There are still sample IDs, so no final clearing is performed.")


            else:
                logger.info(f"Opportunity {opportunity_number} 'update' flag is False. Skipping update for cells A8 onward.")

    except Exception as e:
        logger.error(f"An error occurred in update_documentation_excels task: {e}")

@shared_task
def save_full_size_image(sample_image_id, temp_file_path):
    try:
        # Import models locally
        from .models import SampleImage

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
def send_documentation_completed_email(opportunity_number):
    from .models import Opportunity, Sample
    from .email_utils import send_email, get_rsm_email, NICKNAMES, TEST_LAB_GROUP, generate_email
    import logging

    logger = logging.getLogger(__name__)
    try:
        opp = Opportunity.objects.get(opportunity_number=opportunity_number)
        if not opp.rsm:
            logger.warning(f"No RSM name for {opportunity_number}; cannot send completed email.")
            return

        # Gather CC list (similar to send_sample_received_email)
        apps_eng_values = Sample.objects.filter(opportunity_number=opportunity_number).values_list('apps_eng', flat=True).distinct()
        cc_list = TEST_LAB_GROUP.copy()
        for apps_eng_name in apps_eng_values:
            if apps_eng_name:
                apps_eng_email = generate_email(apps_eng_name)
                if apps_eng_email and apps_eng_email not in cc_list:
                    cc_list.append(apps_eng_email)

        rsm_full_name = opp.rsm
        first_name = rsm_full_name.split()[0]
        greeting_name = NICKNAMES.get(rsm_full_name, first_name)

        subject = f"{opportunity_number} ({opp.customer}) Documentation Completed"
        body = f"""
        <html><body>
            <p>Hello {greeting_name},</p>
            <p>The sample documentation for opportunity {opportunity_number} ({opp.customer}) is now complete. 
            You can access it <a href="{opp.sample_info_url}">here</a>.</p>
            <p>-Test Lab</p>
        </body></html>
        """

        recipient_email = get_rsm_email(rsm_full_name)
        if recipient_email:
            send_email(subject, body, recipient_email, cc_emails=cc_list)
            logger.info(f"Documentation-completed email sent to {recipient_email} for {opportunity_number}")
        else:
            logger.error(f"Unable to generate an email for RSM '{rsm_full_name}'. No email sent.")
    except Opportunity.DoesNotExist:
        logger.error(f"No Opportunity found with number {opportunity_number}")
    except Exception as e:
        logger.error(f"Failed to send 'documentation completed' email: {e}")

@shared_task
def send_missing_sample_info_folder_email(opportunity_number):
    from .models import Opportunity, Sample
    from .email_utils import send_email, get_rsm_email, NICKNAMES, TEST_LAB_GROUP, generate_email
    import logging

    logger = logging.getLogger(__name__)
    try:
        opp = Opportunity.objects.get(opportunity_number=opportunity_number)
        if not opp.rsm:
            logger.warning(f"No RSM name for {opportunity_number}; cannot send missing folder email.")
            return

        # Gather CC list (similar to other email tasks)
        apps_eng_values = Sample.objects.filter(opportunity_number=opportunity_number).values_list('apps_eng', flat=True).distinct()
        cc_list = TEST_LAB_GROUP.copy()
        for apps_eng_name in apps_eng_values:
            if apps_eng_name:
                apps_eng_email = generate_email(apps_eng_name)
                if apps_eng_email and apps_eng_email not in cc_list:
                    cc_list.append(apps_eng_email)

        rsm_full_name = opp.rsm
        first_name = rsm_full_name.split()[0]
        greeting_name = NICKNAMES.get(rsm_full_name, first_name)

        subject = f"{opportunity_number} ({opp.customer}) Missing Sample Info folder"
        body = f"""
        <html><body>
            <p>Hello {greeting_name},</p>
            <p>The Sample Info folder for opportunity {opportunity_number} ({opp.customer}) was not found.
            Please verify that it exists for <strong>{opp.customer}</strong>.</p>
            <p>-Test Lab</p>
        </body></html>
        """

        recipient_email = get_rsm_email(rsm_full_name)
        if recipient_email:
            send_email(subject, body, recipient_email, cc_emails=cc_list)
            logger.info(f"Missing Sample Info folder email sent to {recipient_email} for {opportunity_number}")
        else:
            logger.error(f"Unable to generate an email for RSM '{rsm_full_name}'. No email sent.")
    except Opportunity.DoesNotExist:
        logger.error(f"No Opportunity found with number {opportunity_number}")
    except Exception as e:
        logger.error(f"Failed to send 'missing sample info folder' email: {e}")

@shared_task
def send_sample_received_email(rsm_full_name, date_received, opportunity_number, customer, quantity):
    try:
        # Gather distinct engineers for this opportunity
        from .models import Sample
        from .email_utils import generate_email
        apps_eng_values = Sample.objects.filter(opportunity_number=opportunity_number).values_list('apps_eng', flat=True).distinct()
        cc_list = TEST_LAB_GROUP.copy()  # start with the group list
        for apps_eng_name in apps_eng_values:
            if apps_eng_name:
                apps_eng_email = generate_email(apps_eng_name)
                if apps_eng_email:
                    # Only add if not already present in cc_list
                    if apps_eng_email not in cc_list:
                        cc_list.append(apps_eng_email)
        first_name = rsm_full_name.strip().split()[0]

        # Determine the greeting name (use nickname if available)
        greeting_name = NICKNAMES.get(rsm_full_name, first_name)
        subject = f'{opportunity_number} ({customer}) Samples Received'
        
        from .models import Opportunity
        opp = Opportunity.objects.filter(opportunity_number=opportunity_number).first()
        if opp and opp.sample_info_url:
            folder_link = f'<a href="{opp.sample_info_url}">here</a>'
            folder_message = f"They will be documented and uploaded to the Sample Info folder on SharePoint shortly. You can access it {folder_link}."
        else:
            folder_message = (
                "They will be documented and uploaded to SharePoint shortly. "
                "However, the Sample Info folder was not found. Please verify that it exists "
                "in the Opportunity folder on the Sales Engineering drive."
            )
        body = f"""
        <html><body>
            <p>Hello {greeting_name},</p>
            <p>{quantity} sample(s) for opportunity number {opportunity_number} ({customer}) were received on {date_received}. {folder_message}</p>
            <p>-Test Lab</p>
        </body></html>
        """
        recipient_email = get_rsm_email(rsm_full_name)
        if recipient_email:
            send_email(subject, body, recipient_email, cc_emails=cc_list)
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

    # Specify the full path to rclone
    rclone_executable = settings.RCLONE_EXECUTABLE
    logger.info(f"Using rclone executable at: {rclone_executable}")

    # Add the for loop to iterate over sample_image_ids
    for sample_image_id in sample_image_ids:
        try:
            # Retrieve the SampleImage instance
            sample_image = SampleImage.objects.get(id=sample_image_id)
            sample = sample_image.sample

            # Define source and destination paths
            source_path = sample_image.full_size_image.path
            destination_path = f"TestLabSamples:{sample.opportunity_number}/Samples/{os.path.basename(sample_image.full_size_image.name)}"

            # Log the paths
            logger.info(f"Uploading image {sample_image_id} from {source_path} to {destination_path}")

            # Copy the full-size image to SharePoint
            result = subprocess.run(
                [rclone_executable, 'copyto', source_path, destination_path],
                check=True,
                capture_output=True,
                text=True,
                env=os.environ
            )
            if result.stdout:
                logger.debug(f"rclone stdout: {result.stdout}")
            if result.stderr:
                logger.error(f"rclone stderr: {result.stderr}")

            logger.info(f"Copied full-size image {sample_image_id} to SharePoint: {destination_path}")

        except Exception as e:
            logger.error(f"Failed to upload image {sample_image_id} to SharePoint: {e}")
            logger.exception(e)
@shared_task
def delete_documentation_from_sharepoint_task(opportunity_number):
    logger.info(f"Starting task to delete documentation from SharePoint for opportunity {opportunity_number}")

    # Construct the path to the opportunity directory on SharePoint
    remote_folder_path = f"TestLabSamples:{opportunity_number}"

    # Specify the full path to rclone
    rclone_executable = settings.RCLONE_EXECUTABLE
    logger.info(f"Using rclone executable at: {rclone_executable}")

    # Command to delete the folder using rclone
    try:
        result = subprocess.run(
            [rclone_executable, 'purge', remote_folder_path],
            check=True,
            capture_output=True,
            text=True,
            env=os.environ
        )
        if result.stdout:
            logger.debug(f"rclone stdout: {result.stdout}")
        if result.stderr:
            logger.error(f"rclone stderr: {result.stderr}")
        logger.info(f"Deleted opportunity directory from SharePoint: {remote_folder_path}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to delete opportunity directory from SharePoint: {e}")
        if e.stdout:
            logger.error(f"rclone stdout: {e.stdout}")
        if e.stderr:
            logger.error(f"rclone stderr: {e.stderr}")
        logger.exception(e)
    except Exception as e:
        logger.error(f"An unexpected error occurred in delete_documentation_from_sharepoint_task: {e}")
        logger.exception(e)

@shared_task
def move_documentation_to_archive_task(opportunity_number):
    logger = logging.getLogger(__name__)

    logger.info(f"Starting move_documentation_to_archive_task for opportunity {opportunity_number}")

    # Specify the full path to rclone executable
    rclone_executable = settings.RCLONE_EXECUTABLE
    logger.info(f"Using rclone executable at: {rclone_executable}")
    remote_folder_path = f"TestLabSamples:{opportunity_number}"
    archive_folder_path = f"TestLabSamples:_Archive/{opportunity_number}"

    # Command to move the folder using rclone
    try:
        logger.info(f"Attempting to move {remote_folder_path} to {archive_folder_path}/{opportunity_number}")
        result = subprocess.run(
            [
                rclone_executable,
                'moveto',
                remote_folder_path,
                archive_folder_path
            ],
            check=True,
            capture_output=True,
            text=True,
            env=os.environ
        )
        if result.stdout:
            logger.debug(f"rclone stdout: {result.stdout}")
        if result.stderr:
            logger.error(f"rclone stderr: {result.stderr}")
        logger.info(f"Moved opportunity directory to archive: {remote_folder_path} -> {archive_folder_path}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to move opportunity directory to archive: {e}")
@shared_task
def restore_documentation_from_archive_task(opportunity_number):
    logger = logging.getLogger(__name__)

    logger.info(f"Starting restore_documentation_from_archive_task for opportunity {opportunity_number}")

    # Specify the full path to rclone executable
    rclone_executable = settings.RCLONE_EXECUTABLE
    archive_folder_path = f"TestLabSamples:_Archive/{opportunity_number}"
    main_folder_path = f"TestLabSamples:{opportunity_number}"

    # Command to move the folder back using rclone
    try:
        logger.info(f"Attempting to move {archive_folder_path} back to {main_folder_path}")
        result = subprocess.run(
            [
                rclone_executable,
                'moveto',
                archive_folder_path,
                main_folder_path
            ],
            check=True,
            capture_output=True,
            text=True,
            env=os.environ
        )
        if result.stdout:
            logger.debug(f"rclone stdout: {result.stdout}")
        if result.stderr:
            logger.error(f"rclone stderr: {result.stderr}")
        logger.info(f"Restored opportunity directory from archive: {archive_folder_path} -> {main_folder_path}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to restore opportunity directory from archive: {e}")
        if e.stdout:
            logger.error(f"rclone stdout: {e.stdout}")
        if e.stderr:
            logger.error(f"rclone stderr: {e.stderr}")
    except Exception as e:
        logger.error(f"An unexpected error occurred in restore_documentation_from_archive_task: {e}")
        logger.exception(e)

@shared_task
def set_opportunity_update_false(opportunity_number):
    logger.info(f"Setting opportunity.update = False for {opportunity_number}")
    try:
        from .models import Opportunity
        opportunity = Opportunity.objects.get(opportunity_number=opportunity_number)
        opportunity.update = False
        opportunity.save()
        logger.info(f"Set opportunity.update to False for {opportunity_number}")
    except Opportunity.DoesNotExist:
        logger.warning(f"Opportunity with number {opportunity_number} not found. Could not set update=False.")

@shared_task
def export_documentation(opportunity_number):
    """
    Copy all files from the 'Samples' folder in the Test Engineering library
    into the opportunity’s Sample Info folder (by folder ID) in SharePoint.
    """
    logger.info(f"Starting export_documentation for opportunity {opportunity_number}")

    from .models import Opportunity
    from .CreateOppFolderSharepoint import get_access_token
    import requests
    import time

    # REPLACE this with your actual Test Engineering library drive ID

    try:
        # Retrieve the Opportunity record
        opp = Opportunity.objects.get(opportunity_number=opportunity_number)
        sample_info_folder_id = opp.sample_info_id  # target folder ID
        if not sample_info_folder_id:
            logger.error(f"No sample_info_folder_id for opportunity {opportunity_number}. Aborting export.")
            send_missing_sample_info_folder_email.delay(opportunity_number)
            return

        access_token = get_access_token()
        if not access_token:
            logger.error("Failed to acquire access token; aborting.")
            return
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

        def find_folder_by_name(drive_id, parent_id, folder_name):
            """
            Helper to locate a child folder by exact name under parent_id.
            Return the item's ID or None if not found.
            """
            if parent_id:
                children_url = f"{GRAPH_API_URL}/drives/{drive_id}/items/{parent_id}/children"
            else:
                children_url = f"{GRAPH_API_URL}/drives/{drive_id}/root/children"

            resp = requests.get(children_url, headers=headers)
            if resp.status_code != 200:
                logger.error(f"Failed listing child items under {parent_id}: {resp.text}")
                return None

            for item in resp.json().get("value", []):
                if item.get("name", "").strip().lower() == folder_name.strip().lower() and "folder" in item:
                    return item["id"]
            return None

        def list_children(drive_id, folder_id):
            """List files under the given folder_id."""
            children_url = f"{GRAPH_API_URL}/drives/{drive_id}/items/{folder_id}/children"
            resp = requests.get(children_url, headers=headers)
            if resp.status_code != 200:
                logger.error(f"Failed listing child items under {folder_id}: {resp.text}")
                return []
            return resp.json().get("value", [])

        # 1) Find the folder for this opportunity
        opp_folder_id = find_folder_by_name(TEST_ENGINEERING_LIBRARY_ID, None, opportunity_number)
        if not opp_folder_id:
            logger.warning(f"Opportunity folder '{opportunity_number}' not found in Test Engineering library.")
            return

        # 2) Find the 'Samples' subfolder inside that opportunity folder
        samples_folder_id = find_folder_by_name(TEST_ENGINEERING_LIBRARY_ID, opp_folder_id, "Samples")
        if not samples_folder_id:
            logger.warning(f"No 'Samples' folder found for {opportunity_number} in Test Engineering.")
            return

        # 3) List the files in 'Samples'
        files_to_copy = list_children(TEST_ENGINEERING_LIBRARY_ID, samples_folder_id)
        if not files_to_copy:
            logger.info(f"No files found in 'Samples' folder for {opportunity_number}. Nothing to copy.")
            return

        # 4) For each file, issue a copy request to the sample_info_folder_id
        for file_item in files_to_copy:
            if "folder" in file_item:
                # Skip subfolders unless you want to recurse
                continue

            file_id = file_item["id"]
            file_name = file_item["name"]

            # ──────────────────────────────────────────────────────────────────────────────
            # ADD THIS BLOCK to remove existing file with the same name from destination:
            destination_children_url = f"{GRAPH_API_URL}/drives/{SALES_ENGINEERING_LIBRARY_ID}/items/{sample_info_folder_id}/children"
            dest_resp = requests.get(destination_children_url, headers=headers)
            if dest_resp.status_code == 200:
                for existing_item in dest_resp.json().get("value", []):
                    if existing_item.get("name") and existing_item["name"].lower() == file_name.lower():
                        existing_file_id = existing_item["id"]
                        delete_url = f"{GRAPH_API_URL}/drives/{SALES_ENGINEERING_LIBRARY_ID}/items/{existing_file_id}"
                        logger.info(f"Deleting existing file '{file_name}' from destination to allow overwrite.")
                        del_resp = requests.delete(delete_url, headers=headers)
                        if del_resp.status_code == 204:
                            logger.info("Existing file deleted successfully.")
                        else:
                            logger.warning(f"Failed to delete existing file. Status: {del_resp.status_code}, {del_resp.text}")
            else:
                logger.warning(f"Failed to check destination files: {dest_resp.status_code}, {dest_resp.text}")
            # ──────────────────────────────────────────────────────────────────────────────
        for file_item in files_to_copy:
            if "folder" in file_item:
                # Skip any subfolders (if desired). Otherwise handle recursively.
                continue

            file_id = file_item["id"]
            file_name = file_item["name"]

            copy_endpoint = f"{GRAPH_API_URL}/drives/{TEST_ENGINEERING_LIBRARY_ID}/items/{file_id}/copy"
            copy_body = {
                "parentReference": {
                    "driveId": SALES_ENGINEERING_LIBRARY_ID,
                    "id": sample_info_folder_id
                },
                "name": file_name,
                "@microsoft.graph.conflictBehavior": "replace"
            }

            logger.info(f"Copying '{file_name}' to folder ID {sample_info_folder_id} ...")
            copy_resp = requests.post(copy_endpoint, json=copy_body, headers=headers)
            if copy_resp.status_code not in [200, 202]:
                logger.error(
                    f"Failed copy for {file_name}: {copy_resp.status_code} {copy_resp.text}"
                )
                continue

            # If copy is async (202), you could poll "Location" header. Simple approach: just wait a moment.
            if copy_resp.status_code == 202:
                time.sleep(1)
                logger.info(f"Request accepted for '{file_name}', continuing...")

        logger.info(f"Completed export_documentation for {opportunity_number}.")
        send_documentation_completed_email.delay(opportunity_number)

    except Opportunity.DoesNotExist:
        logger.error(f"No Opportunity found with opportunity_number {opportunity_number}")
    except Exception as e:
        logger.error(f"Unhandled error in export_documentation: {e}")

@shared_task
def find_sample_info_folder_url(customer_name, opportunity_number):
    logger.info(f"Starting find_sample_info_folder_url for opportunity {opportunity_number} with customer {customer_name}")
    # Library ID from find_sample_folder.py
    LIBRARY_ID = SALES_ENGINEERING_LIBRARY_ID

    from .CreateOppFolderSharepoint import get_access_token
    from django.conf import settings
    import requests
    from .models import Opportunity

    def find_folder_by_name(drive_id, parent_id, folder_name, headers):
        if parent_id:
            children_url = f"{GRAPH_API_URL}/drives/{drive_id}/items/{parent_id}/children"
        else:
            children_url = f"{GRAPH_API_URL}/drives/{drive_id}/root/children"

        resp = requests.get(children_url, headers=headers)
        if resp.status_code != 200:
            logger.error(f"Failed to get children for folder {parent_id}: {resp.status_code}, {resp.text}")
            return None

        items = resp.json().get("value", [])
        for item in items:
            if "folder" in item and item.get("name", "").strip().lower() == folder_name.strip().lower():
                return item["id"]
        return None

    def find_folder_containing(drive_id, start_folder_id, substring, headers):
        search_url = f"{GRAPH_API_URL}/drives/{drive_id}/items/{start_folder_id}/search(q='{substring}')"
        resp = requests.get(search_url, headers=headers)
        if resp.status_code != 200:
            logger.error(f"Failed to search within folder {start_folder_id}: {resp.status_code}, {resp.text}")
            return None

        items = resp.json().get('value', [])
        MAX_DEPTH = 3
        for item in items:
            if 'folder' not in item:
                continue
            parent_path = item.get("parentReference", {}).get("path", "")
            if ':' in parent_path:
                path_part = parent_path.split(':', 1)[1]
                depth = path_part.count('/')
            else:
                depth = 0
            if depth <= MAX_DEPTH:
                return item['id']
        return None

    try:
        access_token = get_access_token()
        if not access_token:
            logger.error("Failed to acquire access token.")
            return

        headers = {"Authorization": f"Bearer {access_token}"}

        letter_folder_name = customer_name[0].upper() if customer_name else "#"
        logger.debug(f"Looking for letter folder: {letter_folder_name}")
        letter_folder_id = find_folder_by_name(LIBRARY_ID, None, letter_folder_name, headers)
        if not letter_folder_id:
            logger.warning(f"Letter folder '{letter_folder_name}' not found in library.")
            logger.warning(f"Could not find letter folder for {letter_folder_name}")
            return

        opp_folder_id = find_folder_containing(LIBRARY_ID, letter_folder_id, opportunity_number, headers)
        if not opp_folder_id:
            logger.warning(f"Opportunity folder containing '{opportunity_number}' not found.")
            logger.warning(f"Could not find opportunity folder containing {opportunity_number}")
            return

        info_folder_id = find_folder_by_name(LIBRARY_ID, opp_folder_id, "1 Info", headers)
        if not info_folder_id:
            logger.warning(f"'1 Info' folder not found in opportunity folder.")
            logger.warning(f"Could not find '1 Info' folder")
            return

        sample_info_folder_id = find_folder_by_name(LIBRARY_ID, info_folder_id, "Sample Info", headers)
        if not sample_info_folder_id:
            logger.warning(f"'Sample Info' folder not found in '1 Info' folder.")
            logger.warning(f"Could not find 'Sample Info' folder")
            return

        folder_details_url = f"{GRAPH_API_URL}/drives/{LIBRARY_ID}/items/{sample_info_folder_id}"
        resp = requests.get(folder_details_url, headers=headers)
        if resp.status_code != 200:
            logger.warning(f"Failed to get folder details: {resp.status_code} - {resp.text}")
            return

        folder_data = resp.json()
        web_url = folder_data.get("webUrl", "")
        if web_url:
            logger.info(f"Found 'Sample Info' folder at: {web_url}")
            try:
                opp = Opportunity.objects.get(opportunity_number=opportunity_number)
                opp.sample_info_url = web_url
                opp.sample_info_id = sample_info_folder_id
                opp.save()
            except Opportunity.DoesNotExist:
                logger.error(f"Opportunity {opportunity_number} does not exist.")
    except Exception as e:
        logger.error(f"Error finding sample info folder for opportunity {opportunity_number}: {e}")
