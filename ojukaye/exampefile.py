user_profile/models
from django.contrib import auth
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings

class Listing (models.Model):

    image = models.ImageField(default='default.jpg', upload_to='profile_pics')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.CASCADE)
    created =  models.DateTimeField(auto_now_add=True, null=True)
    updated = models.DateTimeField(auto_now=True)
    rank = models.CharField(max_length=100, null=True)    
    name = models.CharField(max_length=100)
    address = models.CharField(max_length=100)
    zip_code = models.CharField(max_length=100)
    mobile_number = models.CharField(max_length=100)

def create_profile(sender, **kwargs):
    if kwargs['created']:
        user_profile = Listing.objects.create(user=kwargs['instance'])

post_save.connect(create_profile, sender=CustomUser)


# Django User Registration Authentication – SignUpView
# We can implement simple sign up registration by using in-built UserCreationForm Auth Form(signup class based view). We will be using CreateView in View. We can create sign up using only username and password. But we are adding extra fields in forms.py ( django create user form ) while registration like first last name and email.

# urls.py

from django.urls import path
from core.views import SignUpView

urlpatterns = [
    path('signup/', SignUpView.as_view(), name='signup'),
]
# views.py

from django.shortcuts import render
from django.urls import reverse_lazy
from django.views.generic import CreateView
from core.forms import SignUpForm

# Sign Up View
class SignUpView(CreateView):
    form_class = SignUpForm
    success_url = reverse_lazy('login')
    template_name = 'commons/signup.html'
# 
# forms.py

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm

# Sign Up Form
class SignUpForm(UserCreationForm):
    first_name = forms.CharField(max_length=30, required=False, help_text='Optional')
    last_name = forms.CharField(max_length=30, required=False, help_text='Optional')
    email = forms.EmailField(max_length=254, help_text='Enter a valid email address')

    class Meta:
        model = User
        fields = [
            'username', 
            'first_name', 
            'last_name', 
            'email', 
            'password1', 
            'password2', 
            ]

# signup.html

{% extends 'base.html' %}

{% block title %}Sign Page{% endblock title %}

{% block content %} 
    <h2>Sign Page</h2>
    <form method="post">
        {% csrf_token %}
        {{ form.as_p }}
        <button type="submit">Register</button>
        <br><br>
        <a href="{% url 'home' %}">Home</a>
    </form>
{% endblock content %}


# Profile Update View Form After Sign Up in Django
# As we have made a signup module, so it is obvious we are going to need a profile update module. For Profile Update Functionality, we are going to use generic UpdateView. These are the in-built class-based views that make our code DRY. We are going to use the User Model which we have used above.

# views.py

from django.shortcuts import render
from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView
from core.forms import SignUpForm, ProfileForm
from django.contrib.auth.models import User

# Edit Profile View
class ProfileView(UpdateView):
    model = User
    form_class = ProfileForm
    success_url = reverse_lazy('home')
    template_name = 'commons/profile.html'

# forms.py

from django import forms
from django.contrib.auth.models import User

# Profile Form
class ProfileForm(forms.ModelForm):

    class Meta:
        model = User
        fields = [
            'username',
            'first_name', 
            'last_name', 
            'email',
            ]

# urls.py

from django.urls import path
from core.views import SignUpView, ProfileView

urlpatterns = [
    path('signup/', SignUpView.as_view(), name='signup'),
    path('profile/<int:pk>/', ProfileView.as_view(), name='profile'),
]

# profile.html

{% extends 'base.html' %}

{% block title %}Profile Page{% endblock title %}

{% block content %} 
    <h2>Profile Page</h2>
    <form method="post">
        {% csrf_token %}
        {{ form.as_p }}
        <button type="submit">Update</button>
        <br><br>
        <a href="{% url 'home' %}">Back</a>
    </form>
{% endblock content %}


# view function to create new user using customized form
from django.contrib.auth.models import User
user = User.objects.create_user(username='john',
  email='jlennon@beatles.com',
  password='glass onion')

# server database setting
DATABASES = {
    'default': {
        'ENGINE': 'mysql.connector.django',
        'NAME': 'sundayopeyemi$ojukaye',
        'USER': 'sundayopeyemi',
        'PASSWORD': 'sundayschool',
        'HOST': 'sundayopeyemi.mysql.pythonanywhere-services.com',
        'PORT': '3306',
        'OPTIONS': {
            'autocommit': True,
        },
    }
}

