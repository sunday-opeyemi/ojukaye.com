from django.conf.urls import url
from django.urls import path, re_path
from django.views.generic import TemplateView
from ojukaye.userportalapp import views as userportal_views

urlpatterns = [
    url(r'^mediafiles/', userportal_views.addmedia, name='mediafiles'),
    url(r'^shareuser/(?P<shareid>\d+)/', userportal_views.share_user, name='shareuser'),
    url(r'^likeuser/(?P<likeid>\d+)/', userportal_views.like_user, name='likeuser'),
    url(r'^unlikeuser/(?P<unlikeid>\d+)/', userportal_views.unlike_user, name='unlikeuser'), 
    url(r'^replypost/', userportal_views.reply_post, name='replypost'),
    re_path(r'^postbody/(?P<postid>\d+)/$', userportal_views.post_body, name='postbody'), 
    url(r'^repository/(?P<username>.+)/', userportal_views.addmedia, name='repository'),
    url(r'^marketplace/(?P<username>.+)/', userportal_views.addmedia, name='marketplace'),
    url(r'^follower/(?P<username>.+)/', userportal_views.follows, name='follower'),
    url(r'^(?P<username>.+)/$', userportal_views.user_portal, name='userportal'),
    url(r'^(?P<userid>.+)/$', userportal_views.user_profile, name='userprofile'), 
] 