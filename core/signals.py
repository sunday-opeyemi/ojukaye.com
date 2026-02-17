# core/signals.py
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models import F, Sum, Count
from datetime import timedelta
import logging

from .models import (
    UserProfile, UserActivity, Post, Comment, Follow, Repost, 
    Notification, Advertisement, Group, GroupMember, GroupPost,
    SystemSettings, AdAnalytics
)

logger = logging.getLogger(__name__)

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Auto-create UserProfile when User is created"""
    if created:
        UserProfile.objects.get_or_create(user=instance)
        logger.info(f"Created/Retrieved UserProfile for {instance.username}")

@receiver(post_save, sender=Advertisement)
def handle_ad_approval(sender, instance, created, **kwargs):
    """Handle ad approval status changes"""
    if not created and instance.status == 'approved' and not instance.approved_at:
        instance.approved_at = timezone.now()
        instance.save(update_fields=['approved_at'])
        
        # Create notification for business
        Notification.objects.create(
            user=instance.business,
            notification_type='ad_approval',
            message=f'Your ad "{instance.title}" has been approved',
            details={'ad_id': instance.id}
        )
        logger.info(f"Ad {instance.id} approved")

@receiver(post_save, sender=Post)
def handle_sponsored_post(sender, instance, created, **kwargs):
    """Handle sponsored post creation"""
    if instance.is_sponsored and instance.advertisement:
        # Update ad analytics
        if instance.is_banner:
            instance.advertisement.impressions = F('impressions') + 1
            instance.advertisement.save(update_fields=['impressions'])
            
            # Create daily analytics record
            today = timezone.now().date()
            analytics, _ = AdAnalytics.objects.get_or_create(
                advertisement=instance.advertisement,
                date=today
            )
            analytics.impressions += 1
            analytics.save(update_fields=['impressions'])
            logger.info(f"Updated ad analytics for {instance.advertisement.title}")

@receiver(pre_save, sender=Post)
def handle_post_type(sender, instance, **kwargs):
    """Auto-set post properties based on type"""
    if instance.post_type == 'profile_post':
        instance.profile_only = True
        instance.category = None  # Profile posts don't have categories
    
    if instance.post_type == 'sponsored' and instance.advertisement:
        instance.is_sponsored = True
    
    # Auto-approve based on system settings
    if instance.is_auto_fetched:
        try:
            settings = SystemSettings.objects.first()
            if settings and settings.auto_verify_news:
                if instance.verification_score >= settings.verification_threshold:
                    instance.is_approved = True
                    instance.verification_status = 'verified'
        except SystemSettings.DoesNotExist:
            pass

@receiver(post_save, sender=GroupMember)
def update_group_member_count(sender, instance, created, **kwargs):
    """Update group member count"""
    if created:
        instance.group.member_count = GroupMember.objects.filter(
            group=instance.group, 
            is_banned=False
        ).count()
        instance.group.save(update_fields=['member_count'])
        logger.info(f"Updated member count for {instance.group.name}")

@receiver(post_save, sender=GroupPost)
def update_group_post_count(sender, instance, created, **kwargs):
    """Update group post count"""
    if created and instance.is_approved:
        instance.group.post_count = GroupPost.objects.filter(
            group=instance.group,
            is_approved=True
        ).count()
        instance.group.save(update_fields=['post_count'])
        logger.info(f"Updated post count for {instance.group.name}")

@receiver(post_save, sender=UserProfile)
def handle_business_verification(sender, instance, **kwargs):
    """Handle business verification"""
    if instance.account_type == 'business' and instance.is_verified_business:
        # Add welcome ad credits for new verified businesses
        if not hasattr(instance, '_welcome_credits_added'):
            instance.ad_credits += 10000  # ₦10,000 welcome credits
            instance.save(update_fields=['ad_credits'])
            instance._welcome_credits_added = True
            
            # Create notification
            Notification.objects.create(
                user=instance.user,
                notification_type='business_verified',
                message='Your business account has been verified! ₦10,000 ad credits added.',
                details={'credits': 10000}
            )
            logger.info(f"Added welcome credits for {instance.business_name}")

# Schedule tasks for ad expiration
def check_ad_expirations():
    """Check and expire ads"""
    expired_ads = Advertisement.objects.filter(
        end_date__lt=timezone.now(),
        status='active'
    )
    
    for ad in expired_ads:
        ad.status = 'expired'
        ad.is_active = False
        ad.save(update_fields=['status', 'is_active'])
        logger.info(f"Ad {ad.id} expired")

def update_trending_scores():
    """Update trending scores for posts"""
    time_threshold = timezone.now() - timedelta(hours=48)
    
    # Get posts from last 48 hours
    recent_posts = Post.objects.filter(
        created_at__gte=time_threshold,
        status='published'
    )
    
    for post in recent_posts:
        post.update_engagement_score()
    
    logger.info(f"Updated trending scores for {recent_posts.count()} posts")

# These would be called by Celery or scheduled tasks