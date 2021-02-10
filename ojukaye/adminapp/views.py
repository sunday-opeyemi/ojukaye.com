from django.shortcuts import render
from django.contrib.auth.forms import UserCreationForm
from django.urls import reverse_lazy, reverse
from django.views import generic
from django.http import HttpResponseRedirect, HttpResponsePermanentRedirect
from ojukaye.newsapp.models import news_table, comment_table
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import User

category = ''
post_headline = ''
# Create your views here.
@permission_required('User.is_staff')
def homenews(request, url_name='general_news'):
    global category
    if url_name == 'general_news':
        approved_news = news_table.objects.only('post_title', 'approved', 'post_id').filter(approved='unapprove')
        category = ''
    else:
        approved_news = news_table.objects.only('post_title', 'approved', 'post_id').filter(category=url_name)
        category = url_name
    returned_values = {'approved_news':approved_news, 'headline':category}    
    return render(request, 'adminapp/adminhomefeed.html', {'returned_values':returned_values})

@permission_required('User.is_staff')
def approve_news(request, postid):
    news_table.objects.filter(post_id=postid).update(approved='approved')
    return homenews(request, category)

@permission_required('User.is_staff')
def delete_news(request, postid):
    news_table.objects.filter(post_id=postid).delete()
    return homenews(request, category)

@permission_required('User.is_staff')
def user_record(request):      
    returned_users = User.objects.filter(is_superuser='0').only("username", "first_name", "last_name", "email", "is_active", "date_joined")
    return render(request, 'adminapp/user_record.html', {'returned_users':returned_users})

@permission_required('User.is_staff')
def banned_user(request, userid):
    user = User.objects.get(id=userid)
    print(user.is_active)
    if user.is_active:
        user.is_active = 0
    else:
        user.is_active = 1
    user.save()
    return user_record(request)

@permission_required('User.is_staff')
def delete_user(request, userid):
    User.objects.filter(id=userid).delete()
    return user_record(request)
