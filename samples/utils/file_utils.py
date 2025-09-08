import os
from django.conf import settings
import pandas as pd
import logging
from ..sharepoint_config import get_documentation_template_path, SHAREPOINT_REMOTE_NAME
from .rclone_utils import get_rclone_manager

logger = logging.getLogger(__name__)

def create_documentation_on_sharepoint(opportunity_number):
    """Copy documentation template to SharePoint for the opportunity."""
    logger.info(f"[DEBUG] ENTERING create_documentation_on_sharepoint for opportunity {opportunity_number}")
    
    # Get the opportunity to find the folder name
    from samples.models import Opportunity, Sample
    from samples.utils.folder_utils import get_sharepoint_folder_name
    try:
        opportunity = Opportunity.objects.get(opportunity_number=opportunity_number)
        folder_name = get_sharepoint_folder_name(opportunity)
        logger.info(f"[DEBUG] Found opportunity {opportunity_number}, folder_name: {folder_name}")
    except Opportunity.DoesNotExist:
        logger.warning(f"[DEBUG] Opportunity {opportunity_number} not found, using opportunity number as folder name")
        folder_name = opportunity_number
        opportunity = None
    
    # Check if this opportunity has any current samples (to determine if it's in archive)
    has_samples = False
    if opportunity:
        has_samples = Sample.objects.filter(opportunity_number=opportunity_number).exists()
        logger.info(f"[DEBUG] Opportunity {opportunity_number} has_samples: {has_samples}")
    
    # Construct the path to the documentation file on SharePoint
    # If no samples, the folder is in _Archive
    if not has_samples:
        remote_file_path = f"{SHAREPOINT_REMOTE_NAME}:_Archive/{folder_name}/Samples/Documentation_{opportunity_number}.xlsm"
        logger.info(f"[DEBUG] Creating documentation in ARCHIVE folder for opportunity {opportunity_number}")
        logger.info(f"[DEBUG] Remote path: {remote_file_path}")
    else:
        remote_file_path = f"{SHAREPOINT_REMOTE_NAME}:{folder_name}/Samples/Documentation_{opportunity_number}.xlsm"
        logger.info(f"[DEBUG] Creating documentation in MAIN folder for opportunity {opportunity_number}")
        logger.info(f"[DEBUG] Remote path: {remote_file_path}")
    
    # Use centralized template file path
    template_file_path = get_documentation_template_path()

    # Add a check to confirm the template file exists
    if not os.path.exists(template_file_path):
        error_message = f"Template file not found at: {template_file_path}"
        logger.error(error_message)
        raise Exception(error_message)

    # Use the RcloneManager to copy the file
    rclone = get_rclone_manager()
    success = rclone.copy(
        template_file_path,
        remote_file_path,
        ignore_size=True,
        ignore_checksum=True
    )
    
    if success:
        logger.info(f"Copied documentation template to SharePoint: {remote_file_path}")
    else:
        error_message = f"Failed to copy documentation template to SharePoint: {remote_file_path}"
        logger.error(error_message)
        raise Exception(error_message)

def read_excel_data(file_path):
    df = pd.read_excel(file_path)
    return df.to_dict('records')

def get_unique_values(data, key):
    return list({record[key] for record in data})

