# core/forms.py
from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.core.validators import URLValidator, ValidationError
from django.utils import timezone
from .models import SystemSettings
from decimal import Decimal

class RegistrationForm(UserCreationForm):
    ACCOUNT_TYPES = [
        ('individual', 'Individual Account'),
        ('business', 'Business Account'),
    ]
    
    account_type = forms.ChoiceField(
        choices=ACCOUNT_TYPES,
        widget=forms.RadioSelect,
        initial='individual'
    )
    
    # Business fields
    business_name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Your Business Name'
        })
    )
    business_email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'business@example.com'
        })
    )
    business_phone = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '+234 800 000 0000'
        })
    )
    
    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2', 'account_type']
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Choose a username'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'your@email.com',
                'required': True
            }),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        account_type = cleaned_data.get('account_type')
        
        if account_type == 'business':
            business_name = cleaned_data.get('business_name')
            business_email = cleaned_data.get('business_email')
            
            if not business_name:
                self.add_error('business_name', 'Business name is required for business accounts')
            if not business_email:
                self.add_error('business_email', 'Business email is required for business accounts')
        
        return cleaned_data
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        
        if commit:
            user.save()
            
            # Import UserProfile here to avoid circular import
            from .models import UserProfile
            
            # Create user profile with account type
            profile, created = UserProfile.objects.get_or_create(user=user)
            profile.account_type = self.cleaned_data['account_type']
            
            if self.cleaned_data['account_type'] == 'business':
                profile.business_name = self.cleaned_data.get('business_name', '')
                profile.business_email = self.cleaned_data.get('business_email', '')
                profile.business_phone = self.cleaned_data.get('business_phone', '')
            
            profile.save()
        
        return user

class PostForm(forms.ModelForm):
    POST_TYPE_CHOICES = [
        ('discussion', 'Discussion'),
        ('user_news', 'User News'),
        ('profile_post', 'Profile Post'),
    ]
    
    post_type = forms.ChoiceField(
        choices=POST_TYPE_CHOICES,
        widget=forms.RadioSelect,
        initial='discussion'
    )
    
    # Define privacy choices here instead of referencing Post.PRIVACY_CHOICES
    PRIVACY_CHOICES = [
        ('public', 'Public - Everyone can view'),
        ('followers', 'Followers Only - Only my followers can view'),
        ('private', 'Private - Only me'),
        ('specific', 'Specific Followers - Select specific followers'),
    ]
    
    privacy = forms.ChoiceField(
        choices=PRIVACY_CHOICES,
        widget=forms.RadioSelect,
        initial='public',
        required=True
    )
    
    allowed_viewers = forms.ModelMultipleChoiceField(
        queryset=None,  # Will be set in __init__
        widget=forms.SelectMultiple(attrs={'class': 'form-control', 'size': '10'}),
        required=False,
        help_text='Select specific followers who can view this post'
    )
    
    class Meta:
        # Import Post model here to avoid circular import
        from .models import Post
        model = Post
        fields = [
            'title', 'content', 'post_type', 'privacy', 'allowed_viewers',
            'category', 'source_url', 'source_name', 'image',
            'allow_comments', 'allow_sharing'
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter post title',
                'required': True
            }),
            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 8,
                'placeholder': 'Write your post content...',
                'required': True
            }),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'source_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://example.com/news-article'
            }),
            'source_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Source name (e.g., BBC News)'
            }),
            'allow_comments': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'allow_sharing': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Set allowed_viewers queryset to user's followers
        if self.user:
            from django.contrib.auth.models import User
            from .models import Follow
            self.fields['allowed_viewers'].queryset = User.objects.filter(
                followers__follower=self.user
            ).distinct()
    
    def clean(self):
        cleaned_data = super().clean()
        post_type = cleaned_data.get('post_type')
        privacy = cleaned_data.get('privacy')
        allowed_viewers = cleaned_data.get('allowed_viewers')
        source_url = cleaned_data.get('source_url')
        
        if post_type == 'user_news' and not source_url:
            raise forms.ValidationError('Source URL is required for User News posts')
        
        # Validate URL for user news
        if post_type == 'user_news' and source_url:
            try:
                validator = URLValidator()
                validator(source_url)
            except ValidationError:
                raise forms.ValidationError('Please enter a valid URL for the source')
        
        # Profile posts don't need category
        if post_type == 'profile_post':
            cleaned_data['category'] = None
        
        # Validate specific followers selection
        if privacy == 'specific' and not allowed_viewers:
            raise forms.ValidationError('Please select at least one follower to view this post')
        
        return cleaned_data
    
    
    
class AdSubmissionForm(forms.ModelForm):
    ad_type = forms.ChoiceField(
        # Choices will be set in __init__ to avoid circular import
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    class Meta:
        # Import Advertisement model here
        from .models import Advertisement
        model = Advertisement
        fields = [
            'ad_type', 'title', 'content', 'image', 'target_url',
            'budget', 'start_date', 'end_date',
            'target_categories', 'target_locations', 'target_keywords',
            'max_clicks', 'max_impressions'
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ad title'
            }),
            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Ad content (optional for banner ads)'
            }),
            'target_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://your-website.com'
            }),
            'budget': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1000',
                'step': '100'
            }),
            'start_date': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local'
            }),
            'end_date': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local'
            }),
            'target_categories': forms.SelectMultiple(attrs={'class': 'form-control'}),
            'target_locations': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Lagos, Abuja, Nigeria (comma separated)'
            }),
            'target_keywords': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'news, politics, sports (comma separated)'
            }),
            'max_clicks': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'placeholder': '0 = unlimited'
            }),
            'max_impressions': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'placeholder': '0 = unlimited'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set choices after model is loaded
        from .models import Advertisement
        self.fields['ad_type'].choices = Advertisement.AD_TYPES
    
    def clean(self):
        cleaned_data = super().clean()
        budget = cleaned_data.get('budget')
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        # Get system settings
        from .models import SystemSettings
        try:
            settings = SystemSettings.objects.first()
        except SystemSettings.DoesNotExist:
            settings = SystemSettings.objects.create()
        
        # Budget validation
        if budget and budget < settings.min_ad_budget:
            raise forms.ValidationError(
                f'Minimum budget is ₦{settings.min_ad_budget}'
            )
        
        # Date validation
        if start_date and end_date:
            if start_date >= end_date:
                raise forms.ValidationError('End date must be after start date')
            
            if start_date < timezone.now():
                raise forms.ValidationError('Start date cannot be in the past')
        
        return cleaned_data

class BusinessProfileForm(forms.ModelForm):
    class Meta:
        # Import UserProfile model here
        from .models import UserProfile
        model = UserProfile
        fields = [
            'business_name', 'business_registration', 'business_address',
            'business_phone', 'business_email', 'business_website',
            'profile_pic', 'cover_photo', 'bio'
        ]
        widgets = {
            'business_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Official Business Name'
            }),
            'business_registration': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'RC Number or Registration ID'
            }),
            'business_address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Business Address'
            }),
            'business_phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+234 800 000 0000'
            }),
            'business_email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'business@example.com'
            }),
            'business_website': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://your-business.com'
            }),
            'bio': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Tell us about your business...'
            }),
        }

class GroupForm(forms.ModelForm):
    class Meta:
        # Import Group model here
        from .models import Group
        model = Group
        fields = [
            'name', 'description', 'group_type',
            'cover_image', 'icon',
            'allow_member_posts', 'require_post_approval'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Group Name'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Describe your group...'
            }),
            'group_type': forms.Select(attrs={'class': 'form-control'}),
            'allow_member_posts': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'require_post_approval': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class SystemSettingsForm(forms.ModelForm):
    class Meta:
        model = SystemSettings
        fields = '__all__'
        widgets = {
            # AI Settings
            'verification_threshold': forms.NumberInput(attrs={
                'step': '0.01',
                'min': '0',
                'max': '1',
                'class': 'form-control'
            }),
            'max_posts_to_verify': forms.NumberInput(attrs={
                'min': '1',
                'max': '500',
                'class': 'form-control'
            }),
            'verification_schedule': forms.Select(attrs={
                'class': 'form-control'
            }),
            
            # News Fetching
            'fetch_schedule': forms.Select(attrs={
                'class': 'form-control'
            }),
            'max_news_per_fetch': forms.NumberInput(attrs={
                'min': '1',
                'max': '200',
                'class': 'form-control'
            }),
            'trusted_sources': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'e.g. punchng.com, vanguardngr.com, premiumtimesng.com',
                'class': 'form-control'
            }),
            'blocked_sources': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'e.g. fakenews.com, clickbait.net',
                'class': 'form-control'
            }),
            
            # Post Settings
            'max_posts_per_day': forms.NumberInput(attrs={
                'min': '1',
                'max': '100',
                'class': 'form-control'
            }),
            'max_post_length': forms.NumberInput(attrs={
                'min': '100',
                'max': '50000',
                'class': 'form-control'
            }),
            'max_image_size': forms.NumberInput(attrs={
                'min': '1',
                'max': '20',
                'step': '1',
                'class': 'form-control'
            }),
            'allowed_image_types': forms.TextInput(attrs={
                'placeholder': 'jpg,jpeg,png,gif,webp',
                'class': 'form-control'
            }),
            
            # Ad Settings
            'max_ads_per_business': forms.NumberInput(attrs={
                'min': '1',
                'max': '50',
                'class': 'form-control'
            }),
            'banner_rotation_interval': forms.NumberInput(attrs={
                'min': '5',
                'max': '3600',
                'class': 'form-control'
            }),
            'min_ad_budget': forms.NumberInput(attrs={
                'step': '100',
                'min': '100',
                'class': 'form-control'
            }),
            'ad_impression_rate': forms.NumberInput(attrs={
                'step': '0.0001',
                'min': '0.0001',
                'class': 'form-control'
            }),
            'ad_click_rate': forms.NumberInput(attrs={
                'step': '0.01',
                'min': '0.01',
                'class': 'form-control'
            }),
            
            # Group Settings
            'max_groups_per_user': forms.NumberInput(attrs={
                'min': '1',
                'max': '20',
                'class': 'form-control'
            }),
            'min_members_for_public_group': forms.NumberInput(attrs={
                'min': '1',
                'max': '100',
                'class': 'form-control'
            }),
            
            # Trending Settings
            'trending_calculation_interval': forms.NumberInput(attrs={
                'min': '1',
                'max': '72',
                'class': 'form-control'
            }),
            'trending_time_window': forms.NumberInput(attrs={
                'min': '1',
                'max': '168',
                'class': 'form-control'
            }),
            'engagement_weight_like': forms.NumberInput(attrs={
                'step': '0.1',
                'min': '0',
                'class': 'form-control'
            }),
            'engagement_weight_comment': forms.NumberInput(attrs={
                'step': '0.1',
                'min': '0',
                'class': 'form-control'
            }),
            'engagement_weight_share': forms.NumberInput(attrs={
                'step': '0.1',
                'min': '0',
                'class': 'form-control'
            }),
            'engagement_weight_view': forms.NumberInput(attrs={
                'step': '0.001',
                'min': '0',
                'class': 'form-control'
            }),
            
            # Cache & Performance
            'cache_timeout': forms.NumberInput(attrs={
                'min': '0',
                'max': '86400',
                'class': 'form-control'
            }),
            
            # Maintenance
            'maintenance_message': forms.Textarea(attrs={
                'rows': 3,
                'class': 'form-control'
            }),
            
            # SEO
            'meta_description': forms.Textarea(attrs={
                'rows': 2,
                'class': 'form-control'
            }),
            'meta_keywords': forms.Textarea(attrs={
                'rows': 2,
                'class': 'form-control',
                'placeholder': 'news, nigeria, breaking news, politics'
            }),
            'robots_txt': forms.Textarea(attrs={
                'rows': 5,
                'class': 'form-control code-editor',
                'style': 'font-family: monospace;'
            }),
            
            # Social Media
            'facebook_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://facebook.com/yourpage'
            }),
            'twitter_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://twitter.com/yourhandle'
            }),
            'instagram_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://instagram.com/yourpage'
            }),
            'linkedin_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://linkedin.com/company/yourcompany'
            }),
            'youtube_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://youtube.com/c/yourchannel'
            }),
            'telegram_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://t.me/yourgroup'
            }),
            'whatsapp_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+2348012345678'
            }),
            
            # Contact
            'contact_email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'contact@yourdomain.com'
            }),
            'support_email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'support@yourdomain.com'
            }),
            'contact_phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+2348012345678'
            }),
            'address': forms.Textarea(attrs={
                'rows': 2,
                'class': 'form-control'
            }),
            
            # User Settings
            'default_user_role': forms.Select(attrs={
                'class': 'form-control'
            }),
        }
    
    def clean_verification_threshold(self):
        threshold = self.cleaned_data['verification_threshold']
        if threshold < 0 or threshold > 1:
            raise forms.ValidationError('Threshold must be between 0 and 1')
        return threshold
    
    def clean_trusted_sources(self):
        sources = self.cleaned_data['trusted_sources']
        if sources:
            # Clean up the input
            sources_list = [s.strip() for s in sources.split(',') if s.strip()]
            return ', '.join(sources_list)
        return sources
    
    def clean_blocked_sources(self):
        sources = self.cleaned_data['blocked_sources']
        if sources:
            sources_list = [s.strip() for s in sources.split(',') if s.strip()]
            return ', '.join(sources_list)
        return sources
    
    def clean_allowed_image_types(self):
        types = self.cleaned_data['allowed_image_types']
        if types:
            types_list = [t.strip().lower() for t in types.split(',') if t.strip()]
            return ', '.join(types_list)
        return 'jpg,jpeg,png,gif,webp'
    
    
    
# Keep existing forms
class CommentForm(forms.ModelForm):
    class Meta:
        from .models import Comment
        model = Comment
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Add a comment...',
                'required': True
            })
        }

class UserProfileForm(forms.ModelForm):
    class Meta:
        from .models import UserProfile
        model = UserProfile
        fields = [
            'bio', 'profile_pic', 'cover_photo', 'location', 'website', 
            'twitter_handle', 'phone', 'date_of_birth', 'occupation', 
            'interests', 'facebook_url', 'instagram_url', 'linkedin_url'
        ]
        widgets = {
            'bio': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Tell us about yourself...'
            }),
            'location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Your location'
            }),
            'website': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://yourwebsite.com'
            }),
            'twitter_handle': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '@username'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+234 800 000 0000'
            }),
            'date_of_birth': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'occupation': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Your occupation'
            }),
            'interests': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Sports, Technology, Politics, etc.'
            }),
            'facebook_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://facebook.com/username'
            }),
            'instagram_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://instagram.com/username'
            }),
            'linkedin_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://linkedin.com/in/username'
            }),
        }

class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'First name'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Last name'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Email address'
            }),
        }