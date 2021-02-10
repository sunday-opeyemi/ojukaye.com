from django.conf.urls import url
from django.urls import path, re_path
from django.views.generic import TemplateView
from ojukaye.newsapp import views as newsapp_views

urlpatterns = [
    url(r'^$', newsapp_views.homenews, name='homenewsfeed'),
    url(r'^postnews', newsapp_views.post_news, name='postnews'), 
    url(r'^commentpost', newsapp_views.comment_post, name='commentpost'), 
    url(r'^sharepost/(?P<shareid>\d+)/', newsapp_views.share_post, name='sharepost'),
    url(r'^likecomment/(?P<likeid>\d+)/', newsapp_views.like_comment, name='likecomment'),
    url(r'^unlikecomment/(?P<unlikeid>\d+)/', newsapp_views.unlike_comment, name='unlikecomment'), 
    re_path(r'^newsbody/(?P<headline>.+)/$', newsapp_views.news_body, name='newsbody'), 
    url(r'^(?P<url_name>\D+)/', newsapp_views.homenews, name='homenewsfeed'),
]