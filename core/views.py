# core/views.py (Complete Updated Version)

import requests
import json
import re
import logging
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, authenticate
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib import messages
from django.conf import settings
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.core.paginator import Paginator
from django.db.models import Q, Count, Sum, F, Avg, Prefetch
from django.utils import timezone
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_GET, require_http_methods
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import logout as auth_logout
from django.core.cache import cache
from django.template.loader import render_to_string

from .models import (
    Post, Category, Comment, UserProfile, Notification, 
    UserActivity, Follow, Advertisement, Repost, SystemSettings, 
    AdAnalytics, Group, GroupMember, GroupPost, FetchLog, FetchSchedule 
)
from .forms import (
    PostForm, CommentForm, UserProfileForm, UserUpdateForm, 
    BusinessProfileForm, GroupForm, SystemSettingsForm, 
    RegistrationForm, AdSubmissionForm
)
from .news_fetcher_unified import UnifiedNewsFetcher
from .news_verifier import EnhancedNewsVerifier
from .autostart import auto_fetcher

logger = logging.getLogger(__name__)

# ==================== API ENDPOINTS ====================
@login_required
def api_following(request, username):
    """API endpoint to get users that a user is following"""
    try:
        user = User.objects.get(username=username)
        
        # Check if the requesting user has permission to see this list
        if user != request.user and not request.user.is_staff:
            return JsonResponse({'error': 'Permission denied'}, status=403)
        
        following = Follow.objects.filter(
            follower=user
        ).select_related('following', 'following__profile').order_by('-created_at')
        
        users_list = []
        for follow in following:
            followed_user = follow.following
            # Check if profile exists
            profile_pic_url = None
            if hasattr(followed_user, 'profile') and followed_user.profile.profile_pic:
                profile_pic_url = followed_user.profile.profile_pic.url
            
            users_list.append({
                'id': followed_user.id,
                'username': followed_user.username,
                'full_name': followed_user.get_full_name(),
                'avatar': profile_pic_url,
                'bio': followed_user.profile.bio[:100] if hasattr(followed_user, 'profile') and followed_user.profile.bio else '',
                'posts_count': Post.objects.filter(author=followed_user, status='published').count(),
                'followers_count': Follow.objects.filter(following=followed_user).count(),
                'is_following': Follow.objects.filter(follower=request.user, following=followed_user).exists(),
            })
        
        return JsonResponse({'users': users_list})
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)

@login_required
def api_followers(request, username):
    """API endpoint to get users that follow a user"""
    try:
        user = User.objects.get(username=username)
        
        # Check if the requesting user has permission to see this list
        if user != request.user and not request.user.is_staff:
            return JsonResponse({'error': 'Permission denied'}, status=403)
        
        followers = Follow.objects.filter(
            following=user
        ).select_related('follower', 'follower__profile').order_by('-created_at')
        
        users_list = []
        for follow in followers:
            follower_user = follow.follower
            # Check if profile exists
            profile_pic_url = None
            if hasattr(follower_user, 'profile') and follower_user.profile.profile_pic:
                profile_pic_url = follower_user.profile.profile_pic.url
            
            users_list.append({
                'id': follower_user.id,
                'username': follower_user.username,
                'full_name': follower_user.get_full_name(),
                'avatar': profile_pic_url,
                'bio': follower_user.profile.bio[:100] if hasattr(follower_user, 'profile') and follower_user.profile.bio else '',
                'posts_count': Post.objects.filter(author=follower_user, status='published').count(),
                'followers_count': Follow.objects.filter(following=follower_user).count(),
                'is_following': Follow.objects.filter(follower=request.user, following=follower_user).exists(),
            })
        
        return JsonResponse({'users': users_list})
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)
    
    
@require_GET
def check_new_news(request):
    """Check if there are new news articles since last check"""
    last_check_str = request.GET.get('last_check')
    
    try:
        if last_check_str:
            last_check = datetime.fromisoformat(last_check_str.replace('Z', '+00:00'))
        else:
            last_check = timezone.now() - timezone.timedelta(minutes=5)
    except (ValueError, TypeError):
        last_check = timezone.now() - timezone.timedelta(minutes=5)
    
    # Count new auto-fetched news since last check
    new_count = Post.objects.filter(
        is_auto_fetched=True,
        published_at__gt=last_check,
        status='published'
    ).count()
    
    return JsonResponse({
        'has_new': new_count > 0,
        'count': new_count,
        'last_check': timezone.now().isoformat()
    })


@csrf_exempt
@require_POST
def api_fetch_news(request):
    """API endpoint to trigger news fetching"""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    fetcher = NewsFetcher()
    saved_count = fetcher.fetch_all_news()
    
    return JsonResponse({
        'success': True,
        'count': saved_count,
        'message': f'Fetched {saved_count} new articles'
    })


@require_GET
def api_news_feed(request):
    """API endpoint for infinite scroll news feed"""
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 20))
    filter_type = request.GET.get('filter', 'latest')
    category = request.GET.get('category', 'all')
    source = request.GET.get('source', '')
    has_media = request.GET.get('has_media', '')
    
    # Build queryset
    news_posts = Post.objects.filter(
        status='published',
        post_type__in=['news', 'user_news']
    ).select_related('category', 'author').prefetch_related('likes')
    
    # Apply filters
    if category != 'all':
        news_posts = news_posts.filter(category__slug=category)
    
    if source:
        news_posts = news_posts.filter(external_source__icontains=source)
    
    if has_media == 'video':
        news_posts = news_posts.filter(has_media=True).exclude(video_urls=None)
    elif has_media == 'audio':
        news_posts = news_posts.filter(has_media=True).exclude(audio_urls=None)
    elif has_media == 'any':
        news_posts = news_posts.filter(has_media=True)
    
    # Apply sorting
    if filter_type == 'trending':
        news_posts = news_posts.filter(
            created_at__gte=timezone.now() - timedelta(days=2)
        ).annotate(
            like_count=Count('likes', distinct=True),
            comment_count=Count('comments', filter=Q(comments__is_active=True), distinct=True)
        ).annotate(
            engagement=F('like_count') + F('comment_count') * 2 + F('views') / 100
        ).order_by('-engagement', '-published_at')
    elif filter_type == 'popular':
        news_posts = news_posts.order_by('-views', '-published_at')
    elif filter_type == 'verified':
        news_posts = news_posts.filter(verification_status='verified').order_by('-published_at')
    else:
        news_posts = news_posts.order_by('-published_at')
    
    # Paginate
    paginator = Paginator(news_posts, page_size)
    current_page = paginator.get_page(page)
    
    # Format data
    data = {
        'posts': [],
        'has_next': current_page.has_next(),
        'next_page': current_page.next_page_number() if current_page.has_next() else None,
        'total': paginator.count,
        'current_page': page,
    }
    
    for post in current_page:
        # Get media info
        media_info = get_post_media_info(post)
        
        post_data = {
            'id': post.id,
            'title': post.title,
            'excerpt': post.content[:200] + '...' if len(post.content) > 200 else post.content,
            'image_url': post.image.url if post.image else post.image_url,
            'published_at': post.published_at.isoformat(),
            'source': post.external_source or 'Ojukaye',
            'category': post.category.name if post.category else 'News',
            'author': post.author.username,
            'views': post.views,
            'likes': post.likes.count(),
            'comments': post.comments_count,
            'has_media': post.has_media,
            'has_video': media_info['has_video'],
            'has_audio': media_info['has_audio'],
            'url': post.get_absolute_url(),
            'verification_status': post.verification_status,
            'verification_score': post.verification_score,
        }
        data['posts'].append(post_data)
    
    return JsonResponse(data)


@require_GET
def api_news_detail(request, post_id):
    """API endpoint for news detail (AJAX loading)"""
    post = get_object_or_404(Post, id=post_id, status='published')
    
    # Check permissions
    if not can_view_post(request.user, post):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    # Process media
    processed_media = process_post_media(post)
    
    # Get verification info
    verification_info = get_verification_info(post)
    
    data = {
        'id': post.id,
        'title': post.title,
        'content': post.content,
        'image_url': post.image.url if post.image else post.image_url,
        'published_at': post.published_at.isoformat(),
        'source': post.external_source or 'Ojukaye',
        'author': {
            'username': post.author.username,
            'profile_url': post.author.profile.get_absolute_url() if hasattr(post.author, 'profile') else '#',
        },
        'views': post.views,
        'likes': post.likes.count(),
        'comments': post.comments_count,
        'media': processed_media,
        'verification': verification_info,
        'url': post.get_absolute_url(),
    }
    
    return JsonResponse(data)


@require_GET
def api_banners(request):
    """API endpoint for banner ads and featured content"""
    banners = Post.objects.filter(
        is_banner=True,
        status='published',
    ).order_by('-banner_priority', '?')[:10]
    
    # Get active banner ads
    banner_ads = Advertisement.objects.filter(
        ad_type='banner',
        status='approved',
        is_active=True,
        start_date__lte=timezone.now(),
        end_date__gte=timezone.now()
    ).select_related('business').order_by('?')[:5]
    
    data = {
        'banners': [],
        'ads': [],
        'timestamp': timezone.now().isoformat()
    }
    
    for banner in banners:
        data['banners'].append({
            'id': banner.id,
            'title': banner.title,
            'image_url': banner.image.url if banner.image else banner.image_url,
            'url': banner.get_absolute_url(),
            'type': 'content',
            'priority': banner.banner_priority,
            'category': banner.category.name if banner.category else 'Featured',
            'excerpt': banner.content[:120] if banner.content else ''
        })
    
    for ad in banner_ads:
        data['ads'].append({
            'id': str(ad.uuid),
            'title': ad.title,
            'image_url': ad.image.url if ad.image else ad.image_url,
            'target_url': ad.target_url,
            'type': 'advertisement',
            'business': ad.business.username,
            'description': ad.description
        })
    
    return JsonResponse(data)


@require_POST
def api_track_ad_impression(request, ad_id):
    """Track ad impression"""
    try:
        ad = Advertisement.objects.get(uuid=ad_id)
        AdAnalytics.objects.create(
            advertisement=ad,
            date=timezone.now().date(),
            impressions=1,
            clicks=0,
            cost=ad.cost_per_impression if ad.cost_per_impression else 0
        )
        return JsonResponse({'success': True})
    except Advertisement.DoesNotExist:
        return JsonResponse({'error': 'Ad not found'}, status=404)


@require_POST
def api_track_ad_click(request, ad_id):
    """Track ad click"""
    try:
        ad = Advertisement.objects.get(uuid=ad_id)
        AdAnalytics.objects.create(
            advertisement=ad,
            date=timezone.now().date(),
            impressions=0,
            clicks=1,
            cost=ad.cost_per_click if ad.cost_per_click else 0
        )
        return JsonResponse({'success': True})
    except Advertisement.DoesNotExist:
        return JsonResponse({'error': 'Ad not found'}, status=404)


# ==================== HOME PAGE ====================
def dynamic_home(request):
    """
    Dynamic homepage:
    - If user is logged in -> show personal homepage
    - If user is logged out -> show online news
    """
    if request.user.is_authenticated:
        # User is logged in - show personal homepage
        return home(request)  # Call your existing home view
    else:
        # User is logged out - show online news
        return online_news(request)



@login_required
def home(request):
    """Personal user homepage - shows user's own posts and activities"""

    # Debug: Check if posts exist
    all_user_posts = Post.objects.filter(
        author=request.user,
        status='published'
    ).count()
    print(f"DEBUG: User has {all_user_posts} published posts")
    
    # Get user's own posts
    user_posts = Post.objects.filter(
        author=request.user,
        status='published'
    ).select_related('category').order_by('-published_at')[:20]
    
    # Debug: Print each post
    for post in user_posts:
        print(f"DEBUG: Post ID: {post.id}, Title: {post.title}, Status: {post.status}")
        
    # Get user's own posts
    user_posts = Post.objects.filter(
        author=request.user,
        status='published'
    ).select_related('category').order_by('-published_at')[:20]
    
    # Get posts from people the user follows (for feed)
    following_ids = list(Follow.objects.filter(
        follower=request.user
    ).values_list('following_id', flat=True))
    
    # Get public posts and follower-only posts from followed users
    feed_posts = Post.objects.none()
    if following_ids:
        feed_posts = Post.objects.filter(
            status='published',
            author_id__in=following_ids
        ).filter(
            Q(privacy='public') | 
            Q(privacy='followers') |
            Q(privacy='specific', allowed_viewers=request.user)
        ).exclude(
            author=request.user
        ).select_related('author', 'category').order_by('-published_at')[:20]
    
    # Get posts the user has interacted with
    interacted_posts = get_interacted_posts(request.user)
    
    # Get user's recent activities
    recent_activities = UserActivity.objects.filter(
        user=request.user
    ).select_related('post', 'comment', 'target_user').order_by('-created_at')[:20]
    
    # Get suggested users
    suggested_users = get_suggested_users(request.user, following_ids)
    
    # Get following preview (first 5)
    following_preview = Follow.objects.filter(
        follower=request.user
    ).select_related('following', 'following__profile').order_by('-created_at')[:5]
    
    # Get followers preview (first 5)
    followers_preview = Follow.objects.filter(
        following=request.user
    ).select_related('follower', 'follower__profile').order_by('-created_at')[:5]
    
    # Get user stats
    user_stats = get_user_stats(request.user)
    
    # Get unread notifications count
    unread_notifications_count = Notification.objects.filter(
        user=request.user,
        is_read=False
    ).count()
    
    # Get trending topics for sidebar
    trending_topics = get_trending_topics()
    
    context = {
        'user_posts': user_posts,
        'feed_posts': feed_posts,
        'interacted_posts': interacted_posts,
        'recent_activities': recent_activities,
        'suggested_users': suggested_users,
        'following_preview': following_preview,
        'followers_preview': followers_preview,
        'user_stats': user_stats,
        'unread_notifications_count': unread_notifications_count,
        'trending_topics': trending_topics,
        'title': f"{request.user.username}'s Home",
    }
    
    return render(request, 'index.html', context)

def get_interacted_posts(user):
    """Get posts user has interacted with"""
    interacted_posts_ids = set()
    
    # Liked posts
    liked_posts_ids = list(Post.objects.filter(
        likes=user,
        status='published'
    ).values_list('id', flat=True)[:20])
    interacted_posts_ids.update(liked_posts_ids)
    
    # Commented posts
    commented_posts_ids = list(Post.objects.filter(
        comments__user=user,
        status='published'
    ).distinct().values_list('id', flat=True)[:20])
    interacted_posts_ids.update(commented_posts_ids)
    
    # Reposted posts
    reposted_posts_ids = list(Post.objects.filter(
        repost_instances__user=user,
        status='published'
    ).values_list('id', flat=True)[:20])
    interacted_posts_ids.update(reposted_posts_ids)
    
    # Get interacted posts with interaction flags
    interacted_posts = []
    if interacted_posts_ids:
        interacted_id_list = list(interacted_posts_ids)[:20]
        
        posts_qs = Post.objects.filter(
            id__in=interacted_id_list,
            status='published'
        ).select_related('author', 'category').order_by('-published_at')
        
        liked_set = set(liked_posts_ids)
        commented_set = set(commented_posts_ids)
        reposted_set = set(reposted_posts_ids)
        
        for post in posts_qs:
            post_data = {
                'post': post,
                'user_liked': post.id in liked_set,
                'user_commented': post.id in commented_set,
                'user_reposted': post.id in reposted_set,
            }
            interacted_posts.append(post_data)
    
    return interacted_posts


def get_suggested_users(current_user, following_ids, limit=5):
    """Get suggested users to follow"""
    suggested_users = []
    
    # Users with posts
    users_with_posts = User.objects.exclude(
        Q(id=current_user.id) | Q(id__in=following_ids)
    ).filter(
        is_active=True,
        posts__isnull=False
    ).annotate(
        posts_count=Count('posts')
    ).order_by('-posts_count')[:10]
    
    for user in users_with_posts:
        if len(suggested_users) < limit:
            suggested_users.append(user)
    
    # Random active users if not enough
    if len(suggested_users) < limit:
        suggested_ids = [u.id for u in suggested_users]
        
        additional_users = User.objects.exclude(
            Q(id=current_user.id) | 
            Q(id__in=following_ids) | 
            Q(id__in=suggested_ids)
        ).filter(
            is_active=True
        ).order_by('?')[:limit - len(suggested_users)]
        
        suggested_users.extend(additional_users)
    
    return suggested_users


def get_user_stats(user):
    """Get user statistics"""
    return {
        'total_posts': Post.objects.filter(author=user, status='published').count(),
        'total_likes_given': Post.objects.filter(likes=user, status='published').count(),
        'total_comments': Comment.objects.filter(user=user, is_active=True).count(),
        'total_reposts': Repost.objects.filter(user=user).count(),
        'followers_count': Follow.objects.filter(following=user).count(),
        'following_count': Follow.objects.filter(follower=user).count(),
    }

    
# ==================== ONLINE NEWS PAGE ====================

def online_news(request):
    """Enhanced news page with better filtering, media support and fetcher integration"""
    # Get filter parameters
    filter_type = request.GET.get('filter', 'latest')
    category_slug = request.GET.get('category', 'all')
    search_query = request.GET.get('q', '')
    source = request.GET.get('source', '')
    has_media = request.GET.get('has_media', '')
    time_range = request.GET.get('time', '')
    verification = request.GET.get('verification', 'all')  # all, verified, pending, fake
    
    # Base queryset - Only news posts
    news_posts = Post.objects.filter(
        status='published',
        post_type__in=['news', 'user_news']
    ).select_related('author', 'category').prefetch_related(
        Prefetch('likes', queryset=User.objects.only('id')),
        Prefetch('comments', queryset=Comment.objects.filter(is_active=True).only('id'))
    )
    
    # Auto-fetch if news count is low (staff only, rate limited)
    auto_fetch_if_needed(request, news_posts)
    
    # Apply filters
    news_posts = apply_news_filters(
        news_posts, filter_type, category_slug, 
        search_query, source, has_media, time_range, verification
    )
    
    # Get banner posts (featured news)
    banner_posts = get_banner_posts()
    
    # Get sponsored content
    sponsored_posts = get_sponsored_content()
    
    # Get sidebar data
    sidebar_data = get_news_sidebar_data()
    
    # Get fetcher stats for staff
    fetcher_stats = None
    if request.user.is_staff:
        fetcher_stats = get_fetcher_stats()
    
    # Pagination
    paginator = Paginator(news_posts, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # Add media info and verification badges to each post
    for post in page_obj:
        media_info = get_post_media_info(post)
        post.has_video = media_info['has_video']
        post.has_audio = media_info['has_audio']
        post.media_count = media_info['media_count']
        post.verification_badge = get_verification_badge(post)
        post.media_preview = get_media_preview(post)
    
    # Get trending topics
    trending_topics = get_trending_topics()
    
    context = {
        'posts': page_obj,
        'page_obj': page_obj,
        'categories': sidebar_data['categories'],
        'top_sources': sidebar_data['top_sources'],
        'trending_news': sidebar_data['trending_news'],
        'breaking_news': sidebar_data['breaking_news'],
        'banner_posts': banner_posts,
        'sponsored_posts': sponsored_posts,
        'filter_type': filter_type,
        'current_category': category_slug,
        'search_query': search_query,
        'selected_source': source,
        'has_media_filter': has_media,
        'time_range': time_range,
        'verification_filter': verification,
        'total_users': sidebar_data['total_users'],
        'total_news': sidebar_data['total_news'],
        'total_comments': sidebar_data['total_comments'],
        'verified_count': sidebar_data['verified_count'],
        'trending_topics': trending_topics,
        'fetcher_stats': fetcher_stats,
        'title': 'Online News',
        'today_count': Post.objects.filter(
            status='published',
            post_type__in=['news', 'user_news'],
            published_at__date=timezone.now().date()
        ).count(),
        'media_count': Post.objects.filter(
            status='published',
            post_type__in=['news', 'user_news'],
            has_media=True
        ).count(),
    }
    
    return render(request, 'online_news.html', context)


def auto_fetch_if_needed(request, news_posts):
    """Auto-fetch news if count is low (staff only, rate limited)"""
    # Only fetch if there are very few news items and user is staff
    if request.user.is_staff and news_posts.filter(is_auto_fetched=True).count() < 20:
        cache_key = 'last_news_fetch'
        last_fetch = cache.get(cache_key)
        
        if not last_fetch or (timezone.now() - last_fetch) > timedelta(minutes=15):
            try:
                # Use ThreadPoolExecutor to not block the request
                import threading
                def fetch_async():
                    from .news_fetcher import NewsFetcher
                    fetcher = NewsFetcher()
                    saved = fetcher.fetch_all_news()
                    logger.info(f"Auto-fetched {saved} news articles")
                
                thread = threading.Thread(target=fetch_async)
                thread.daemon = True
                thread.start()
                
                cache.set(cache_key, timezone.now(), 900)  # 15 minutes
                
            except Exception as e:
                logger.error(f"Auto-fetch failed: {e}")


def get_fetcher_stats():
    """Get statistics about fetched news"""
    cache_key = 'fetcher_stats'
    stats = cache.get(cache_key)
    
    if stats is None:
        stats = {
            'total_fetched': Post.objects.filter(is_auto_fetched=True).count(),
            'last_24h': Post.objects.filter(
                is_auto_fetched=True,
                created_at__gte=timezone.now() - timedelta(hours=24)
            ).count(),
            'with_media': Post.objects.filter(
                is_auto_fetched=True,
                has_media=True
            ).count(),
            'verified': Post.objects.filter(
                is_auto_fetched=True,
                verification_status='verified'
            ).count(),
            'pending': Post.objects.filter(
                is_auto_fetched=True,
                verification_status='pending'
            ).count(),
            'sources': list(Post.objects.filter(
                is_auto_fetched=True
            ).exclude(
                external_source__isnull=True
            ).exclude(
                external_source=''
            ).values('external_source').annotate(
                count=Count('id')
            ).order_by('-count')[:5]),
        }
        cache.set(cache_key, stats, 3600)  # 1 hour
    
    return stats


def get_media_preview(post):
    """Get media preview information for post cards"""
    preview = {
        'type': None,
        'thumbnail': None,
        'duration': None
    }
    
    # Check for video
    if post.video_urls:
        try:
            videos = post.video_urls if isinstance(post.video_urls, list) else json.loads(post.video_urls)
            if videos and isinstance(videos, list) and len(videos) > 0:
                first_video = videos[0]
                video_url = first_video.get('url', '') if isinstance(first_video, dict) else first_video
                
                # YouTube thumbnail
                if 'youtube' in str(video_url) or 'youtu.be' in str(video_url):
                    video_id = extract_youtube_id(video_url)
                    if video_id:
                        preview['type'] = 'youtube'
                        preview['thumbnail'] = f'https://img.youtube.com/vi/{video_id}/mqdefault.jpg'
                        preview['video_id'] = video_id
                # Vimeo thumbnail (would need additional API call)
                elif 'vimeo' in str(video_url):
                    preview['type'] = 'vimeo'
        except Exception as e:
            logger.error(f"Error processing video preview: {e}")
            pass
    
    # Check for audio (Spotify, SoundCloud)
    elif post.audio_urls:
        try:
            audios = post.audio_urls if isinstance(post.audio_urls, list) else json.loads(post.audio_urls)
            if audios and isinstance(audios, list) and len(audios) > 0:
                first_audio = audios[0]
                audio_url = first_audio.get('url', '') if isinstance(first_audio, dict) else first_audio
                
                if 'spotify' in str(audio_url):
                    preview['type'] = 'spotify'
                elif 'soundcloud' in str(audio_url):
                    preview['type'] = 'soundcloud'
        except Exception as e:
            logger.error(f"Error processing audio preview: {e}")
            pass
    
    return preview


def extract_youtube_id(url):
    """Extract YouTube video ID from URL"""
    if not url:
        return None
    
    patterns = [
        r'youtube\.com/watch\?v=([a-zA-Z0-9_-]+)',
        r'youtu\.be/([a-zA-Z0-9_-]+)',
        r'youtube\.com/embed/([a-zA-Z0-9_-]+)',
        r'youtube\.com/v/([a-zA-Z0-9_-]+)'
    ]
    for pattern in patterns:
        match = re.search(pattern, str(url))
        if match:
            return match.group(1)
    return None


def apply_news_filters(queryset, filter_type, category_slug, search_query, 
                       source, has_media, time_range, verification):
    """Apply all filters to news queryset"""
    
    # Category filter
    if category_slug != 'all':
        try:
            category = Category.objects.get(slug=category_slug)
            queryset = queryset.filter(category=category)
        except Category.DoesNotExist:
            pass
    
    # Search filter
    if search_query:
        queryset = queryset.filter(
            Q(title__icontains=search_query) |
            Q(content__icontains=search_query) |
            Q(external_source__icontains=search_query)
        )
    
    # Source filter
    if source:
        queryset = queryset.filter(external_source__icontains=source)
    
    # Media filter
    if has_media == 'video':
        queryset = queryset.filter(has_media=True).exclude(video_urls__isnull=True).exclude(video_urls='[]')
    elif has_media == 'audio':
        queryset = queryset.filter(has_media=True).exclude(audio_urls__isnull=True).exclude(audio_urls='[]')
    elif has_media == 'any':
        queryset = queryset.filter(has_media=True)
    
    # Verification filter
    if verification != 'all':
        queryset = queryset.filter(verification_status=verification)
    
    # Time range filter
    now = timezone.now()
    if time_range == 'today':
        queryset = queryset.filter(published_at__date=now.date())
    elif time_range == 'week':
        queryset = queryset.filter(published_at__gte=now - timedelta(days=7))
    elif time_range == 'month':
        queryset = queryset.filter(published_at__gte=now - timedelta(days=30))
    elif time_range == 'year':
        queryset = queryset.filter(published_at__gte=now - timedelta(days=365))
    
    # Sorting
    if filter_type == 'trending':
        time_threshold = now - timedelta(hours=48)
        queryset = queryset.filter(
            created_at__gte=time_threshold
        ).annotate(
            like_count=Count('likes', distinct=True),
            comment_count_val=Count('comments', filter=Q(comments__is_active=True), distinct=True)
        ).annotate(
            engagement=F('like_count') + F('comment_count_val') * 2 + F('views') / 100
        ).order_by('-engagement', '-published_at')
    elif filter_type == 'popular':
        queryset = queryset.order_by('-views', '-published_at')
    elif filter_type == 'verified':
        queryset = queryset.filter(verification_status='verified').order_by('-published_at')
    else:  # latest
        queryset = queryset.order_by('-published_at')
    
    return queryset


def get_banner_posts():
    """Get banner/featured posts with caching"""
    cache_key = 'banner_posts'
    banner_posts = cache.get(cache_key)
    
    if banner_posts is None:
        # Get featured posts
        banner_posts = list(Post.objects.filter(
            status='published',
            is_featured=True,
            post_type__in=['news', 'user_news']
        ).select_related('category')[:4])
        
        # If not enough, add trending ones
        if len(banner_posts) < 4:
            trending = Post.objects.filter(
                status='published',
                post_type__in=['news', 'user_news'],
                created_at__gte=timezone.now() - timedelta(days=7)
            ).annotate(
                like_count=Count('likes'),
                comment_count=Count('comments', filter=Q(comments__is_active=True))
            ).annotate(
                engagement=F('like_count') + F('comment_count') * 2 + F('views') / 100
            ).order_by('-engagement')[:4 - len(banner_posts)]
            
            banner_posts.extend(list(trending))
        
        # Cache for 1 hour
        cache.set(cache_key, banner_posts, 3600)
    
    return banner_posts


def get_sponsored_content():
    """Get sponsored posts and ads"""
    cache_key = 'sponsored_content'
    sponsored = cache.get(cache_key)
    
    if sponsored is None:
        sponsored_posts = list(Post.objects.filter(
            is_sponsored=True,
            status='published',
            post_type__in=['news', 'user_news', 'sponsored']
        ).select_related('author').order_by('?')[:3])
        
        active_ads = list(Advertisement.objects.filter(
            status='approved',
            is_active=True,
            start_date__lte=timezone.now(),
            end_date__gte=timezone.now()
        ).select_related('business').order_by('?')[:3])
        
        sponsored = sponsored_posts + active_ads
        cache.set(cache_key, sponsored, 1800)  # 30 minutes
    
    return sponsored


def get_news_sidebar_data():
    """Get all sidebar data with caching"""
    cache_key = 'news_sidebar'
    data = cache.get(cache_key)
    
    if data is None:
        now = timezone.now()
        week_ago = now - timedelta(days=7)
        
        # FIXED: Changed all 'post' to 'posts'
        categories = Category.objects.filter(
            posts__status='published',  # ← FIXED: 'posts' not 'post'
            posts__post_type__in=['news', 'user_news']
        ).annotate(
            news_count=Count('posts', filter=Q(  # ← FIXED: 'posts' not 'post'
                posts__status='published',  # ← FIXED: 'posts' not 'post'
                posts__post_type__in=['news', 'user_news']
            ))
        ).filter(news_count__gt=0).distinct().order_by('-news_count')[:10]
        
        # Top sources (this is correct - querying Post directly)
        top_sources = Post.objects.filter(
            post_type__in=['news', 'user_news'],
            status='published'
        ).exclude(
            external_source__isnull=True
        ).exclude(
            external_source=''
        ).values('external_source').annotate(
            count=Count('id')
        ).order_by('-count')[:10]
        
        # Clean source names
        for source in top_sources:
            if source['external_source']:
                source['external_source'] = source['external_source'].replace('NewsAPI:', '').replace('NewsAPI', '').strip()
        
        # Trending news (this is correct - querying Post directly)
        trending_news = Post.objects.filter(
            status='published',
            post_type__in=['news', 'user_news'],
            created_at__gte=week_ago
        ).annotate(
            like_count=Count('likes', distinct=True),
            comment_count=Count('comments', filter=Q(comments__is_active=True), distinct=True)
        ).annotate(
            engagement=F('like_count') + F('comment_count') * 2 + F('views') / 100
        ).order_by('-engagement')[:5]
        
        # Breaking news (this is correct - querying Post directly)
        breaking_news = Post.objects.filter(
            is_banner=True,
            status='published',
            post_type__in=['news', 'user_news']
        ).order_by('-published_at')[:3]
        
        # Stats (all correct - querying Post directly)
        total_users = User.objects.filter(is_active=True).count()
        total_news = Post.objects.filter(
            status='published',
            post_type__in=['news', 'user_news']
        ).count()
        total_comments = Comment.objects.filter(is_active=True).count()
        verified_count = Post.objects.filter(
            status='published',
            verification_status='verified',
            post_type__in=['news', 'user_news']
        ).count()
        
        # Trending topics
        trending_topics = get_trending_topics()
        
        data = {
            'categories': categories,
            'top_sources': top_sources,
            'trending_news': trending_news,
            'breaking_news': breaking_news,
            'total_users': total_users,
            'total_news': total_news,
            'total_comments': total_comments,
            'verified_count': verified_count,
            'trending_topics': trending_topics,
        }
        
        cache.set(cache_key, data, 1800)  # 30 minutes
    
    return data


def get_post_media_info(post):
    """Get media information for a post"""
    has_video = False
    has_audio = False
    
    if post.video_urls:
        try:
            videos = post.video_urls if isinstance(post.video_urls, list) else json.loads(post.video_urls)
            has_video = bool(videos and len(videos) > 0)
        except:
            has_video = bool(post.video_urls)
    
    if post.audio_urls:
        try:
            audios = post.audio_urls if isinstance(post.audio_urls, list) else json.loads(post.audio_urls)
            has_audio = bool(audios and len(audios) > 0)
        except:
            has_audio = bool(post.audio_urls)
    
    media_count = (1 if has_video else 0) + (1 if has_audio else 0)
    
    return {
        'has_video': has_video,
        'has_audio': has_audio,
        'media_count': media_count,
    }


def get_verification_badge(post):
    """Get verification badge type"""
    if post.verification_status == 'verified':
        return 'verified'
    elif post.verification_score and post.verification_score > 0.7:
        return 'trusted'
    return None


def get_trending_topics(limit=5):
    """Get trending topics from recent posts with caching"""
    cache_key = 'trending_topics'
    topics = cache.get(cache_key)
    
    if topics is None:
        recent_posts = Post.objects.filter(
            status='published',
            created_at__gte=timezone.now() - timedelta(days=2)
        ).order_by('-views')[:50]
        
        # Extract common words from titles
        words = {}
        stop_words = {'the', 'and', 'for', 'with', 'this', 'that', 'from', 
                     'have', 'were', 'has', 'had', 'will', 'are', 'was', 'been',
                     'what', 'when', 'where', 'who', 'why', 'how', 'all', 'one',
                     'would', 'could', 'should', 'their', 'they', 'them', 'our'}
        
        for post in recent_posts:
            if post.title:
                title_words = post.title.lower().split()
                for word in title_words:
                    word = word.strip('.,!?()[]{}:;"\'')
                    if len(word) > 3 and word not in stop_words and not word.isdigit():
                        words[word] = words.get(word, 0) + 1
        
        # Sort by frequency
        trending = sorted(words.items(), key=lambda x: x[1], reverse=True)[:limit]
        topics = [{'topic': word, 'count': count} for word, count in trending]
        
        cache.set(cache_key, topics, 3600)  # 1 hour
    
    return topics

# ==================== POST DETAIL PAGE (ENHANCED) ====================

# ==================== POST DETAIL PAGE (FULL CONTENT & MEDIA READY) ====================

def post_detail(request, post_id):
    """Enhanced post detail with full content, video/audio playback, and media support"""
    post = get_object_or_404(Post, id=post_id, status='published')
    
    # Check permissions
    if not can_view_post(request.user, post):
        messages.error(request, 'You do not have permission to view this post')
        return redirect('online_news' if post.post_type in ['news', 'user_news'] else 'home')
    
    # Increment view count (using F() to avoid race conditions)
    Post.objects.filter(id=post_id).update(views=F('views') + 1)
    post.refresh_from_db()
    
    # CRITICAL: Process media for display - this extracts all videos and audio
    processed_media = process_post_media_for_display(post)
    
    # Debug: Print what media we found
    print(f"DEBUG - Post {post_id}: {post.title}")
    print(f"DEBUG - Has video_urls: {bool(post.video_urls)}")
    print(f"DEBUG - Has audio_urls: {bool(post.audio_urls)}")
    print(f"DEBUG - Processed videos: {len(processed_media['videos'])}")
    print(f"DEBUG - Processed audios: {len(processed_media['audios'])}")
    
    # Get full verification details
    verification_info = get_verification_info(post)
    
    # Get comments with replies (optimized)
    comments = Comment.objects.filter(
        post=post, 
        parent__isnull=True, 
        is_active=True
    ).select_related(
        'user', 'user__profile'
    ).prefetch_related(
        Prefetch('replies', queryset=Comment.objects.filter(is_active=True).select_related('user', 'user__profile')),
        'likes'
    ).order_by('-created_at')
    
    # Check user interactions
    user_interactions = get_user_interactions(request.user, post)
    
    # Get related content
    related_content = get_related_content(post, request.user)
    
    # Get trending topics
    trending_topics = get_trending_topics()
    
    # Get categories for sidebar
    categories = Category.objects.filter(
        posts__status='published',
        posts__post_type__in=['news', 'user_news']
    ).annotate(
        news_count=Count('posts', filter=Q(
            posts__status='published',
            posts__post_type__in=['news', 'user_news']
        ))
    ).filter(news_count__gt=0).distinct().order_by('-news_count')[:10]
    
    # Get top sources
    top_sources = Post.objects.filter(
        post_type__in=['news', 'user_news'],
        status='published'
    ).exclude(
        external_source__isnull=True
    ).exclude(
        external_source=''
    ).values('external_source').annotate(
        count=Count('id')
    ).order_by('-count')[:10]
    
    # Get trending news
    trending_news = Post.objects.filter(
        status='published',
        post_type__in=['news', 'user_news'],
        created_at__gte=timezone.now() - timedelta(days=7)
    ).annotate(
        like_count=Count('likes', distinct=True),
        comment_count=Count('comments', filter=Q(comments__is_active=True), distinct=True)
    ).annotate(
        engagement=F('like_count') + F('comment_count') * 2 + F('views') / 100
    ).order_by('-engagement')[:5]
    
    # Handle comment submission
    if request.method == 'POST' and request.user.is_authenticated:
        return handle_comment_submission(request, post)
    
    # Format the full content properly
    full_content = post.content
    if full_content:
        # Ensure content is properly formatted for display
        full_content = full_content.replace('\n', '<br>')
    
    context = {
        'post': post,
        'full_content': full_content,  # Pass full content separately
        'processed_media': processed_media,  # This contains all videos/audio ready for display
        'verification_info': verification_info,
        'comments': comments,
        'related_posts': related_content['related_posts'],
        'trending_in_category': related_content['trending_in_category'],
        'trending_topics': trending_topics,
        'categories': categories,
        'top_sources': top_sources,
        'trending_news': trending_news,
        'user_interactions': user_interactions,
        'user_liked': user_interactions['liked'],
        'user_bookmarked': user_interactions['bookmarked'],
        'is_following': user_interactions['is_following'],
        'can_edit': request.user == post.author or request.user.is_staff,
        'title': post.title,
        'meta_description': post.meta_description or post.content[:160],
        'meta_image': post.image.url if post.image else post.image_url,
        'total_news': Post.objects.filter(status='published', post_type__in=['news', 'user_news']).count(),
    }
    
    return render(request, 'post/post_detail.html', context)


def process_post_media_for_display(post):
    """
    CRITICAL FUNCTION: Process post media for actual display in templates
    This ensures videos and audio are properly formatted for playback
    """
    media = {
        'videos': [],
        'audios': [],
        'images': [],
        'has_video': False,
        'has_audio': False,
        'video_count': 0,
        'audio_count': 0,
    }
    
    # Process video URLs - this is where the magic happens
    if post.video_urls:
        try:
            # Parse video URLs (could be string or list)
            video_urls = post.video_urls
            if isinstance(video_urls, str):
                if video_urls.startswith('[') or video_urls.startswith('{'):
                    video_urls = json.loads(video_urls)
                else:
                    # Simple string URL
                    video_urls = [{'url': video_urls, 'type': 'direct'}]
            
            # Handle different formats
            if isinstance(video_urls, list):
                for video in video_urls:
                    if isinstance(video, dict):
                        video_url = video.get('url', '')
                        video_type = video.get('type', '')
                    else:
                        video_url = str(video)
                        video_type = self._detect_video_type(video_url)
                    
                    if video_url:
                        processed_video = self._process_video_for_display(video_url, video_type, video if isinstance(video, dict) else {})
                        if processed_video:
                            media['videos'].append(processed_video)
            
            media['video_count'] = len(media['videos'])
            media['has_video'] = media['video_count'] > 0
            
        except Exception as e:
            print(f"DEBUG - Error processing video URLs: {e}")
            logger.error(f"Error processing video URLs: {e}")
    
    # Process audio URLs
    if post.audio_urls:
        try:
            # Parse audio URLs
            audio_urls = post.audio_urls
            if isinstance(audio_urls, str):
                if audio_urls.startswith('[') or audio_urls.startswith('{'):
                    audio_urls = json.loads(audio_urls)
                else:
                    audio_urls = [{'url': audio_urls, 'type': 'direct'}]
            
            if isinstance(audio_urls, list):
                for audio in audio_urls:
                    if isinstance(audio, dict):
                        audio_url = audio.get('url', '')
                        audio_type = audio.get('type', '')
                    else:
                        audio_url = str(audio)
                        audio_type = self._detect_audio_type(audio_url)
                    
                    if audio_url:
                        processed_audio = self._process_audio_for_display(audio_url, audio_type, audio if isinstance(audio, dict) else {})
                        if processed_audio:
                            media['audios'].append(processed_audio)
            
            media['audio_count'] = len(media['audios'])
            media['has_audio'] = media['audio_count'] > 0
            
        except Exception as e:
            print(f"DEBUG - Error processing audio URLs: {e}")
            logger.error(f"Error processing audio URLs: {e}")
    
    # Process images
    if post.image:
        media['images'].append({
            'url': post.image.url,
            'type': 'local',
            'title': post.title
        })
    
    if post.image_url and not post.image:
        media['images'].append({
            'url': post.image_url,
            'type': 'remote',
            'title': post.title
        })
    
    return media


def _detect_video_type(url):
    """Detect video platform from URL"""
    url_lower = url.lower()
    if 'youtube.com' in url_lower or 'youtu.be' in url_lower:
        return 'youtube'
    elif 'vimeo.com' in url_lower:
        return 'vimeo'
    elif 'dailymotion.com' in url_lower:
        return 'dailymotion'
    elif 'facebook.com' in url_lower:
        return 'facebook'
    elif 'instagram.com' in url_lower:
        return 'instagram'
    elif 'tiktok.com' in url_lower:
        return 'tiktok'
    elif url_lower.endswith(('.mp4', '.webm', '.ogg', '.mov')):
        return 'direct'
    else:
        return 'embed'


def _detect_audio_type(url):
    """Detect audio platform from URL"""
    url_lower = url.lower()
    if 'spotify.com' in url_lower:
        return 'spotify'
    elif 'soundcloud.com' in url_lower:
        return 'soundcloud'
    elif 'apple.com' in url_lower and 'podcast' in url_lower:
        return 'apple_podcast'
    elif url_lower.endswith(('.mp3', '.m4a', '.ogg', '.wav', '.aac')):
        return 'direct'
    else:
        return 'embed'


def _process_video_for_display(url, video_type, metadata=None):
    """Process video for display - generate proper embed URLs"""
    if not url:
        return None
    
    metadata = metadata or {}
    
    # YouTube
    if video_type == 'youtube':
        video_id = extract_youtube_id(url)
        if video_id:
            return {
                'type': 'youtube',
                'embed_url': f'https://www.youtube.com/embed/{video_id}',
                'watch_url': f'https://www.youtube.com/watch?v={video_id}',
                'thumbnail': f'https://img.youtube.com/vi/{video_id}/maxresdefault.jpg',
                'id': video_id,
                'title': metadata.get('title', 'YouTube Video'),
                'platform': 'YouTube'
            }
    
    # Vimeo
    elif video_type == 'vimeo':
        video_id = extract_vimeo_id(url)
        if video_id:
            return {
                'type': 'vimeo',
                'embed_url': f'https://player.vimeo.com/video/{video_id}',
                'watch_url': url,
                'id': video_id,
                'title': metadata.get('title', 'Vimeo Video'),
                'platform': 'Vimeo'
            }
    
    # Dailymotion
    elif video_type == 'dailymotion':
        video_id = extract_dailymotion_id(url)
        if video_id:
            return {
                'type': 'dailymotion',
                'embed_url': f'https://www.dailymotion.com/embed/video/{video_id}',
                'watch_url': url,
                'id': video_id,
                'platform': 'Dailymotion'
            }
    
    # Facebook
    elif video_type == 'facebook':
        return {
            'type': 'facebook',
            'embed_url': f'https://www.facebook.com/plugins/video.php?href={url}',
            'watch_url': url,
            'platform': 'Facebook'
        }
    
    # Instagram
    elif video_type == 'instagram':
        return {
            'type': 'instagram',
            'embed_url': f'{url}embed/',
            'watch_url': url,
            'platform': 'Instagram'
        }
    
    # TikTok
    elif video_type == 'tiktok':
        return {
            'type': 'tiktok',
            'embed_url': url.replace('@', '').replace('video/', ''),
            'watch_url': url,
            'platform': 'TikTok'
        }
    
    # Direct video file
    elif video_type == 'direct':
        return {
            'type': 'direct',
            'url': url,
            'poster': metadata.get('poster', ''),
            'platform': 'Direct'
        }
    
    # Generic embed
    else:
        return {
            'type': 'embed',
            'url': url,
            'platform': 'Unknown'
        }


def _process_audio_for_display(url, audio_type, metadata=None):
    """Process audio for display - generate proper embed URLs"""
    if not url:
        return None
    
    metadata = metadata or {}
    
    # Spotify
    if audio_type == 'spotify':
        spotify_id = extract_spotify_id(url)
        if spotify_id:
            if 'track' in url:
                embed_url = f'https://open.spotify.com/embed/track/{spotify_id}'
            elif 'episode' in url:
                embed_url = f'https://open.spotify.com/embed/episode/{spotify_id}'
            elif 'album' in url:
                embed_url = f'https://open.spotify.com/embed/album/{spotify_id}'
            else:
                embed_url = f'https://open.spotify.com/embed/{spotify_id}'
            
            return {
                'type': 'spotify',
                'embed_url': embed_url,
                'open_url': url,
                'id': spotify_id,
                'platform': 'Spotify'
            }
    
    # SoundCloud
    elif audio_type == 'soundcloud':
        return {
            'type': 'soundcloud',
            'embed_url': f'https://w.soundcloud.com/player/?url={url}&color=%23ff5500&auto_play=false&hide_related=false&show_comments=true&show_user=true&show_reposts=false&show_teaser=true',
            'open_url': url,
            'platform': 'SoundCloud'
        }
    
    # Apple Podcasts
    elif audio_type == 'apple_podcast':
        return {
            'type': 'apple_podcast',
            'url': url,
            'platform': 'Apple Podcasts'
        }
    
    # Direct audio file
    elif audio_type == 'direct':
        return {
            'type': 'direct',
            'url': url,
            'platform': 'Direct'
        }
    
    # Generic embed
    else:
        return {
            'type': 'embed',
            'url': url,
            'platform': 'Unknown'
        }


def extract_youtube_id(url):
    """Extract YouTube video ID from URL"""
    if not url:
        return None
    
    patterns = [
        r'youtube\.com/watch\?v=([a-zA-Z0-9_-]+)',
        r'youtu\.be/([a-zA-Z0-9_-]+)',
        r'youtube\.com/embed/([a-zA-Z0-9_-]+)',
        r'youtube\.com/v/([a-zA-Z0-9_-]+)',
        r'youtube\.com/shorts/([a-zA-Z0-9_-]+)'
    ]
    for pattern in patterns:
        match = re.search(pattern, str(url))
        if match:
            return match.group(1)
    return None


def extract_vimeo_id(url):
    """Extract Vimeo video ID from URL"""
    if not url:
        return None
    match = re.search(r'vimeo\.com/(?:video/)?(\d+)', str(url))
    return match.group(1) if match else None


def extract_dailymotion_id(url):
    """Extract Dailymotion video ID from URL"""
    if not url:
        return None
    match = re.search(r'dailymotion\.com/video/([a-zA-Z0-9]+)', str(url))
    return match.group(1) if match else None


def extract_spotify_id(url):
    """Extract Spotify ID from URL"""
    if not url:
        return None
    match = re.search(r'(?:open\.spotify\.com|spotify\.com)/(?:track|episode|album)/([a-zA-Z0-9]+)', str(url))
    return match.group(1) if match else None


def get_user_interactions(user, post):
    """Get user interactions with a post"""
    interactions = {
        'liked': False,
        'bookmarked': False,
        'reposted': False,
        'is_following': False,
    }
    
    if user.is_authenticated:
        interactions['liked'] = post.likes.filter(id=user.id).exists()
        interactions['bookmarked'] = post.bookmarks.filter(id=user.id).exists()
        interactions['reposted'] = Repost.objects.filter(
            user=user, 
            original_post=post
        ).exists()
        interactions['is_following'] = Follow.objects.filter(
            follower=user,
            following=post.author
        ).exists()
    
    return interactions


def get_related_content(post, user):
    """Get related posts and trending content"""
    # Related posts (same category or auto-fetched)
    related_posts = Post.objects.filter(
        Q(category=post.category) | Q(is_auto_fetched=True),
        status='published'
    ).exclude(id=post.id).annotate(
        relevance_score=Count('likes') + F('views') / 100
    ).select_related('category').order_by('-relevance_score', '-published_at')[:5]
    
    # Trending in same category
    trending_in_category = Post.objects.filter(
        category=post.category,
        status='published',
        created_at__gte=timezone.now() - timedelta(days=7)
    ).exclude(id=post.id).annotate(
        like_count=Count('likes')
    ).select_related('category').order_by('-like_count', '-views')[:5]
    
    return {
        'related_posts': related_posts,
        'trending_in_category': trending_in_category,
    }


def can_view_post(user, post):
    """Check if a user can view a specific post based on privacy settings"""
    # Admin/staff can view everything
    if user.is_authenticated and (user.is_staff or user.is_superuser):
        return True
    
    # Author can always view their own posts
    if user.is_authenticated and post.author == user:
        return True
    
    # News posts are always public
    if post.post_type in ['news', 'user_news']:
        return True
    
    # Check privacy settings
    if post.privacy == 'public':
        return True
    elif post.privacy == 'private':
        return user.is_authenticated and post.author == user
    elif post.privacy == 'followers':
        if not user.is_authenticated:
            return False
        # Check if user is following the author
        return Follow.objects.filter(
            follower=user,
            following=post.author
        ).exists()
    elif post.privacy == 'specific':
        if not user.is_authenticated:
            return False
        # Check if user is in allowed viewers list
        return post.allowed_viewers.filter(id=user.id).exists()
    
    return False


def handle_comment_submission(request, post):
    """Handle comment submission with improved validation"""
    content = request.POST.get('content', '').strip()
    parent_id = request.POST.get('parent_id')
    comment_image = request.FILES.get('comment_image')
    
    if not content:
        messages.error(request, 'Comment cannot be empty')
        return redirect('post_detail', post_id=post.id)
    
    if len(content) > 1000:
        messages.error(request, 'Comment is too long (maximum 1000 characters)')
        return redirect('post_detail', post_id=post.id)
    
    # Create comment
    comment = Comment.objects.create(
        post=post,
        user=request.user,
        content=content,
        parent_id=parent_id if parent_id else None,
        image=comment_image
    )
    
    # Update comment count
    Post.objects.filter(id=post.id).update(comments_count=F('comments_count') + 1)
    
    # Create notifications
    create_comment_notifications(request.user, post, comment, parent_id)
    
    # Create activity
    UserActivity.objects.create(
        user=request.user,
        activity_type='comment_added',
        post=post,
        comment=comment,
        details={'content': content[:50]}
    )
    
    messages.success(request, 'Comment added successfully!')
    
    # Return to comment section
    return redirect(f'{post.get_absolute_url()}#comment-{comment.id}')


def create_comment_notifications(user, post, comment, parent_id):
    """Create notifications for comment/reply"""
    # Notify post author if not own post
    if post.author != user:
        Notification.objects.create(
            user=post.author,
            from_user=user,
            notification_type='comment',
            message=f'{user.username} commented on your post',
            post=post,
            comment=comment
        )
    
    # Notify parent comment author if replying
    if parent_id:
        try:
            parent_comment = Comment.objects.get(id=parent_id)
            if parent_comment.user != user:
                Notification.objects.create(
                    user=parent_comment.user,
                    from_user=user,
                    notification_type='reply',
                    message=f'{user.username} replied to your comment',
                    post=post,
                    comment=comment
                )
        except Comment.DoesNotExist:
            pass


def process_post_media(post):
    """Process post media for display with enhanced platform support"""
    media = {
        'videos': [],
        'audios': [],
        'images': [],
        'has_youtube': False,
        'has_vimeo': False,
        'has_spotify': False,
        'has_soundcloud': False,
        'has_dailymotion': False,
        'has_facebook': False,
        'has_instagram': False,
        'has_tiktok': False,
    }
    
    # Process video URLs
    if post.video_urls:
        try:
            video_urls = post.video_urls
            if isinstance(video_urls, str):
                video_urls = json.loads(video_urls)
            
            for video in video_urls:
                if isinstance(video, dict):
                    video_url = video.get('url', '')
                    
                    # Generate embed URLs for different platforms
                    if 'youtube' in video_url or 'youtu.be' in video_url:
                        video_id = extract_youtube_id(video_url)
                        if video_id:
                            media['videos'].append({
                                'type': 'youtube',
                                'embed_url': f'https://www.youtube.com/embed/{video_id}',
                                'thumbnail': f'https://img.youtube.com/vi/{video_id}/maxresdefault.jpg',
                                'id': video_id,
                                'title': video.get('title', 'YouTube Video')
                            })
                            media['has_youtube'] = True
                    
                    elif 'vimeo' in video_url:
                        video_id = extract_vimeo_id(video_url)
                        if video_id:
                            media['videos'].append({
                                'type': 'vimeo',
                                'embed_url': f'https://player.vimeo.com/video/{video_id}',
                                'id': video_id,
                                'title': video.get('title', 'Vimeo Video')
                            })
                            media['has_vimeo'] = True
                    
                    elif 'dailymotion' in video_url:
                        video_id = extract_dailymotion_id(video_url)
                        if video_id:
                            media['videos'].append({
                                'type': 'dailymotion',
                                'embed_url': f'https://www.dailymotion.com/embed/video/{video_id}',
                                'id': video_id
                            })
                            media['has_dailymotion'] = True
                    
                    elif 'facebook.com' in video_url:
                        media['videos'].append({
                            'type': 'facebook',
                            'embed_url': f'https://www.facebook.com/plugins/video.php?href={video_url}',
                            'url': video_url
                        })
                        media['has_facebook'] = True
                    
                    elif 'instagram.com' in video_url:
                        media['videos'].append({
                            'type': 'instagram',
                            'embed_url': f'{video_url}embed/',
                            'url': video_url
                        })
                        media['has_instagram'] = True
                    
                    elif 'tiktok.com' in video_url:
                        media['videos'].append({
                            'type': 'tiktok',
                            'embed_url': video_url.replace('@', '').replace('video/', ''),
                            'url': video_url
                        })
                        media['has_tiktok'] = True
                    
                    elif video_url.lower().endswith(('.mp4', '.webm', '.ogg', '.mov')):
                        media['videos'].append({
                            'type': 'direct',
                            'url': video_url,
                            'poster': video.get('poster', '')
                        })
        except Exception as e:
            logger.error(f"Error processing video URLs: {e}")
    
    # Process audio URLs
    if post.audio_urls:
        try:
            audio_urls = post.audio_urls
            if isinstance(audio_urls, str):
                audio_urls = json.loads(audio_urls)
            
            for audio in audio_urls:
                if isinstance(audio, dict):
                    audio_url = audio.get('url', '')
                    
                    if 'spotify' in audio_url:
                        spotify_id = extract_spotify_id(audio_url)
                        if spotify_id:
                            if 'track' in audio_url:
                                embed_url = f'https://open.spotify.com/embed/track/{spotify_id}'
                            elif 'episode' in audio_url:
                                embed_url = f'https://open.spotify.com/embed/episode/{spotify_id}'
                            elif 'album' in audio_url:
                                embed_url = f'https://open.spotify.com/embed/album/{spotify_id}'
                            else:
                                embed_url = f'https://open.spotify.com/embed/{spotify_id}'
                            
                            media['audios'].append({
                                'type': 'spotify',
                                'embed_url': embed_url,
                                'platform': 'spotify',
                                'id': spotify_id
                            })
                            media['has_spotify'] = True
                    
                    elif 'soundcloud' in audio_url:
                        media['audios'].append({
                            'type': 'soundcloud',
                            'embed_url': f'https://w.soundcloud.com/player/?url={audio_url}&color=%23ff5500&auto_play=false&hide_related=false&show_comments=true&show_user=true&show_reposts=false&show_teaser=true',
                            'platform': 'soundcloud'
                        })
                        media['has_soundcloud'] = True
                    
                    elif 'apple.com' in audio_url and 'podcast' in audio_url:
                        media['audios'].append({
                            'type': 'apple_podcast',
                            'embed_url': audio_url,
                            'platform': 'apple_podcast'
                        })
                    
                    elif audio_url.lower().endswith(('.mp3', '.m4a', '.ogg', '.wav', '.aac', '.opus')):
                        media['audios'].append({
                            'type': 'direct',
                            'url': audio_url
                        })
        except Exception as e:
            logger.error(f"Error processing audio URLs: {e}")
    
    return media


def extract_youtube_id(url):
    """Extract YouTube video ID from URL"""
    if not url:
        return None
    
    patterns = [
        r'youtube\.com/watch\?v=([a-zA-Z0-9_-]+)',
        r'youtu\.be/([a-zA-Z0-9_-]+)',
        r'youtube\.com/embed/([a-zA-Z0-9_-]+)',
        r'youtube\.com/v/([a-zA-Z0-9_-]+)',
        r'youtube\.com/shorts/([a-zA-Z0-9_-]+)'
    ]
    for pattern in patterns:
        match = re.search(pattern, str(url))
        if match:
            return match.group(1)
    return None


def extract_vimeo_id(url):
    """Extract Vimeo video ID from URL"""
    if not url:
        return None
    match = re.search(r'vimeo\.com/(?:video/)?(\d+)', str(url))
    return match.group(1) if match else None


def extract_dailymotion_id(url):
    """Extract Dailymotion video ID from URL"""
    if not url:
        return None
    match = re.search(r'dailymotion\.com/video/([a-zA-Z0-9]+)', str(url))
    return match.group(1) if match else None


def extract_spotify_id(url):
    """Extract Spotify ID from URL"""
    if not url:
        return None
    match = re.search(r'(?:open\.spotify\.com|spotify\.com)/(?:track|episode|album)/([a-zA-Z0-9]+)', str(url))
    return match.group(1) if match else None


def get_verification_info(post):
    """Get detailed verification information for display"""
    if post.verification_status == 'verified' and post.verification_details:
        try:
            if isinstance(post.verification_details, str):
                details = json.loads(post.verification_details)
            else:
                details = post.verification_details
            
            # Extract check results
            checks = details.get('checks', {})
            strengths = []
            concerns = []
            
            # Source check
            source_check = checks.get('source', {})
            if source_check.get('score', 0) > 0.7:
                strengths.append("✓ Source appears credible and reputable")
            elif source_check.get('score', 0) < 0.3:
                concerns.append("⚠ Source credibility is questionable")
            
            # URL check
            url_check = checks.get('url', {})
            if url_check.get('score', 0) > 0.7:
                strengths.append("✓ URL structure is legitimate")
            elif url_check.get('score', 0) < 0.5:
                concerns.append("⚠ URL structure raises concerns")
            
            # Content check
            content_check = checks.get('content', {})
            if content_check.get('score', 0) > 0.7:
                strengths.append("✓ Content quality and depth are good")
            
            # Sensationalism check
            sens_check = checks.get('sensationalism', {})
            if sens_check.get('score', 0) > 0.7:
                strengths.append("✓ Language is factual and balanced")
            elif sens_check.get('score', 0) < 0.5:
                concerns.append("⚠ May contain sensationalist language")
            
            # Language check
            lang_check = checks.get('language', {})
            if lang_check.get('score', 0) > 0.7:
                strengths.append("✓ Language is professional and objective")
            elif lang_check.get('score', 0) < 0.5:
                concerns.append("⚠ Language appears emotionally charged")
            
            # Bias check
            bias_check = checks.get('bias', {})
            if bias_check.get('score', 0) > 0.7:
                strengths.append("✓ Content appears balanced and unbiased")
            elif bias_check.get('score', 0) < 0.5:
                concerns.append("⚠ Possible bias detected")
            
            # Fact-check sources
            fact_check_sources = details.get('fact_check_sources', [])
            if fact_check_sources:
                strengths.append(f"✓ Verified by {len(fact_check_sources)} fact-checking sources")
            
            # Overall assessment
            if post.verification_score >= 0.8:
                overall = "Highly Reliable"
                overall_color = "success"
            elif post.verification_score >= 0.6:
                overall = "Mostly Reliable"
                overall_color = "info"
            elif post.verification_score >= 0.4:
                overall = "Partially Reliable"
                overall_color = "warning"
            else:
                overall = "Needs Verification"
                overall_color = "danger"
            
            return {
                'score': post.verification_score,
                'score_percentage': int(post.verification_score * 100) if post.verification_score else 0,
                'status': post.verification_status,
                'strengths': strengths,
                'concerns': concerns,
                'overall': overall,
                'overall_color': overall_color,
                'checks': checks,
                'fact_check_sources': fact_check_sources,
                'verified_at': details.get('verified_at'),
                'verification_method': details.get('method', 'Automated')
            }
        except Exception as e:
            logger.error(f"Error parsing verification details: {e}")
    
    # Return basic info for non-verified posts
    return {
        'score': post.verification_score,
        'score_percentage': int(post.verification_score * 100) if post.verification_score else 0,
        'status': post.verification_status,
        'strengths': [],
        'concerns': [],
        'overall': 'Pending Verification' if post.verification_status == 'pending' else 'Not Verified',
        'overall_color': 'secondary' if post.verification_status == 'pending' else 'default'
    }


def get_trending_topics(limit=5):
    """Get trending topics from recent posts with caching"""
    cache_key = 'trending_topics'
    topics = cache.get(cache_key)
    
    if topics is None:
        recent_posts = Post.objects.filter(
            status='published',
            created_at__gte=timezone.now() - timedelta(days=2)
        ).order_by('-views')[:50]
        
        # Extract common words from titles
        words = {}
        stop_words = {'the', 'and', 'for', 'with', 'this', 'that', 'from', 
                     'have', 'were', 'has', 'had', 'will', 'are', 'was', 'been',
                     'what', 'when', 'where', 'who', 'why', 'how', 'all', 'one',
                     'would', 'could', 'should', 'their', 'they', 'them', 'our'}
        
        for post in recent_posts:
            if post.title:
                title_words = post.title.lower().split()
                for word in title_words:
                    word = word.strip('.,!?()[]{}:;"\'')
                    if len(word) > 3 and word not in stop_words and not word.isdigit():
                        words[word] = words.get(word, 0) + 1
        
        # Sort by frequency
        trending = sorted(words.items(), key=lambda x: x[1], reverse=True)[:limit]
        topics = [{'topic': word, 'count': count} for word, count in trending]
        
        cache.set(cache_key, topics, 3600)  # 1 hour
    
    return topics


def handle_comment_submission(request, post):
    """Handle comment submission with improved validation"""
    content = request.POST.get('content', '').strip()
    parent_id = request.POST.get('parent_id')
    comment_image = request.FILES.get('comment_image')
    
    if not content:
        messages.error(request, 'Comment cannot be empty')
        return redirect('post_detail', post_id=post.id)
    
    if len(content) > 1000:
        messages.error(request, 'Comment is too long (maximum 1000 characters)')
        return redirect('post_detail', post_id=post.id)
    
    # Create comment
    comment = Comment.objects.create(
        post=post,
        user=request.user,
        content=content,
        parent_id=parent_id if parent_id else None,
        image=comment_image
    )
    
    # Update comment count
    Post.objects.filter(id=post.id).update(comments_count=F('comments_count') + 1)
    
    # Create notifications
    create_comment_notifications(request.user, post, comment, parent_id)
    
    # Create activity
    UserActivity.objects.create(
        user=request.user,
        activity_type='comment_added',
        post=post,
        comment=comment,
        details={'content': content[:50]}
    )
    
    messages.success(request, 'Comment added successfully!')
    
    # Return to comment section
    return redirect(f'{post.get_absolute_url()}#comment-{comment.id}')


# ==================== CREATE/EDIT/DELETE POST ====================

@login_required
def create_post(request):
    """Create a new post with privacy settings and media"""
    categories = Category.objects.all()
    
    # Get user's drafts
    drafts = Post.objects.filter(
        author=request.user,
        status='draft'
    ).order_by('-updated_at')[:5]
    
    if request.method == 'POST':
        # DEBUG: Print all POST data
        print("\n" + "="*50)
        print("DEBUG - POST DATA:")
        for key, value in request.POST.items():
            print(f"  {key}: {value}")
        print("="*50 + "\n")
        
        # CRITICAL FIX: Ensure post_type is in POST data
        # If it's missing but we have a hidden field, add it
        if 'post_type' not in request.POST:
            # Check if it might be in a different format
            hidden_post_type = request.POST.get('post_type_hidden') or request.POST.get('post_type_value')
            if hidden_post_type:
                # Create a mutable copy of POST data
                post_data = request.POST.copy()
                post_data['post_type'] = hidden_post_type
                request.POST = post_data
                print(f"✓ Added post_type from hidden field: {hidden_post_type}")
        
        # Create form with POST data
        form = PostForm(request.POST, request.FILES, user=request.user)
        
        # Check if form is valid
        if form.is_valid():
            print("✓ Form is valid!")
            
            # Save the post but don't commit yet
            post = form.save(commit=False)
            post.author = request.user
            
            # FIX: Set post_type and is_news_submission consistently
            post_type = form.cleaned_data.get('post_type')
            print(f"DEBUG - Post type from form: {post_type}")
            
            if post_type == 'user_news':
                post.post_type = 'user_news'
                post.is_news_submission = True  # IMPORTANT: Set this to True
                post.status = 'draft'  # News posts need approval
                post.submission_status = 'pending'
                messages.info(request, 'Your news submission has been sent for review.')
            elif post_type == 'discussion':
                post.post_type = 'discussion'
                post.is_news_submission = False
                post.status = 'published'
                messages.success(request, 'Discussion post created successfully!')
            else:  # profile_post
                post.post_type = 'profile_post'
                post.is_news_submission = False
                post.status = 'published'
                messages.success(request, 'Profile post created successfully!')
            
            # Handle media
            if form.cleaned_data.get('video_url'):
                post.has_media = True
            
            if form.cleaned_data.get('audio_url'):
                post.has_media = True
            
            # Save the post
            post.save()
            form.save_m2m()  # Save many-to-many relationships
            
            # Handle allowed viewers for specific privacy
            if post.privacy == 'specific' and form.cleaned_data.get('allowed_viewers'):
                post.allowed_viewers.set(form.cleaned_data['allowed_viewers'])
            
            # Create activity
            UserActivity.objects.create(
                user=request.user,
                activity_type='post_created',
                post=post,
                details={'title': post.title[:50]}
            )
            
            # Redirect based on post type
            if post.post_type == 'user_news':
                return redirect('news_submissions')
            else:
                return redirect('post_detail', post_id=post.id)
        else:
            print("✗ Form is invalid!")
            print("Form errors:", form.errors)
            
            # Show specific error for post_type
            if 'post_type' in form.errors:
                print("post_type errors:", form.errors['post_type'])
            
            # Add error messages to be displayed
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        # GET request - initialize form
        initial_data = {}
        post_type = request.GET.get('type')
        if post_type in ['discussion', 'user_news', 'profile_post']:
            initial_data['post_type'] = post_type
        
        form = PostForm(user=request.user, initial=initial_data)
    
    trending_topics = get_trending_topics()
    
    context = {
        'form': form,
        'categories': categories,
        'drafts': drafts,
        'trending_topics': trending_topics,
        'followers_count': Follow.objects.filter(following=request.user).count(),
        'title': 'Create Post',
    }
    return render(request, 'create_post.html', context)


@login_required
def edit_post(request, post_id):
    """Edit an existing post"""
    post = get_object_or_404(Post, id=post_id)
    
    # Check permissions
    if post.author != request.user and not request.user.is_staff:
        messages.error(request, 'You do not have permission to edit this post')
        return redirect('post_detail', post_id=post_id)
    
    categories = Category.objects.all()
    trending_topics = get_trending_topics()
    
    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES, instance=post, user=request.user)
        if form.is_valid():
            updated_post = form.save(commit=False)
            
            # Handle media updates
            video_url = request.POST.get('video_url')
            if video_url:
                updated_post.video_urls = [{'url': video_url, 'type': 'embed', 'source': 'user'}]
                updated_post.has_media = True
            
            audio_url = request.POST.get('audio_url')
            if audio_url:
                updated_post.audio_urls = [{'url': audio_url, 'type': 'embed', 'source': 'user'}]
                updated_post.has_media = True
            
            updated_post.save()
            form.save_m2m()
            
            messages.success(request, 'Post updated successfully!')
            return redirect('post_detail', post_id=post_id)
    else:
        form = PostForm(instance=post, user=request.user)
    
    context = {
        'form': form,
        'post': post,
        'categories': categories,
        'trending_topics': trending_topics,
        'title': f'Edit: {post.title}',
    }
    return render(request, 'create_post.html', context)


@login_required
@require_POST
def delete_post(request, post_id):
    """Delete a post"""
    post = get_object_or_404(Post, id=post_id)
    
    if post.author != request.user and not request.user.is_staff:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'error': 'Permission denied'}, status=403)
        messages.error(request, 'You cannot delete this post')
        return redirect('post_detail', post_id=post_id)
    
    post.delete()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True})
    
    messages.success(request, 'Post deleted successfully!')
    return redirect('home')


# ==================== INTERACTION VIEWS ====================
@login_required
@csrf_exempt
def test_ajax(request):
    """Test view to verify AJAX is working"""
    if request.method == 'POST':
        return JsonResponse({
            'success': True,
            'message': 'AJAX is working!',
            'user': request.user.username
        })
    return JsonResponse({'error': 'GET not allowed'}, status=405)



def like_post(request, post_id):
    """Like/Unlike a post - handles both AJAX and regular requests"""
    
    # Check if user is authenticated
    if not request.user.is_authenticated:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': 'Please login to like posts',
                'login_required': True
            }, status=401)
        else:
            from django.shortcuts import redirect
            return redirect(f'/login/?next={request.path}')
    
    try:
        post = get_object_or_404(Post, id=post_id)
        
        if request.user in post.likes.all():
            post.likes.remove(request.user)
            liked = False
        else:
            post.likes.add(request.user)
            liked = True
            
            # Create notification if not liking own post
            if post.author != request.user:
                try:
                    from .models import Notification
                    Notification.objects.create(
                        user=post.author,
                        from_user=request.user,
                        notification_type='like',
                        message=f'{request.user.username} liked your post',
                        post=post
                    )
                except Exception as e:
                    print(f"Error creating notification: {e}")
        
        # Return JSON for AJAX requests
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'liked': liked,
                'like_count': post.likes.count()
            })
        
        # Regular request - redirect
        from django.shortcuts import redirect
        return redirect('post_detail', post_id=post_id)
    
    except Exception as e:
        print(f"Error in like_post: {e}")
        import traceback
        traceback.print_exc()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
        raise
    
    

@login_required
@require_POST
def bookmark_post(request, post_id):
    """Bookmark/Unbookmark a post"""
    try:
        post = get_object_or_404(Post, id=post_id)
        
        if request.user in post.bookmarks.all():
            post.bookmarks.remove(request.user)
            bookmarked = False
        else:
            post.bookmarks.add(request.user)
            bookmarked = True
            
            # Create activity
            UserActivity.objects.create(
                user=request.user,
                activity_type='post_saved',
                post=post,
                details={'title': post.title[:50]}
            )
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'bookmarked': bookmarked,
                'bookmark_count': post.bookmarks.count()
            })
        
        return redirect('post_detail', post_id=post_id)
    
    except Exception as e:
        logger.error(f"Error in bookmark_post: {e}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
        raise

@login_required
@require_POST
def repost_post(request, post_id):
    """Repost a post"""
    post = get_object_or_404(Post, id=post_id)
    content = request.POST.get('repost_content', '').strip()
    
    repost, created = Repost.objects.get_or_create(
        user=request.user,
        original_post=post,
        defaults={'content': content}
    )
    
    if created:
        post.repost_count = F('repost_count') + 1
        post.save()
        
        # Create activity
        UserActivity.objects.create(
            user=request.user,
            activity_type='post_reposted',
            post=post,
            details={'content': content[:50]}
        )
        
        # Create notification
        if post.author != request.user:
            Notification.objects.create(
                user=post.author,
                from_user=request.user,
                notification_type='repost',
                message=f'{request.user.username} reposted your post',
                post=post
            )
        
        message = 'Post reposted!'
    else:
        repost.delete()
        post.repost_count = F('repost_count') - 1
        post.save()
        message = 'Repost removed'
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'reposted': created,
            'repost_count': post.repost_count,
            'message': message
        })
    
    messages.success(request, message)
    return redirect('post_detail', post_id=post_id)


@login_required
@require_POST
def like_comment(request, comment_id):
    """Like/Unlike a comment"""
    comment = get_object_or_404(Comment, id=comment_id)
    
    if request.user in comment.likes.all():
        comment.likes.remove(request.user)
    else:
        comment.likes.add(request.user)
        
        # Create notification if not liking own comment
        if comment.user != request.user:
            Notification.objects.create(
                user=comment.user,
                from_user=request.user,
                notification_type='like',
                message=f'{request.user.username} liked your comment',
                comment=comment
            )
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'like_count': comment.likes.count()
        })
    
    return redirect('post_detail', post_id=comment.post.id)


@login_required
@require_POST
def delete_comment(request, comment_id):
    """Delete a comment"""
    comment = get_object_or_404(Comment, id=comment_id)
    
    if comment.user != request.user and not request.user.is_staff:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'error': 'Permission denied'}, status=403)
        messages.error(request, 'You cannot delete this comment')
        return redirect('post_detail', post_id=comment.post.id)
    
    post_id = comment.post.id
    comment.delete()
    
    # Update post comment count
    Post.objects.filter(id=post_id).update(
        comments_count=F('comments_count') - 1
    )
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True})
    
    messages.success(request, 'Comment deleted successfully!')
    return redirect('post_detail', post_id=post_id)


# ==================== PROFILE VIEWS ====================

def profile_view(request, username=None):
    """Enhanced profile view with follow functionality"""
    if username:
        user = get_object_or_404(User, username=username)
    else:
        user = request.user
    
    # Get or create profile
    profile, created = UserProfile.objects.get_or_create(user=user)
    
    # Get current tab
    tab = request.GET.get('tab', 'posts')
    
    # Get user's activities
    activities = UserActivity.objects.filter(user=user).select_related(
        'post', 'comment', 'target_user'
    ).order_by('-created_at')[:50]
    
    # Get user's posts - filter by privacy
    user_posts = Post.objects.filter(
        author=user, 
        status='published'
    ).select_related('category')
    
    # Filter posts based on viewer permissions
    if request.user != user:
        filtered_posts = []
        for post in user_posts:
            if can_view_post(request.user, post):
                filtered_posts.append(post.id)
        user_posts = user_posts.filter(id__in=filtered_posts)
    
    user_posts = user_posts.order_by('-published_at')
    
    # Get user's comments
    comments = Comment.objects.filter(user=user, is_active=True).select_related(
        'post'
    ).order_by('-created_at')
    
    # Get liked posts
    liked_posts = Post.objects.filter(likes=user, status='published').select_related(
        'category'
    )[:20]
    
    # Get followers and following
    followers = User.objects.filter(followers__following=user).distinct()
    following = User.objects.filter(following__follower=user).distinct()
    
    followers_count = followers.count()
    following_count = following.count()
    
    # Check if current user is following this profile
    is_following = False
    if request.user.is_authenticated and user != request.user:
        is_following = Follow.objects.filter(
            follower=request.user,
            following=user
        ).exists()
    
    # Get trending topics
    trending_topics = get_trending_topics()
    
    # Update last seen
    if user == request.user:
        profile.last_seen = timezone.now()
        profile.save()
    
    context = {
        'profile_user': user,
        'profile': profile,
        'tab': tab,
        'activities': activities,
        'posts': user_posts,
        'comments': comments,
        'liked_posts': liked_posts,
        'followers': followers,
        'following': following,
        'followers_count': followers_count,
        'following_count': following_count,
        'is_following': is_following,
        'is_own_profile': user == request.user,
        'can_view_posts': True,
        'trending_topics': trending_topics,
    }
    
    return render(request, 'profile/profile.html', context)


@login_required
def edit_profile(request):
    """Profile editing functionality"""
    trending_topics = get_trending_topics()
    
    if request.method == 'POST':
        user_form = UserUpdateForm(request.POST, instance=request.user)
        profile_form = UserProfileForm(request.POST, request.FILES, instance=request.user.profile)
        
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            
            # Track profile update
            UserActivity.objects.create(
                user=request.user,
                activity_type='profile_updated',
                details={'changes': 'Profile information updated'}
            )
            
            messages.success(request, 'Your profile has been updated!')
            return redirect('profile_view', username=request.user.username)
    else:
        user_form = UserUpdateForm(instance=request.user)
        profile_form = UserProfileForm(instance=request.user.profile)
    
    # Add timestamp to force image refresh
    import time
    timestamp = int(time.time())
    
    context = {
        'user_form': user_form,
        'profile_form': profile_form,
        'trending_topics': trending_topics,
        'title': 'Edit Profile',
        'timestamp': timestamp,  # Add this to the context
    }
    
    return render(request, 'profile/edit_profile.html', context)


@login_required
@require_POST
def follow_user(request, username):
    """Follow/Unfollow a user with proper AJAX response"""
    try:
        user_to_follow = get_object_or_404(User, username=username)
        
        if user_to_follow == request.user:
            return JsonResponse({
                'error': 'You cannot follow yourself',
                'success': False
            }, status=400)
        
        # Check if already following
        follow, created = Follow.objects.get_or_create(
            follower=request.user,
            following=user_to_follow
        )
        
        if not created:
            # Unfollow
            follow.delete()
            followed = False
            is_following = False
            message = f'Unfollowed {user_to_follow.username}'
        else:
            # Follow
            followed = True
            is_following = True
            message = f'Now following {user_to_follow.username}'
            
            # Create notification
            Notification.objects.create(
                user=user_to_follow,
                from_user=request.user,
                notification_type='follow',
                message=f'{request.user.username} started following you'
            )
            
            # Create activity
            UserActivity.objects.create(
                user=request.user,
                activity_type='followed_user',
                target_user=user_to_follow,
                details={'username': user_to_follow.username}
            )
        
        # Get updated counts
        followers_count = Follow.objects.filter(following=user_to_follow).count()
        following_count = Follow.objects.filter(follower=request.user).count()
        
        return JsonResponse({
            'followed': followed,
            'is_following': is_following,
            'followers_count': followers_count,
            'following_count': following_count,
            'message': message,
            'success': True
        })
        
    except Exception as e:
        return JsonResponse({
            'error': str(e),
            'success': False
        }, status=500)


@login_required
def profile_posts(request, username):
    """View only profile posts of a user"""
    user = get_object_or_404(User, username=username)
    
    posts = Post.objects.filter(
        author=user,
        post_type='profile_post',
        status='published'
    ).select_related('category').order_by('-published_at')
    
    # Filter based on viewer permissions
    if request.user != user:
        filtered_posts = []
        for post in posts:
            if can_view_post(request.user, post):
                filtered_posts.append(post.id)
        posts = posts.filter(id__in=filtered_posts)
    
    # Pagination
    paginator = Paginator(posts, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # Get trending topics
    trending_topics = get_trending_topics()
    
    context = {
        'profile_user': user,
        'posts': page_obj,
        'page_obj': page_obj,
        'tab': 'profile_posts',
        'trending_topics': trending_topics,
        'title': f'{user.username}\'s Profile Posts',
    }
    
    return render(request, 'profile/posts.html', context)


@login_required
def activity_feed(request):
    """User's activity feed"""
    activities = UserActivity.objects.filter(user=request.user).select_related(
        'post', 'comment', 'target_user'
    ).order_by('-created_at')
    
    # Pagination
    paginator = Paginator(activities, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # Get trending topics
    trending_topics = get_trending_topics()
    
    context = {
        'page_obj': page_obj,
        'activities': page_obj,
        'trending_topics': trending_topics,
        'title': 'Activity Feed',
    }
    
    return render(request, 'profile/activity_feed.html', context)


# ==================== NOTIFICATIONS ====================

@login_required
def notifications(request):
    """View user notifications"""
    user_notifications = Notification.objects.filter(
        user=request.user
    ).select_related('from_user', 'post', 'comment').order_by('-created_at')
    
    # Mark as read when viewing
    user_notifications.filter(is_read=False).update(is_read=True)
    
    # Get trending topics
    trending_topics = get_trending_topics()
    
    return render(request, 'notifications/notifications.html', {
        'notifications': user_notifications,
        'trending_topics': trending_topics,
        'title': 'Notifications'
    })


@login_required
def notifications_count(request):
    """Get unread notifications count (AJAX)"""
    count = Notification.objects.filter(user=request.user, is_read=False).count()
    return JsonResponse({'count': count})


# ==================== BOOKMARKS ====================

@login_required
def bookmarks(request):
    """View bookmarked posts"""
    bookmarked_posts = Post.objects.filter(
        bookmarks=request.user,
        status='published'
    ).select_related('category', 'author').order_by('-published_at')
    
    # Get trending topics
    trending_topics = get_trending_topics()
    
    return render(request, 'bookmarks/bookmarks.html', {
        'bookmarks': bookmarked_posts,
        'trending_topics': trending_topics,
        'title': 'Bookmarks'
    })


# ==================== SEARCH ====================

def search(request):
    """Enhanced search functionality with autocomplete support"""
    query = request.GET.get('q', '').strip()
    
    # Get trending topics
    trending_topics = get_trending_topics()
    
    context = {
        'query': query,
        'trending_topics': trending_topics,
        'title': f'Search: {query}' if query else 'Search'
    }
    
    if query and len(query) >= 2:
        # Base search results
        results = {
            'posts': [],
            'users': [],
            'categories': [],
            'comments': [],
            'admin': [] if request.user.is_staff else None
        }
        
        # Search posts (public content)
        posts = Post.objects.filter(
            Q(title__icontains=query) | 
            Q(content__icontains=query)
        ).filter(status='published').select_related('author', 'category').distinct()[:20]
        
        # Filter posts based on privacy
        filtered_posts = []
        for post in posts:
            if can_view_post(request.user, post):
                filtered_posts.append(post)
        results['posts'] = filtered_posts
        
        # Search users (public profiles)
        results['users'] = User.objects.filter(
            Q(username__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(email__icontains=query) |
            Q(profile__bio__icontains=query)
        ).filter(is_active=True).distinct()[:15]
        
        # Search categories
        results['categories'] = Category.objects.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query)
        )[:10]
        
        # Search comments
        results['comments'] = Comment.objects.filter(
            Q(content__icontains=query) &
            Q(is_active=True)
        ).select_related('user', 'post').distinct()[:10]
        
        # Admin-only search results
        if request.user.is_staff:
            # Admin posts (including drafts, pending, etc.)
            admin_posts = Post.objects.filter(
                Q(title__icontains=query) | 
                Q(content__icontains=query)
            ).exclude(status='published').select_related('author', 'category')[:10]
            
            # Pending news submissions
            pending_news = Post.objects.filter(
                Q(title__icontains=query) & 
                Q(is_news_submission=True) &
                Q(submission_status='pending')
            )[:10]
            
            # Flagged content
            flagged = Post.objects.filter(
                Q(title__icontains=query) &
                Q(verification_status='fake')
            )[:10]
            
            # User management (all users for admin)
            all_users = User.objects.filter(
                Q(username__icontains=query) |
                Q(email__icontains=query) |
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query)
            )[:15]
            
            results['admin'] = {
                'posts': admin_posts,
                'pending_news': pending_news,
                'flagged': flagged,
                'users': all_users
            }
        
        context['results'] = results
    
    # Check if this is an AJAX request for autocomplete
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse(get_autocomplete_suggestions(request, query))
    
    return render(request, 'search/search.html', context)


@require_GET
def search_suggestions(request):
    """Get search suggestions via AJAX for autocomplete"""
    query = request.GET.get('q', '').strip()
    
    if len(query) < 2:
        return JsonResponse({'suggestions': []})
    
    suggestions = get_autocomplete_suggestions(request, query)
    return JsonResponse(suggestions)


def get_autocomplete_suggestions(request, query):
    """Generate autocomplete suggestions based on user role"""
    suggestions = {
        'posts': [],
        'users': [],
        'categories': [],
        'quick_links': [],
        'admin': [] if request.user.is_staff else None
    }
    
    # Post title suggestions (public)
    posts = Post.objects.filter(
        title__icontains=query,
        status='published'
    ).select_related('category')[:5]
    
    for post in posts:
        if can_view_post(request.user, post):
            suggestions['posts'].append({
                'id': post.id,
                'title': post.title,
                'url': post.get_absolute_url(),
                'category': post.category.name if post.category else 'Post',
                'type': 'post',
                'image': post.image.url if post.image else None
            })
    
    # User suggestions
    users = User.objects.filter(
        Q(username__icontains=query) |
        Q(first_name__icontains=query) |
        Q(last_name__icontains=query)
    ).filter(is_active=True)[:5]
    
    for user in users:
        suggestions['users'].append({
            'id': user.id,
            'username': user.username,
            'full_name': user.get_full_name(),
            'url': reverse('profile_view', args=[user.username]),
            'type': 'user',
            'avatar': user.profile.profile_pic.url if hasattr(user, 'profile') and user.profile.profile_pic else None
        })
    
    # Category suggestions
    categories = Category.objects.filter(
        Q(name__icontains=query) |
        Q(description__icontains=query)
    )[:5]
    
    for category in categories:
        suggestions['categories'].append({
            'id': category.id,
            'name': category.name,
            'url': reverse('category_view', args=[category.slug]),
            'type': 'category',
            'post_count': category.posts.filter(status='published').count()
        })
    
    # Quick links (common search terms)
    quick_links = [
        {'text': 'Latest News', 'url': reverse('online_news'), 'icon': 'newspaper'},
        {'text': 'Trending', 'url': reverse('trending_posts'), 'icon': 'fire'},
        {'text': 'Discover', 'url': reverse('discover'), 'icon': 'compass'},
    ]
    
    # Filter quick links based on query
    for link in quick_links:
        if query.lower() in link['text'].lower():
            suggestions['quick_links'].append(link)
    
    # Admin-only suggestions
    if request.user.is_staff:
        admin_suggestions = []
        
        # Admin pages
        admin_pages = [
            {'text': 'Admin Dashboard', 'url': reverse('admin_dashboard'), 'icon': 'tachometer-alt'},
            {'text': 'Manage Posts', 'url': reverse('admin_posts'), 'icon': 'file-alt'},
            {'text': 'News Submissions', 'url': reverse('admin_news_submissions'), 'icon': 'newspaper'},
            {'text': 'Auto-Fetched News', 'url': reverse('admin_auto_fetched_news'), 'icon': 'sync-alt'},
            {'text': 'Quick Fetch News', 'url': reverse('quick_fetch_news'), 'icon': 'bolt'},
            {'text': 'System Settings', 'url': reverse('admin_system_settings'), 'icon': 'cogs'},
        ]
        
        for page in admin_pages:
            if query.lower() in page['text'].lower():
                admin_suggestions.append(page)
        
        # Pending items
        pending_count = Post.objects.filter(is_news_submission=True, submission_status='pending').count()
        if pending_count > 0:
            admin_suggestions.append({
                'text': f'Pending Submissions ({pending_count})',
                'url': reverse('admin_news_submissions') + '?filter=pending',
                'icon': 'clock',
                'badge': str(pending_count)
            })
        
        # Flagged items
        flagged_count = Post.objects.filter(verification_status='fake').count()
        if flagged_count > 0:
            admin_suggestions.append({
                'text': f'Flagged Content ({flagged_count})',
                'url': reverse('admin_posts') + '?filter=fake',
                'icon': 'exclamation-triangle',
                'badge': str(flagged_count)
            })
        
        suggestions['admin'] = admin_suggestions
    
    return suggestions

# ==================== FETCH NEWS (STAFF ONLY) ====================

@staff_member_required
def fetch_news(request):
    """Enhanced manual news fetching with options"""
    from .news_fetcher import NewsFetcher
    
    # Get parameters
    source = request.GET.get('source', 'all')
    days = int(request.GET.get('days', 7))
    limit = int(request.GET.get('limit', 100))
    
    fetcher = NewsFetcher()
    
    # Show fetch status in real-time if requested
    if request.GET.get('stream'):
        response = HttpResponse(content_type='text/event-stream')
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        
        def generate():
            yield f"data: Starting news fetch from {source} for last {days} days...\n\n"
            time.sleep(1)
            
            try:
                saved_count = fetcher.fetch_all_news()
                yield f"data: Completed! Saved {saved_count} new articles\n\n"
                
                # Get stats
                total = Post.objects.filter(is_auto_fetched=True).count()
                today = Post.objects.filter(
                    is_auto_fetched=True,
                    created_at__date=timezone.now().date()
                ).count()
                
                yield f"data: Total fetched: {total}, Today: {today}\n\n"
                yield "event: close\ndata: \n\n"
                
            except Exception as e:
                yield f"data: Error: {str(e)}\n\n"
                yield "event: close\ndata: \n\n"
        
        response.streaming_content = generate()
        return response
    
    # Normal fetch
    saved_count = fetcher.fetch_all_news()
    
    if saved_count > 0:
        messages.success(request, f'Successfully fetched {saved_count} new articles!')
    else:
        messages.info(request, 'No new articles found.')
    
    return redirect('online_news')



@staff_member_required
def fetch_news_status(request):
    """Get news fetch status and statistics"""
    stats = {
        'total_fetched': Post.objects.filter(is_auto_fetched=True).count(),
        'last_24h': Post.objects.filter(
            is_auto_fetched=True,
            created_at__gte=timezone.now() - timedelta(hours=24)
        ).count(),
        'with_media': Post.objects.filter(
            is_auto_fetched=True,
            has_media=True
        ).count(),
        'verified': Post.objects.filter(
            is_auto_fetched=True,
            verification_status='verified'
        ).count(),
        'fake': Post.objects.filter(
            is_auto_fetched=True,
            verification_status='fake'
        ).count(),
        'pending': Post.objects.filter(
            is_auto_fetched=True,
            verification_status='pending'
        ).count(),
        'categories': list(Post.objects.filter(
            is_auto_fetched=True
        ).values('category__name').annotate(
            count=Count('id')
        ).order_by('-count')[:10]),
    }
    
    return JsonResponse(stats)


# ==================== AUTH VIEWS ====================

def login_view(request):
    """User login with admin detection"""
    if request.user.is_authenticated:
        return redirect('home')  # This will now go to dynamic_home
    
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            
            if user is not None:
                login(request, user)
                
                if user.is_staff or user.is_superuser:
                    messages.success(request, f'Welcome back, Admin {username}!')
                    next_page = request.GET.get('next', 'admin_dashboard')
                else:
                    messages.success(request, f'Welcome back, {username}!')
                    next_page = request.GET.get('next', 'home')  # Goes to dynamic_home
                
                return redirect(next_page)
            else:
                messages.error(request, 'Invalid username or password.')
        else:
            messages.error(request, 'Invalid username or password.')
    else:
        form = AuthenticationForm()
    
    context = {'form': form}
    return render(request, 'registration/login.html', context)



def register_view(request):
    """User registration"""
    if request.user.is_authenticated:
        return redirect('home')  # This will now go to dynamic_home
    
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            
            # Create user profile
            UserProfile.objects.create(user=user)
            
            # Auto login
            login(request, user)
            messages.success(request, 'Registration successful! Welcome to Ojukaye!')
            return redirect('home') 
    else:
        form = UserCreationForm()
    
    context = {'form': form}
    return render(request, 'registration/register.html', context)


def logout_view(request):
    """User logout"""
    auth_logout(request)
    messages.success(request, 'You have been logged out successfully!')
    return redirect('home')




# ==================== STATIC PAGES ====================

def about(request):
    """About page"""
    trending_topics = get_trending_topics()
    return render(request, 'about/about.html', {
        'trending_topics': trending_topics,
        'title': 'About Ojukaye'
    })


def privacy_policy(request):
    """Privacy policy page"""
    trending_topics = get_trending_topics()
    return render(request, 'legal/privacy.html', {
        'trending_topics': trending_topics,
        'title': 'Privacy Policy'
    })


def terms_of_service(request):
    """Terms of service page"""
    trending_topics = get_trending_topics()
    return render(request, 'legal/terms.html', {
        'trending_topics': trending_topics,
        'title': 'Terms of Service'
    })


def help_center(request):
    """Help center"""
    trending_topics = get_trending_topics()
    return render(request, 'help/help.html', {
        'trending_topics': trending_topics,
        'title': 'Help Center'
    })


def contact(request):
    """Contact page"""
    trending_topics = get_trending_topics()
    
    if request.method == 'POST':
        # Handle contact form submission
        name = request.POST.get('name')
        email = request.POST.get('email')
        message = request.POST.get('message')
        
        # You can add email sending logic here
        # send_mail(...)
        
        messages.success(request, 'Thank you for your message. We will get back to you soon!')
        return redirect('contact')
    
    return render(request, 'contact/contact.html', {
        'trending_topics': trending_topics,
        'title': 'Contact Us'
    })


# ==================== CATEGORY VIEWS ====================

def category_view(request, category_slug):
    """View posts by category"""
    category = get_object_or_404(Category, slug=category_slug)
    
    # Get posts in this category
    posts = Post.objects.filter(
        category=category,
        status='published'
    ).select_related('author').order_by('-published_at')
    
    # Get subcategories if any
    subcategories = Category.objects.filter(parent=category)
    
    # If there are subcategories, include their posts too
    if subcategories.exists():
        posts = posts | Post.objects.filter(
            category__in=subcategories,
            status='published'
        ).select_related('author').order_by('-published_at')
    
    # Get filter from query params
    filter_type = request.GET.get('filter', 'latest')
    search_query = request.GET.get('q', '')
    
    # Apply search
    if search_query:
        posts = posts.filter(
            Q(title__icontains=search_query) |
            Q(content__icontains=search_query)
        )
    
    # Apply time filter
    now = timezone.now()
    if filter_type == 'today':
        posts = posts.filter(published_at__date=now.date())
    elif filter_type == 'week':
        posts = posts.filter(published_at__gte=now - timedelta(days=7))
    elif filter_type == 'month':
        posts = posts.filter(published_at__gte=now - timedelta(days=30))
    elif filter_type == 'trending':
        time_threshold = now - timedelta(hours=48)
        posts = posts.filter(
            created_at__gte=time_threshold
        ).annotate(
            like_count=Count('likes'),
            comment_count_val=Count('comments', filter=Q(comments__is_active=True))
        ).annotate(
            engagement=F('like_count') + F('comment_count_val') * 2 + F('views') / 100
        ).order_by('-engagement')
    else:  # latest
        posts = posts.order_by('-published_at')
    
    # Pagination
    paginator = Paginator(posts.distinct(), 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # Get trending topics
    trending_topics = get_trending_topics()
    
    # Get related categories
    related_categories = Category.objects.filter(
        parent=category.parent if category.parent else None
    ).exclude(id=category.id)[:5]
    
    context = {
        'category': category,
        'page_obj': page_obj,
        'posts': page_obj,
        'subcategories': subcategories,
        'related_categories': related_categories,
        'filter_type': filter_type,
        'search_query': search_query,
        'trending_topics': trending_topics,
        'title': f'{category.name} - Ojukaye',
    }
    
    return render(request, 'category.html', context)


# ==================== TRENDING/DISCOVER VIEWS ====================

def trending_posts(request):
    """View trending posts"""
    time_threshold = timezone.now() - timedelta(days=2)
    
    trending = Post.objects.filter(
        status='published',
        created_at__gte=time_threshold
    ).annotate(
        like_count=Count('likes', distinct=True),
        comment_count=Count('comments', filter=Q(comments__is_active=True), distinct=True)
    ).annotate(
        engagement=F('like_count') + F('comment_count') * 2 + F('views') / 100
    ).select_related('author', 'category').order_by('-engagement')[:50]
    
    # Pagination
    paginator = Paginator(trending, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # Get trending topics
    trending_topics = get_trending_topics()
    
    context = {
        'trending_posts': page_obj,
        'page_obj': page_obj,
        'trending_topics': trending_topics,
        'title': 'Trending Posts',
    }
    
    return render(request, 'trending/trending.html', context)


def discover(request):
    """Discover new content and users"""
    # Get suggested users (excluding self and already followed)
    if request.user.is_authenticated:
        following_ids = Follow.objects.filter(follower=request.user).values_list('following_id', flat=True)
        suggested_users = User.objects.exclude(
            Q(id=request.user.id) | Q(id__in=following_ids)
        ).filter(is_active=True).order_by('?')[:10]
    else:
        suggested_users = User.objects.filter(is_active=True).order_by('?')[:10]
    
    # Get trending posts
    time_threshold = timezone.now() - timedelta(days=1)
    trending = Post.objects.filter(
        status='published',
        created_at__gte=time_threshold
    ).select_related('author', 'category').order_by('-views')[:20]
    
    # Get popular categories
    popular_categories = Category.objects.annotate(
        post_count=Count('post', filter=Q(post__status='published'))
    ).filter(post_count__gt=0).order_by('-post_count')[:10]
    
    # Get recent posts
    recent_posts = Post.objects.filter(
        status='published'
    ).select_related('author', 'category').order_by('-published_at')[:20]
    
    # Get trending topics
    trending_topics = get_trending_topics()
    
    context = {
        'suggested_users': suggested_users,
        'trending_posts': trending,
        'popular_categories': popular_categories,
        'recent_posts': recent_posts,
        'trending_topics': trending_topics,
        'title': 'Discover',
    }
    
    return render(request, 'discover/discover.html', context)


# ==================== MESSAGES/SETTINGS ====================

@login_required
def messages_view(request):
    """View messages (placeholder)"""
    trending_topics = get_trending_topics()
    
    return render(request, 'messages/messages.html', {
        'trending_topics': trending_topics,
        'title': 'Messages'
    })


@login_required
def settings_view(request):
    """User settings page"""
    trending_topics = get_trending_topics()
    
    return render(request, 'settings/settings.html', {
        'trending_topics': trending_topics,
        'title': 'Settings'
    })


# ==================== NEWSLETTER ====================

@require_POST
def newsletter_signup(request):
    """Handle newsletter signup"""
    email = request.POST.get('email')
    
    if email:
        # Add to newsletter list logic here
        # NewsletterSubscriber.objects.get_or_create(email=email)
        
        messages.success(request, 'Thank you for subscribing to our newsletter!')
    else:
        messages.error(request, 'Please provide a valid email address.')
    
    # Redirect back to the page they came from
    next_url = request.META.get('HTTP_REFERER', 'home')
    return redirect(next_url)


# ==================== LOAD MORE COMMENTS (AJAX) ====================

@require_GET
def load_more_comments(request, post_id):
    """Load more comments via AJAX"""
    post = get_object_or_404(Post, id=post_id)
    offset = int(request.GET.get('offset', 0))
    limit = 12
    
    comments = Comment.objects.filter(
        post=post,
        parent__isnull=True,
        is_active=True
    ).select_related('user', 'user__profile').order_by('-created_at')[offset:offset + limit]
    
    html = ''
    for comment in comments:
        html += render_comment_html(comment, request.user)
    
    return JsonResponse({
        'html': html,
        'has_more': comments.count() == limit
    })


def render_comment_html(comment, user):
    """Helper function to render comment HTML for AJAX"""
    return render_to_string('includes/comment.html', {
        'comment': comment,
        'user': user
    })


# ==================== TOGGLE DARK MODE ====================

@require_POST
def toggle_dark_mode(request):
    """Toggle dark mode preference"""
    if request.user.is_authenticated:
        request.session['dark_mode'] = not request.session.get('dark_mode', False)
        return JsonResponse({
            'success': True,
            'dark_mode': request.session['dark_mode']
        })
    return JsonResponse({'error': 'Not authenticated'}, status=401)


# ==================== UPDATE PROFILE PICTURE ====================

@login_required
@require_POST
def update_profile_pic(request):
    """Update profile picture via AJAX"""
    if request.FILES.get('profile_pic'):
        profile = request.user.profile
        profile.profile_pic = request.FILES['profile_pic']
        profile.save()
        
        return JsonResponse({
            'success': True,
            'image_url': profile.profile_pic.url
        })
    return JsonResponse({'success': False}, status=400)


@login_required
@require_POST
def update_cover_photo(request):
    """Update cover photo via AJAX"""
    if request.FILES.get('cover_photo'):
        profile = request.user.profile
        profile.cover_photo = request.FILES['cover_photo']
        profile.save()
        
        return JsonResponse({
            'success': True,
            'image_url': profile.cover_photo.url
        })
    return JsonResponse({'success': False}, status=400)


# ==================== ADMIN VIEWS ====================

@staff_member_required
def admin_dashboard(request):
    """Enhanced admin dashboard with accurate statistics"""
    from django.utils import timezone
    from datetime import timedelta
    
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Calculate statistics
    total_posts = Post.objects.count()
    total_users = User.objects.count()
    
    # News statistics
    pending_news = Post.objects.filter(
        is_news_submission=True,
        submission_status='pending'
    ).count()
    
    auto_fetched = Post.objects.filter(is_auto_fetched=True).count()
    auto_fetched_today = Post.objects.filter(
        is_auto_fetched=True,
        created_at__gte=today_start
    ).count()
    
    # Verification statistics
    verified_posts = Post.objects.filter(verification_status='verified').count()
    fake_posts = Post.objects.filter(verification_status='fake').count()
    pending_verification = Post.objects.filter(verification_status='pending').count()
    
    # Posts today
    posts_today = Post.objects.filter(created_at__gte=today_start).count()
    users_today = User.objects.filter(date_joined__gte=today_start).count()
    
    # Calculate percentages
    verified_percent = 0
    fake_percent = 0
    if total_posts > 0:
        verified_percent = round((verified_posts / total_posts) * 100, 1)
        fake_percent = round((fake_posts / total_posts) * 100, 1)
    
    # Recent activities
    recent_activities = UserActivity.objects.select_related(
        'user', 'post', 'target_user'
    ).order_by('-created_at')[:15]
    
    # Pending submissions (latest 5)
    pending_submissions = Post.objects.filter(
        is_news_submission=True,
        submission_status='pending'
    ).select_related('author').order_by('-created_at')[:5]
    
    # Recent users (latest 5)
    recent_users = User.objects.filter(is_active=True).order_by('-date_joined')[:5]
    
    # FIXED: Changed 'post' to 'posts' in the Count filter
    top_categories = Category.objects.annotate(
        post_count=Count('posts', filter=Q(posts__status='published'))
    ).filter(post_count__gt=0).order_by('-post_count')[:5]
    
    # Calculate percentages for categories
    for category in top_categories:
        if total_posts > 0:
            category.percentage = round((category.post_count / total_posts) * 100, 1)
        else:
            category.percentage = 0
    
    # Additional stats
    total_comments = Comment.objects.filter(is_active=True).count()
    total_groups = Group.objects.count()
    total_ads = Advertisement.objects.count()
    total_categories = Category.objects.count()
    
    # News with media
    news_with_media = Post.objects.filter(
        post_type__in=['news', 'user_news'],
        has_media=True
    ).count()
    
    # User submitted news
    user_submitted = Post.objects.filter(
        is_news_submission=True
    ).count()
    
    # Unique news sources
    news_sources = Post.objects.filter(
        is_auto_fetched=True
    ).exclude(
        external_source__isnull=True
    ).exclude(
        external_source=''
    ).values('external_source').distinct().count()
    
    # Average verification score
    avg_verification_score = Post.objects.filter(
        verification_score__isnull=False
    ).aggregate(avg=Avg('verification_score'))['avg'] or 0
    
    trending_topics = get_trending_topics()
    
    context = {
        # Main stats
        'total_posts': total_posts,
        'total_users': total_users,
        'pending_news': pending_news,
        'auto_fetched': auto_fetched,
        'verified_posts': verified_posts,
        'fake_posts': fake_posts,
        
        # Additional stats
        'posts_today': posts_today,
        'users_today': users_today,
        'verified_percent': verified_percent,
        'fake_percent': fake_percent,
        'auto_fetched_today': auto_fetched_today,
        'pending_verification': pending_verification,
        
        # Lists
        'recent_activities': recent_activities,
        'pending_submissions': pending_submissions,
        'recent_users': recent_users,
        'top_categories': top_categories,
        
        # System stats
        'total_comments': total_comments,
        'total_groups': total_groups,
        'total_ads': total_ads,
        'total_categories': total_categories,
        'news_with_media': news_with_media,
        'user_submitted': user_submitted,
        'news_sources': news_sources,
        'avg_verification_score': avg_verification_score,
        
        'trending_topics': trending_topics,
        'is_admin': True,
        'title': 'Admin Dashboard',
    }
    
    return render(request, 'admin/dashboard.html', context)


@staff_member_required
def admin_posts(request):
    """Admin post management"""
    posts = Post.objects.select_related('author', 'category').order_by('-created_at')
    
    # Filtering
    filter_type = request.GET.get('filter', 'all')
    search_query = request.GET.get('q', '')
    category_id = request.GET.get('category', '')
    post_type = request.GET.get('type', '')
    verification = request.GET.get('verification', '')
    
    if filter_type == 'pending':
        posts = posts.filter(verification_status='pending')
    elif filter_type == 'verified':
        posts = posts.filter(verification_status='verified')
    elif filter_type == 'fake':
        posts = posts.filter(verification_status='fake')
    elif filter_type == 'news':
        posts = posts.filter(post_type__in=['news', 'user_news'])
    elif filter_type == 'discussion':
        posts = posts.filter(post_type='discussion')
    elif filter_type == 'profile':
        posts = posts.filter(post_type='profile_post')
    elif filter_type == 'featured':
        posts = posts.filter(is_featured=True)
    elif filter_type == 'sponsored':
        posts = posts.filter(is_sponsored=True)
    elif filter_type == 'banner':
        posts = posts.filter(is_banner=True)
    
    # Category filter
    if category_id and category_id.isdigit():
        posts = posts.filter(category_id=int(category_id))
    
    # Post type filter
    if post_type:
        posts = posts.filter(post_type=post_type)
    
    # Verification filter
    if verification:
        posts = posts.filter(verification_status=verification)
    
    # Search
    if search_query:
        posts = posts.filter(
            Q(title__icontains=search_query) |
            Q(content__icontains=search_query) |
            Q(author__username__icontains=search_query) |
            Q(external_source__icontains=search_query)
        )
    
    # Statistics
    stats = {
        'total_posts': Post.objects.count(),
        'verified_posts': Post.objects.filter(verification_status='verified').count(),
        'pending_verification': Post.objects.filter(verification_status='pending').count(),
        'fake_posts': Post.objects.filter(verification_status='fake').count(),
        'news_posts': Post.objects.filter(post_type__in=['news', 'user_news']).count(),
        'featured_posts': Post.objects.filter(is_featured=True).count(),
    }
    
    # Categories for filter dropdown
    categories = Category.objects.all()
    
    # Pagination
    paginator = Paginator(posts, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    trending_topics = get_trending_topics()
    
    context = {
        'posts': page_obj,
        'page_obj': page_obj,
        'stats': stats,
        'filter_type': filter_type,
        'search_query': search_query,
        'selected_category': category_id,
        'post_type': post_type,
        'verification': verification,
        'categories': categories,
        'trending_topics': trending_topics,
        'is_admin': True,
        'title': 'Manage Posts',
    }
    
    return render(request, 'admin/posts.html', context)


@staff_member_required
def admin_system_settings(request):
    """Admin system settings control panel"""
    system_settings, created = SystemSettings.objects.get_or_create(id=1)
    
    if request.method == 'POST':
        form = SystemSettingsForm(request.POST, instance=system_settings)
        if form.is_valid():
            form.save()
            messages.success(request, 'System settings updated successfully!')
            return redirect('admin_system_settings')
    else:
        form = SystemSettingsForm(instance=system_settings)
    
    context = {
        'form': form,
        'settings': system_settings,
        'title': 'System Settings',
    }
    return render(request, 'admin/system_settings.html', context)


@staff_member_required
def admin_news_submissions(request):
    """Admin view for managing news submissions"""
    filter_type = request.GET.get('filter', 'pending')
    search_query = request.GET.get('q', '')
    
    # FIX: Make sure we're getting ALL user-submitted news
    # Either post_type='user_news' OR is_news_submission=True
    submissions = Post.objects.filter(
        Q(post_type='user_news') | Q(is_news_submission=True)
    ).select_related('author', 'category', 'reviewed_by').order_by('-created_at')
    
    # Apply filters
    if filter_type == 'pending':
        submissions = submissions.filter(submission_status='pending')
    elif filter_type == 'approved':
        submissions = submissions.filter(submission_status='approved')
    elif filter_type == 'rejected':
        submissions = submissions.filter(submission_status='rejected')
    elif filter_type == 'flagged':
        submissions = submissions.filter(submission_status='flagged')
    
    # Search
    if search_query:
        submissions = submissions.filter(
            Q(title__icontains=search_query) |
            Q(content__icontains=search_query) |
            Q(author__username__icontains=search_query) |
            Q(external_source__icontains=search_query)
        )
    
    # Statistics
    stats = {
        'pending': Post.objects.filter(
            Q(post_type='user_news') | Q(is_news_submission=True),
            submission_status='pending'
        ).count(),
        'approved': Post.objects.filter(
            Q(post_type='user_news') | Q(is_news_submission=True),
            submission_status='approved'
        ).count(),
        'rejected': Post.objects.filter(
            Q(post_type='user_news') | Q(is_news_submission=True),
            submission_status='rejected'
        ).count(),
        'flagged': Post.objects.filter(
            Q(post_type='user_news') | Q(is_news_submission=True),
            submission_status='flagged'
        ).count(),
    }
    
    # Pagination
    paginator = Paginator(submissions, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    context = {
        'submissions': page_obj,
        'page_obj': page_obj,
        'stats': stats,
        'filter_type': filter_type,
        'search_query': search_query,
        'title': 'News Submissions',
    }
    
    return render(request, 'admin/news_submissions.html', context)

@staff_member_required
def admin_auto_fetched_news(request):
    """Admin view for managing auto-fetched news"""
    filter_type = request.GET.get('filter', 'all')
    search_query = request.GET.get('q', '')
    source_filter = request.GET.get('source', '')
    
    # Base queryset - auto-fetched news
    news = Post.objects.filter(
        is_auto_fetched=True
    ).select_related('category').order_by('-created_at')
    
    # Apply filters
    if filter_type == 'verified':
        news = news.filter(verification_status='verified')
    elif filter_type == 'fake':
        news = news.filter(verification_status='fake')
    elif filter_type == 'pending':
        news = news.filter(verification_status='pending')
    elif filter_type == 'with_media':
        news = news.filter(has_media=True)
    
    # Source filter
    if source_filter:
        news = news.filter(external_source__icontains=source_filter)
    
    # Search
    if search_query:
        news = news.filter(
            Q(title__icontains=search_query) |
            Q(content__icontains=search_query) |
            Q(external_source__icontains=search_query)
        )
    
    # Get all sources for filter dropdown
    all_sources = Post.objects.filter(
        is_auto_fetched=True
    ).exclude(
        external_source__isnull=True
    ).exclude(
        external_source=''
    ).values_list('external_source', flat=True).distinct().order_by('external_source')
    
    # Statistics
    stats = {
        'total': Post.objects.filter(is_auto_fetched=True).count(),
        'verified': Post.objects.filter(is_auto_fetched=True, verification_status='verified').count(),
        'fake': Post.objects.filter(is_auto_fetched=True, verification_status='fake').count(),
        'pending': Post.objects.filter(is_auto_fetched=True, verification_status='pending').count(),
        'with_media': Post.objects.filter(is_auto_fetched=True, has_media=True).count(),
    }
    
    # Pagination
    paginator = Paginator(news, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    context = {
        'news': page_obj,
        'page_obj': page_obj,
        'stats': stats,
        'filter_type': filter_type,
        'source_filter': source_filter,
        'search_query': search_query,
        'all_sources': all_sources,
        'title': 'Auto-Fetched News',
    }
    
    return render(request, 'admin/auto_fetched_news.html', context)


@staff_member_required
def get_fetcher_status(request):
    """Get current fetcher status and configuration"""
    try:
        # Get current auto-fetcher status from cache or autostart
        status = {
            'running': auto_fetcher._running if hasattr(auto_fetcher, '_running') else False,
            'test_mode': getattr(auto_fetcher, 'TEST_MODE', False),
            'prod_interval': getattr(auto_fetcher, 'prod_interval', 12),
            'prod_unit': getattr(auto_fetcher, 'prod_unit', 'hours'),
            'prod_days': getattr(auto_fetcher, 'prod_days', 1),
            'prod_limit': getattr(auto_fetcher, 'prod_limit', 100),
            'prod_workers': getattr(auto_fetcher, 'prod_workers', 5),
            'test_interval': getattr(auto_fetcher, 'test_interval', 5),
            'test_unit': getattr(auto_fetcher, 'test_unit', 'minutes'),
            'test_days': getattr(auto_fetcher, 'test_days', 1),
            'test_limit': getattr(auto_fetcher, 'test_limit', 20),
            'test_workers': getattr(auto_fetcher, 'test_workers', 2),
            'last_fetch': cache.get('last_fetch_time', 'Never'),
            'next_fetch': cache.get('next_fetch_time', 'Not scheduled'),
            'fetch_count': getattr(auto_fetcher, 'fetch_count', 0),
        }
        
        # Format interval for display
        if status['test_mode']:
            interval = status['test_interval']
            unit = status['test_unit']
        else:
            interval = status['prod_interval']
            unit = status['prod_unit']
        
        if unit == 'seconds':
            status['interval_display'] = f"Every {interval} seconds"
        elif unit == 'minutes':
            status['interval_display'] = f"Every {interval} minutes"
        else:
            status['interval_display'] = f"Every {interval} hours"
        
        return JsonResponse({'status': 'success', 'data': status})
    
    except Exception as e:
        logger.error(f"Error getting fetcher status: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)})


@staff_member_required
def save_fetcher_settings(request):
    """Save auto-fetcher settings"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Method not allowed'})
    
    try:
        # Get settings from POST
        test_mode = request.POST.get('test_mode') == 'true'
        
        # Production settings
        prod_interval = int(request.POST.get('prod_interval', 12))
        prod_unit = request.POST.get('prod_unit', 'hours')
        prod_days = int(request.POST.get('prod_days', 1))
        prod_limit = int(request.POST.get('prod_limit', 100))
        prod_workers = int(request.POST.get('prod_workers', 5))
        
        # Test settings
        test_interval = int(request.POST.get('test_interval', 5))
        test_unit = request.POST.get('test_unit', 'minutes')
        test_days = int(request.POST.get('test_days', 1))
        test_limit = int(request.POST.get('test_limit', 20))
        test_workers = int(request.POST.get('test_workers', 2))
        
        # Validate settings
        if prod_interval < 1:
            return JsonResponse({'status': 'error', 'message': 'Production interval must be at least 1'})
        if test_interval < 1:
            return JsonResponse({'status': 'error', 'message': 'Test interval must be at least 1'})
        if prod_limit > 500:
            return JsonResponse({'status': 'error', 'message': 'Production limit cannot exceed 500'})
        if test_limit > 200:
            return JsonResponse({'status': 'error', 'message': 'Test limit cannot exceed 200'})
        
        # Save to auto_fetcher instance
        auto_fetcher.TEST_MODE = test_mode
        auto_fetcher.prod_interval = prod_interval
        auto_fetcher.prod_unit = prod_unit
        auto_fetcher.prod_days = prod_days
        auto_fetcher.prod_limit = prod_limit
        auto_fetcher.prod_workers = prod_workers
        auto_fetcher.test_interval = test_interval
        auto_fetcher.test_unit = test_unit
        auto_fetcher.test_days = test_days
        auto_fetcher.test_limit = test_limit
        auto_fetcher.test_workers = test_workers
        
        # Update fetch interval
        if test_mode:
            auto_fetcher.fetch_interval = auto_fetcher._convert_to_seconds(test_interval, test_unit)
            auto_fetcher.days_to_fetch = test_days
            auto_fetcher.limit = test_limit
            auto_fetcher.workers = test_workers
        else:
            auto_fetcher.fetch_interval = auto_fetcher._convert_to_seconds(prod_interval, prod_unit)
            auto_fetcher.days_to_fetch = prod_days
            auto_fetcher.limit = prod_limit
            auto_fetcher.workers = prod_workers
        
        # Save to cache for persistence
        cache.set('auto_fetcher_settings', {
            'test_mode': test_mode,
            'prod_interval': prod_interval,
            'prod_unit': prod_unit,
            'prod_days': prod_days,
            'prod_limit': prod_limit,
            'prod_workers': prod_workers,
            'test_interval': test_interval,
            'test_unit': test_unit,
            'test_days': test_days,
            'test_limit': test_limit,
            'test_workers': test_workers,
        }, timeout=None)  # Never expire
        
        # Log the change
        FetchLog.objects.create(
            action='settings_update',
            details=f"Updated fetcher settings: Mode={'test' if test_mode else 'production'}"
        )
        
        return JsonResponse({
            'status': 'success',
            'message': 'Settings saved successfully!',
            'interval_display': auto_fetcher._format_interval(auto_fetcher.fetch_interval)
        })
    
    except Exception as e:
        logger.error(f"Error saving fetcher settings: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)})


@staff_member_required
def toggle_auto_fetcher(request):
    """Start or stop the auto-fetcher"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Method not allowed'})
    
    try:
        action = request.POST.get('action', 'toggle')
        
        if action == 'start':
            if not auto_fetcher._running:
                auto_fetcher.start()
                message = 'Auto-fetcher started successfully!'
            else:
                message = 'Auto-fetcher is already running'
        
        elif action == 'stop':
            if auto_fetcher._running:
                auto_fetcher.stop()
                message = 'Auto-fetcher stopped successfully!'
            else:
                message = 'Auto-fetcher is already stopped'
        
        elif action == 'restart':
            if auto_fetcher._running:
                auto_fetcher.stop()
                time.sleep(2)
            auto_fetcher.start()
            message = 'Auto-fetcher restarted successfully!'
        
        else:
            # Toggle
            if auto_fetcher._running:
                auto_fetcher.stop()
                message = 'Auto-fetcher stopped'
            else:
                auto_fetcher.start()
                message = 'Auto-fetcher started'
        
        # Log the action
        FetchLog.objects.create(
            action=f'auto_fetcher_{action}',
            details=message
        )
        
        return JsonResponse({
            'status': 'success',
            'message': message,
            'running': auto_fetcher._running
        })
    
    except Exception as e:
        logger.error(f"Error toggling auto-fetcher: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)})


@staff_member_required
def trigger_manual_fetch(request):
    """Trigger an immediate manual fetch"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Method not allowed'})
    
    try:
        # Get parameters
        days = int(request.POST.get('days', 1))
        limit = int(request.POST.get('limit', 50))
        workers = int(request.POST.get('workers', 5))
        sources = request.POST.get('sources', 'all')
        extract_full = request.POST.get('extract_full') == 'true'
        
        # Start fetch in background (or return task ID for polling)
        from .tasks import fetch_news_task
        task = fetch_news_task.delay(days, limit, workers, sources, extract_full)
        
        return JsonResponse({
            'status': 'started',
            'message': 'Fetch started in background',
            'task_id': task.id
        })
    
    except Exception as e:
        logger.error(f"Error triggering manual fetch: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)})



@staff_member_required
def quick_fetch_news(request):
    """Enhanced admin panel for quick news fetching with full controls"""
    from .news_fetcher_unified import UnifiedNewsFetcher
    from django.conf import settings
    import hashlib
    import random
    
    # Get API key
    api_key = getattr(settings, 'NEWS_API_KEY', '')
    
    # Handle AJAX fetch request
    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            # Get fetch parameters
            days = int(request.POST.get('days', 1))
            limit = int(request.POST.get('limit', 50))
            workers = int(request.POST.get('workers', 5))
            sources = request.POST.get('sources', 'all')
            content_type = request.POST.get('content_type', 'all')
            extract_full = request.POST.get('extract_full') == 'true'
            
            # Initialize fetcher
            fetcher = UnifiedNewsFetcher()
            
            response_data = {
                'status': 'started',
                'message': 'Starting fetch...',
                'logs': []
            }
            
            # Log start
            response_data['logs'].append(f'🚀 Starting fetch at {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
            response_data['logs'].append(f'📅 Days: {days}, Limit: {limit}, Workers: {workers}')
            response_data['logs'].append(f'📡 Sources: {sources}, Extract Full: {extract_full}')
            
            # Fetch based on sources
            all_articles = []
            
            if sources in ['all', 'newsapi']:
                response_data['logs'].append('📰 Fetching from NewsAPI...')
                newsapi_articles = fetcher.fetch_from_newsapi(api_key, days=days, limit=limit // 2)
                all_articles.extend(newsapi_articles)
                response_data['logs'].append(f'   ✅ Found {len(newsapi_articles)} articles from NewsAPI')
            
            if sources in ['all', 'rss']:
                response_data['logs'].append('📡 Fetching from RSS feeds...')
                rss_articles = fetcher.fetch_from_rss(limit=limit // 2)
                all_articles.extend(rss_articles)
                response_data['logs'].append(f'   ✅ Found {len(rss_articles)} articles from RSS')
            
            if not all_articles:
                return JsonResponse({
                    'status': 'error',
                    'message': 'No articles found from any source',
                    'logs': response_data['logs'] + ['❌ No articles found!']
                })
            
            # Remove duplicates
            response_data['logs'].append('🔍 Removing duplicates...')
            unique_articles = fetcher.remove_duplicates(all_articles)
            response_data['logs'].append(f'   ✅ {len(unique_articles)} unique articles (removed {len(all_articles) - len(unique_articles)} duplicates)')
            
            # Filter by content type
            if content_type != 'all':
                filtered_articles = []
                response_data['logs'].append(f'🔍 Filtering by content type: {content_type}...')
                
                # First, do quick checks on existing data
                for article in unique_articles:
                    if content_type == 'with_video':
                        if article.get('has_video') or 'youtube' in article.get('url', '').lower():
                            filtered_articles.append(article)
                    elif content_type == 'with_audio':
                        if article.get('has_audio'):
                            filtered_articles.append(article)
                    elif content_type == 'with_images':
                        if article.get('image') or article.get('has_images'):
                            filtered_articles.append(article)
                    elif content_type == 'text_only':
                        if not (article.get('has_video') or article.get('has_audio')):
                            filtered_articles.append(article)
                
                # If we need to check deeper and extract full content
                if len(filtered_articles) < len(unique_articles) * 0.1 and extract_full:
                    response_data['logs'].append('   ⚠️ Not enough matches, doing deeper extraction...')
                    # Process a sample to check
                    sample = unique_articles[:min(10, len(unique_articles))]
                    processed = fetcher.process_articles_parallel(sample, max_workers=2, extract_full=True)
                    
                    for i, article in enumerate(unique_articles):
                        if i < len(processed) and processed[i].get('videos'):
                            filtered_articles.append(article)
                
                if filtered_articles:
                    unique_articles = filtered_articles
                    response_data['logs'].append(f'   ✅ Filtered to {len(unique_articles)} articles based on content type')
                else:
                    response_data['logs'].append('   ⚠️ No matches found, using all articles')
            
            # Extract content if requested
            if extract_full and unique_articles:
                response_data['logs'].append('🔍 Extracting full content and media...')
                response_data['logs'].append(f'   Using {workers} worker threads...')
                
                processed_articles = fetcher.process_articles_parallel(
                    unique_articles, 
                    max_workers=workers,
                    extract_full=True
                )
                
                # Count media
                total_videos = sum(len(a.get('videos', [])) for a in processed_articles)
                total_audio = sum(len(a.get('audios', [])) for a in processed_articles)
                total_images = sum(len(a.get('images', [])) for a in processed_articles)
                
                response_data['logs'].append(f'   ✅ Extraction complete!')
                response_data['logs'].append(f'      📹 Videos: {total_videos}')
                response_data['logs'].append(f'      🎵 Audio: {total_audio}')
                response_data['logs'].append(f'      🖼️  Images: {total_images}')
            else:
                processed_articles = unique_articles
            
            # Save to database
            response_data['logs'].append('💾 Saving to database...')
            saved_count = 0
            media_stats = {'videos': 0, 'audio': 0, 'images': 0}
            
            # Get or create system user
            try:
                system_user = User.objects.get(username='news_bot')
            except User.DoesNotExist:
                system_user = User.objects.create_user(
                    username='news_bot',
                    email='news@ojukaye.com',
                    password='NewsBot123!',
                    first_name='News',
                    last_name='Bot',
                    is_active=False
                )
            
            for article in processed_articles:
                try:
                    title = article.get('title', '').strip()
                    url = article.get('url', '').strip()
                    
                    if not title or not url:
                        continue
                    
                    # Check if exists
                    if Post.objects.filter(external_url=url).exists():
                        continue
                    
                    # Generate ID
                    external_id = hashlib.md5(url.encode()).hexdigest()
                    
                    # Get content
                    content = article.get('full_content') or article.get('description') or article.get('content') or title
                    content = fetcher.clean_html(content)[:15000]
                    
                    # Get category
                    category_name = fetcher.detect_category(title, content)
                    category, _ = Category.objects.get_or_create(
                        name=category_name,
                        defaults={'slug': category_name.lower().replace(' ', '-')}
                    )
                    
                    # Parse date
                    published_at = fetcher.parse_date(article.get('published_at'))
                    
                    # Get media
                    videos = article.get('videos', [])
                    audios = article.get('audios', [])
                    images = article.get('images', [])
                    main_image = article.get('image') or article.get('main_image') or (images[0]['url'] if images else '')
                    
                    # Create post
                    post = Post.objects.create(
                        title=title[:200],
                        content=content,
                        post_type='news',
                        category=category,
                        author=system_user,
                        external_source=article.get('source', 'Unknown')[:100],
                        external_url=url[:500],
                        external_id=external_id,
                        image_url=main_image[:1000] if main_image else '',
                        published_at=published_at,
                        status='published',
                        is_auto_fetched=True,
                        is_approved=True,
                        verification_status='pending',
                        meta_description=content[:160] if content else title[:160],
                        video_urls=videos if videos else None,
                        audio_urls=audios if audios else None,
                        has_media=bool(videos or audios),
                        views=random.randint(10, 100)
                    )
                    
                    saved_count += 1
                    media_stats['videos'] += len(videos)
                    media_stats['audio'] += len(audios)
                    media_stats['images'] += len(images)
                    
                except Exception as e:
                    logger.error(f"Error saving article: {e}")
                    continue
            
            response_data['logs'].append(f'   ✅ Saved {saved_count} articles')
            response_data['logs'].append(f'      📹 Videos: {media_stats["videos"]}')
            response_data['logs'].append(f'      🎵 Audio: {media_stats["audio"]}')
            response_data['logs'].append(f'      🖼️  Images: {media_stats["images"]}')
            response_data['logs'].append(f'✅ Fetch completed at {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
            
            # Create fetch log
            FetchLog.objects.create(
                action='manual_fetch',
                details=f"Fetched {saved_count} articles ({media_stats['videos']} videos, {media_stats['audio']} audio)",
                user=request.user
            )
            
            return JsonResponse({
                'status': 'success',
                'message': f'Successfully fetched {saved_count} articles!',
                'logs': response_data['logs'],
                'stats': {
                    'saved': saved_count,
                    'videos': media_stats['videos'],
                    'audio': media_stats['audio'],
                    'images': media_stats['images']
                }
            })
            
        except Exception as e:
            logger.error(f"Error in quick fetch: {e}")
            return JsonResponse({
                'status': 'error',
                'message': str(e),
                'logs': response_data.get('logs', []) + [f'❌ Error: {str(e)}']
            })
    
    # Get current stats
    stats = {
        'total_fetched': Post.objects.filter(is_auto_fetched=True).count(),
        'last_24h': Post.objects.filter(
            is_auto_fetched=True,
            created_at__gte=timezone.now() - timedelta(hours=24)
        ).count(),
        'with_video': Post.objects.filter(
            is_auto_fetched=True,
            has_media=True
        ).exclude(video_urls__isnull=True).count(),
        'with_audio': Post.objects.filter(
            is_auto_fetched=True,
            has_media=True
        ).exclude(audio_urls__isnull=True).count(),
        'verified': Post.objects.filter(
            is_auto_fetched=True,
            verification_status='verified'
        ).count(),
    }
    
    # Get auto-fetcher status
    fetcher_status = {
        'running': auto_fetcher._running if hasattr(auto_fetcher, '_running') else False,
        'test_mode': getattr(auto_fetcher, 'TEST_MODE', False),
        'prod_interval': getattr(auto_fetcher, 'prod_interval', 12),
        'prod_unit': getattr(auto_fetcher, 'prod_unit', 'hours'),
        'prod_days': getattr(auto_fetcher, 'prod_days', 1),
        'prod_limit': getattr(auto_fetcher, 'prod_limit', 100),
        'prod_workers': getattr(auto_fetcher, 'prod_workers', 5),
        'test_interval': getattr(auto_fetcher, 'test_interval', 5),
        'test_unit': getattr(auto_fetcher, 'test_unit', 'minutes'),
        'test_days': getattr(auto_fetcher, 'test_days', 1),
        'test_limit': getattr(auto_fetcher, 'test_limit', 20),
        'test_workers': getattr(auto_fetcher, 'test_workers', 2),
        'last_fetch': cache.get('last_fetch_time', 'Never'),
        'next_fetch': cache.get('next_fetch_time', 'Not scheduled'),
    }
    
    # Format interval for display
    if fetcher_status['test_mode']:
        interval = fetcher_status['test_interval']
        unit = fetcher_status['test_unit']
    else:
        interval = fetcher_status['prod_interval']
        unit = fetcher_status['prod_unit']
    
    if unit == 'seconds':
        fetcher_status['interval_display'] = f"Every {interval} seconds"
    elif unit == 'minutes':
        fetcher_status['interval_display'] = f"Every {interval} minutes"
    else:
        fetcher_status['interval_display'] = f"Every {interval} hours"
    
    # Get recent fetch logs
    recent_logs = FetchLog.objects.all().order_by('-created_at')[:10]
    
    context = {
        'stats': stats,
        'api_key_exists': bool(api_key),
        'auto_fetcher_status': fetcher_status,
        'recent_logs': recent_logs,
        'title': 'News Fetch Control Center',
    }
    
    return render(request, 'admin/quick_fetch.html', context)


# ============================================================================
# FETCH LOGS & HISTORY
# ============================================================================

@staff_member_required
def get_fetch_logs(request):
    """Get fetch logs"""
    try:
        days = int(request.GET.get('days', 7))
        limit = int(request.GET.get('limit', 50))
        
        logs = FetchLog.objects.filter(
            created_at__gte=timezone.now() - timedelta(days=days)
        ).order_by('-created_at')[:limit]
        
        data = [{
            'action': log.action,
            'details': log.details,
            'user': log.user.username if log.user else 'System',
            'created_at': log.created_at.strftime('%Y-%m-%d %H:%M:%S')
        } for log in logs]
        
        return JsonResponse({'status': 'success', 'logs': data})
    
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@staff_member_required
def clear_fetch_logs(request):
    """Clear fetch logs"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Method not allowed'})
    
    try:
        # Keep only last 30 days
        cutoff = timezone.now() - timedelta(days=30)
        deleted = FetchLog.objects.filter(created_at__lt=cutoff).delete()
        
        return JsonResponse({
            'status': 'success',
            'message': f'Cleared {deleted[0]} old logs'
        })
    
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# ============================================================================
# SCHEDULE MANAGEMENT
# ============================================================================

@staff_member_required
def get_fetch_schedule(request):
    """Get upcoming fetch schedule"""
    try:
        # Calculate next 5 fetch times
        schedule = []
        if auto_fetcher._running:
            current_time = timezone.now()
            interval = auto_fetcher.fetch_interval
            
            for i in range(5):
                next_time = current_time + timedelta(seconds=interval * (i + 1))
                schedule.append({
                    'time': next_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'type': 'Auto Fetch',
                    'status': 'scheduled'
                })
        
        return JsonResponse({'status': 'success', 'schedule': schedule})
    
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@staff_member_required
def add_scheduled_fetch(request):
    """Add a custom scheduled fetch"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Method not allowed'})
    
    try:
        fetch_time = request.POST.get('fetch_time')
        fetch_type = request.POST.get('fetch_type', 'auto')
        days = int(request.POST.get('days', 1))
        limit = int(request.POST.get('limit', 50))
        
        # Create schedule
        schedule = FetchSchedule.objects.create(
            scheduled_time=fetch_time,
            fetch_type=fetch_type,
            days=days,
            limit=limit,
            created_by=request.user
        )
        
        return JsonResponse({
            'status': 'success',
            'message': f'Scheduled fetch at {fetch_time}',
            'id': schedule.id
        })
    
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@staff_member_required
def clear_fetch_schedule(request):
    """Clear all scheduled fetches"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Method not allowed'})
    
    try:
        # Clear all future schedules
        deleted = FetchSchedule.objects.filter(
            scheduled_time__gte=timezone.now(),
            completed=False
        ).delete()
        
        return JsonResponse({
            'status': 'success',
            'message': f'Cleared {deleted[0]} scheduled fetches'
        })
    
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# ============================================================================
# FETCH STATISTICS
# ============================================================================

@staff_member_required
def get_fetch_statistics(request):
    """Get detailed fetch statistics"""
    try:
        from django.db.models import Count
        from django.db.models.functions import TruncDate
        
        # Fetch counts by day
        daily_fetches = Post.objects.filter(
            is_auto_fetched=True,
            created_at__gte=timezone.now() - timedelta(days=30)
        ).annotate(
            date=TruncDate('created_at')
        ).values('date').annotate(
            count=Count('id')
        ).order_by('date')
        
        # Source breakdown
        sources = Post.objects.filter(
            is_auto_fetched=True
        ).values('external_source').annotate(
            count=Count('id')
        ).order_by('-count')[:10]
        
        # Category breakdown
        categories = Post.objects.filter(
            is_auto_fetched=True
        ).values('category__name').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Media statistics
        media_stats = {
            'with_video': Post.objects.filter(is_auto_fetched=True).exclude(video_urls__isnull=True).count(),
            'with_audio': Post.objects.filter(is_auto_fetched=True).exclude(audio_urls__isnull=True).count(),
            'with_images': Post.objects.filter(is_auto_fetched=True).exclude(image_url='').count(),
        }
        
        return JsonResponse({
            'status': 'success',
            'data': {
                'daily': list(daily_fetches),
                'sources': list(sources),
                'categories': list(categories),
                'media': media_stats,
                'total': Post.objects.filter(is_auto_fetched=True).count()
            }
        })
    
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

@staff_member_required
def admin_news_detail(request, post_id):
    """Admin view for reviewing a specific news submission"""
    post = get_object_or_404(Post, id=post_id)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        notes = request.POST.get('notes', '')
        rejection_reason = request.POST.get('rejection_reason', '')
        
        if action == 'approve':
            post.submission_status = 'approved'
            post.status = 'published'
            post.reviewed_by = request.user
            post.reviewed_at = timezone.now()
            post.review_notes = notes
            post.save()
            
            # Create notification for user
            from .models import Notification
            Notification.objects.create(
                user=post.author,
                notification_type='news_approved',
                message=f'Your news article "{post.title}" has been approved and published!',
                post=post
            )
            
            messages.success(request, f'News article "{post.title}" approved and published!')
            
        elif action == 'reject':
            post.submission_status = 'rejected'
            post.status = 'draft'
            post.reviewed_by = request.user
            post.reviewed_at = timezone.now()
            post.rejection_reason = rejection_reason or 'Not suitable for publication'
            post.save()
            
            # Create notification for user
            from .models import Notification
            Notification.objects.create(
                user=post.author,
                notification_type='news_rejected',
                message=f'Your news article "{post.title}" was rejected. Reason: {post.rejection_reason}',
                post=post
            )
            
            messages.warning(request, f'News article "{post.title}" rejected.')
            
        elif action == 'run_ai':
            # Run AI verification
            from .news_verifier import process_news_submission
            process_news_submission(post)
            messages.success(request, f'AI verification completed. Score: {post.verification_score}')
        
        return redirect('admin_news_submissions')
    
    context = {
        'post': post,
        'title': f'Review: {post.title}',
    }
    return render(request, 'admin/news_review.html', context)


@staff_member_required
def admin_bulk_news_action(request):
    """Bulk actions for news submissions"""
    if request.method != 'POST':
        return redirect('admin_news_submissions')
    
    action = request.POST.get('bulk_action')
    post_ids = request.POST.getlist('post_ids')
    
    if not post_ids:
        messages.error(request, 'No posts selected')
        return redirect('admin_news_submissions')
    
    posts = Post.objects.filter(id__in=post_ids)
    
    if action == 'approve':
        for post in posts:
            post.submission_status = 'approved'
            post.status = 'published'
            post.save()
        messages.success(request, f'{posts.count()} posts approved')
        
    elif action == 'reject':
        for post in posts:
            post.submission_status = 'rejected'
            post.status = 'draft'
            post.save()
        messages.success(request, f'{posts.count()} posts rejected')
        
    elif action == 'run_ai':
        from .news_verifier import process_news_submission
        for post in posts:
            process_news_submission(post)
        messages.success(request, f'AI verification run for {posts.count()} posts')
    
    return redirect('admin_news_submissions')


# ==================== BUSINESS/ADVERTISING VIEWS ====================

@login_required
def business_registration(request):
    """Business account registration/upgrade"""
    if request.user.profile.account_type == 'business':
        messages.info(request, 'You already have a business account')
        return redirect('profile_view', username=request.user.username)
    
    trending_topics = get_trending_topics()
    
    if request.method == 'POST':
        form = BusinessProfileForm(request.POST, request.FILES, instance=request.user.profile)
        if form.is_valid():
            profile = form.save(commit=False)
            profile.account_type = 'business'
            profile.save()
            
            # Create activity
            UserActivity.objects.create(
                user=request.user,
                activity_type='profile_updated',
                details={'action': 'upgraded_to_business'}
            )
            
            messages.success(request, 
                'Business registration submitted! Our team will review and verify your account soon.'
            )
            return redirect('profile_view', username=request.user.username)
    else:
        initial_data = {
            'business_name': request.user.get_full_name() or request.user.username,
            'business_email': request.user.email,
        }
        form = BusinessProfileForm(instance=request.user.profile, initial=initial_data)
    
    context = {
        'form': form,
        'trending_topics': trending_topics,
        'title': 'Business Registration',
    }
    return render(request, 'business/registration.html', context)


@login_required
def ad_submission(request):
    """Submit a new advertisement"""
    # Check if user can submit ads
    if not request.user.profile.can_submit_ads():
        messages.error(request, 'Business verification required to submit ads')
        return redirect('business_registration')
    
    # Check remaining ad credits
    remaining_credits = request.user.profile.get_remaining_ad_credits()
    if remaining_credits <= 0:
        messages.error(request, 'Insufficient ad credits. Please top up your account.')
        return redirect('ad_credits')
    
    trending_topics = get_trending_topics()
    
    if request.method == 'POST':
        form = AdSubmissionForm(request.POST, request.FILES)
        if form.is_valid():
            ad = form.save(commit=False)
            ad.business = request.user
            
            # Check budget against remaining credits
            if ad.budget > remaining_credits:
                messages.error(request, f'Budget exceeds remaining credits (₦{remaining_credits:.2f})')
                return render(request, 'ads/submit.html', {'form': form, 'trending_topics': trending_topics})
            
            # Set initial status based on system settings
            settings = SystemSettings.objects.first()
            if settings and settings.ad_approval_required:
                ad.status = 'pending'
            else:
                ad.status = 'approved'
                ad.is_active = True
                ad.approved_by = request.user
                ad.approved_at = timezone.now()
            
            ad.save()
            form.save_m2m()
            
            # Create activity
            UserActivity.objects.create(
                user=request.user,
                activity_type='ad_submitted',
                details={'ad_title': ad.title, 'budget': str(ad.budget)}
            )
            
            messages.success(request, 'Advertisement submitted successfully!')
            return redirect('ad_manage')
    else:
        form = AdSubmissionForm()
    
    context = {
        'form': form,
        'remaining_credits': remaining_credits,
        'trending_topics': trending_topics,
        'title': 'Submit Advertisement',
    }
    return render(request, 'ads/submit.html', context)


@login_required
def ad_manage(request):
    """Manage user's advertisements"""
    ads = Advertisement.objects.filter(business=request.user).select_related(
        'approved_by'
    ).order_by('-created_at')
    
    trending_topics = get_trending_topics()
    
    context = {
        'ads': ads,
        'trending_topics': trending_topics,
        'title': 'Manage Advertisements',
    }
    return render(request, 'ads/manage.html', context)


@login_required
def ad_detail(request, uuid):
    """View ad details and analytics"""
    ad = get_object_or_404(Advertisement, uuid=uuid, business=request.user)
    
    # Get analytics
    analytics = AdAnalytics.objects.filter(advertisement=ad).order_by('-date')[:30]
    
    # Calculate totals
    total_impressions = analytics.aggregate(Sum('impressions'))['impressions__sum'] or 0
    total_clicks = analytics.aggregate(Sum('clicks'))['clicks__sum'] or 0
    total_cost = analytics.aggregate(Sum('cost'))['cost__sum'] or 0
    
    trending_topics = get_trending_topics()
    
    context = {
        'ad': ad,
        'analytics': analytics,
        'total_impressions': total_impressions,
        'total_clicks': total_clicks,
        'total_cost': total_cost,
        'trending_topics': trending_topics,
        'title': ad.title,
    }
    return render(request, 'ads/detail.html', context)


@login_required
def ad_credits(request):
    """View and purchase ad credits"""
    if request.user.profile.account_type != 'business':
        messages.error(request, 'Only business accounts can purchase ad credits')
        return redirect('profile_view', username=request.user.username)
    
    trending_topics = get_trending_topics()
    
    if request.method == 'POST':
        amount = request.POST.get('amount')
        payment_method = request.POST.get('payment_method')
        
        try:
            amount_decimal = Decimal(amount)
            if amount_decimal > 0:
                request.user.profile.ad_credits += amount_decimal
                request.user.profile.save()
                
                messages.success(request, f'₦{amount_decimal:.2f} added to your ad credits')
                return redirect('ad_manage')
        except (ValueError, InvalidOperation):
            messages.error(request, 'Invalid amount')
    
    # Credit packages
    packages = [
        {'amount': 5000, 'bonus': 0, 'label': '₦5,000'},
        {'amount': 10000, 'bonus': 500, 'label': '₦10,000 (₦500 bonus)'},
        {'amount': 25000, 'bonus': 2000, 'label': '₦25,000 (₦2,000 bonus)'},
        {'amount': 50000, 'bonus': 5000, 'label': '₦50,000 (₦5,000 bonus)'},
        {'amount': 100000, 'bonus': 12000, 'label': '₦100,000 (₦12,000 bonus)'},
    ]
    
    context = {
        'packages': packages,
        'current_credits': request.user.profile.ad_credits,
        'trending_topics': trending_topics,
        'title': 'Purchase Ad Credits',
    }
    return render(request, 'ads/credits.html', context)


# ==================== HELPER FUNCTIONS ====================

def can_view_post(user, post):
    """Check if a user can view a specific post based on privacy settings"""
    # Admin/staff can view everything
    if user.is_authenticated and (user.is_staff or user.is_superuser):
        return True
    
    # Author can always view their own posts
    if user.is_authenticated and post.author == user:
        return True
    
    # News posts are always public
    if post.post_type in ['news', 'user_news']:
        return True
    
    # Check privacy settings
    if post.privacy == 'public':
        return True
    elif post.privacy == 'private':
        return user.is_authenticated and post.author == user
    elif post.privacy == 'followers':
        if not user.is_authenticated:
            return False
        # Check if user is following the author
        return Follow.objects.filter(
            follower=user,
            following=post.author
        ).exists()
    elif post.privacy == 'specific':
        if not user.is_authenticated:
            return False
        # Check if user is in allowed viewers list
        return post.allowed_viewers.filter(id=user.id).exists()
    
    return False


def get_trending_topics(limit=5):
    """Get trending topics from recent posts with caching"""
    cache_key = 'trending_topics'
    topics = cache.get(cache_key)
    
    if topics is None:
        recent_posts = Post.objects.filter(
            status='published',
            created_at__gte=timezone.now() - timedelta(days=2)
        ).order_by('-views')[:50]
        
        # Extract common words from titles
        words = {}
        stop_words = {'the', 'and', 'for', 'with', 'this', 'that', 'from', 
                     'have', 'were', 'has', 'had', 'will', 'are', 'was', 'been',
                     'what', 'when', 'where', 'who', 'why', 'how', 'all', 'one',
                     'would', 'could', 'should', 'their', 'they', 'them', 'our'}
        
        for post in recent_posts:
            title_words = post.title.lower().split()
            for word in title_words:
                word = word.strip('.,!?()[]{}:;"\'')
                if len(word) > 3 and word not in stop_words and not word.isdigit():
                    words[word] = words.get(word, 0) + 1
        
        # Sort by frequency
        trending = sorted(words.items(), key=lambda x: x[1], reverse=True)[:limit]
        topics = [{'topic': word, 'count': count} for word, count in trending]
        
        cache.set(cache_key, topics, 3600)  # 1 hour
    
    return topics

@require_GET
def get_modal_messages(request):
    """API endpoint to get messages for modal display"""
    messages_list = []
    
    if 'modal_messages' in request.session:
        messages_list = request.session['modal_messages']
        # Clear after retrieving
        del request.session['modal_messages']
    
    return JsonResponse({'messages': messages_list})

def resources(request):
    """Resources page"""
    trending_topics = get_trending_topics()
    
    context = {
        'trending_topics': trending_topics,
        'title': 'Resources',
    }
    return render(request, 'resources/resources.html', context)


def help_center(request):
    """Help center page"""
    trending_topics = get_trending_topics()
    
    # Get help articles by category
    help_categories = [
        {
            'name': 'Account & Profile',
            'icon': 'user-circle',
            'articles': [
                {'title': 'How to create an account', 'url': '?article=create-account'},
                {'title': 'Editing your profile', 'url': '?article=edit-profile'},
                {'title': 'Changing your password', 'url': '?article=change-password'},
                {'title': 'Account verification', 'url': '?article=verification'},
                {'title': 'Deleting your account', 'url': '?article=delete-account'},
            ]
        },
        {
            'name': 'Posts & Content',
            'icon': 'pen',
            'articles': [
                {'title': 'Creating a post', 'url': '?article=create-post'},
                {'title': 'Adding images and media', 'url': '?article=add-media'},
                {'title': 'Post privacy settings', 'url': '?article=post-privacy'},
                {'title': 'Commenting on posts', 'url': '?article=commenting'},
                {'title': 'Liking and bookmarking', 'url': '?article=likes-bookmarks'},
            ]
        },
        {
            'name': 'News & Verification',
            'icon': 'newspaper',
            'articles': [
                {'title': 'How news is verified', 'url': '?article=news-verification'},
                {'title': 'Submitting news articles', 'url': '?article=submit-news'},
                {'title': 'Understanding verification badges', 'url': '?article=verification-badges'},
                {'title': 'Reporting fake news', 'url': '?article=report-fake'},
            ]
        },
        {
            'name': 'Business & Advertising',
            'icon': 'briefcase',
            'articles': [
                {'title': 'Business account benefits', 'url': '?article=business-benefits'},
                {'title': 'How to advertise', 'url': '?article=how-to-advertise'},
                {'title': 'Ad pricing and credits', 'url': '?article=ad-pricing'},
                {'title': 'Analytics and insights', 'url': '?article=analytics'},
            ]
        },
        {
            'name': 'Technical Support',
            'icon': 'code',
            'articles': [
                {'title': 'Browser requirements', 'url': '?article=browser-requirements'},
                {'title': 'Troubleshooting issues', 'url': '?article=troubleshooting'},
                {'title': 'Report a bug', 'url': '?article=report-bug'},
            ]
        },
        {
            'name': 'Safety & Privacy',
            'icon': 'shield-alt',
            'articles': [
                {'title': 'Privacy policy overview', 'url': '?article=privacy-overview'},
                {'title': 'Blocking and reporting', 'url': '?article=block-report'},
                {'title': 'Safety tips', 'url': '?article=safety-tips'},
                {'title': 'Two-factor authentication', 'url': '?article=2fa'},
            ]
        },
    ]
    
    context = {
        'trending_topics': trending_topics,
        'help_categories': help_categories,
        'title': 'Help Center',
    }
    return render(request, 'help/help.html', context)



def people_to_follow(request):
    """People to follow suggestions page"""
    if request.user.is_authenticated:
        following_ids = Follow.objects.filter(follower=request.user).values_list('following_id', flat=True)
        suggested_users = User.objects.exclude(
            Q(id=request.user.id) | Q(id__in=following_ids)
        ).filter(is_active=True).order_by('?')[:20]
    else:
        suggested_users = User.objects.filter(is_active=True).order_by('?')[:20]
    
    trending_topics = get_trending_topics()
    
    context = {
        'suggested_users': suggested_users,
        'trending_topics': trending_topics,
        'title': 'People to Follow',
    }
    return render(request, 'discover/people.html', context)


def faq(request):
    """FAQ page"""
    trending_topics = get_trending_topics()
    
    faq_items = [
        {
            'question': 'How do I create an account?',
            'answer': 'Click the "Register" button on the top right corner and fill in your details. You\'ll need a valid email address and a strong password.',
            'category': 'account'
        },
        {
            'question': 'How do I reset my password?',
            'answer': 'Go to the login page and click "Forgot Password". Enter your email address and we\'ll send you instructions to reset your password.',
            'category': 'account'
        },
        {
            'question': 'How do I report a post?',
            'answer': 'Click the three dots on any post and select "Report". Our moderation team will review the content.',
            'category': 'moderation'
        },
        {
            'question': 'How do I verify my business account?',
            'answer': 'Go to your profile settings, select "Upgrade to Business", and submit your business details for verification.',
            'category': 'business'
        },
        {
            'question': 'How does news verification work?',
            'answer': 'Our system automatically checks news sources for credibility, fact-checks content, and assigns a verification score. Staff members also review flagged content.',
            'category': 'news'
        },
        {
            'question': 'Can I delete my account?',
            'answer': 'Yes, go to your profile settings and select "Delete Account". Please note this action is permanent and cannot be undone.',
            'category': 'account'
        },
    ]
    
    context = {
        'trending_topics': trending_topics,
        'faq_items': faq_items,
        'title': 'Frequently Asked Questions',
    }
    return render(request, 'help/faq.html', context)

@require_POST
def track_share(request, post_id):
    """Track post shares"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    try:
        post = Post.objects.get(id=post_id)
        post.shares = F('shares') + 1
        post.save()
        
        return JsonResponse({'success': True})
    except Post.DoesNotExist:
        return JsonResponse({'error': 'Post not found'}, status=404)


@login_required
@csrf_exempt
def test_ajax(request):
    """Test view to verify AJAX is working"""
    if request.method == 'POST':
        return JsonResponse({
            'success': True,
            'message': 'AJAX is working!',
            'user': request.user.username
        })
    return JsonResponse({'error': 'GET not allowed'}, status=405)

@require_POST
def track_share(request, post_id):
    """Track post shares"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    try:
        post = Post.objects.get(id=post_id)
        post.shares = F('shares') + 1
        post.save()
        
        return JsonResponse({'success': True})
    except Post.DoesNotExist:
        return JsonResponse({'error': 'Post not found'}, status=404)