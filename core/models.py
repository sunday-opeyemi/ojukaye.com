# core/models.py (CLEAN VERSION - NO DUPLICATES)

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import MaxValueValidator, MinValueValidator
import uuid
from django.urls import reverse
from django.db.models import Count, Q
from decimal import Decimal

# ==================== CATEGORY MODEL (ONLY ONE) ====================
class Category(models.Model):
    """Category model for posts"""
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')
    icon = models.CharField(max_length=50, blank=True, help_text="Font Awesome icon class")
    color = models.CharField(max_length=20, default='#3b82f6')
    order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Cache for post count
    cached_post_count = models.PositiveIntegerField(default=0)
    
    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['order', 'name']
    
    def __str__(self):
        return self.name
    
    def get_post_count(self):
        """Get actual post count for this category"""
        if self.cached_post_count == 0:
            count = self.post_set.filter(status='published').count()
            self.cached_post_count = count
            self.save(update_fields=['cached_post_count'])
        return self.cached_post_count
    
    def update_post_count(self):
        """Update cached post count"""
        self.cached_post_count = self.posts.filter(status='published').count()
        self.save(update_fields=['cached_post_count'])
    
    def get_absolute_url(self):
        return reverse('category_view', args=[self.slug])


# ==================== SYSTEM SETTINGS MODEL ====================
class SystemSettings(models.Model):
    """System-wide settings controlled by admin"""
    
    # News verification settings
    auto_approve_threshold = models.FloatField(default=0.8, help_text="AI score threshold for auto-approval (0.0-1.0)")
    require_manual_review_for_fake = models.BooleanField(default=True, help_text="Require manual review for posts marked as fake")
    notify_admin_on_submission = models.BooleanField(default=True)
    notify_user_on_approval = models.BooleanField(default=True)
    
    # Source reputation settings
    trusted_sources = models.TextField(blank=True, help_text="Comma-separated list of trusted news sources")
    blocked_sources = models.TextField(blank=True, help_text="Comma-separated list of blocked sources")
    
    # AI & Automation Settings
    auto_verify_news = models.BooleanField(
        default=True,
        help_text='Automatically verify news articles using AI'
    )
    auto_post_verified_news = models.BooleanField(
        default=False,
        help_text='Automatically post verified news to online news page'
    )
    auto_delete_fake_news = models.BooleanField(
        default=False,
        help_text='Automatically delete/archive news detected as fake'
    )
    verification_threshold = models.FloatField(
        default=0.7,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
        help_text='Minimum confidence score (0-1) for auto-approval'
    )
    verification_schedule = models.CharField(
        max_length=20,
        choices=[
            ('hourly', 'Hourly'),
            ('every_6_hours', 'Every 6 Hours'),
            ('every_12_hours', 'Every 12 Hours'),
            ('daily', 'Daily'),
            ('manual', 'Manual Only'),
        ],
        default='daily',
        help_text='How often to run automatic verification'
    )
    max_posts_to_verify = models.IntegerField(
        default=50,
        validators=[MinValueValidator(1), MaxValueValidator(500)],
        help_text='Maximum number of posts to verify per batch'
    )
    
    # News Fetching Settings
    enable_auto_fetch = models.BooleanField(
        default=True,
        help_text='Automatically fetch news from RSS feeds'
    )
    fetch_schedule = models.CharField(
        max_length=20,
        choices=[
            ('hourly', 'Hourly'),
            ('every_3_hours', 'Every 3 Hours'),
            ('every_6_hours', 'Every 6 Hours'),
            ('daily', 'Daily'),
            ('manual', 'Manual Only'),
        ],
        default='daily'
    )
    max_news_per_fetch = models.IntegerField(
        default=50,
        validators=[MinValueValidator(1), MaxValueValidator(200)]
    )
    
    # Post & Content Settings
    enable_guest_access = models.BooleanField(
        default=True,
        help_text='Allow non-logged-in users to view content'
    )
    max_posts_per_day = models.IntegerField(
        default=10,
        validators=[MinValueValidator(1)],
        help_text='Maximum posts per user per day'
    )
    require_post_approval = models.BooleanField(
        default=True,
        help_text='Require admin approval for user posts'
    )
    max_post_length = models.IntegerField(
        default=10000,
        validators=[MinValueValidator(100)],
        help_text='Maximum characters per post'
    )
    max_image_size = models.IntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(20)],
        help_text='Maximum image size in MB'
    )
    allowed_image_types = models.CharField(
        max_length=200,
        default='jpg,jpeg,png,gif,webp',
        help_text='Comma-separated list of allowed image formats'
    )
    
    # User Settings
    allow_registrations = models.BooleanField(
        default=True,
        help_text='Allow new user registrations'
    )
    require_email_verification = models.BooleanField(
        default=False,
        help_text='Require email verification for new accounts'
    )
    default_user_role = models.CharField(
        max_length=20,
        choices=[
            ('user', 'User'),
            ('contributor', 'Contributor'),
            ('editor', 'Editor'),
        ],
        default='user'
    )
    
    # Advertisement Settings
    max_ads_per_business = models.IntegerField(
        default=5,
        validators=[MinValueValidator(1)],
        help_text='Maximum active ads per business'
    )
    banner_rotation_interval = models.IntegerField(
        default=30,
        validators=[MinValueValidator(5)],
        help_text='Banner rotation interval in seconds'
    )
    ad_approval_required = models.BooleanField(
        default=True,
        help_text='Require admin approval for new ads'
    )
    min_ad_budget = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('1000.00'),
        validators=[MinValueValidator(Decimal('100.00'))],
        help_text='Minimum budget per advertisement'
    )
    ad_impression_rate = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        default=Decimal('0.0010'),
        validators=[MinValueValidator(Decimal('0.0001'))],
        help_text='Cost per impression (in NGN)'
    )
    ad_click_rate = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        default=Decimal('0.0500'),
        validators=[MinValueValidator(Decimal('0.0100'))],
        help_text='Cost per click (in NGN)'
    )
    
    # Group Settings
    allow_group_creation = models.BooleanField(
        default=True,
        help_text='Allow users to create groups'
    )
    max_groups_per_user = models.IntegerField(
        default=5,
        validators=[MinValueValidator(1)],
        help_text='Maximum groups a user can create'
    )
    min_members_for_public_group = models.IntegerField(
        default=10,
        validators=[MinValueValidator(1)],
        help_text='Minimum members required to become a public group'
    )
    require_group_approval = models.BooleanField(
        default=False,
        help_text='Require admin approval for new groups'
    )
    
    # Trending & Analytics
    trending_calculation_interval = models.IntegerField(
        default=6,
        validators=[MinValueValidator(1)],
        help_text='Trending calculation interval in hours'
    )
    trending_time_window = models.IntegerField(
        default=48,
        validators=[MinValueValidator(1)],
        help_text='Time window for trending posts in hours'
    )
    engagement_weight_like = models.FloatField(
        default=1.0,
        help_text='Weight multiplier for likes in trending calculation'
    )
    engagement_weight_comment = models.FloatField(
        default=2.0,
        help_text='Weight multiplier for comments in trending calculation'
    )
    engagement_weight_share = models.FloatField(
        default=3.0,
        help_text='Weight multiplier for shares in trending calculation'
    )
    engagement_weight_view = models.FloatField(
        default=0.01,
        help_text='Weight multiplier for views in trending calculation'
    )
    
    # Cache & Performance
    cache_timeout = models.IntegerField(
        default=300,
        validators=[MinValueValidator(0)],
        help_text='Cache timeout in seconds'
    )
    compress_images = models.BooleanField(
        default=True,
        help_text='Automatically compress uploaded images'
    )
    
    # Maintenance
    maintenance_mode = models.BooleanField(
        default=False,
        help_text='Put site in maintenance mode'
    )
    maintenance_message = models.TextField(
        default='Site is under maintenance. Please check back soon.',
        blank=True
    )
    allow_admin_during_maintenance = models.BooleanField(
        default=True,
        help_text='Allow admin access during maintenance'
    )
    
    # SEO Settings
    meta_description = models.TextField(
        blank=True,
        help_text='Default meta description for SEO'
    )
    meta_keywords = models.TextField(
        blank=True,
        help_text='Default meta keywords for SEO'
    )
    robots_txt = models.TextField(
        default='User-agent: *\nDisallow: /admin/\nDisallow: /private/\nAllow: /\nSitemap: /sitemap.xml',
        blank=True
    )
    
    # Social Media Links
    facebook_url = models.URLField(blank=True)
    twitter_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    linkedin_url = models.URLField(blank=True)
    youtube_url = models.URLField(blank=True)
    telegram_url = models.URLField(blank=True)
    whatsapp_number = models.CharField(max_length=20, blank=True)
    
    # Contact Information
    contact_email = models.EmailField(blank=True)
    support_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    
    # Notification Settings
    enable_email_notifications = models.BooleanField(default=True)
    enable_push_notifications = models.BooleanField(default=False)
    notify_admin_on_new_post = models.BooleanField(default=True)
    notify_admin_on_new_user = models.BooleanField(default=True)
    notify_admin_on_fake_news = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='system_settings_updates'
    )
    
    class Meta:
        verbose_name_plural = "System Settings"
    
    def save(self, *args, **kwargs):
        if not self.pk and SystemSettings.objects.exists():
            existing = SystemSettings.objects.first()
            self.pk = existing.pk
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"System Settings (Updated: {self.updated_at.strftime('%Y-%m-%d %H:%M')})"
    
    @classmethod
    def get_settings(cls):
        settings, created = cls.objects.get_or_create(pk=1)
        return settings
    
    def get_trusted_sources_list(self):
        if self.trusted_sources:
            return [s.strip() for s in self.trusted_sources.split(',') if s.strip()]
        return []
    
    def get_blocked_sources_list(self):
        if self.blocked_sources:
            return [s.strip() for s in self.blocked_sources.split(',') if s.strip()]
        return []
    
    def get_allowed_image_types_list(self):
        return [t.strip().lower() for t in self.allowed_image_types.split(',') if t.strip()]
    
    def is_ai_verification_active(self):
        return self.auto_verify_news
    
    def should_auto_post(self):
        return self.auto_verify_news and self.auto_post_verified_news


# ==================== ADVERTISEMENT MODEL (ONLY ONE) ====================
class Advertisement(models.Model):
    AD_TYPES = [
        ('banner', 'Banner Ad'),
        ('sponsored_post', 'Sponsored Post'),
        ('sidebar', 'Sidebar Ad'),
        ('in_feed', 'In-Feed Ad'),
    ]
    
    AD_STATUS = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('completed', 'Completed'),
        ('expired', 'Expired'),
    ]
    
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    business = models.ForeignKey(User, on_delete=models.CASCADE, related_name='advertisements')
    ad_type = models.CharField(max_length=20, choices=AD_TYPES, default='banner')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)  # Using 'description' consistently
    image = models.ImageField(upload_to='ads/', blank=True, null=True)
    image_url = models.URLField(max_length=1000, blank=True)
    target_url = models.URLField(max_length=1000)
    
    # Budget & Duration
    budget = models.DecimalField(max_digits=10, decimal_places=2)
    spent = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField()
    
    # Pricing
    cost_per_impression = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cost_per_click = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Targeting
    target_categories = models.ManyToManyField(Category, blank=True, related_name='advertisements')
    target_locations = models.CharField(max_length=500, blank=True)
    target_keywords = models.CharField(max_length=500, blank=True)
    
    # Status & Approval
    status = models.CharField(max_length=20, choices=AD_STATUS, default='pending')
    is_active = models.BooleanField(default=False)
    approved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='approved_ads'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    
    # Performance tracking
    max_clicks = models.IntegerField(default=0)
    max_impressions = models.IntegerField(default=0)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} - {self.business.username}"
    
    @property
    def clicks(self):
        return self.analytics.aggregate(total=models.Sum('clicks'))['total'] or 0
    
    @property
    def impressions(self):
        return self.analytics.aggregate(total=models.Sum('impressions'))['total'] or 0
    
    @property
    def is_live(self):
        now = timezone.now()
        return (self.status == 'active' and 
                self.is_active and
                self.start_date <= now <= self.end_date and
                (self.max_clicks == 0 or self.clicks < self.max_clicks) and
                (self.max_impressions == 0 or self.impressions < self.max_impressions))
    
    def remaining_budget(self):
        return self.budget - self.spent
    
    def days_remaining(self):
        if self.end_date < timezone.now():
            return 0
        return (self.end_date - timezone.now()).days


# ==================== POST MODEL ====================
class Post(models.Model):
    POST_TYPES = [
        ('discussion', 'Discussion'),
        ('business', 'Business'),
        ('user_news', 'User News'),
        ('news', 'Auto-Fetched News'),
        ('profile_post', 'Profile Post'),
        ('sponsored', 'Sponsored Post'),
    ]
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('featured', 'Featured'),
        ('archived', 'Archived'),
    ] 
    
    PRIVACY_CHOICES = [
        ('public', 'Public - Everyone can view'),
        ('followers', 'Followers Only - Only my followers can view'),
        ('private', 'Private - Only me'),
        ('specific', 'Specific Followers - Select specific followers'),
    ]
    
    # Basic Information
    title = models.CharField(max_length=200)
    content = models.TextField()
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='posts')
    post_type = models.CharField(max_length=20, choices=POST_TYPES, default='discussion')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='posts')
    
    # Privacy Settings
    privacy = models.CharField(max_length=20, choices=PRIVACY_CHOICES, default='public')
    allowed_viewers = models.ManyToManyField(
        User, 
        blank=True, 
        related_name='can_view_posts',
        help_text='Specific followers who can view this post (for privacy="specific")'
    )
    
    # Source Information (for news posts)
    source_url = models.URLField(max_length=1000, blank=True, null=True)
    source_name = models.CharField(max_length=200, blank=True)
    
    # External News Information (for auto-fetched news)
    external_source = models.CharField(max_length=200, blank=True)
    external_url = models.URLField(max_length=1000, blank=True) 
    external_id = models.CharField(max_length=200, blank=True, null=True, unique=True)
    is_auto_fetched = models.BooleanField(default=False)
    original_published_at = models.DateTimeField(null=True, blank=True)
    
    # News Submission & Approval Workflow
    is_news_submission = models.BooleanField(default=False)
    submission_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending Review'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
            ('flagged', 'Flagged for Review'),
        ],
        default='pending'
    )
    reviewed_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='reviewed_news'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    
    # AI Verification Fields
    verification_status = models.CharField(
        max_length=20,
        choices=[
            ('unverified', 'Unverified'),
            ('pending', 'Pending AI Verification'),
            ('verified', 'Verified'),
            ('fake', 'Fake News'),
            ('questionable', 'Questionable'),
        ],
        default='unverified'
    )
    verification_score = models.FloatField(default=0.0)
    verification_details = models.JSONField(default=dict, blank=True)
    verification_method = models.CharField(max_length=50, default='manual')
    is_verified = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=False)
    
    # Source Reputation
    source_reputation_score = models.FloatField(default=0.0)
    source_trust_level = models.CharField(
        max_length=20,
        choices=[
            ('unknown', 'Unknown'),
            ('trusted', 'Trusted'),
            ('questionable', 'Questionable'),
            ('untrusted', 'Untrusted'),
        ],
        default='unknown'
    )
    
    # Media Content
    image = models.ImageField(upload_to='post_images/', blank=True, null=True)
    image_url = models.URLField(max_length=1000, blank=True, null=True)
    video_urls = models.JSONField(null=True, blank=True, default=list)
    audio_urls = models.JSONField(null=True, blank=True, default=list)
    has_media = models.BooleanField(default=False)
    
    # Special Content Types
    is_sponsored = models.BooleanField(default=False)
    is_banner = models.BooleanField(default=False)
    profile_only = models.BooleanField(default=False)
    advertisement = models.ForeignKey(
        Advertisement, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='posts'
    )
    
    # Banner-specific fields
    banner_expires_at = models.DateTimeField(null=True, blank=True)
    banner_priority = models.IntegerField(default=0)
    banner_clicks = models.PositiveIntegerField(default=0)
    banner_impressions = models.PositiveIntegerField(default=0)
    
    # Group association
    group = models.ForeignKey('Group', on_delete=models.SET_NULL, null=True, blank=True, related_name='group_posts')
    
    # Interaction Settings
    allow_comments = models.BooleanField(default=True)
    allow_sharing = models.BooleanField(default=True)
    
    # Statistics
    views = models.PositiveIntegerField(default=0)
    shares = models.PositiveIntegerField(default=0)
    repost_count = models.PositiveIntegerField(default=0)
    comments_count = models.PositiveIntegerField(default=0)
    share_count = models.PositiveIntegerField(default=0)
    
    # Engagement & Trending
    engagement_score = models.FloatField(default=0.0)
    last_engagement_update = models.DateTimeField(auto_now=True)
    is_featured = models.BooleanField(default=False)
    is_trending = models.BooleanField(default=False)
    
    # SEO
    meta_description = models.TextField(blank=True)
    keywords = models.CharField(max_length=500, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(default=timezone.now)
    
    # Many-to-Many Relationships
    likes = models.ManyToManyField(User, related_name='liked_posts', blank=True)
    bookmarks = models.ManyToManyField(User, related_name='bookmarked_posts', blank=True)
    
    class Meta:
        ordering = ['-published_at']
        indexes = [
            models.Index(fields=['-published_at']),
            models.Index(fields=['status']),
            models.Index(fields=['post_type']),
            models.Index(fields=['category']),
            models.Index(fields=['is_auto_fetched']),
            models.Index(fields=['is_sponsored']),
            models.Index(fields=['profile_only']),
            models.Index(fields=['verification_status']),
            models.Index(fields=['submission_status']),
        ]
    
    def __str__(self):
        return self.title[:100]
    
    def like_count(self):
        return self.likes.count()
    
    def comment_count(self):
        return self.comments.filter(is_active=True).count()
    
    def bookmark_count(self):
        return self.bookmarks.count()
    
    def update_engagement_score(self):
        self.comments_count = self.comments.filter(is_active=True).count()
        
        like_weight = 1
        comment_weight = 3
        repost_weight = 5
        view_weight = 0.01
        
        self.engagement_score = (
            self.likes.count() * like_weight +
            self.comments_count * comment_weight +
            self.repost_count * repost_weight +
            self.views * view_weight
        )
        self.last_engagement_update = timezone.now()
        self.save(update_fields=['engagement_score', 'last_engagement_update', 'comments_count'])
    
    def save(self, *args, **kwargs):
        if self.author and hasattr(self.author, 'username') and self.author.username == 'news_bot':
            self.is_auto_fetched = True
            self.post_type = 'news'
        
        if self.external_id or self.external_url or self.external_source:
            self.is_auto_fetched = True
            self.post_type = 'news'
        
        if self.post_type == 'profile_post':
            self.profile_only = True
            self.category = None
            
        if self.post_type == 'sponsored' and self.advertisement:
            self.is_sponsored = True
        
        if self.video_urls or self.audio_urls:
            self.has_media = True
        
        if self.status in ['published', 'featured'] and not self.published_at:
            self.published_at = timezone.now()
        
        super().save(*args, **kwargs)
    
    def get_absolute_url(self):
        return reverse('post_detail', args=[str(self.id)])


# ==================== COMMENT MODEL ====================
class Comment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='comments')
    image = models.ImageField(upload_to='comment_images/', blank=True, null=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    likes = models.ManyToManyField(User, related_name='liked_comments', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Comment by {self.user.username} on {self.post.title[:50]}"
    
    def like_count(self):
        return self.likes.count()


# ==================== USER PROFILE MODEL ====================
class UserProfile(models.Model):
    ACCOUNT_TYPES = [
        ('individual', 'Individual'),
        ('business', 'Business'),
        ('group', 'Group Account'),
        ('admin', 'Admin'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    bio = models.TextField(blank=True)
    profile_pic = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    cover_photo = models.ImageField(upload_to='cover_photos/', blank=True, null=True)
    location = models.CharField(max_length=100, blank=True)
    website = models.URLField(max_length=1000, blank=True)
    twitter_handle = models.CharField(max_length=50, blank=True)
    
    phone = models.CharField(max_length=20, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    occupation = models.CharField(max_length=100, blank=True)
    interests = models.TextField(blank=True, help_text="Comma separated list of interests")
    
    facebook_url = models.URLField(max_length=1000, blank=True)
    instagram_url = models.URLField(max_length=1000, blank=True)
    linkedin_url = models.URLField(max_length=1000, blank=True)
    
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES, default='individual')
    is_verified_business = models.BooleanField(default=False)
    ad_credits = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    business_name = models.CharField(max_length=200, blank=True)
    business_registration = models.CharField(max_length=100, blank=True)
    business_address = models.TextField(blank=True)
    business_phone = models.CharField(max_length=20, blank=True)
    business_email = models.EmailField(blank=True)
    business_website = models.URLField(max_length=1000, blank=True)
    
    business_verified_at = models.DateTimeField(null=True, blank=True)
    business_verified_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='verified_businesses'
    )
    
    receive_promo_emails = models.BooleanField(default=True)
    ad_notifications = models.BooleanField(default=True)
    
    is_group_account = models.BooleanField(default=False)
    group = models.ForeignKey('Group', on_delete=models.SET_NULL, null=True, blank=True, related_name='profile')
    
    total_posts = models.PositiveIntegerField(default=0)
    total_comments = models.PositiveIntegerField(default=0)
    total_likes_received = models.PositiveIntegerField(default=0)
    followers_count = models.PositiveIntegerField(default=0)
    following_count = models.PositiveIntegerField(default=0)
    
    email_notifications = models.BooleanField(default=True)
    show_online_status = models.BooleanField(default=True)
    privacy_level = models.CharField(
        max_length=20,
        choices=[
            ('public', 'Public'),
            ('private', 'Private'),
            ('friends_only', 'Friends Only')
        ],
        default='public'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_seen = models.DateTimeField(default=timezone.now)
    
    def __str__(self):
        if self.account_type == 'business' and self.business_name:
            return f"{self.business_name} ({self.user.username})"
        return f"{self.user.username}'s Profile"
    
    @property
    def full_name(self):
        return f"{self.user.first_name} {self.user.last_name}".strip() or self.user.username
    
    def update_stats(self):
        self.total_posts = self.user.posts.count()
        self.total_comments = self.user.comment_set.count()
        self.total_likes_received = self.user.posts.aggregate(
            total_likes=models.Sum('likes')
        )['total_likes'] or 0
        self.save()
    
    def get_interests_list(self):
        if self.interests:
            return [interest.strip() for interest in self.interests.split(',')]
        return []
    
    def can_submit_ads(self):
        return self.account_type == 'business' and self.is_verified_business
    
    def get_remaining_ad_credits(self):
        active_ads = Advertisement.objects.filter(
            business=self.user,
            status__in=['active', 'approved'],
            is_active=True
        )
        total_budget = sum(ad.budget for ad in active_ads)
        return self.ad_credits - total_budget


# ==================== FOLLOW MODEL ====================
class Follow(models.Model):
    follower = models.ForeignKey(User, on_delete=models.CASCADE, related_name='following')
    following = models.ForeignKey(User, on_delete=models.CASCADE, related_name='followers')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['follower', 'following']
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.follower.username} follows {self.following.username}"


# ==================== USER ACTIVITY MODEL ====================
class UserActivity(models.Model):
    ACTIVITY_TYPES = [
        ('post_created', 'Post Created'),
        ('comment_created', 'Comment Created'),
        ('post_liked', 'Post Liked'),
        ('post_shared', 'Post Shared'),
        ('post_saved', 'Post Saved'),
        ('post_reposted', 'Post Reposted'),
        ('profile_updated', 'Profile Updated'),
        ('followed_user', 'Followed User'),
        ('ad_submitted', 'Ad Submitted'),
        ('group_created', 'Group Created'),
        ('group_joined', 'Group Joined'),
        ('ad_approved', 'Ad Approved'),
        ('ad_rejected', 'Ad Rejected'),
        ('business_verified', 'Business Verified'),
        ('group_post_created', 'Group Post Created'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activities')
    activity_type = models.CharField(max_length=30, choices=ACTIVITY_TYPES)
    post = models.ForeignKey(Post, on_delete=models.CASCADE, null=True, blank=True)
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, null=True, blank=True)
    target_user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name='target_activities'
    )
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'User Activities'
    
    def __str__(self):
        return f"{self.user.username} - {self.get_activity_type_display()}"


# ==================== NOTIFICATION MODEL ====================
class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('like', 'Like'),
        ('comment', 'Comment'),
        ('follow', 'Follow'),
        ('mention', 'Mention'),
        ('post', 'New Post'),
        ('reply', 'Reply'),
        ('ad_approval', 'Ad Approval'),
        ('business_verification', 'Business Verification'),
        ('group_invite', 'Group Invite'),
        ('group_post_approved', 'Group Post Approved'),
        ('group_post_rejected', 'Group Post Rejected'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    from_user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='sent_notifications')
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPES)
    message = models.CharField(max_length=500)
    post = models.ForeignKey(Post, on_delete=models.CASCADE, null=True, blank=True)
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, null=True, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.notification_type} notification for {self.user.username}"


# ==================== REPOST MODEL ====================
class Repost(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reposts')
    original_post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='repost_instances')
    content = models.TextField(blank=True, help_text="Optional comment when reposting")
    created_at = models.DateTimeField(auto_now_add=True)
    reposts = models.PositiveIntegerField(default=0)
    
    class Meta:
        unique_together = ['user', 'original_post']
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.username} reposted {self.original_post.title}"


# ==================== GROUP MODELS ====================
class Group(models.Model):
    GROUP_TYPES = [
        ('public', 'Public - Anyone can join'),
        ('private', 'Private - Approval required'),
        ('secret', 'Secret - Invitation only'),
    ]
    
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    group_type = models.CharField(max_length=20, choices=GROUP_TYPES, default='public')
    
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_groups')
    admins = models.ManyToManyField(User, related_name='administered_groups', blank=True)
    moderators = models.ManyToManyField(User, related_name='moderated_groups', blank=True)
    
    allow_member_posts = models.BooleanField(default=True)
    require_post_approval = models.BooleanField(default=False)
    
    cover_image = models.ImageField(upload_to='groups/covers/', blank=True, null=True)
    icon = models.ImageField(upload_to='groups/icons/', blank=True, null=True)
    
    member_count = models.PositiveIntegerField(default=0)
    post_count = models.PositiveIntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        from django.utils.text import slugify
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
    
    def update_member_count(self):
        self.member_count = self.members.count()
        self.save(update_fields=['member_count'])
    
    def update_post_count(self):
        self.post_count = self.group_posts.count()
        self.save(update_fields=['post_count'])


class GroupMember(models.Model):
    ROLE_CHOICES = [
        ('member', 'Member'),
        ('moderator', 'Moderator'),
        ('admin', 'Admin'),
    ]
    
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='group_memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    joined_at = models.DateTimeField(auto_now_add=True)
    is_banned = models.BooleanField(default=False)
    banned_at = models.DateTimeField(null=True, blank=True)
    banned_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='banned_members'
    )
    
    class Meta:
        unique_together = ['group', 'user']
    
    def __str__(self):
        return f"{self.user.username} in {self.group.name}"


class GroupPost(models.Model):
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='posts')
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='group_posts')
    posted_by = models.ForeignKey(User, on_delete=models.CASCADE)
    is_approved = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        unique_together = ['group', 'post']
    
    def __str__(self):
        return f"{self.post.title} in {self.group.name}"


# ==================== AD ANALYTICS MODEL ====================
class AdAnalytics(models.Model):
    advertisement = models.ForeignKey(Advertisement, on_delete=models.CASCADE, related_name='analytics')
    date = models.DateField(default=timezone.now)
    
    impressions = models.PositiveIntegerField(default=0)
    clicks = models.PositiveIntegerField(default=0)
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    ctr = models.FloatField(default=0)
    cpc = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    
    class Meta:
        unique_together = ['advertisement', 'date']
        verbose_name_plural = "Ad Analytics"
    
    def update_metrics(self):
        if self.impressions > 0:
            self.ctr = (self.clicks / self.impressions) * 100
        if self.clicks > 0:
            self.cpc = self.cost / self.clicks
        self.save()