# core/context_processors.py
from django.utils import timezone
from django.db.models import Count, Q
from .models import Category, Notification, Post, User, SystemSettings, Advertisement
from datetime import timedelta


def site_context(request):
    """Add common context to all templates"""
    context = {
        'site_name': 'Ojukaye',
        'site_description': "Nigeria's Modern News & Discussion Platform",
        'current_time': timezone.now(),
    }
    
    try:
        # Get system settings
        settings = SystemSettings.objects.first()
        if settings:
            context['system_settings'] = settings
        
        # Get categories with cached counts
        categories = Category.objects.filter(
            parent__isnull=True
        ).annotate(
            post_count=Count('posts')
        ).filter(post_count__gt=0).order_by('-post_count')[:15]
        
        for category in categories:
            # Update cached count if needed
            if category.cached_post_count != category.post_count:
                category.cached_post_count = category.post_count
                category.save(update_fields=['cached_post_count'])
        
        context['categories'] = categories
        
        # Get stats
        context['total_posts'] = Post.objects.filter(status='published').count()
        context['total_users'] = User.objects.filter(is_active=True).count()
        
        # Get active banner ads for rotation
        banner_ads = Advertisement.objects.filter(
            ad_type='banner',
            status='active',
            is_active=True,
            start_date__lte=timezone.now(),
            end_date__gte=timezone.now()
        )[:10]  # Limit to 10
        
        if banner_ads.exists():
            context['banner_ads'] = banner_ads
        
        # Add user-specific context
        if request.user.is_authenticated:
            # Notification count
            notification_count = Notification.objects.filter(
                user=request.user, 
                is_read=False
            ).count()
            context['notification_count'] = notification_count
            
            # User account type
            if hasattr(request.user, 'profile'):
                profile = request.user.profile
                context['user_account_type'] = profile.account_type
                context['user_is_verified_business'] = profile.is_verified_business
                context['user_ad_credits'] = profile.ad_credits
            
            # Online users count (last 15 minutes)
            fifteen_minutes_ago = timezone.now() - timedelta(minutes=15)
            online_users = User.objects.filter(
                last_login__gte=fifteen_minutes_ago,
                is_active=True
            ).count()
            context['online_users_count'] = min(online_users, 50)  # Cap at 50 for display
        
        # Guest access flag
        context['enable_guest_access'] = getattr(settings, 'enable_guest_access', True) if settings else True
        
    except Exception as e:
        # Log but don't crash
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in site_context: {e}")
        
        # Set defaults
        context['categories'] = []
        context['total_posts'] = 0
        context['total_users'] = 0
        context['enable_guest_access'] = True
        context['notification_count'] = 0
    
    return context

def news_stats(request):
    if not request.user.is_authenticated:
        return {}
    
    stats = {
        'verified_count': Post.objects.filter(
            is_auto_fetched=True,
            verification_status='verified'
        ).count(),
        'pending_count': Post.objects.filter(
            is_auto_fetched=True,
            verification_status='pending'
        ).count(),
        'checked_count': Post.objects.filter(
            is_auto_fetched=True
        ).exclude(verification_status='pending').count(),
    }
    
    return stats