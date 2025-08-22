"""
Custom exception classes for better error handling in the samples application.
"""

class SharePointError(Exception):
    """Base exception for SharePoint-related errors."""
    pass

class SharePointAuthenticationError(SharePointError):
    """Raised when SharePoint authentication fails."""
    pass

class SharePointAPIError(SharePointError):
    """Raised when SharePoint API calls fail."""
    def __init__(self, message, status_code=None, response_text=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text

class ConfigurationError(Exception):
    """Raised when required configuration is missing or invalid."""
    pass

class EmailError(Exception):
    """Base exception for email-related errors."""
    pass

class EmailAuthenticationError(EmailError):
    """Raised when email authentication fails."""
    pass

class EmailSendError(EmailError):
    """Raised when sending email fails."""
    pass