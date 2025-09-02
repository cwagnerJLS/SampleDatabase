from django.shortcuts import redirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin


class UserIdentificationMiddleware(MiddlewareMixin):
    """
    Middleware to ensure all requests have a valid user identifier cookie.
    If not, redirect to user selection page.
    """
    
    COOKIE_NAME = 'sample_db_user'
    VALID_USERS = [
        'Corey Wagner',
        'Mike Mooney', 
        'Colby Wentz',
        'Noah Dekker'
    ]
    
    EXEMPT_PATHS = [
        '/select-user/',
        '/set-user/',
        '/health/',
        '/admin/',
        '/static/',
        '/media/',
    ]
    
    def process_request(self, request):
        # Check if this path is exempt from user identification
        for exempt_path in self.EXEMPT_PATHS:
            if request.path.startswith(exempt_path):
                return None
        
        # Get the user from cookie
        user_name = request.COOKIES.get(self.COOKIE_NAME)
        
        # Validate the user
        if user_name and user_name in self.VALID_USERS:
            # Attach user to request object for easy access
            request.current_user = user_name
            return None
        
        # No valid user cookie, redirect to selection page
        # But only for GET requests to avoid losing POST data
        if request.method == 'GET':
            # Store the original URL to redirect back after selection
            request.session['redirect_after_user_selection'] = request.get_full_path()
            return redirect('select_user')
        
        # For non-GET requests without valid user, set as anonymous
        request.current_user = 'Unknown User'
        return None