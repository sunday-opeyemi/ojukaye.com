# core/urls.py
from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Home and posts
    path('', views.home, name='home'),
    
    path('online-news/', views.online_news, name='online_news'),
    
    # Post URLs
    path('post/<int:post_id>/', views.post_detail, name='post_detail'),
    path('post/create/', views.create_post, name='create_post'),
    path('post/<int:post_id>/like/', views.like_post, name='like_post'),
    path('post/<int:post_id>/bookmark/', views.bookmark_post, name='bookmark_post'),
    path('post/<int:post_id>/repost/', views.repost_post, name='repost_post'),
    path('post/<int:post_id>/edit/', views.edit_post, name='edit_post'),
    path('post/<int:post_id>/delete/', views.delete_post, name='delete_post'),
    
    # Following views
    path('api/users/<str:username>/following/', views.api_following, name='api_following'),
    path('api/users/<str:username>/followers/', views.api_followers, name='api_followers'),
    
    # Category URLs
    path('category/<slug:category_slug>/', views.category_view, name='category_view'),
    
    # User URLs
    path('profile/edit/', views.edit_profile, name='edit_profile'), 
    path('profile/<str:username>/', views.profile_view, name='profile_view'),
    path('profile/update-pic/', views.update_profile_pic, name='update_profile_pic'),
    path('profile/update-cover/', views.update_cover_photo, name='update_cover_photo'),
    path('profile/<str:username>/posts/', views.profile_posts, name='profile_posts'),
    
    # Auth URLs
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
    path('dashboard/force-fetch-news/', views.force_fetch_news, name='force_fetch_news'),
    path('dashboard/fetch-news-status/', views.fetch_news_status, name='fetch_news_status'),
    path('dashboard/news/submissions/', views.admin_news_submissions, name='admin_news_submissions'),
    path('dashboard/news/auto-fetched/', views.admin_auto_fetched_news, name='admin_auto_fetched_news'),
    path('dashboard/news/<int:post_id>/', views.admin_news_detail, name='admin_news_detail'),
    path('dashboard/news/bulk-action/', views.admin_bulk_news_action, name='admin_bulk_news_action'),
    path('dashboard/system-settings/', views.admin_system_settings, name='admin_system_settings'),
    
    # Other URLs
    path('trending/', views.trending_posts, name='trending_posts'),
    path('bookmarks/', views.bookmarks, name='bookmarks'),
    path('search/', views.search, name='search'),
    path('search/suggestions/', views.search_suggestions, name='search_suggestions'),
    path('activity/', views.activity_feed, name='activity_feed'),
    path('follow/<str:username>/', views.follow_user, name='follow_user'),
    path('discover/', views.discover, name='discover'),
    
    # API URLs
    path('api/fetch-news/', views.api_fetch_news, name='api_fetch_news'),
    path('api/banners/', views.api_banners, name='api_banners'),
    path('api/news-feed/', views.api_news_feed, name='api_news_feed'),
    path('api/news/<int:post_id>/', views.api_news_detail, name='api_news_detail'),
    path('api/check-new-news/', views.check_new_news, name='check_new_news'),
    path('api/track-ad-impression/<str:ad_id>/', views.api_track_ad_impression, name='api_track_ad_impression'),
    path('api/track-ad-click/<str:ad_id>/', views.api_track_ad_click, name='api_track_ad_click'),
    
    # Settings
    path('api/toggle-dark-mode/', views.toggle_dark_mode, name='toggle_dark_mode'),
    
    # Notifications
    path('notifications/', views.notifications, name='notifications'),
    path('notifications/count/', views.notifications_count, name='notifications_count'),
    
    # Messages
    path('messages/', views.messages_view, name='messages'),
    
    # Settings pages
    path('privacy/', views.privacy_policy, name='privacy'),
    path('terms/', views.terms_of_service, name='terms'),
    path('about/', views.about, name='about'),
    path('contact/', views.contact, name='contact'),
    path('help/', views.help_center, name='help'),
    
    # Newsletter
    path('newsletter/signup/', views.newsletter_signup, name='newsletter_signup'),
    
    # Business/Ad URLs
    # path('business/register/', views.business_registration, name='business_registration'),
    path('ads/submit/', views.ad_submission, name='ad_submission'),
    path('ads/manage/', views.ad_manage, name='ad_manage'),
    path('ads/<uuid:uuid>/', views.ad_detail, name='ad_detail'),
    path('ads/credits/', views.ad_credits, name='ad_credits'),
]