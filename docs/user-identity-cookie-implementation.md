# Django User Identity Cookie System Implementation Guide

This guide explains how to implement a simple user identity system using browser cookies in Django. This system prompts new users to identify themselves on first visit and remembers their choice for future visits.

## Overview

The system consists of:
- Custom Django middleware to check for user cookies
- A user selection page for first-time visitors
- Cookie management to persist user identity
- Automatic redirection after user selection

## Implementation Steps

### 1. Create the Middleware

Create a file `middleware.py` in your Django app:

```python
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
```

### 2. Add Middleware to Settings

In your `settings.py`, add the middleware to `MIDDLEWARE`:

```python
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # Add your custom middleware here
    'yourapp.middleware.UserIdentificationMiddleware',
]
```

### 3. Create View Functions

Add these views to your `views.py`:

```python
from django.shortcuts import render, redirect

def select_user(request):
    """Display user selection page"""
    return render(request, 'yourapp/select_user.html')

def set_user(request):
    """Set the user cookie based on selection"""
    if request.method == 'POST':
        user_name = request.POST.get('user_name')
        
        # Validate user name
        valid_users = ['Corey Wagner', 'Mike Mooney', 'Colby Wentz', 'Noah Dekker']
        if user_name in valid_users:
            # Get redirect URL from session or default to home
            redirect_url = request.session.pop('redirect_after_user_selection', '/')
            
            response = redirect(redirect_url)
            # Set cookie for 1 year
            max_age = 365 * 24 * 60 * 60  # 1 year in seconds
            response.set_cookie(
                'sample_db_user',
                user_name,
                max_age=max_age,
                httponly=True,
                samesite='Lax'
            )
            return response
    
    return redirect('select_user')
```

### 4. Create the User Selection Template

Create `templates/yourapp/select_user.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Select User - Sample Database</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        
        .container {
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            padding: 40px;
            max-width: 500px;
            width: 100%;
            text-align: center;
        }
        
        h1 {
            color: #333;
            margin-bottom: 10px;
            font-size: 28px;
        }
        
        .subtitle {
            color: #666;
            margin-bottom: 30px;
            font-size: 16px;
        }
        
        .user-grid {
            display: grid;
            grid-template-columns: 1fr;
            gap: 15px;
            margin-bottom: 30px;
        }
        
        .user-button {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 20px;
            border-radius: 10px;
            font-size: 18px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
        }
        
        .user-button:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
        }
        
        .user-button:active {
            transform: translateY(0);
        }
        
        .info-text {
            color: #999;
            font-size: 14px;
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid #eee;
        }
        
        .icon {
            font-size: 48px;
            margin-bottom: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="icon">👤</div>
        <h1>Welcome to Your Application</h1>
        <p class="subtitle">Please select your name to continue</p>
        
        <form method="POST" action="{% url 'set_user' %}">
            {% csrf_token %}
            <div class="user-grid">
                <button type="submit" name="user_name" value="Corey Wagner" class="user-button">
                    Corey Wagner
                </button>
                <button type="submit" name="user_name" value="Mike Mooney" class="user-button">
                    Mike Mooney
                </button>
                <button type="submit" name="user_name" value="Colby Wentz" class="user-button">
                    Colby Wentz
                </button>
                <button type="submit" name="user_name" value="Noah Dekker" class="user-button">
                    Noah Dekker
                </button>
            </div>
        </form>
        
        <p class="info-text">
            This is a one-time setup for this computer.<br>
            Your selection will be remembered permanently.
        </p>
    </div>
</body>
</html>
```

### 5. Configure URL Patterns

Add these URL patterns to your `urls.py`:

```python
from django.urls import path
from . import views

urlpatterns = [
    # ... your other URL patterns ...
    path('select-user/', views.select_user, name='select_user'),
    path('set-user/', views.set_user, name='set_user'),
]
```

## How It Works

### Flow Diagram
```
New User Visit → No Cookie Found → Redirect to Selection Page → User Selects Identity → 
Cookie Set → Redirect to Original Page → Future Visits Use Stored Cookie
```

### Key Features

1. **Automatic Detection**: The middleware runs on every request and checks for the presence of a valid user cookie.

2. **Session Preservation**: When redirecting to the selection page, the original URL is stored in the session so users return to where they intended to go.

3. **Exempt Paths**: Certain paths (admin, static files, the selection page itself) are exempt from the check to prevent redirect loops.

4. **Cookie Security**:
   - `httponly=True`: Prevents JavaScript access to the cookie
   - `samesite='Lax'`: Provides CSRF protection
   - 1-year expiration: Balances convenience with security

5. **Request Enhancement**: The middleware adds `request.current_user` to every validated request, making the user's name available throughout your application.

## Using the Current User in Your Application

Once implemented, you can access the current user's name anywhere in your views:

```python
def my_view(request):
    user_name = request.current_user  # e.g., "Corey Wagner"
    # Use the user_name as needed
    return render(request, 'template.html', {'user': user_name})
```

In templates:
```html
<p>Welcome, {{ request.current_user }}!</p>
```

## Customization Options

### Modify Valid Users
Change the `VALID_USERS` list in the middleware and update the template buttons accordingly.

### Change Cookie Duration
Modify the `max_age` parameter in the `set_user` view:
```python
max_age = 30 * 24 * 60 * 60  # 30 days instead of 1 year
```

### Add More Exempt Paths
Update the `EXEMPT_PATHS` list in the middleware to exclude additional URLs from user identification.

### Dynamic User List
Instead of hardcoding users, you could fetch them from a database:
```python
VALID_USERS = User.objects.values_list('username', flat=True)
```

## Security Considerations

1. **Not for Authentication**: This system is for user identification only, not security. It should not replace proper authentication for sensitive operations.

2. **Cookie Tampering**: Users can modify cookies. Validate the cookie value against your allowed users list.

3. **HTTPS**: Always use HTTPS in production to prevent cookie interception.

4. **Additional Security**: For sensitive applications, consider adding:
   - IP address validation
   - User agent checking
   - Shorter cookie expiration times
   - Server-side session storage instead of cookies

## Troubleshooting

### Users Get Redirected in a Loop
- Ensure `/select-user/` and `/set-user/` are in the `EXEMPT_PATHS` list
- Check that the middleware is properly configured in settings

### Cookie Not Being Set
- Verify CSRF token is included in the form
- Check browser cookie settings
- Ensure the domain/path settings are correct

### User Identity Not Available in Views
- Confirm middleware is in the correct position in `MIDDLEWARE` list
- The middleware should come after `SessionMiddleware` but before view processing

## Conclusion

This implementation provides a simple, effective way to identify users in a Django application without requiring full authentication. It's particularly useful for internal tools, logging systems, or applications where you need to track user actions without managing passwords.