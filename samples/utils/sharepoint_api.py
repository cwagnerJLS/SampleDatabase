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


class FolderAPIClient:
    """
    Client for SharePoint folder operations via Graph API.
    Centralizes folder navigation and search operations.
    """
    
    @staticmethod
    def find_folder_by_name(
        drive_id: str,
        parent_id: Optional[str],
        folder_name: str,
        access_token: str
    ) -> Optional[str]:
        """
        Find a folder by exact name under a parent folder.
        
        Args:
            drive_id: SharePoint drive/library ID
            parent_id: Parent folder ID (None for root)
            folder_name: Exact folder name to find
            access_token: Bearer token for authentication
        
        Returns:
            Folder ID if found, None otherwise
        """
        from samples.sharepoint_config import GRAPH_API_URL
        
        if parent_id:
            children_url = f"{GRAPH_API_URL}/drives/{drive_id}/items/{parent_id}/children"
        else:
            children_url = f"{GRAPH_API_URL}/drives/{drive_id}/root/children"
        
        result = GraphAPIClient.get(children_url, access_token, raise_on_error=False)
        if not result:
            logger.error(f"Failed to list children for folder {parent_id or 'root'}")
            return None
        
        # Search for exact folder name match (case-insensitive)
        for item in result.get("value", []):
            if "folder" in item and item.get("name", "").strip().lower() == folder_name.strip().lower():
                return item["id"]
        
        return None
    
    @staticmethod
    def find_folder_containing(
        drive_id: str,
        start_folder_id: str,
        substring: str,
        access_token: str,
        max_depth: int = 3
    ) -> Optional[str]:
        """
        Search for a folder that STARTS with the specified substring (opportunity number).
        
        Args:
            drive_id: SharePoint drive/library ID
            start_folder_id: Folder ID to start search from
            substring: Opportunity number that folder name must START with
            access_token: Bearer token for authentication
            max_depth: Maximum folder depth to search
        
        Returns:
            Folder ID if found, None otherwise
        """
        from samples.sharepoint_config import GRAPH_API_URL
        import re
        
        # Note: SharePoint search will return any folder containing the substring anywhere
        # We'll filter the results to only match folders starting with the opportunity number
        search_url = f"{GRAPH_API_URL}/drives/{drive_id}/items/{start_folder_id}/search(q='{substring}')"
        result = GraphAPIClient.get(search_url, access_token, raise_on_error=False)
        
        if not result:
            logger.error(f"Failed to search within folder {start_folder_id}")
            return None
        
        items = result.get('value', [])
        
        # CRITICAL: Only consider folders where the opportunity number is at the START
        # Valid patterns:
        #   "7157 - Kevin's Natural Foods..."  (starts with opportunity number)
        #   "7157_Customer_Name..."            (starts with opportunity number)
        # Invalid patterns:
        #   "8044_Line 7157..."                (opportunity number not at start)
        #   "Customer 7157 Project..."         (opportunity number not at start)
        
        for item in items:
            if 'folder' not in item:
                continue
                
            folder_name = item.get('name', '').strip()
            
            # Check if folder name starts with the opportunity number
            # Allow for immediate separator after number (space, dash, underscore)
            pattern = rf'^{re.escape(substring)}[\s\-_]'
            
            if not (folder_name.startswith(substring + ' ') or 
                    folder_name.startswith(substring + '-') or 
                    folder_name.startswith(substring + '_') or
                    folder_name == substring):  # Exact match (unlikely but possible)
                logger.debug(f"Skipping folder '{folder_name}' - opportunity number '{substring}' not at start")
                continue
                
            # Check depth by counting path separators
            parent_path = item.get("parentReference", {}).get("path", "")
            if ':' in parent_path:
                path_part = parent_path.split(':', 1)[1]
                depth = path_part.count('/')
            else:
                depth = 0
                
            if depth <= max_depth:
                logger.info(f"Found opportunity folder: '{folder_name}' starting with '{substring}'")
                return item['id']
        
        logger.debug(f"No folder found starting with opportunity number '{substring}'")
        return None
    
    @staticmethod
    def list_children(
        drive_id: str,
        folder_id: str,
        access_token: str,
        folders_only: bool = False
    ) -> List[Dict[str, Any]]:
        """
        List all children of a folder.
        
        Args:
            drive_id: SharePoint drive/library ID
            folder_id: Parent folder ID
            access_token: Bearer token for authentication
            folders_only: If True, return only folders
        
        Returns:
            List of child items
        """
        from samples.sharepoint_config import GRAPH_API_URL
        
        children_url = f"{GRAPH_API_URL}/drives/{drive_id}/items/{folder_id}/children"
        result = GraphAPIClient.get(children_url, access_token, raise_on_error=False)
        
        if not result:
            logger.error(f"Failed to list children for folder {folder_id}")
            return []
        
        items = result.get("value", [])
        
        if folders_only:
            return [item for item in items if "folder" in item]
        
        return items
    
    @staticmethod
    def get_folder_details(
        drive_id: str,
        folder_id: str,
        access_token: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a folder.
        
        Args:
            drive_id: SharePoint drive/library ID
            folder_id: Folder ID
            access_token: Bearer token for authentication
        
        Returns:
            Folder details including webUrl, or None if error
        """
        from samples.sharepoint_config import GRAPH_API_URL
        
        folder_url = f"{GRAPH_API_URL}/drives/{drive_id}/items/{folder_id}"
        return GraphAPIClient.get(folder_url, access_token, raise_on_error=False)


# Convenience functions for backward compatibility
def get_api_headers(access_token: str) -> Dict[str, str]:
    """Get standard API headers."""
    return GraphAPIClient.get_headers(access_token)


def make_graph_request(method: str, url: str, access_token: str, **kwargs) -> Optional[Dict[str, Any]]:
    """Make a Graph API request."""
    http_method = HTTPMethod[method.upper()]
    return GraphAPIClient.make_request(http_method, url, access_token, **kwargs)