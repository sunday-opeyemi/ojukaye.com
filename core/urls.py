from django.urls import path
from . import views

urlpatterns = [
    
    # Home & Main Pages
    path('', views.dynamic_home, name='home'), 
    path('online-news/', views.online_news, name='online_news'), 
    
    # Auth URLs
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    
    # Trending & Discover
    path('trending/', views.trending_posts, name='trending'),
    path('trending/', views.trending_posts, name='trending_posts'),
    path('discover/', views.discover, name='discover'),
    path('people-to-follow/', views.people_to_follow, name='people_to_follow'),
    
    # Resources & Help
    path('resources/', views.resources, name='resources'),
    path('help/', views.help_center, name='help_center'),
    path('help/', views.help_center, name='help'),
    path('faq/', views.faq, name='faq'),
    
    # About & Contact
    path('about/', views.about, name='about'),
    path('contact/', views.contact, name='contact'),
    
    # Legal
    path('privacy/', views.privacy_policy, name='privacy'),
    path('terms/', views.terms_of_service, name='terms'),
    
    # Posts
    path('post/<int:post_id>/', views.post_detail, name='post_detail'),
    path('post/<int:post_id>/like/', views.like_post, name='like_post'),
    path('post/<int:post_id>/bookmark/', views.bookmark_post, name='bookmark_post'),
    path('post/<int:post_id>/delete/', views.delete_post, name='delete_post'),
    path('post/<int:post_id>/comments/', views.load_more_comments, name='load_more_comments'),
    
    # Create/Edit Posts
    path('create/', views.create_post, name='create_post'),
    path('edit/<int:post_id>/', views.edit_post, name='edit_post'),
    
    # Profile
    path('profile/', views.profile_view, name='profile'),
    path('profile/<str:username>/', views.profile_view, name='profile_view'),
    path('profile/<str:username>/posts/', views.profile_posts, name='profile_posts'),
    path('edit-profile/', views.edit_profile, name='edit_profile'),
    
    # Interactions
    path('follow/<str:username>/', views.follow_user, name='follow_user'),
    path('repost/<int:post_id>/', views.repost_post, name='repost_post'),
    path('comment/<int:comment_id>/like/', views.like_comment, name='like_comment'),
    path('comment/<int:comment_id>/delete/', views.delete_comment, name='delete_comment'),
    
    # User Lists
    path('bookmarks/', views.bookmarks, name='bookmarks'),
    path('notifications/', views.notifications, name='notifications'),
    path('notifications/count/', views.notifications_count, name='notifications_count'),
    path('activity-feed/', views.activity_feed, name='activity_feed'),
    
    # Search
    path('search/', views.search, name='search'),
    path('search/suggestions/', views.search_suggestions, name='search_suggestions'),
    
    # Categories
    path('category/<slug:category_slug>/', views.category_view, name='category_view'),
    
    # API Endpoints
    path('api/users/<str:username>/following/', views.api_following, name='api_following'),
    path('api/users/<str:username>/followers/', views.api_followers, name='api_followers'),
    path('api/check-new-news/', views.check_new_news, name='check_new_news'),
    path('api/fetch-news/', views.api_fetch_news, name='api_fetch_news'),
    path('api/news-feed/', views.api_news_feed, name='api_news_feed'),
    path('api/news/<int:post_id>/', views.api_news_detail, name='api_news_detail'),
    path('api/banners/', views.api_banners, name='api_banners'),
    path('api/track-ad-impression/<str:ad_id>/', views.api_track_ad_impression, name='api_track_ad_impression'),
    path('api/track-ad-click/<str:ad_id>/', views.api_track_ad_click, name='api_track_ad_click'),
    path('api/track-share/<int:post_id>/', views.track_share, name='track_share'),
    path('api/toggle-dark-mode/', views.toggle_dark_mode, name='toggle_dark_mode'),
    path('api/get-modal-messages/', views.get_modal_messages, name='get_modal_messages'),
    
    # Admin URLs
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('admin-posts/', views.admin_posts, name='admin_posts'),
    path('admin-system-settings/', views.admin_system_settings, name='admin_system_settings'),
    path('admin-news-submissions/', views.admin_news_submissions, name='admin_news_submissions'),
    path('admin-auto-fetched-news/', views.admin_auto_fetched_news, name='admin_auto_fetched_news'),
    path('admin-news/<int:post_id>/', views.admin_news_detail, name='admin_news_detail'),
    path('admin-bulk-news-action/', views.admin_bulk_news_action, name='admin_bulk_news_action'),
    
    # Fetch News
    path('fetch-news/', views.fetch_news, name='fetch_news'),
    path('fetch-news-status/', views.fetch_news_status, name='fetch_news_status'),
    path('quick-fetch-news/', views.quick_fetch_news, name='quick_fetch_news'),
    path('get-fetcher-status/', views.get_fetcher_status, name='get_fetcher_status'),
    path('save-fetcher-settings/', views.save_fetcher_settings, name='save_fetcher_settings'),
    path('toggle-auto-fetcher/', views.toggle_auto_fetcher, name='toggle_auto_fetcher'),
    path('trigger-manual-fetch/', views.trigger_manual_fetch, name='trigger_manual_fetch'),
    path('get-fetch-logs/', views.get_fetch_logs, name='get_fetch_logs'),
    path('clear-fetch-logs/', views.clear_fetch_logs, name='clear_fetch_logs'),
    path('get-fetch-schedule/', views.get_fetch_schedule, name='get_fetch_schedule'),
    path('add-scheduled-fetch/', views.add_scheduled_fetch, name='add_scheduled_fetch'),
    path('clear-fetch-schedule/', views.clear_fetch_schedule, name='clear_fetch_schedule'),
    path('get-fetch-statistics/', views.get_fetch_statistics, name='get_fetch_statistics'),
    
    # Business & Advertising
    path('business-registration/', views.business_registration, name='business_registration'),
    path('ad-submission/', views.ad_submission, name='ad_submission'),
    path('ad-manage/', views.ad_manage, name='ad_manage'),
    path('ad/<str:uuid>/', views.ad_detail, name='ad_detail'),
    path('ad-credits/', views.ad_credits, name='ad_credits'),
    
    # Profile Picture Upload
    path('update-profile-pic/', views.update_profile_pic, name='update_profile_pic'),
    path('update-cover-photo/', views.update_cover_photo, name='update_cover_photo'),
    
    # Newsletter
    path('newsletter-signup/', views.newsletter_signup, name='newsletter_signup'),
    
    # Test
    path('test-ajax/', views.test_ajax, name='test_ajax'),
]