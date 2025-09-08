import re
import logging
from typing import Optional, Tuple
from .rclone_utils import get_rclone_manager
from ..sharepoint_config import SHAREPOINT_REMOTE_NAME

logger = logging.getLogger(__name__)

def check_sharepoint_folder_status(opportunity_number: str) -> Tuple[bool, bool, str]:
    """
    Check if a SharePoint folder exists for an opportunity in main library or archive.
    
    Args:
        opportunity_number: The opportunity number to check
    
    Returns:
        tuple: (exists_in_main, exists_in_archive, folder_name)
    """
    from samples.models import Opportunity
    
    try:
        opportunity = Opportunity.objects.get(opportunity_number=opportunity_number)
        folder_name = get_sharepoint_folder_name(opportunity)
    except Opportunity.DoesNotExist:
        logger.warning(f"Opportunity {opportunity_number} not found, using opportunity number as folder name")
        folder_name = str(opportunity_number)
    
    rclone = get_rclone_manager()
    
    # Check main library
    main_path = f"{SHAREPOINT_REMOTE_NAME}:{folder_name}"
    exists_in_main = rclone.folder_exists(main_path)
    
    # Check archive
    archive_path = f"{SHAREPOINT_REMOTE_NAME}:_Archive/{folder_name}"
    exists_in_archive = rclone.folder_exists(archive_path)
    
    logger.info(f"Folder status for {opportunity_number}: Main={exists_in_main}, Archive={exists_in_archive}")
    
    return exists_in_main, exists_in_archive, folder_name

def sanitize_folder_name(name: str) -> str:
    """
    Sanitize a string for use as a SharePoint folder name.
    
    Removes or replaces invalid characters and ensures the name meets SharePoint requirements:
    - Removes leading/trailing spaces and dots
    - Replaces invalid characters with hyphens
    - Limits length to 400 characters
    - Handles empty strings
    
    Args:
        name: The original folder name (typically the description)
        
    Returns:
        A sanitized folder name safe for SharePoint
    """
    if not name or not name.strip():
        return ""
    
    # Remove leading/trailing whitespace
    name = name.strip()
    
    # Replace invalid characters: / \ : * ? " < > | # % & { } ~ 
    # Also replace multiple spaces with single space
    invalid_chars = r'[/\\:*?"<>|#%&{}~]'
    name = re.sub(invalid_chars, '-', name)
    name = re.sub(r'\s+', ' ', name)  # Replace multiple spaces with single space
    
    # Remove leading/trailing dots and spaces (SharePoint doesn't allow these)
    name = name.strip('. ')
    
    # Replace sequences of multiple hyphens with single hyphen
    name = re.sub(r'-+', '-', name)
    
    # Ensure the name isn't too long (SharePoint limit is 400 chars for folder names)
    if len(name) > 400:
        name = name[:397] + '...'  # Leave room for ellipsis
        
    # Final trim of any trailing special characters created by truncation
    name = name.rstrip('-. ')
    
    return name


def get_sharepoint_folder_name(opportunity) -> str:
    """
    Get the SharePoint folder name for an opportunity.
    
    Uses the description as the folder name, with fallback to opportunity number
    if description is empty or invalid. Handles duplicate names by appending
    the opportunity number.
    
    Args:
        opportunity: An Opportunity model instance
        
    Returns:
        The SharePoint folder name to use
    """
    # First try to use the saved folder name if it exists
    if hasattr(opportunity, 'sharepoint_folder_name') and opportunity.sharepoint_folder_name:
        return opportunity.sharepoint_folder_name
    
    # Otherwise, generate from description
    if opportunity.description:
        folder_name = sanitize_folder_name(opportunity.description)
        
        # If sanitization resulted in empty string, use opportunity number
        if not folder_name:
            logger.warning(f"Description for opportunity {opportunity.opportunity_number} "
                         f"resulted in empty folder name after sanitization. Using opportunity number.")
            return str(opportunity.opportunity_number)
        
        # Return the sanitized description without appending opportunity number
        # since the description already starts with the opportunity number
        return folder_name
    else:
        # No description available, use opportunity number
        logger.info(f"No description for opportunity {opportunity.opportunity_number}. "
                   f"Using opportunity number as folder name.")
        return str(opportunity.opportunity_number)


def get_sharepoint_folder_name_simple(description: str, opportunity_number: str) -> str:
    """
    Get SharePoint folder name from description and opportunity number without model.
    
    This is useful for operations that don't have access to the Opportunity model.
    
    Args:
        description: The opportunity description
        opportunity_number: The opportunity number
        
    Returns:
        The SharePoint folder name to use
    """
    if description:
        folder_name = sanitize_folder_name(description)
        if folder_name:
            # Return the sanitized description without appending opportunity number
            # since the description already starts with the opportunity number
            return folder_name
    
    # Fallback to opportunity number
    return str(opportunity_number)


def extract_opportunity_number_from_folder(folder_name: str) -> Optional[str]:
    """
    Extract the opportunity number from a folder name.
    
    Handles multiple formats:
    - Just number: "7000"
    - Number at start: "7000 - Company - Location"
    - Number in parentheses at end: "Description (7000)" (legacy format)
    
    Args:
        folder_name: The SharePoint folder name
        
    Returns:
        The opportunity number if found, None otherwise
    """
    # First check if it's just a number (old format)
    if folder_name.isdigit():
        return folder_name
    
    # Try to extract from format with number at the beginning: "7000 - Description"
    match = re.match(r'^(\d+)\s*-', folder_name)
    if match:
        return match.group(1)
    
    # Try to extract from legacy format with parentheses: "Description (7000)"
    match = re.search(r'\((\d+)\)$', folder_name)
    if match:
        return match.group(1)
    
    return None