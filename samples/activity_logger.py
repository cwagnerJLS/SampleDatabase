"""
Activity logging utilities for tracking user actions in the Sample Database
"""
import json
import logging
from typing import Dict, Any, Optional, List
from django.utils import timezone
from .models import ActivityLog, Sample

logger = logging.getLogger('samples')


def get_client_ip(request) -> Optional[str]:
    """Get the client's IP address from the request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def log_activity(
    request,
    action: str,
    object_type: Optional[str] = None,
    object_id: Optional[str] = None,
    changes: Optional[Dict[str, Any]] = None,
    details: Optional[str] = None,
    status: str = 'SUCCESS',
    error_message: Optional[str] = None,
    affected_count: int = 1,
    customer: Optional[str] = None,
    opportunity: Optional[str] = None
) -> ActivityLog:
    """
    Central function to log any user activity
    
    Args:
        request: Django request object
        action: Action type from ActivityLog.ACTION_CHOICES
        object_type: Type of object affected (e.g., 'Sample', 'Opportunity')
        object_id: ID of the affected object
        changes: Dictionary of changes (before/after values)
        details: Human-readable description
        status: SUCCESS, FAILED, or PARTIAL
        error_message: Error message if status is FAILED
        affected_count: Number of objects affected (for bulk operations)
        customer: Customer name associated with the activity
        opportunity: Opportunity number associated with the activity
    
    Returns:
        Created ActivityLog instance
    """
    try:
        user = getattr(request, 'current_user', 'Unknown User')
        
        log_entry = ActivityLog.objects.create(
            user=user,
            action=action,
            timestamp=timezone.now(),
            status=status,
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],  # Limit length
            object_type=object_type,
            object_id=str(object_id) if object_id else None,
            changes=changes,
            details=details,
            error_message=error_message,
            affected_count=affected_count,
            session_id=request.session.session_key if hasattr(request, 'session') else None,
            customer=customer,
            opportunity=opportunity
        )
        
        logger.debug(f"Activity logged: {user} - {action} - {object_type}:{object_id}")
        return log_entry
        
    except Exception as e:
        logger.error(f"Failed to log activity: {e}")
        # Don't let logging failures break the application
        return None


def log_sample_change(
    request,
    sample: Sample,
    action: str,
    old_values: Optional[Dict[str, Any]] = None,
    new_values: Optional[Dict[str, Any]] = None,
    details: Optional[str] = None
) -> ActivityLog:
    """
    Helper function specifically for logging sample changes
    
    Args:
        request: Django request object
        sample: Sample instance
        action: Action type
        old_values: Previous values
        new_values: New values
        details: Additional details
    
    Returns:
        Created ActivityLog instance
    """
    changes = {}
    if old_values and new_values:
        # Only record actual changes
        for key, new_val in new_values.items():
            old_val = old_values.get(key)
            if old_val != new_val:
                changes[key] = {
                    'old': old_val,
                    'new': new_val
                }
    
    if not details:
        # Generate automatic description
        if action == 'SAMPLE_CREATE':
            details = f"Created sample {sample.unique_id} for {sample.customer}"
        elif action == 'LOCATION_CHANGE':
            old_loc = old_values.get('storage_location') if old_values else None
            new_loc = new_values.get('storage_location') if new_values else sample.storage_location
            details = f"Location changed: {old_loc or 'None'} → {new_loc or 'None'}"
        elif action == 'SAMPLE_AUDIT':
            details = f"Audited sample {sample.unique_id}"
    
    return log_activity(
        request=request,
        action=action,
        object_type='Sample',
        object_id=sample.unique_id,
        changes=changes,
        details=details,
        customer=sample.customer,
        opportunity=sample.opportunity_number
    )


def log_bulk_operation(
    request,
    action: str,
    sample_ids: List[int],
    details: str,
    status: str = 'SUCCESS',
    error_message: Optional[str] = None
) -> ActivityLog:
    """
    Helper function for logging bulk operations
    
    Args:
        request: Django request object
        action: Bulk action type
        sample_ids: List of affected sample IDs
        details: Description of the operation
        status: Operation status
        error_message: Error if failed
    
    Returns:
        Created ActivityLog instance
    """
    # Try to get customer and opportunity from the first sample
    customer = None
    opportunity = None
    if sample_ids:
        try:
            first_sample = Sample.objects.filter(unique_id=sample_ids[0]).first()
            if first_sample:
                customer = first_sample.customer
                opportunity = first_sample.opportunity_number
                # Check if all samples have same customer/opportunity
                samples = Sample.objects.filter(unique_id__in=sample_ids[:10])  # Check first 10
                customers = set(s.customer for s in samples if s.customer)
                opportunities = set(s.opportunity_number for s in samples if s.opportunity_number)
                # If multiple customers/opportunities, indicate in the fields
                if len(customers) > 1:
                    customer = f"Multiple ({len(customers)})"
                if len(opportunities) > 1:
                    opportunity = f"Multiple ({len(opportunities)})"
        except Exception:
            pass  # Don't let this break the logging
    
    return log_activity(
        request=request,
        action=action,
        object_type='Sample',
        object_id=json.dumps(sample_ids[:100]),  # Limit to first 100 IDs to avoid huge logs
        details=details,
        status=status,
        error_message=error_message,
        affected_count=len(sample_ids),
        customer=customer,
        opportunity=opportunity
    )


def log_export(
    request,
    export_type: str,
    details: str,
    sample_count: int = 0,
    customer: Optional[str] = None,
    opportunity: Optional[str] = None,
    object_id: Optional[str] = None
) -> ActivityLog:
    """
    Log data export operations
    
    Args:
        request: Django request object
        export_type: Type of export (CSV, Excel, Documentation, etc.)
        details: Export details
        sample_count: Number of samples exported
        customer: Customer name associated with the export
        opportunity: Opportunity number associated with the export
        object_id: ID of the object being exported (e.g., opportunity number)
    
    Returns:
        Created ActivityLog instance
    """
    return log_activity(
        request=request,
        action='EXPORT',
        object_type='Export',
        object_id=object_id,
        details=f"{export_type}: {details}",
        affected_count=sample_count,
        customer=customer,
        opportunity=opportunity
    )


def log_error(
    request,
    operation: str,
    error_message: str,
    object_type: Optional[str] = None,
    object_id: Optional[str] = None
) -> ActivityLog:
    """
    Log failed operations
    
    Args:
        request: Django request object
        operation: What operation failed
        error_message: Error details
        object_type: Type of object involved
        object_id: ID of object involved
    
    Returns:
        Created ActivityLog instance
    """
    return log_activity(
        request=request,
        action='ERROR',
        object_type=object_type,
        object_id=object_id,
        details=f"Failed operation: {operation}",
        status='FAILED',
        error_message=error_message
    )


def get_user_activity_summary(user: str, days: int = 30) -> Dict[str, Any]:
    """
    Get summary of user's recent activity
    
    Args:
        user: Username
        days: Number of days to look back
    
    Returns:
        Dictionary with activity summary
    """
    cutoff_date = timezone.now() - timezone.timedelta(days=days)
    user_logs = ActivityLog.objects.filter(
        user=user,
        timestamp__gte=cutoff_date
    )
    
    summary = {
        'total_actions': user_logs.count(),
        'samples_created': user_logs.filter(action='SAMPLE_CREATE').count(),
        'samples_audited': user_logs.filter(action='SAMPLE_AUDIT').count(),
        'location_changes': user_logs.filter(action='LOCATION_CHANGE').count(),
        'exports': user_logs.filter(action='EXPORT').count(),
        'errors': user_logs.filter(status='FAILED').count(),
        'last_activity': user_logs.first().timestamp if user_logs.exists() else None
    }
    
    return summary