def current_user(request):
    """Add current user to template context"""
    return {
        'current_user': getattr(request, 'current_user', None)
    }