# core/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.urls import path
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta

# Import models
from .models import (
    Post, Category, Comment, UserProfile, Notification, 
    Advertisement, Group, GroupMember, SystemSettings, AdAnalytics,
    UserActivity, Follow, Repost, GroupPost, User
)
from .forms import SystemSettingsForm

# Register SystemSettings first
@admin.register(SystemSettings)
class SystemSettingsAdmin(admin.ModelAdmin):
    """System Settings Admin"""
    def has_add_permission(self, request):
        # Only allow one instance
        return not SystemSettings.objects.exists()

@admin.register(Advertisement)
class AdvertisementAdmin(admin.ModelAdmin):
    list_display = ['title', 'business', 'ad_type', 'status', 'budget', 'spent', 'is_active', 'created_at']
    list_filter = ['ad_type', 'status', 'is_active', 'created_at']
    search_fields = ['title', 'business__username', 'business__profile__business_name']
    readonly_fields = ['spent', 'uuid', 'created_at', 'updated_at']
    actions = ['approve_selected', 'reject_selected', 'activate_selected', 'pause_selected']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('business', 'ad_type', 'title', 'content', 'image', 'target_url')
        }),
        ('Budget & Duration', {
            'fields': ('budget', 'spent', 'start_date', 'end_date')
        }),
        ('Targeting', {
            'fields': ('target_categories', 'target_locations', 'target_keywords')
        }),
        ('Status & Approval', {
            'fields': ('status', 'is_active', 'approved_by', 'approved_at', 'rejection_reason')
        }),
        ('Performance Limits', {
            'fields': ('max_clicks', 'max_impressions')
        }),
        ('Metadata', {
            'fields': ('uuid', 'created_at', 'updated_at')
        }),
    )
    
    def approve_selected(self, request, queryset):
        queryset.update(
            status='approved',
            is_active=True,
            approved_by=request.user,
            approved_at=timezone.now()
        )
        self.message_user(request, f"{queryset.count()} ads approved.")
    approve_selected.short_description = "Approve selected ads"
    
    def reject_selected(self, request, queryset):
        queryset.update(status='rejected', is_active=False)
        self.message_user(request, f"{queryset.count()} ads rejected.")
    reject_selected.short_description = "Reject selected ads"
    
    def activate_selected(self, request, queryset):
        queryset.update(is_active=True, status='active')
        self.message_user(request, f"{queryset.count()} ads activated.")
    activate_selected.short_description = "Activate selected ads"
    
    def pause_selected(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, f"{queryset.count()} ads paused.")
    pause_selected.short_description = "Pause selected ads"

@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_by', 'group_type', 'member_count', 'post_count', 'is_active']
    list_filter = ['group_type', 'is_active', 'created_at']
    search_fields = ['name', 'description', 'created_by__username']
    filter_horizontal = ['admins', 'moderators']
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('group-analytics/', self.admin_site.admin_view(self.group_analytics),
                 name='group-analytics'),
        ]
        return custom_urls + urls
    
    def group_analytics(self, request):
        """Group analytics view"""
        groups = Group.objects.all()
        
        context = {
            'title': 'Group Analytics',
            'groups': groups,
            'total_groups': groups.count(),
            'total_members': groups.aggregate(Sum('member_count'))['member_count__sum'] or 0,
            'total_posts': groups.aggregate(Sum('post_count'))['post_count__sum'] or 0,
        }
        return render(request, 'admin/groups/analytics.html', context)

@admin.register(GroupMember)
class GroupMemberAdmin(admin.ModelAdmin):
    list_display = ['group', 'user', 'role', 'joined_at', 'is_banned']
    list_filter = ['role', 'is_banned', 'joined_at']
    search_fields = ['group__name', 'user__username']

@admin.register(GroupPost)
class GroupPostAdmin(admin.ModelAdmin):
    list_display = ['group', 'post', 'posted_by', 'is_approved', 'created_at']
    list_filter = ['is_approved', 'created_at']
    search_fields = ['group__name', 'post__title', 'posted_by__username']  # Fixed line 399

@admin.register(AdAnalytics)
class AdAnalyticsAdmin(admin.ModelAdmin):
    list_display = ['advertisement', 'date', 'impressions', 'clicks', 'cost', 'ctr', 'cpc']
    list_filter = ['date', 'advertisement__ad_type']
    readonly_fields = ['ctr', 'cpc']
    
    def has_add_permission(self, request):
        return False  # Analytics should be auto-generated

# Update PostAdmin
@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'author', 'post_type', 'category', 'status', 
        'verification_status_badge', 'is_approved', 'is_sponsored', 
        'profile_only', 'views', 'created_at'
    ]
    list_filter = [
        'post_type', 'status', 'category', 'created_at',
        'verification_status', 'is_approved', 'is_verified',
        'is_sponsored', 'profile_only', 'is_auto_fetched'
    ]
    search_fields = ['title', 'content', 'author__username', 'external_source']
    readonly_fields = [
        'views', 'created_at', 'updated_at', 
        'verification_score', 'verification_status', 'verification_details_display',
        'banner_clicks', 'banner_impressions'
    ]
    actions = [
        'approve_selected', 'reject_selected', 'verify_selected',
        'mark_as_fake', 'delete_fake_news', 'run_verification',
        'mark_as_sponsored', 'mark_as_banner', 'mark_as_profile_only'
    ]
    
    def verification_status_badge(self, obj):
        colors = {
            'pending': 'gray',
            'verified': 'green',
            'fake': 'red',
            'checking': 'orange'
        }
        color = colors.get(obj.verification_status, 'gray')
        return format_html(
            '<span style="padding: 5px 10px; background: {}; color: white; border-radius: 10px;">{}</span>',
            color,
            obj.get_verification_status_display().upper()
        )
    verification_status_badge.short_description = 'Verification'
    
    def verification_details_display(self, obj):
        if not obj.verification_details:
            return "No verification details"
        
        details = obj.verification_details
        html = "<div style='max-height: 300px; overflow-y: auto;'>"
        
        if 'source_check' in details:
            html += f"<strong>Source:</strong> Score: {details['source_check'].get('score', 0):.2f}<br>"
        
        if 'content_check' in details:
            html += f"<strong>Content:</strong> Score: {details['content_check'].get('score', 0):.2f}<br>"
            if 'red_flags' in details['content_check']:
                html += f"Red flags: {', '.join(details['content_check']['red_flags'][:3])}<br>"
        
        if 'clickbait_check' in details:
            html += f"<strong>Clickbait:</strong> Score: {details['clickbait_check'].get('score', 0):.2f}<br>"
        
        html += f"<strong>Final Score:</strong> {obj.verification_score:.2f}<br>"
        html += "</div>"
        return format_html(html)
    verification_details_display.short_description = 'Verification Details'
    
    fieldsets = (
        ('Content', {
            'fields': ('title', 'content', 'author', 'category', 'post_type')
        }),
        ('Media', {
            'fields': ('image', 'image_url')
        }),
        ('News Information', {
            'fields': ('source_url', 'source_name', 'external_source', 'external_url')
        }),
        ('Status', {
            'fields': ('status', 'is_featured', 'is_trending')
        }),
        ('Visibility', {
            'fields': ('profile_only', 'allow_comments', 'allow_sharing')
        }),
        ('Advertisement', {
            'fields': ('is_sponsored', 'advertisement')
        }),
        ('Banner', {
            'fields': ('is_banner', 'banner_expires_at', 'banner_priority')
        }),
        ('Group', {
            'fields': ('group',)
        }),
        ('Verification', {
            'fields': ('is_verified', 'is_approved', 'verification_score', 
                      'verification_status', 'verification_details')
        }),
        ('Stats', {
            'fields': ('views', 'banner_clicks', 'banner_impressions')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at', 'published_at')
        }),
    )
    
    # Custom actions
    def approve_selected(self, request, queryset):
        queryset.update(is_approved=True, verification_status='verified')
        self.message_user(request, f"{queryset.count()} posts approved.")
    approve_selected.short_description = "Approve selected posts"
    
    def reject_selected(self, request, queryset):
        queryset.update(is_approved=False, verification_status='pending')
        self.message_user(request, f"{queryset.count()} posts rejected.")
    reject_selected.short_description = "Reject selected posts"
    
    def mark_as_fake(self, request, queryset):
        queryset.update(verification_status='fake', is_approved=False, status='archived')
        self.message_user(request, f"{queryset.count()} posts marked as fake.")
    mark_as_fake.short_description = "Mark as fake news"
    
    def delete_fake_news(self, request, queryset):
        fake_news = queryset.filter(verification_status='fake')
        count = fake_news.count()
        fake_news.delete()
        self.message_user(request, f"{count} fake news posts deleted.")
    delete_fake_news.short_description = "Delete fake news"
    
    def run_verification(self, request, queryset):
        from .news_verifier import NewsVerifier
        verifier = NewsVerifier()
        updated = 0
        
        for post in queryset:
            if post.is_auto_fetched and post.external_url:
                article = {
                    'title': post.title,
                    'content': post.content,
                    'url': post.external_url,
                    'source': post.external_source
                }
                
                result = verifier.verify_article(article)
                
                post.verification_score = result['score']
                post.verification_status = result['status']
                post.verification_details = result['details']
                
                # Auto-approve if score is high
                if result['score'] >= 0.7:
                    post.is_verified = True
                
                post.save()
                updated += 1
        
        self.message_user(request, f"Verified {updated} posts.")
    run_verification.short_description = "Run verification check"
    
    def verify_selected(self, request, queryset):
        queryset.update(is_verified=True, verification_status='verified')
        self.message_user(request, f"{queryset.count()} posts verified.")
    verify_selected.short_description = "Mark as verified"
    
    # Add new actions
    def mark_as_sponsored(self, request, queryset):
        queryset.update(is_sponsored=True)
        self.message_user(request, f"{queryset.count()} posts marked as sponsored.")
    mark_as_sponsored.short_description = "Mark as sponsored"
    
    def mark_as_banner(self, request, queryset):
        queryset.update(is_banner=True, banner_expires_at=timezone.now() + timedelta(days=7))
        self.message_user(request, f"{queryset.count()} posts marked as banners.")
    mark_as_banner.short_description = "Mark as banner"
    
    def mark_as_profile_only(self, request, queryset):
        queryset.update(profile_only=True)
        self.message_user(request, f"{queryset.count()} posts marked as profile-only.")
    mark_as_profile_only.short_description = "Mark as profile-only"

# Update UserProfileAdmin
@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'account_type', 'is_verified_business', 
        'ad_credits', 'total_posts', 'total_comments'
    ]
    list_filter = ['account_type', 'is_verified_business']
    search_fields = ['user__username', 'business_name']
    actions = ['verify_business', 'downgrade_to_individual', 'add_ad_credits']
    
    fieldsets = (
        ('Account Information', {
            'fields': ('user', 'account_type', 'is_verified_business')
        }),
        ('Business Information', {
            'fields': ('business_name', 'business_registration', 'business_address',
                      'business_phone', 'business_email', 'business_website',
                      'business_verified_at', 'business_verified_by')
        }),
        ('Ad Credits', {
            'fields': ('ad_credits',)
        }),
        ('Profile Information', {
            'fields': ('bio', 'profile_pic', 'cover_photo', 'location', 'website')
        }),
        ('Social Media', {
            'fields': ('twitter_handle', 'facebook_url', 'instagram_url', 'linkedin_url')
        }),
        ('Settings', {
            'fields': ('privacy_level', 'email_notifications', 'show_online_status',
                      'receive_promo_emails', 'ad_notifications')
        }),
        ('Stats', {
            'fields': ('total_posts', 'total_comments', 'total_likes_received',
                      'followers_count', 'following_count')
        }),
    )
    
    def verify_business(self, request, queryset):
        queryset.update(
            is_verified_business=True,
            business_verified_at=timezone.now(),
            business_verified_by=request.user
        )
        self.message_user(request, f"{queryset.count()} businesses verified.")
    verify_business.short_description = "Verify selected businesses"
    
    def downgrade_to_individual(self, request, queryset):
        queryset.update(account_type='individual', is_verified_business=False)
        self.message_user(request, f"{queryset.count()} accounts downgraded to individual.")
    downgrade_to_individual.short_description = "Downgrade to individual account"
    
    def add_ad_credits(self, request, queryset):
        for profile in queryset:
            if profile.account_type == 'business':
                profile.ad_credits += 10000
                profile.save()
        self.message_user(request, f"Added ₦10,000 credits to {queryset.count()} business accounts.")
    add_ad_credits.short_description = "Add ₦10,000 ad credits"

# Register other models
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'parent', 'order', 'cached_post_count']
    prepopulated_fields = {'slug': ('name',)}
    list_filter = ['parent']
    search_fields = ['name']

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ['user', 'post', 'created_at', 'is_active']
    list_filter = ['is_active', 'created_at']
    search_fields = ['content', 'user__username', 'post__title']

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'notification_type', 'message', 'is_read', 'created_at']
    list_filter = ['notification_type', 'is_read', 'created_at']
    search_fields = ['message', 'user__username']

@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
    list_display = ['user', 'activity_type', 'created_at']
    list_filter = ['activity_type', 'created_at']
    search_fields = ['user__username']

@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
    list_display = ['follower', 'following', 'created_at']
    search_fields = ['follower__username', 'following__username']

@admin.register(Repost)
class RepostAdmin(admin.ModelAdmin):
    list_display = ['user', 'original_post', 'created_at']
    search_fields = ['user__username', 'original_post__title']