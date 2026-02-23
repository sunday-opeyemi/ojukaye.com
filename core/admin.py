from django.contrib import admin
from django.utils.html import format_html
from django.urls import path, reverse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth.models import User

from .models import (
    Post, Category, Comment, UserProfile, Notification, 
    Advertisement, Group, GroupMember, SystemSettings, AdAnalytics,
    UserActivity, Follow, Repost, GroupPost
)
from .forms import SystemSettingsForm
from .news_verifier import process_news_submission, verify_existing_posts

# Register SystemSettings first
@admin.register(SystemSettings)
class SystemSettingsAdmin(admin.ModelAdmin):
    """System Settings Admin"""
    # Fixed: Use actual field names from SystemSettings model
    list_display = ['id', 'maintenance_mode', 'auto_approve_threshold', 'updated_at']
    # Or if you want to show site name, you'll need to add it to the model first
    # For now, we'll use id or other existing fields
    
    def has_add_permission(self, request):
        # Only allow one instance
        return not SystemSettings.objects.exists()
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('system-stats/', self.admin_site.admin_view(self.system_stats),
                 name='system-stats'),
        ]
        return custom_urls + urls
    
    def system_stats(self, request):
        """System statistics view"""
        stats = {
            'total_posts': Post.objects.count(),
            'total_users': User.objects.count(),
            'total_categories': Category.objects.count(),
            'total_groups': Group.objects.count(),
            'pending_news': Post.objects.filter(is_news_submission=True, submission_status='pending').count(),
            'auto_fetched': Post.objects.filter(is_auto_fetched=True).count(),
            'verified_posts': Post.objects.filter(verification_status='verified').count(),
            'fake_posts': Post.objects.filter(verification_status='fake').count(),
        }
        
        context = {
            'title': 'System Statistics',
            'stats': stats,
        }
        return render(request, 'admin/system_stats.html', context)


@admin.register(Advertisement)
class AdvertisementAdmin(admin.ModelAdmin):
    list_display = ['title', 'business', 'ad_type', 'status_badge', 'budget', 'spent', 'is_active', 'created_at']
    list_filter = ['ad_type', 'status', 'is_active', 'created_at']
    search_fields = ['title', 'business__username', 'business__profile__business_name']
    readonly_fields = ['uuid', 'created_at', 'updated_at', 'spent']
    actions = ['approve_selected', 'reject_selected', 'activate_selected', 'pause_selected']
    
    def status_badge(self, obj):
        colors = {
            'pending': 'orange',
            'approved': 'green',
            'rejected': 'red',
            'expired': 'gray'
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="padding: 3px 8px; background: {}; color: white; border-radius: 5px;">{}</span>',
            color,
            obj.get_status_display().upper()
        )
    status_badge.short_description = 'Status'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('business', 'ad_type', 'title', 'description', 'image', 'target_url')
        }),
        ('Budget & Duration', {
            'fields': ('budget', 'spent', 'start_date', 'end_date')
        }),
        ('Pricing', {
            'fields': ('cost_per_impression', 'cost_per_click')
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
    list_display = ['name', 'created_by', 'group_type', 'member_count', 'post_count', 'is_active', 'created_at']
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
    search_fields = ['group__name', 'post__title', 'posted_by__username']


@admin.register(AdAnalytics)
class AdAnalyticsAdmin(admin.ModelAdmin):
    list_display = ['advertisement', 'date', 'impressions', 'clicks', 'cost', 'ctr_display', 'cpc_display']
    list_filter = ['date', 'advertisement__ad_type']
    readonly_fields = ['ctr_display', 'cpc_display']
    
    def ctr_display(self, obj):
        return f"{obj.ctr:.2f}%"
    ctr_display.short_description = 'CTR'
    
    def cpc_display(self, obj):
        return f"₦{obj.cpc:.2f}" if obj.cpc else "₦0.00"
    cpc_display.short_description = 'CPC'
    
    def has_add_permission(self, request):
        return False  # Analytics should be auto-generated


# Custom filter for verification status
class VerificationStatusFilter(admin.SimpleListFilter):
    title = 'verification status'
    parameter_name = 'verification_status'
    
    def lookups(self, request, model_admin):
        return (
            ('verified', 'Verified'),
            ('fake', 'Fake News'),
            ('pending', 'Pending AI'),
            ('questionable', 'Questionable'),
            ('unverified', 'Unverified'),
        )
    
    def queryset(self, request, queryset):
        if self.value() == 'verified':
            return queryset.filter(verification_status='verified')
        if self.value() == 'fake':
            return queryset.filter(verification_status='fake')
        if self.value() == 'pending':
            return queryset.filter(verification_status='pending')
        if self.value() == 'questionable':
            return queryset.filter(verification_status='questionable')
        if self.value() == 'unverified':
            return queryset.filter(verification_status='unverified')
        return queryset


class SubmissionStatusFilter(admin.SimpleListFilter):
    title = 'submission status'
    parameter_name = 'submission_status'
    
    def lookups(self, request, model_admin):
        return (
            ('pending', 'Pending Review'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
            ('flagged', 'Flagged'),
        )
    
    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(submission_status=self.value())
        return queryset


# Update PostAdmin with news management features
@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = [
        'title_preview', 'author', 'post_type', 'category', 
        'status_badge', 'verification_badge', 'submission_badge',
        'is_sponsored', 'views', 'created_at'
    ]
    list_filter = [
        'post_type', 'status', 'category', 'created_at',
        VerificationStatusFilter, SubmissionStatusFilter,
        'is_approved', 'is_verified', 'is_sponsored', 
        'is_auto_fetched', 'has_media'
    ]
    search_fields = ['title', 'content', 'author__username', 'external_source']
    readonly_fields = [
        'views', 'created_at', 'updated_at', 'published_at',
        'verification_score', 'verification_status', 'verification_details_display',
        'banner_clicks', 'banner_impressions'
    ]
    actions = [
        'approve_selected', 'reject_selected', 'verify_selected',
        'mark_as_fake', 'delete_fake_news', 'run_ai_verification',
        'mark_as_sponsored', 'mark_as_banner', 'mark_as_profile_only',
        'publish_selected', 'archive_selected'
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'content', 'author', 'category', 'post_type')
        }),
        ('Media', {
            'fields': ('image', 'image_url', 'video_urls', 'audio_urls', 'has_media')
        }),
        ('News Information', {
            'fields': ('external_source', 'external_url', 'is_auto_fetched', 'is_news_submission')
        }),
        ('Status & Approval', {
            'fields': ('status', 'submission_status', 'is_approved', 'reviewed_by', 'reviewed_at', 'review_notes', 'rejection_reason')
        }),
        ('Verification', {
            'fields': ('is_verified', 'verification_status', 'verification_score', 'verification_details', 'verification_method')
        }),
        ('Visibility & Privacy', {
            'fields': ('privacy', 'profile_only', 'allow_comments', 'allow_sharing')
        }),
        ('Advertisement', {
            'fields': ('is_sponsored', 'advertisement')
        }),
        ('Banner Settings', {
            'fields': ('is_banner', 'banner_expires_at', 'banner_priority', 'banner_clicks', 'banner_impressions')
        }),
        ('Group', {
            'fields': ('group',)
        }),
        ('Stats', {
            'fields': ('views', 'comments_count', 'repost_count')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at', 'published_at')
        }),
    )
    
    def title_preview(self, obj):
        return format_html(
            '<a href="{}" target="_blank">{}</a>',
            reverse('post_detail', args=[obj.id]),
            obj.title[:50] + ('...' if len(obj.title) > 50 else '')
        )
    title_preview.short_description = 'Title'
    
    def status_badge(self, obj):
        colors = {
            'published': 'green',
            'draft': 'gray',
            'archived': 'orange',
            'deleted': 'red'
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="padding: 3px 8px; background: {}; color: white; border-radius: 5px;">{}</span>',
            color,
            obj.get_status_display().upper()
        )
    status_badge.short_description = 'Status'
    
    def verification_badge(self, obj):
        colors = {
            'verified': 'green',
            'fake': 'red',
            'pending': 'orange',
            'questionable': 'orange',
            'unverified': 'gray'
        }
        color = colors.get(obj.verification_status, 'gray')
        return format_html(
            '<span style="padding: 3px 8px; background: {}; color: white; border-radius: 5px;">{}</span>',
            color,
            obj.get_verification_status_display().upper()
        )
    verification_badge.short_description = 'Verification'
    
    def submission_badge(self, obj):
        if not obj.is_news_submission:
            return '—'
        colors = {
            'pending': 'orange',
            'approved': 'green',
            'rejected': 'red',
            'flagged': 'purple'
        }
        color = colors.get(obj.submission_status, 'gray')
        return format_html(
            '<span style="padding: 3px 8px; background: {}; color: white; border-radius: 5px;">{}</span>',
            color,
            obj.get_submission_status_display().upper()
        )
    submission_badge.short_description = 'Submission'
    
    def verification_details_display(self, obj):
        if not obj.verification_details:
            return "No verification details available"
        
        details = obj.verification_details
        html = "<div style='max-height: 300px; overflow-y: auto; padding: 10px; background: #f8f9fa; border-radius: 5px;'>"
        
        # Overall score
        html += f"<h4>Overall Score: <strong>{details.get('overall_score', 0):.2f}</strong></h4>"
        html += f"<p>Status: <strong>{details.get('status', 'unknown').upper()}</strong></p>"
        
        # Checks
        if 'checks' in details:
            html += "<h4 style='margin-top: 10px;'>Individual Checks:</h4>"
            html += "<ul>"
            for check_name, check_result in details['checks'].items():
                score = check_result.get('score', 0)
                color = 'green' if score >= 0.7 else 'orange' if score >= 0.4 else 'red'
                html += f"<li>{check_name.title()}: <span style='color: {color}; font-weight: bold;'>{score:.2f}</span></li>"
            html += "</ul>"
        
        # Warnings
        if details.get('warnings'):
            html += "<h4 style='margin-top: 10px; color: red;'>Warnings:</h4>"
            html += "<ul>"
            for warning in details['warnings']:
                html += f"<li style='color: #666;'>⚠ {warning}</li>"
            html += "</ul>"
        
        # Strengths
        if details.get('strengths'):
            html += "<h4 style='margin-top: 10px; color: green;'>Strengths:</h4>"
            html += "<ul>"
            for strength in details['strengths']:
                html += f"<li style='color: #666;'>✓ {strength}</li>"
            html += "</ul>"
        
        # Recommendations
        if details.get('recommendations'):
            html += "<h4 style='margin-top: 10px;'>Recommendations:</h4>"
            html += "<ul>"
            for rec in details['recommendations']:
                html += f"<li style='color: #666;'>{rec}</li>"
            html += "</ul>"
        
        html += f"<p style='margin-top: 10px; font-size: 0.9em; color: #999;'>Verified at: {details.get('verified_at', 'N/A')}</p>"
        html += "</div>"
        
        return format_html(html)
    verification_details_display.short_description = 'Verification Details'
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('news-pending/', self.admin_site.admin_view(self.pending_news),
                 name='pending-news'),
            path('news-auto-fetched/', self.admin_site.admin_view(self.auto_fetched_news),
                 name='auto-fetched-news'),
            path('news-verify-batch/', self.admin_site.admin_view(self.verify_batch),
                 name='verify-news-batch'),
        ]
        return custom_urls + urls
    
    def pending_news(self, request):
        """View for pending news submissions"""
        pending = Post.objects.filter(
            is_news_submission=True,
            submission_status='pending'
        ).select_related('author', 'category').order_by('-created_at')
        
        context = {
            'title': 'Pending News Submissions',
            'posts': pending,
            'count': pending.count()
        }
        return render(request, 'admin/pending_news.html', context)
    
    def auto_fetched_news(self, request):
        """View for auto-fetched news"""
        auto_news = Post.objects.filter(
            is_auto_fetched=True
        ).select_related('category').order_by('-created_at')[:100]
        
        context = {
            'title': 'Auto-Fetched News',
            'posts': auto_news,
            'count': auto_news.count()
        }
        return render(request, 'admin/auto_fetched_news.html', context)
    
    def verify_batch(self, request):
        """Run verification on a batch of posts"""
        if request.method == 'POST':
            post_ids = request.POST.getlist('post_ids')
            posts = Post.objects.filter(id__in=post_ids)
            
            for post in posts:
                process_news_submission(post)
            
            self.message_user(request, f"Verified {posts.count()} posts")
            return redirect('admin:core_post_changelist')
        
        # GET request - show selection form
        pending_posts = Post.objects.filter(
            Q(verification_status='pending') | Q(verification_status='unverified')
        ).select_related('author')[:50]
        
        context = {
            'title': 'Run Batch Verification',
            'posts': pending_posts
        }
        return render(request, 'admin/verify_batch.html', context)
    
    # Custom actions
    def approve_selected(self, request, queryset):
        count = queryset.update(
            is_approved=True,
            verification_status='verified',
            submission_status='approved',
            status='published',
            reviewed_by=request.user,
            reviewed_at=timezone.now()
        )
        self.message_user(request, f"{count} posts approved.")
    approve_selected.short_description = "Approve selected posts"
    
    def reject_selected(self, request, queryset):
        count = queryset.update(
            is_approved=False,
            verification_status='pending',
            submission_status='rejected',
            status='draft',
            reviewed_by=request.user,
            reviewed_at=timezone.now()
        )
        self.message_user(request, f"{count} posts rejected.")
    reject_selected.short_description = "Reject selected posts"
    
    def verify_selected(self, request, queryset):
        count = queryset.update(
            is_verified=True,
            verification_status='verified'
        )
        self.message_user(request, f"{count} posts marked as verified.")
    verify_selected.short_description = "Mark as verified"
    
    def mark_as_fake(self, request, queryset):
        count = queryset.update(
            verification_status='fake',
            is_approved=False,
            status='archived'
        )
        self.message_user(request, f"{count} posts marked as fake news.")
    mark_as_fake.short_description = "Mark as fake news"
    
    def delete_fake_news(self, request, queryset):
        fake_news = queryset.filter(verification_status='fake')
        count = fake_news.count()
        fake_news.delete()
        self.message_user(request, f"{count} fake news posts deleted.")
    delete_fake_news.short_description = "Delete fake news"
    
    def run_ai_verification(self, request, queryset):
        from .news_verifier import EnhancedNewsVerifier
        verifier = EnhancedNewsVerifier()
        updated = 0
        
        for post in queryset:
            article = {
                'title': post.title,
                'content': post.content,
                'url': post.external_url or '',
                'source': post.external_source or ''
            }
            
            result = verifier.verify_article(article)
            
            post.verification_score = result['overall_score']
            post.verification_status = result['status']
            post.verification_details = result
            post.save()
            updated += 1
        
        self.message_user(request, f"AI verification completed for {updated} posts.")
    run_ai_verification.short_description = "Run AI verification"
    
    def publish_selected(self, request, queryset):
        count = queryset.update(
            status='published',
            published_at=timezone.now()
        )
        self.message_user(request, f"{count} posts published.")
    publish_selected.short_description = "Publish selected"
    
    def archive_selected(self, request, queryset):
        count = queryset.update(status='archived')
        self.message_user(request, f"{count} posts archived.")
    archive_selected.short_description = "Archive selected"
    
    def mark_as_sponsored(self, request, queryset):
        count = queryset.update(is_sponsored=True)
        self.message_user(request, f"{count} posts marked as sponsored.")
    mark_as_sponsored.short_description = "Mark as sponsored"
    
    def mark_as_banner(self, request, queryset):
        count = queryset.update(
            is_banner=True,
            banner_expires_at=timezone.now() + timedelta(days=7)
        )
        self.message_user(request, f"{count} posts marked as banners.")
    mark_as_banner.short_description = "Mark as banner"
    
    def mark_as_profile_only(self, request, queryset):
        count = queryset.update(profile_only=True)
        self.message_user(request, f"{count} posts marked as profile-only.")
    mark_as_profile_only.short_description = "Mark as profile-only"


# Update UserProfileAdmin
@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'account_type', 'is_verified_business', 
        'ad_credits', 'total_posts_display', 'followers_count'
    ]
    list_filter = ['account_type', 'is_verified_business']
    search_fields = ['user__username', 'business_name', 'user__email']
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
    
    def total_posts_display(self, obj):
        return obj.total_posts or Post.objects.filter(author=obj.user, status='published').count()
    total_posts_display.short_description = 'Total Posts'
    
    def verify_business(self, request, queryset):
        queryset.update(
            is_verified_business=True,
            account_type='business',
            business_verified_at=timezone.now(),
            business_verified_by=request.user
        )
        self.message_user(request, f"{queryset.count()} businesses verified.")
    verify_business.short_description = "Verify selected businesses"
    
    def downgrade_to_individual(self, request, queryset):
        queryset.update(
            account_type='individual',
            is_verified_business=False,
            business_verified_at=None,
            business_verified_by=None
        )
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
    list_display = ['name', 'slug', 'parent', 'order', 'post_count']
    prepopulated_fields = {'slug': ('name',)}
    list_filter = ['parent']
    search_fields = ['name', 'description']
    
    def post_count(self, obj):
        return obj.post_set.filter(status='published').count()
    post_count.short_description = 'Published Posts'


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ['user', 'post_title', 'created_at', 'is_active', 'likes_count']
    list_filter = ['is_active', 'created_at']
    search_fields = ['content', 'user__username', 'post__title']
    actions = ['approve_comments', 'hide_comments']
    
    def post_title(self, obj):
        return obj.post.title[:50]
    post_title.short_description = 'Post'
    
    def likes_count(self, obj):
        return obj.likes.count()
    likes_count.short_description = 'Likes'
    
    def approve_comments(self, request, queryset):
        queryset.update(is_active=True)
        self.message_user(request, f"{queryset.count()} comments approved.")
    approve_comments.short_description = "Approve selected comments"
    
    def hide_comments(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, f"{queryset.count()} comments hidden.")
    hide_comments.short_description = "Hide selected comments"


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'notification_type', 'message_preview', 'is_read', 'created_at']
    list_filter = ['notification_type', 'is_read', 'created_at']
    search_fields = ['message', 'user__username']
    actions = ['mark_as_read', 'mark_as_unread']
    
    def message_preview(self, obj):
        return obj.message[:50] + ('...' if len(obj.message) > 50 else '')
    message_preview.short_description = 'Message'
    
    def mark_as_read(self, request, queryset):
        queryset.update(is_read=True)
        self.message_user(request, f"{queryset.count()} notifications marked as read.")
    mark_as_read.short_description = "Mark as read"
    
    def mark_as_unread(self, request, queryset):
        queryset.update(is_read=False)
        self.message_user(request, f"{queryset.count()} notifications marked as unread.")
    mark_as_unread.short_description = "Mark as unread"


@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
    list_display = ['user', 'activity_type', 'post_title', 'created_at']
    list_filter = ['activity_type', 'created_at']
    search_fields = ['user__username', 'details']
    # Fixed: Removed ip_address and user_agent from readonly_fields
    # since they don't exist in the model
    readonly_fields = ['user', 'activity_type', 'post', 'comment', 'target_user', 'details', 'created_at']
    
    def post_title(self, obj):
        return obj.post.title[:50] if obj.post else '-'
    post_title.short_description = 'Post'
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
    list_display = ['follower', 'following', 'created_at']
    list_filter = ['created_at']
    search_fields = ['follower__username', 'following__username']


@admin.register(Repost)
class RepostAdmin(admin.ModelAdmin):
    list_display = ['user', 'original_post', 'content_preview', 'created_at']
    list_filter = ['created_at']
    search_fields = ['user__username', 'original_post__title']
    
    def content_preview(self, obj):
        return obj.content[:50] + ('...' if obj.content and len(obj.content) > 50 else '') if obj.content else '-'
    content_preview.short_description = 'Content'