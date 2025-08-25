"""
SharePoint/Graph API utility functions to eliminate duplicate API call patterns.
Centralizes API request handling, headers, and error management.
"""
import requests
import logging
from typing import Optional, Dict, Any, List
from enum import Enum

logger = logging.getLogger(__name__)


class HTTPMethod(Enum):
    """HTTP methods for API requests."""
    GET = "GET"
    POST = "POST"
    PATCH = "PATCH"
    DELETE = "DELETE"
    PUT = "PUT"


class SharePointAPIError(Exception):
    """Custom exception for SharePoint API failures."""
    def __init__(self, message: str, status_code: Optional[int] = None, response_text: Optional[str] = None):
        self.status_code = status_code
        self.response_text = response_text
        super().__init__(message)


class GraphAPIClient:
    """
    Client for Microsoft Graph API operations.
    Centralizes request handling and error management.
    """
    
    @staticmethod
    def get_headers(access_token: str, content_type: str = "application/json") -> Dict[str, str]:
        """
        Get standard headers for Graph API requests.
        
        Args:
            access_token: Bearer token for authentication
            content_type: Content type for the request
        
        Returns:
            Dictionary of headers
        """
        headers = {"Authorization": f"Bearer {access_token}"}
        if content_type:
            headers["Content-Type"] = content_type
        return headers
    
    @staticmethod
    def make_request(
        method: HTTPMethod,
        url: str,
        access_token: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        raise_on_error: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Make a request to the Graph API with consistent error handling.
        
        Args:
            method: HTTP method to use
            url: Full URL for the API endpoint
            access_token: Bearer token for authentication
            json_data: JSON body for POST/PATCH requests
            params: Query parameters
            raise_on_error: Whether to raise exception on non-200 status
        
        Returns:
            Response JSON if successful, None if failed and raise_on_error=False
        
        Raises:
            SharePointAPIError: If request fails and raise_on_error=True
        """
        headers = GraphAPIClient.get_headers(access_token)
        
        logger.debug(f"{method.value} request to: {url}")
        
        try:
            if method == HTTPMethod.GET:
                response = requests.get(url, headers=headers, params=params)
            elif method == HTTPMethod.POST:
                response = requests.post(url, headers=headers, json=json_data, params=params)
            elif method == HTTPMethod.PATCH:
                response = requests.patch(url, headers=headers, json=json_data, params=params)
            elif method == HTTPMethod.DELETE:
                response = requests.delete(url, headers=headers, params=params)
            elif method == HTTPMethod.PUT:
                response = requests.put(url, headers=headers, json=json_data, params=params)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            # Check for success status codes
            if response.status_code in [200, 201, 202, 204]:
                if response.status_code == 204:  # No content
                    return {}
                try:
                    return response.json() if response.text else {}
                except ValueError:
                    return {}
            else:
                error_msg = f"{method.value} request failed with status {response.status_code}"
                logger.error(f"{error_msg}. Response: {response.text}")
                
                if raise_on_error:
                    raise SharePointAPIError(error_msg, response.status_code, response.text)
                return None
                
        except requests.RequestException as e:
            error_msg = f"{method.value} request failed: {str(e)}"
            logger.error(error_msg)
            if raise_on_error:
                raise SharePointAPIError(error_msg)
            return None
    
    @staticmethod
    def get(url: str, access_token: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Convenience method for GET requests."""
        return GraphAPIClient.make_request(HTTPMethod.GET, url, access_token, **kwargs)
    
    @staticmethod
    def post(url: str, access_token: str, json_data: Dict[str, Any], **kwargs) -> Optional[Dict[str, Any]]:
        """Convenience method for POST requests."""
        return GraphAPIClient.make_request(HTTPMethod.POST, url, access_token, json_data=json_data, **kwargs)
    
    @staticmethod
    def patch(url: str, access_token: str, json_data: Dict[str, Any], **kwargs) -> Optional[Dict[str, Any]]:
        """Convenience method for PATCH requests."""
        return GraphAPIClient.make_request(HTTPMethod.PATCH, url, access_token, json_data=json_data, **kwargs)
    
    @staticmethod
    def delete(url: str, access_token: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Convenience method for DELETE requests."""
        return GraphAPIClient.make_request(HTTPMethod.DELETE, url, access_token, **kwargs)


class ExcelAPIClient:
    """
    Specialized client for Excel operations via Graph API.
    Builds on GraphAPIClient with Excel-specific methods.
    """
    
    @staticmethod
    def get_worksheet_url(library_id: str, file_id: str, worksheet_name: str) -> str:
        """
        Build the base URL for worksheet operations.
        
        Args:
            library_id: SharePoint library ID
            file_id: Excel file ID
            worksheet_name: Name of the worksheet
        
        Returns:
            Base URL for worksheet operations
        """
        from samples.sharepoint_config import GRAPH_API_URL
        return f"{GRAPH_API_URL}/drives/{library_id}/items/{file_id}/workbook/worksheets/{worksheet_name}"
    
    @staticmethod
    def get_range_url(library_id: str, file_id: str, worksheet_name: str, range_address: str) -> str:
        """
        Build URL for range operations.
        
        Args:
            library_id: SharePoint library ID
            file_id: Excel file ID
            worksheet_name: Name of the worksheet
            range_address: Excel range (e.g., "A1:B10")
        
        Returns:
            URL for range operations
        """
        base_url = ExcelAPIClient.get_worksheet_url(library_id, file_id, worksheet_name)
        return f"{base_url}/range(address='{range_address}')"
    
    @staticmethod
    def get_cell_value(
        access_token: str,
        library_id: str,
        file_id: str,
        worksheet_name: str,
        cell_address: str
    ) -> Optional[Any]:
        """
        Get value from a specific cell.
        
        Args:
            access_token: Bearer token
            library_id: SharePoint library ID
            file_id: Excel file ID
            worksheet_name: Name of the worksheet
            cell_address: Cell address (e.g., "A1")
        
        Returns:
            Cell value or None if error
        """
        url = ExcelAPIClient.get_range_url(library_id, file_id, worksheet_name, cell_address)
        result = GraphAPIClient.get(url, access_token)
        
        if result and "values" in result and result["values"]:
            return result["values"][0][0] if result["values"][0] else None
        return None
    
    @staticmethod
    def update_range(
        access_token: str,
        library_id: str,
        file_id: str,
        worksheet_name: str,
        range_address: str,
        values: List[List[Any]]
    ) -> bool:
        """
        Update a range of cells with new values.
        
        Args:
            access_token: Bearer token
            library_id: SharePoint library ID
            file_id: Excel file ID
            worksheet_name: Name of the worksheet
            range_address: Range address (e.g., "A1:B10")
            values: 2D array of values to write
        
        Returns:
            True if successful, False otherwise
        """
        url = ExcelAPIClient.get_range_url(library_id, file_id, worksheet_name, range_address)
        data = {"values": values}
        result = GraphAPIClient.patch(url, access_token, data)
        return result is not None
    
    @staticmethod
    def clear_range(
        access_token: str,
        library_id: str,
        file_id: str,
        worksheet_name: str,
        range_address: str
    ) -> bool:
        """
        Clear a range of cells.
        
        Args:
            access_token: Bearer token
            library_id: SharePoint library ID
            file_id: Excel file ID
            worksheet_name: Name of the worksheet
            range_address: Range address to clear
        
        Returns:
            True if successful, False otherwise
        """
        url = ExcelAPIClient.get_range_url(library_id, file_id, worksheet_name, range_address)
        clear_url = f"{url}/clear"
        result = GraphAPIClient.post(clear_url, access_token, {})
        return result is not None


# Convenience functions for backward compatibility
def get_api_headers(access_token: str) -> Dict[str, str]:
    """Get standard API headers."""
    return GraphAPIClient.get_headers(access_token)


def make_graph_request(method: str, url: str, access_token: str, **kwargs) -> Optional[Dict[str, Any]]:
    """Make a Graph API request."""
    http_method = HTTPMethod[method.upper()]
    return GraphAPIClient.make_request(http_method, url, access_token, **kwargs)