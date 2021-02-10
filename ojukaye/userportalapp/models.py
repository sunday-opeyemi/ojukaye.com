from django.db import models
from django.contrib.auth.models import User
from datetime import date
from django.utils import timezone

# Create your models here.

class userprofile_table(models.Model):
    profile_id = models.AutoField(primary_key=True)
    datetime = models.DateTimeField(default=timezone.now)
    user =  models.ForeignKey(User, on_delete=models.CASCADE)
    username = models.CharField(max_length=30)
    last_update = models.DateTimeField(default=timezone.now)
    location = models.CharField(unique=True, max_length=250)
    profile_picture = models.ImageField(upload_to='profileImage/', unique=False, null=True)

class userpost_table(models.Model):
    userp_id = models.AutoField(primary_key=True)
    user =  models.ForeignKey(User, on_delete=models.CASCADE)
    username = models.CharField(max_length=30)
    datetime = models.DateTimeField(default=timezone.now)
    post_content = models.CharField(max_length=5000, null=True)
    picture = models.ImageField(upload_to='userpics/', unique=False, null=True)
    video = models.FileField(upload_to='uservideo/', unique=False, null=True)
    audio = models.FileField(upload_to='useraudio/', unique=False, null=True)
    share_num = models.IntegerField(default=0)
