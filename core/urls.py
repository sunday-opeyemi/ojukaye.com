# core/urls.py
from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Home and posts
    path('', views.home, name='home'),
    
    path('online-news/', views.online_news, name='online_news'),
    
    # Post URLs - THIS IS WHAT'S MISSING
    path('post/<int:post_id>/', views.post_detail, name='post_detail'),
    path('post/create/', views.create_post, name='create_post'),
    path('post/<int:post_id>/like/', views.like_post, name='like_post'),
    path('post/<int:post_id>/bookmark/', views.bookmark_post, name='bookmark_post'),
    path('post/<int:post_id>/repost/', views.repost_post, name='repost_post'),
    
    # Category URLs
    path('category/<slug:category_slug>/', views.category_view, name='category_view'),
    
    # User URLs
    path('profile/edit/', views.edit_profile, name='edit_profile'), 
    path('profile/<str:username>/', views.profile_view, name='profile_view'),
    path('profile/update-pic/', views.update_profile_pic, name='update_profile_pic'),
    path('profile/update-cover/', views.update_cover_photo, name='update_cover_photo'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Comment URLs
    path('comment/<int:comment_id>/like/', views.like_comment, name='like_comment'),
    path('comment/<int:comment_id>/delete/', views.delete_comment, name='delete_comment'),
    
    # Admin URLs
    path('dashboard/admin/', views.admin_dashboard, name='admin_dashboard'),
    path('dashboard/posts/', views.admin_posts, name='admin_posts'),
    path('dashboard/fetch-news/', views.fetch_news, name='fetch_news'),
    path('dashboard/business-verification/', views.admin_business_verification, name='admin_business_verification'),
    path('dashboard/system-settings/', views.admin_system_settings, name='admin_system_settings'),
    
    # Other URLs
    path('trending/', views.trending_posts, name='trending_posts'),
    path('bookmarks/', views.bookmarks, name='bookmarks'),
    path('search/', views.search, name='search'),
    path('activity/', views.activity_feed, name='activity_feed'),
    path('follow/<str:username>/', views.follow_user, name='follow_user'),
    
    # API URLs
    path('api/fetch-news/', views.api_fetch_news, name='api_fetch_news'),
    path('api/banners/', views.api_banners, name='api_banners'),
    path('api/check-new-news/', views.check_new_news, name='check_new_news'),
    
    
    # Settings
    path('api/toggle-dark-mode/', views.toggle_dark_mode, name='toggle_dark_mode'),
    
    path('notifications/', views.notifications, name='notifications'),
    path('messages/', views.messages_view, name='messages'),
    path('discover/', views.discover, name='discover'),
    path('search/', views.search, name='search'),
    
    # Settings pages
    path('settings/', views.settings, name='settings'),
    path('privacy/', views.privacy_policy, name='privacy'),
    path('terms/', views.terms_of_service, name='terms'),
    path('about/', views.about, name='about'),
    path('contact/', views.contact, name='contact'),
    path('help/', views.help_center, name='help'),
]