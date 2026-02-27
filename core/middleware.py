from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin
from django.contrib import messages
from django.utils.cache import add_never_cache_headers
import json

class MessageToModalMiddleware(MiddlewareMixin):
    """
    Convert Django messages to modal display
    """
    def process_response(self, request, response):
        # Check if there are messages and this is not an AJAX request
        if hasattr(request, '_messages') and not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            message_list = []
            storage = messages.get_messages(request)
            
            for message in storage:
                message_list.append({
                    'message': str(message),
                    'tags': message.tags,
                    'level': message.level
                })
            
            if message_list:
                # Store messages in session for modal display
                request.session['modal_messages'] = message_list
                
                # Clear the messages so they don't appear in regular alerts
                storage.used = True
        
        return response


class DisableBrowserCacheMiddleware:
    """
    Disable browser caching during development
    This ensures templates and CSS changes appear immediately
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        # Only disable cache in debug mode
        if settings.DEBUG:
            add_never_cache_headers(response)
            response['Cache-Control'] = 'no-cache, no-store, must-revalidate, private'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
        
        return response

        
class StaticFilesDebugMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith('/static/'):
            print(f"Static file requested: {request.path}")
            print(f"STATIC_ROOT: {settings.STATIC_ROOT}")
            print(f"STATICFILES_DIRS: {settings.STATICFILES_DIRS}")
        return response
    
# Update GuestRestrictionMiddleware
class GuestRestrictionMiddleware(MiddlewareMixin):
    """
    Restrict guest users to specific pages only
    Guests can only view online news and public content
    """
    
    # Pages that guests can access (PUBLIC)
    ALLOWED_PATHS = [
        '/online-news/',  # Online news page - MAIN PUBLIC PAGE
        '/login/',  # Login page
        '/register/',  # Registration page
        '/static/',  # Static files
        '/media/',  # Media files
        '/api/banners/',  # Banner API
        '/api/check-new-news/',  # Check news API
        '/api/news-feed/',  # News feed API
        '/about/',  # About page
        '/contact/',  # Contact page
        '/privacy/',  # Privacy policy
        '/terms/',  # Terms of service
        '/help/',  # Help center
        '/faq/',  # FAQ
        '/resources/',  # Resources
        '/category/',  # Public category pages
        '/search/',  # Public search
    ]
    
    # Public post URLs that guests can view
    ALLOWED_POST_PATHS = [
        '/post/',  # Individual post view
    ]
    
    def process_request(self, request):
        # Skip middleware for API endpoints (except specific public ones)
        if request.path.startswith('/api/') and not any(
            request.path.startswith(path) for path in ['/api/banners/', '/api/check-new-news/', '/api/news-feed/']
        ):
            return
        
        # Allow superusers and staff
        if request.user.is_authenticated and (request.user.is_superuser or request.user.is_staff):
            return
        
        # Check if path is allowed for guests
        if any(request.path.startswith(path) for path in self.ALLOWED_PATHS):
            return
        
        # Check if it's a public post view
        if any(request.path.startswith(path) for path in self.ALLOWED_POST_PATHS):
            # Allow guests to view individual posts
            return
        
        # If user is authenticated, allow access to personal pages
        if request.user.is_authenticated:
            return
        
        # Guest trying to access protected page - redirect to online_news
        messages.info(request, 'Please login to access your personal dashboard')
        return redirect('online_news')
        
        # Check business account restrictions
        if request.path.startswith('/ads/') and hasattr(request.user, 'profile'):
            if not request.user.profile.can_submit_ads():
                messages.error(request, 'Business account verification required to submit ads')
                return redirect('profile')

class BusinessAccountMiddleware(MiddlewareMixin):
    """
    Restrict ad-related features to verified business accounts
    """
    
    AD_PATHS = [
        '/ads/submit/',
        '/ads/manage/',
        '/ads/edit/',
        '/ads/stats/',
    ]
    
    def process_request(self, request):
        # Only check for ad-related paths
        if not any(request.path.startswith(path) for path in self.AD_PATHS):
            return
        
        # Check if user is authenticated
        if not request.user.is_authenticated:
            return redirect('login')
        
        # Check if user has a profile
        if not hasattr(request.user, 'profile'):
            messages.error(request, 'Please complete your profile first')
            return redirect('edit_profile')
        
        # Check if user is a business account
        if request.user.profile.account_type != 'business':
            messages.error(request, 'This feature is only available for business accounts')
            return redirect('profile')
        
        # Check if business is verified
        if not request.user.profile.is_verified_business:
            messages.error(request, 'Your business account needs verification to submit ads')
            return redirect('business_verification')