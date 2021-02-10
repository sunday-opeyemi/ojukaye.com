from django import forms
from django.forms import PasswordInput
from .models import news_table
# from django.db import models
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm

class News_post_form(forms.Form):
    post_title = forms.CharField(max_length=250)
    news_post = forms.CharField(widget=forms.Textarea())
    news_source = forms.CharField(max_length=250)
    picture = forms.ImageField(required=False, widget=forms.ClearableFileInput(attrs={'multiple': True}), max_length=5000)
    video = forms.FileField(required=False)
    audio = forms.FileField(required=False)

class Comment_form(forms.Form):
    comment = forms.CharField(widget=forms.Textarea())
    picture = forms.ImageField(required=False, widget=forms.ClearableFileInput(attrs={'multiple': True}), max_length=2000)
    video = forms.FileField(required=False)
    audio = forms.FileField(required=False)

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

class Search_bar_form(forms.Form):
    search = forms.CharField(max_length=100, label='', widget=forms.TextInput(
        attrs={'placeholder': 'Enter topic to search'}))