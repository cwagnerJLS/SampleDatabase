import pandas as pd
import subprocess
import logging

def create_documentation_on_sharepoint(opportunity_number):
    logger = logging.getLogger(__name__)

    # Construct the path to the documentation file on SharePoint
    remote_file_path = f"TestLabSamples:{opportunity_number}/Samples/Documentation_{opportunity_number}.xlsm"
    template_file_path = "TestLabSamples:_Templates/DocumentationTemplate.xlsm"

    # Command to copy the template file to the new location using rclone
    try:
        subprocess.run(['rclone', 'copy', template_file_path, remote_file_path], check=True)
        logger.info(f"Copied documentation template to SharePoint: {remote_file_path}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to copy documentation template to SharePoint: {e}")

def read_excel_data(file_path):
    df = pd.read_excel(file_path)
    return df.to_dict('records')

def get_unique_values(data, key):
    return list({record[key] for record in data})

