# core/allauth_forms.py
from allauth.account.forms import SignupForm, LoginForm
from django import forms
from django.contrib.auth.models import User

class CustomSignupForm(SignupForm):
    """Custom signup form with first/last name and account type"""
    
    ACCOUNT_TYPES = [
        ('individual', 'Individual Account'),
        ('business', 'Business Account'),
    ]
    
    first_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'First Name'})
    )
    last_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Last Name'})
    )
    account_type = forms.ChoiceField(
        choices=ACCOUNT_TYPES,
        widget=forms.RadioSelect(attrs={'class': 'account-type-radio'}),
        initial='individual'
    )
    
    def save(self, request):
        user = super().save(request)
        
        # Set first and last name
        user.first_name = self.cleaned_data.get('first_name')
        user.last_name = self.cleaned_data.get('last_name')
        user.save()
        
        # Create or update profile
        from .models import UserProfile
        profile, created = UserProfile.objects.get_or_create(user=user)
        profile.account_type = self.cleaned_data.get('account_type')
        
        # If business account, set initial fields
        if profile.account_type == 'business':
            profile.business_name = f"{user.first_name} {user.last_name}'s Business"
            profile.business_email = user.email
        
        profile.save()
        
        return user

class CustomLoginForm(LoginForm):
    """Custom login form with remember me"""
    
    remember = forms.BooleanField(required=False, initial=False)
    
    def login(self, request, redirect_url=None):
        ret = super().login(request, redirect_url)
        
        # Handle remember me - if not checked, session expires on browser close
        if not self.cleaned_data.get('remember'):
            request.session.set_expiry(0)
        
        return ret