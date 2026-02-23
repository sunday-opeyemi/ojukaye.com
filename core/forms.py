# core/forms.py
from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.core.validators import URLValidator, ValidationError
from django.utils import timezone
from .models import (
    Post, Category, Comment, UserProfile, Advertisement, 
    Group, Follow, SystemSettings
)
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

    
    

class BusinessProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = [
            'business_name', 'business_registration', 'business_address',
            'business_phone', 'business_email', 'business_website',
        ]
        widgets = {
            'business_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your Business Name'}),
            'business_registration': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Registration Number'}),
            'business_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Business Address'}),
            'business_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone Number'}),
            'business_email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Business Email'}),
            'business_website': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://example.com'}),
        }


class AdSubmissionForm(forms.ModelForm):
    class Meta:
        model = Advertisement
        fields = [
            'ad_type', 'title', 'description', 'image', 'target_url',
            'budget', 'start_date', 'end_date',
            'target_categories', 'target_locations', 'target_keywords',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ad Title'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Ad Description'}),
            'target_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://example.com'}),
            'budget': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Budget in NGN'}),
            'start_date': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'end_date': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'target_locations': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Lagos, Abuja, Port Harcourt'}),
            'target_keywords': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'tech, business, sports'}),
            'ad_type': forms.Select(attrs={'class': 'form-control'}),
            'target_categories': forms.SelectMultiple(attrs={'class': 'form-control', 'size': '5'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make required fields
        self.fields['budget'].required = True
        self.fields['start_date'].required = True
        self.fields['end_date'].required = True
        self.fields['target_url'].required = True
    
    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        budget = cleaned_data.get('budget')
        
        if start_date and end_date and start_date >= end_date:
            raise ValidationError('End date must be after start date')
        
        if budget and budget < 1000:
            raise ValidationError('Minimum budget is ₦1,000')
        
        return cleaned_data



class GroupForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = ['name', 'description', 'group_type', 'cover_image', 'icon']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Group Name'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Group Description'}),
            'group_type': forms.Select(attrs={'class': 'form-control'}),
        }

class SystemSettingsForm(forms.ModelForm):
    """Form for system settings"""
    class Meta:
        model = SystemSettings
        fields = '__all__'
        widgets = {
            'maintenance_message': forms.Textarea(attrs={'rows': 3}),
            'meta_description': forms.Textarea(attrs={'rows': 3}),
            'robots_txt': forms.Textarea(attrs={'rows': 5}),
            'trusted_sources': forms.Textarea(attrs={'rows': 3, 'placeholder': 'punchng.com, vanguardngr.com, premiumtimesng.com'}),
            'blocked_sources': forms.Textarea(attrs={'rows': 3, 'placeholder': 'suspicious-site.com'}),
        }


class PostForm(forms.ModelForm):
    POST_TYPE_CHOICES = [
        ('discussion', 'Discussion - Public discussion post'),
        ('user_news', 'User News - Submit news for verification'),
        ('profile_post', 'Profile Post - Private profile update'),
    ]
    
    post_type = forms.ChoiceField(
        choices=POST_TYPE_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'post-type-radio'}),
        initial='discussion',
        required=True,
        error_messages={
            'required': 'Please select a post type'
        }
    )
    
    
    PRIVACY_CHOICES = [
        ('public', '🌍 Public - Everyone can view'),
        ('followers', '👥 Followers Only - Only my followers can view'),
        ('private', '🔒 Private - Only me'),
        ('specific', '🎯 Specific Followers - Select specific followers'),
    ]
    
    privacy = forms.ChoiceField(
        choices=PRIVACY_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'privacy-radio'}),
        initial='public',
        required=False
    )
    
    allowed_viewers = forms.ModelMultipleChoiceField(
        queryset=None,
        widget=forms.SelectMultiple(attrs={'class': 'form-control', 'size': '5'}),
        required=False
    )
    
    # Media fields
    video_url = forms.URLField(required=False, widget=forms.URLInput(attrs={'class': 'form-control'}))
    audio_url = forms.URLField(required=False, widget=forms.URLInput(attrs={'class': 'form-control'}))
    image = forms.ImageField(required=False, widget=forms.FileInput(attrs={'class': 'form-control'}))
    image_url = forms.URLField(required=False, widget=forms.URLInput(attrs={'class': 'form-control'}))
    
    # News source fields
    source_url = forms.URLField(required=False, widget=forms.URLInput(attrs={'class': 'form-control'}))
    source_name = forms.CharField(required=False, max_length=255, widget=forms.TextInput(attrs={'class': 'form-control'}))
    
    # Category
    category = forms.ModelChoiceField(
        queryset=Category.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    # Settings
    allow_comments = forms.BooleanField(required=False, initial=True, widget=forms.CheckboxInput())
    allow_sharing = forms.BooleanField(required=False, initial=True, widget=forms.CheckboxInput())
    
    class Meta:
        model = Post
        fields = [
            'title', 'content', 'post_type', 'privacy', 'allowed_viewers',
            'category', 'source_url', 'source_name', 'image', 'image_url',
            'video_url', 'audio_url', 'allow_comments', 'allow_sharing'
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
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Make post_type required and ensure it's in the form
        self.fields['post_type'].required = True
        
        # Debug print to see what's happening
        if self.data:
            print("PostForm received data:", self.data)
            if 'post_type' in self.data:
                print("post_type value:", self.data['post_type'])
            else:
                print("WARNING: post_type not in POST data!")
        
        # Set initial post_type if provided in initial data
        if 'initial' in kwargs and 'post_type' in kwargs['initial']:
            self.fields['post_type'].initial = kwargs['initial']['post_type']
        
        if self.user:
            from .models import Follow
            # Get followers for allowed_viewers
            followers = User.objects.filter(
                followers__follower=self.user
            ).distinct().order_by('username')
            self.fields['allowed_viewers'].queryset = followers
            
            # Set help text if no followers
            if followers.count() == 0:
                self.fields['allowed_viewers'].help_text = "You don't have any followers yet"
        
        # Set conditional requirements based on post type
        self.set_conditional_requirements()


    def set_conditional_requirements(self):
        """Set field requirements based on post type"""
        post_type = self.data.get('post_type') or self.initial.get('post_type')
        
        if post_type == 'user_news':
            # News posts require source URL and category
            self.fields['source_url'].required = True
            self.fields['source_url'].error_messages = {
                'required': 'Source URL is required for news posts'
            }
            self.fields['category'].required = True
            self.fields['category'].error_messages = {
                'required': 'Please select a category for your news post'
            }
        elif post_type == 'profile_post':
            # Profile posts don't need category
            self.fields['category'].required = False
            self.fields['source_url'].required = False
            self.fields['source_name'].required = False
        else:  # discussion
            # Discussion posts have optional category
            self.fields['category'].required = False
            self.fields['source_url'].required = False
            self.fields['source_name'].required = False
    
    def clean_post_type(self):
            """Validate post_type field"""
            post_type = self.cleaned_data.get('post_type')
            
            if not post_type:
                raise forms.ValidationError('Please select a post type')
            
            valid_types = [choice[0] for choice in self.POST_TYPE_CHOICES]
            if post_type not in valid_types:
                raise forms.ValidationError(f'Invalid post type: {post_type}')
            
            return post_type
    
    def clean(self):
        cleaned_data = super().clean()
        post_type = cleaned_data.get('post_type')
        privacy = cleaned_data.get('privacy')
        allowed_viewers = cleaned_data.get('allowed_viewers')
        source_url = cleaned_data.get('source_url')
        category = cleaned_data.get('category')
        
        # Validate based on post type
        if post_type == 'user_news':
            # News posts must have source URL
            if not source_url:
                self.add_error('source_url', 'Source URL is required for news posts')
            
            # News posts must have category
            if not category:
                self.add_error('category', 'Category is required for news posts')
        elif post_type == 'profile_post':
            # Profile posts don't need category
            cleaned_data['category'] = None
        else:  # discussion
            # Discussion posts have optional category
            pass
        
        # Validate privacy settings
        if privacy == 'specific':
            if not allowed_viewers or allowed_viewers.count() == 0:
                self.add_error('allowed_viewers', 'Please select at least one follower for specific privacy')
            elif allowed_viewers.count() > 0 and self.user:
                # Ensure selected users are actually followers
                followers = User.objects.filter(
                    followers__follower=self.user
                ).values_list('id', flat=True)
                
                for viewer in allowed_viewers:
                    if viewer.id not in followers:
                        self.add_error('allowed_viewers', f'{viewer.username} is not following you')
        
        # Profile posts should have private privacy by default
        if post_type == 'profile_post' and privacy != 'private':
            cleaned_data['privacy'] = 'private'
        
        # Validate title and content length
        title = cleaned_data.get('title', '')
        if title and len(title) < 3:
            self.add_error('title', 'Title must be at least 3 characters long')
        elif title and len(title) > 200:
            self.add_error('title', 'Title must be less than 200 characters')
        
        content = cleaned_data.get('content', '')
        if content and len(content) < 3:
            self.add_error('content', 'Content must be at least 3 characters long')
        
        return cleaned_data
    
    def save(self, commit=True):
        post = super().save(commit=False)
        
        # Set post_type explicitly
        post.post_type = self.cleaned_data.get('post_type')
        
        # Handle media URLs
        video_url = self.cleaned_data.get('video_url')
        if video_url:
            post.video_urls = [{'url': video_url, 'type': 'embed', 'source': 'user'}]
            post.has_media = True
        
        audio_url = self.cleaned_data.get('audio_url')
        if audio_url:
            post.audio_urls = [{'url': audio_url, 'type': 'embed', 'source': 'user'}]
            post.has_media = True
        
        # Handle image
        if self.cleaned_data.get('image'):
            post.image = self.cleaned_data['image']
        elif self.cleaned_data.get('image_url'):
            post.image_url = self.cleaned_data['image_url']
        
        # Handle source for news posts
        if post.post_type == 'user_news':
            if self.cleaned_data.get('source_url'):
                post.external_url = self.cleaned_data['source_url']
                post.source_url = self.cleaned_data['source_url']  # Set both fields
            if self.cleaned_data.get('source_name'):
                post.external_source = self.cleaned_data['source_name']
                post.source_name = self.cleaned_data['source_name']  # Set both fields
        
        # Handle privacy settings
        post.privacy = self.cleaned_data.get('privacy', 'public')
        
        if commit:
            post.save()
            self.save_m2m()
            
            # Handle allowed viewers for specific privacy
            if post.privacy == 'specific' and self.cleaned_data.get('allowed_viewers'):
                post.allowed_viewers.set(self.cleaned_data['allowed_viewers'])
        
        return post
    
    def clean_title(self):
        """Validate title field"""
        title = self.cleaned_data.get('title', '').strip()
        if not title:
            raise forms.ValidationError('Title is required')
        return title
    
    def clean_content(self):
        """Validate content field"""
        content = self.cleaned_data.get('content', '').strip()
        if not content:
            raise forms.ValidationError('Content is required')
        return content

    
# Keep existing forms
class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['content', 'image']
        widgets = {
            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Write your comment...'
            }),
            'image': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
        }
    
    def clean_content(self):
        content = self.cleaned_data.get('content')
        if not content or len(content.strip()) < 2:
            raise ValidationError('Comment must be at least 2 characters long')
        return content

class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = [
            'bio', 'profile_pic', 'cover_photo', 'location', 'website',
            'phone', 'date_of_birth', 'occupation', 'interests',
            'facebook_url', 'twitter_handle', 'instagram_url', 'linkedin_url',
            'privacy_level', 'email_notifications', 'show_online_status',
            'receive_promo_emails', 'ad_notifications'
        ]
        widgets = {
            'bio': forms.Textarea(attrs={'rows': 4, 'class': 'form-control', 'placeholder': 'Tell us about yourself...'}),
            'date_of_birth': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'interests': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Technology, Sports, Politics'}),
        }


class UserUpdateForm(forms.ModelForm):
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'class': 'form-control'}))
    
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'}),
        }
