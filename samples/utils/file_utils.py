import os
from django.conf import settings
import pandas as pd
import subprocess
import logging
from ..sharepoint_config import get_documentation_template_path

def create_documentation_on_sharepoint(opportunity_number):
    logger = logging.getLogger(__name__)

    # Construct the path to the documentation file on SharePoint
    remote_file_path = f"TestLabSamples:{opportunity_number}/Samples/Documentation_{opportunity_number}.xlsm"
    
    # Use centralized template file path
    template_file_path = get_documentation_template_path()

    # Add a check to confirm the template file exists
    if not os.path.exists(template_file_path):
        error_message = f"Template file not found at: {template_file_path}"
        logger.error(error_message)
        raise Exception(error_message)

    # Command to copy the template file to the new location using rclone
    # Command to copy the template file to the new location using rclone
    command = [
        '/usr/bin/rclone', 'copyto',  # Use the full path to rclone
        template_file_path,
        remote_file_path,
        '--ignore-size',
        '--ignore-checksum'
    ]

    logger.debug(f"Running command: {' '.join(command)}")

    try:
        result = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        logger.info(f"Copied documentation template to SharePoint: {remote_file_path}")
        logger.debug(f"Command output: {result.stdout}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to copy documentation template to SharePoint: {e.stderr}")
        raise Exception(f"Failed to copy documentation template: {e.stderr}")

def read_excel_data(file_path):
    df = pd.read_excel(file_path)
    return df.to_dict('records')

def get_unique_values(data, key):
    return list({record[key] for record in data})

