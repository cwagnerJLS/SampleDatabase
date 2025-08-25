"""
Date utility functions for consistent date formatting across the application.
Eliminates duplicate date formatting code.
"""
from datetime import datetime, date
from typing import Optional, Union
import logging

logger = logging.getLogger(__name__)

# Standard date format used throughout the application
STANDARD_DATE_FORMAT = '%Y-%m-%d'


def format_date_for_display(date_obj: Optional[Union[date, datetime]]) -> str:
    """
    Format a date object for display in the standard format (YYYY-MM-DD).
    
    Args:
        date_obj: A date or datetime object, or None
    
    Returns:
        Formatted date string, or empty string if date_obj is None
    """
    if date_obj is None:
        return ''
    
    if isinstance(date_obj, datetime):
        return date_obj.strftime(STANDARD_DATE_FORMAT)
    elif isinstance(date_obj, date):
        return date_obj.strftime(STANDARD_DATE_FORMAT)
    else:
        logger.warning(f"Unexpected date type: {type(date_obj)}")
        return str(date_obj)


def parse_date_from_string(date_string: str) -> Optional[date]:
    """
    Parse a date string in the standard format.
    
    Args:
        date_string: Date string in YYYY-MM-DD format
    
    Returns:
        date object, or None if parsing fails
    """
    if not date_string:
        return None
    
    try:
        return datetime.strptime(date_string, STANDARD_DATE_FORMAT).date()
    except ValueError as e:
        logger.error(f"Failed to parse date '{date_string}': {e}")
        return None


def format_date_for_excel(date_obj: Optional[Union[date, datetime]]) -> str:
    """
    Format a date for Excel/SharePoint operations.
    Uses the same standard format as display.
    
    Args:
        date_obj: A date or datetime object, or None
    
    Returns:
        Formatted date string for Excel
    """
    return format_date_for_display(date_obj)


def format_date_for_filename(date_obj: Optional[Union[date, datetime]] = None) -> str:
    """
    Format a date for use in filenames (using underscores instead of hyphens).
    
    Args:
        date_obj: A date or datetime object, or None (defaults to today)
    
    Returns:
        Formatted date string suitable for filenames (YYYY_MM_DD)
    """
    if date_obj is None:
        date_obj = datetime.now()
    
    formatted = format_date_for_display(date_obj)
    return formatted.replace('-', '_')


def get_today_formatted() -> str:
    """
    Get today's date in the standard format.
    
    Returns:
        Today's date as a formatted string (YYYY-MM-DD)
    """
    return format_date_for_display(date.today())


def format_datetime_for_display(dt_obj: Optional[datetime]) -> str:
    """
    Format a datetime object for display including time.
    
    Args:
        dt_obj: A datetime object, or None
    
    Returns:
        Formatted datetime string (YYYY-MM-DD HH:MM:SS), or empty string if None
    """
    if dt_obj is None:
        return ''
    
    return dt_obj.strftime(f'{STANDARD_DATE_FORMAT} %H:%M:%S')


def is_valid_date_format(date_string: str) -> bool:
    """
    Check if a string is in the valid date format.
    
    Args:
        date_string: String to validate
    
    Returns:
        True if the string is in YYYY-MM-DD format, False otherwise
    """
    if not date_string:
        return False
    
    try:
        datetime.strptime(date_string, STANDARD_DATE_FORMAT)
        return True
    except ValueError:
        return False