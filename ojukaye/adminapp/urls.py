from django.conf.urls import url
from django.urls import path, re_path
from django.views.generic import TemplateView
from ojukaye.adminapp import views as admin_views

urlpatterns = [
    url(r'^$', admin_views.homenews, name='adminhomefeed'),
    url(r'^user_record/$', admin_views.user_record, name='userRecord'),
    url(r'^(?P<url_name>\D+)/$', admin_views.homenews, name='adminhomefeed'),
    url(r'^approve_news/(?P<postid>\d+)/$', admin_views.approve_news, name='approvenews'),
    url(r'^delete_news/(?P<postid>\d+)/$', admin_views.delete_news, name='deletenews'),
    url(r'^banneduser/(?P<userid>\d+)/$', admin_views.banned_user, name='banneduser'),
    url(r'^deleteuser/(?P<userid>\d+)/$', admin_views.delete_user, name='deleteuser'),
]