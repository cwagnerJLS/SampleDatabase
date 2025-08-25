"""
Centralized Microsoft authentication service.
Eliminates duplicate authentication code across multiple modules.
"""
import logging
from typing import List, Optional
from msal import PublicClientApplication
from samples.token_cache_utils import get_token_cache
from samples.sharepoint_config import (
    AZURE_CLIENT_ID,
    AZURE_USERNAME,
    AZURE_TENANT_ID
)
from samples.exceptions import (
    SharePointAuthenticationError,
    EmailAuthenticationError,
    ConfigurationError
)

logger = logging.getLogger(__name__)


class MicrosoftAuthService:
    """
    Centralized service for Microsoft authentication using MSAL.
    Handles token acquisition for various Microsoft services (Graph API, SharePoint, etc.)
    """
    
    _instance = None
    _app = None
    
    def __new__(cls):
        """Singleton pattern to reuse the same MSAL app instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize the MSAL application if not already initialized."""
        if MicrosoftAuthService._app is None:
            self._initialize_app()
    
    def _initialize_app(self):
        """Initialize the MSAL PublicClientApplication."""
        if not AZURE_CLIENT_ID or not AZURE_USERNAME:
            raise ConfigurationError("Required Azure AD configuration is missing")
        
        try:
            authority = f"https://login.microsoftonline.com/{AZURE_TENANT_ID}"
            cache = get_token_cache()
            
            MicrosoftAuthService._app = PublicClientApplication(
                client_id=AZURE_CLIENT_ID,
                authority=authority,
                token_cache=cache
            )
            logger.info("MSAL application initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize MSAL application: {e}")
            raise ConfigurationError(f"Failed to initialize authentication: {e}")
    
    def get_access_token(self, scopes: List[str], use_device_flow: bool = True) -> str:
        """
        Acquire an access token for the specified scopes.
        
        Args:
            scopes: List of scopes to request (e.g., ["Mail.Send"], ["Sites.ReadWrite.All"])
            use_device_flow: Whether to fall back to device flow if silent acquisition fails
        
        Returns:
            Access token string
        
        Raises:
            SharePointAuthenticationError: If authentication fails for SharePoint scopes
            EmailAuthenticationError: If authentication fails for email scopes
        """
        if not MicrosoftAuthService._app:
            self._initialize_app()
        
        # Determine the type of authentication based on scopes
        is_email_auth = "Mail.Send" in scopes
        is_sharepoint_auth = any("Sites" in scope or "Files" in scope for scope in scopes)
        
        # Try silent token acquisition first
        token = self._try_silent_acquisition(scopes)
        if token:
            logger.debug(f"Token acquired silently for scopes: {scopes}")
            return token
        
        # Fall back to device flow if enabled
        if use_device_flow:
            token = self._acquire_token_by_device_flow(scopes)
            if token:
                logger.info(f"Token acquired via device flow for scopes: {scopes}")
                return token
        
        # Raise appropriate exception based on scope type
        error_msg = f"Failed to acquire token for scopes: {scopes}"
        if is_email_auth:
            raise EmailAuthenticationError(error_msg)
        elif is_sharepoint_auth:
            raise SharePointAuthenticationError(error_msg)
        else:
            raise ConfigurationError(error_msg)
    
    def _try_silent_acquisition(self, scopes: List[str]) -> Optional[str]:
        """
        Attempt to acquire token silently from cache.
        
        Args:
            scopes: List of scopes to request
        
        Returns:
            Access token if successful, None otherwise
        """
        try:
            accounts = MicrosoftAuthService._app.get_accounts(username=AZURE_USERNAME)
            if accounts:
                result = MicrosoftAuthService._app.acquire_token_silent(
                    scopes, 
                    account=accounts[0]
                )
                if result and "access_token" in result:
                    return result["access_token"]
        except Exception as e:
            logger.debug(f"Silent token acquisition failed: {e}")
        
        return None
    
    def _acquire_token_by_device_flow(self, scopes: List[str]) -> Optional[str]:
        """
        Acquire token using device code flow.
        
        Args:
            scopes: List of scopes to request
        
        Returns:
            Access token if successful, None otherwise
        """
        try:
            flow = MicrosoftAuthService._app.initiate_device_flow(scopes=scopes)
            if "user_code" not in flow:
                logger.error("Failed to create device flow")
                return None
            
            # Display authentication instructions to user
            print(flow["message"])
            logger.info(f"Device flow initiated with code: {flow['user_code']}")
            
            # Poll for the access token (blocking call)
            result = MicrosoftAuthService._app.acquire_token_by_device_flow(flow)
            
            if result and "access_token" in result:
                return result["access_token"]
            else:
                logger.error(f"Device flow failed: {result.get('error_description', 'Unknown error')}")
                return None
                
        except Exception as e:
            logger.error(f"Device flow authentication failed: {e}")
            return None
    
    def clear_cache(self):
        """Clear the token cache for the current user."""
        if MicrosoftAuthService._app:
            accounts = MicrosoftAuthService._app.get_accounts(username=AZURE_USERNAME)
            for account in accounts:
                MicrosoftAuthService._app.remove_account(account)
            logger.info("Token cache cleared")
    
    def get_cached_token(self, scopes: List[str]) -> Optional[str]:
        """
        Get token from cache only (no new acquisition).
        
        Args:
            scopes: List of scopes to check
        
        Returns:
            Access token if in cache, None otherwise
        """
        return self._try_silent_acquisition(scopes)


# Convenience functions for backward compatibility
def get_sharepoint_token() -> str:
    """
    Get an access token for SharePoint operations.
    
    Returns:
        Access token for SharePoint
    
    Raises:
        SharePointAuthenticationError: If authentication fails
    """
    auth_service = MicrosoftAuthService()
    scopes = ["https://graph.microsoft.com/.default"]
    return auth_service.get_access_token(scopes)


def get_email_token() -> str:
    """
    Get an access token for sending emails.
    
    Returns:
        Access token for email operations
    
    Raises:
        EmailAuthenticationError: If authentication fails
    """
    auth_service = MicrosoftAuthService()
    scopes = ["Mail.Send"]
    return auth_service.get_access_token(scopes)


def get_graph_token(scopes: List[str]) -> str:
    """
    Get an access token for Microsoft Graph API operations.
    
    Args:
        scopes: List of Graph API scopes required
    
    Returns:
        Access token for Graph API
    
    Raises:
        ConfigurationError: If authentication fails
    """
    auth_service = MicrosoftAuthService()
    return auth_service.get_access_token(scopes)