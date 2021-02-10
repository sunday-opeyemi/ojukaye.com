from django.db import models
from datetime import date
from django.utils import timezone
from django.contrib.auth.models import User
from ojukaye.userportalapp.models import  userpost_table

# Create your models here.

class news_table(models.Model):
    post_id = models.AutoField(primary_key=True)
    username = models.CharField(max_length=30)
    datetime = models.DateTimeField(default=timezone.now)
    post_title = models.CharField(unique=True, max_length=250)
    news_post = models.CharField(max_length=5000)
    category = models.CharField(max_length=20)
    picture = models.ImageField(upload_to='picture/', unique=False, null=True)
    video = models.FileField(upload_to='video/', unique=False, null=True)
    audio = models.FileField(upload_to='audio/', unique=False, null=True)
    post_source = models.CharField(max_length=250, unique=False, null=True)
    share_num = models.IntegerField(default=0)
    approved = models.CharField(unique=False, max_length=10, null=True)

class comment_table(models.Model):
    comment_id = models.AutoField(primary_key=True)
    post =  models.ForeignKey(news_table, on_delete=models.CASCADE, null=True)
    userp =  models.ForeignKey(userpost_table, on_delete=models.CASCADE, null=True)
    username = models.CharField(max_length=30) 
    datetime = models.DateTimeField(default=timezone.now)
    comment_post = models.CharField(max_length=3000)
    post_title =  models.CharField(unique=False, max_length=250)
    picture = models.ImageField(upload_to='picture/', unique=False, null=True)
    video = models.FileField(upload_to='video/', unique=False, null=True)
    audio = models.FileField(upload_to='audio', unique=False, null=True)
    like_num = models.IntegerField(default=0) 
    unlike_num = models.IntegerField(default=0)
    
class likeshare_table(models.Model):
    sharelike_id = models.AutoField(primary_key=True)
    datetime = models.DateTimeField(default=timezone.now)
    post =  models.ForeignKey(news_table, on_delete=models.CASCADE, null=True)
    userp =  models.ForeignKey(userpost_table, on_delete=models.CASCADE, null=True)
    comment =  models.ForeignKey(comment_table, on_delete=models.CASCADE, null=True)
    username = models.CharField(max_length=30) 
    like = models.CharField(max_length=30, null=True) 
    unlike = models.CharField(max_length=30, null=True) 
    share = models.CharField(max_length=30, null=True) 
