"""
Centralized response utilities for consistent JSON responses.
Eliminates duplicate response code throughout the application.
"""
from django.http import JsonResponse
from typing import Optional, Dict, Any


def error_response(message: str, status: int = 400) -> JsonResponse:
    """
    Create a standardized error response.
    
    Args:
        message: The error message to return
        status: HTTP status code (default: 400)
    
    Returns:
        JsonResponse with error status and message
    """
    return JsonResponse({'status': 'error', 'error': message}, status=status)


def success_response(message: Optional[str] = None, data: Optional[Dict[str, Any]] = None, **kwargs) -> JsonResponse:
    """
    Create a standardized success response.
    
    Args:
        message: Optional success message
        data: Optional dictionary of additional data to include
        **kwargs: Additional key-value pairs to include in response
    
    Returns:
        JsonResponse with success status and optional message/data
    """
    response = {'status': 'success'}
    
    if message:
        response['message'] = message
    
    if data:
        response.update(data)
    
    # Add any additional kwargs
    response.update(kwargs)
    
    return JsonResponse(response)


def validation_error_response(field: str, message: str) -> JsonResponse:
    """
    Create a standardized validation error response.
    
    Args:
        field: The field that failed validation
        message: The validation error message
    
    Returns:
        JsonResponse with validation error details
    """
    return JsonResponse({
        'status': 'error',
        'error': 'Validation failed',
        'details': {field: message}
    }, status=400)


def not_found_response(resource: str, identifier: Optional[str] = None) -> JsonResponse:
    """
    Create a standardized not found response.
    
    Args:
        resource: The type of resource not found (e.g., 'Sample', 'Image')
        identifier: Optional identifier of the resource
    
    Returns:
        JsonResponse with not found error
    """
    if identifier:
        message = f'{resource} with ID {identifier} not found'
    else:
        message = f'{resource} not found'
    
    return error_response(message, status=404)


def method_not_allowed_response() -> JsonResponse:
    """
    Create a standardized method not allowed response.
    
    Returns:
        JsonResponse with method not allowed error
    """
    return error_response('Method not allowed', status=405)


def server_error_response(details: Optional[str] = None) -> JsonResponse:
    """
    Create a standardized server error response.
    
    Args:
        details: Optional error details (will be converted to string)
    
    Returns:
        JsonResponse with server error
    """
    if details:
        message = str(details)
    else:
        message = 'An unexpected error occurred'
    
    return error_response(message, status=500)