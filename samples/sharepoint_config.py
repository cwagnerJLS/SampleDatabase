"""
Centralized configuration for SharePoint and Azure AD settings.
All SharePoint and Azure AD related configuration should be imported from this module.
Configuration values are read from environment variables for security.
"""
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env file if it exists
env_path = Path(__file__).resolve().parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

def get_required_env_var(var_name):
    """
    Get a required environment variable or raise an error.
    
    Args:
        var_name: Name of the environment variable
        
    Returns:
        The value of the environment variable
        
    Raises:
        ValueError: If the environment variable is not set
    """
    value = os.environ.get(var_name)
    if not value:
        error_msg = f"Required environment variable '{var_name}' is not set"
        logger.error(error_msg)
        raise ValueError(error_msg)
    return value

try:
    # Azure AD Configuration
    AZURE_CLIENT_ID = get_required_env_var("AZURE_CLIENT_ID")
    AZURE_TENANT_ID = get_required_env_var("AZURE_TENANT_ID")
    AZURE_AUTHORITY = f"https://login.microsoftonline.com/{AZURE_TENANT_ID}"
    AZURE_USERNAME = get_required_env_var("AZURE_USERNAME")

    # SharePoint Library IDs
    TEST_ENGINEERING_LIBRARY_ID = get_required_env_var("TEST_ENGINEERING_LIBRARY_ID")
    SALES_ENGINEERING_LIBRARY_ID = get_required_env_var("SALES_ENGINEERING_LIBRARY_ID")

    # Email Configuration
    EMAIL_SENDER = get_required_env_var("EMAIL_SENDER")
    EMAIL_DOMAIN = get_required_env_var("EMAIL_DOMAIN")
    TEST_MODE_EMAIL = get_required_env_var("TEST_MODE_EMAIL")
    
    # Test Lab Group Emails (parse comma-separated list)
    test_lab_emails_str = get_required_env_var("TEST_LAB_GROUP_EMAILS")
    TEST_LAB_GROUP_EMAILS = [email.strip() for email in test_lab_emails_str.split(',')]
    
except ValueError as e:
    logger.critical(f"Configuration error: {e}")
    # Set variables to None to allow module import but fail on usage
    AZURE_CLIENT_ID = None
    AZURE_TENANT_ID = None
    AZURE_AUTHORITY = None
    AZURE_USERNAME = None
    TEST_ENGINEERING_LIBRARY_ID = None
    SALES_ENGINEERING_LIBRARY_ID = None
    EMAIL_SENDER = None
    EMAIL_DOMAIN = None
    TEST_MODE_EMAIL = None
    TEST_LAB_GROUP_EMAILS = []

# SharePoint API Scopes (these are constants, not secrets)
SHAREPOINT_SCOPES = ["Sites.ReadWrite.All", "Files.ReadWrite.All"]
EMAIL_SCOPES = ["Mail.Send", "Mail.ReadWrite"]

# Graph API Base URL (this is a constant, not a secret)
GRAPH_API_URL = "https://graph.microsoft.com/v1.0"

def get_library_url(library_id, endpoint=""):
    """Generate SharePoint library URL for Graph API."""
    if not library_id:
        raise ValueError("Library ID is not configured. Check environment variables.")
    base_url = f"{GRAPH_API_URL}/drives/{library_id}"
    if endpoint:
        return f"{base_url}/{endpoint}"
    return base_url

def get_authority_url():
    """Get the Azure AD authority URL."""
    if not AZURE_AUTHORITY:
        raise ValueError("Azure Authority URL is not configured. Check AZURE_TENANT_ID environment variable.")
    return AZURE_AUTHORITY

# File Paths and Templates
# -------------------------
def get_documentation_template_path():
    """Get the documentation template path (lazy evaluation for Django settings)."""
    from django.conf import settings
    return os.path.join(
        settings.BASE_DIR, 
        'OneDrive_Sync', 
        '_Templates', 
        'DocumentationTemplate.xlsm'
    )

def get_apps_database_path():
    """Get the apps database path (lazy evaluation for Django settings)."""
    from django.conf import settings
    return os.path.join(
        settings.BASE_DIR, 
        'Apps_Database.xlsx'
    )

# SharePoint Folder Structure
SHAREPOINT_FOLDERS = {
    'info': '1 Info',
    'sample_info': 'Sample Info',
    'archive': '_Archive',
    'templates': '_Templates'
}

# Label Configuration
LABEL_WIDTH_MM = float(os.getenv('LABEL_WIDTH_MM', '101.6'))
LABEL_HEIGHT_MM = float(os.getenv('LABEL_HEIGHT_MM', '50.8'))

# Image Configuration
THUMBNAIL_SIZE = (
    int(os.getenv('THUMBNAIL_WIDTH', '200')),
    int(os.getenv('THUMBNAIL_HEIGHT', '200'))
)

def is_configured():
    """Check if all required configuration is present."""
    required_vars = [
        AZURE_CLIENT_ID,
        AZURE_TENANT_ID,
        AZURE_USERNAME,
        TEST_ENGINEERING_LIBRARY_ID,
        SALES_ENGINEERING_LIBRARY_ID,
        EMAIL_SENDER
    ]
    return all(var is not None for var in required_vars)