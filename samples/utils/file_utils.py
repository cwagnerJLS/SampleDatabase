import os
from django.conf import settings
import pandas as pd
import logging
from ..sharepoint_config import get_documentation_template_path
from .rclone_utils import get_rclone_manager

logger = logging.getLogger(__name__)

def create_documentation_on_sharepoint(opportunity_number):
    """Copy documentation template to SharePoint for the opportunity."""
    # Construct the path to the documentation file on SharePoint
    remote_file_path = f"TestLabSamples:{opportunity_number}/Samples/Documentation_{opportunity_number}.xlsm"
    
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

