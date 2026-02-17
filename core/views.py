import requests
import json
from datetime import datetime, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, authenticate
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib import messages
from .models import Repost 
from django.conf import settings
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q, Count, Sum, F, Avg
from django.utils import timezone
from django.contrib.auth.models import User
from decimal import Decimal, InvalidOperation
from django.db import models  
from django.core.files.base import ContentFile
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_http_methods
from django.contrib.admin.views.decorators import staff_member_required
from .models import Post, Category, Comment, UserProfile, Notification, UserActivity, Follow, Post, Advertisement, Group, GroupMember, GroupPost, UserProfile, Category, Comment, UserActivity, SystemSettings, AdAnalytics
from .forms import PostForm, CommentForm, UserProfileForm, UserUpdateForm, BusinessProfileForm, GroupForm, SystemSettingsForm,RegistrationForm, PostForm, AdSubmissionForm
from .news_fetcher import NewsFetcher
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST, require_GET
from django.contrib.auth import logout as auth_logout


@staff_member_required
def admin_dashboard(request):
    """Enhanced admin dashboard"""
    total_posts = Post.objects.count()
    
    top_categories = Category.objects.annotate(
        post_count=Count('post')
    ).order_by('-post_count')[:5]
    
    # Calculate percentages in the view
    for category in top_categories:
        if total_posts > 0:
            category.percentage = (category.post_count / total_posts) * 100
        else:
            category.percentage = 0
    
    stats = {
        'total_posts': total_posts,
        'total_users': User.objects.count(),
        'pending_verification': Post.objects.filter(
            verification_status='pending'
        ).count(),
        'fake_news': Post.objects.filter(
            verification_status='fake'
        ).count(),
        'recent_users': User.objects.order_by('-date_joined')[:10],
        'top_categories': top_categories,  # Now with percentage attribute
    }
    
    # Recent activities
    recent_activities = UserActivity.objects.select_related(
        'user', 'post', 'target_user'
    ).order_by('-created_at')[:20]
    
    context = {
        'stats': stats,
        'recent_activities': recent_activities,
        'is_admin': True,
    }
    
    return render(request, 'admin/dashboard.html', context)

@staff_member_required
def admin_posts(request):
    """Admin post management"""
    posts = Post.objects.select_related('author', 'category').order_by('-created_at')
    
    # Filtering
    filter_type = request.GET.get('filter', 'all')
    if filter_type == 'pending':
        posts = posts.filter(verification_status='pending')
    elif filter_type == 'fake':
        posts = posts.filter(verification_status='fake')
    elif filter_type == 'unverified':
        posts = posts.filter(is_verified=False)
    
    paginator = Paginator(posts, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    context = {
        'posts': page_obj,
        'page_obj': page_obj,
        'filter_type': filter_type,
        'is_admin': True,
    }
    
    return render(request, 'admin/posts.html', context)

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


@login_required
def home(request):
    """Personal user homepage - shows user's own posts and activities"""
    # Get user's own posts
    user_posts = Post.objects.filter(
        author=request.user,
        status='published'
    ).order_by('-published_at')[:20]
    
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
        ).order_by('-published_at')[:20]
    
    # Get posts the user has interacted with - COLLECT IDs FIRST
    interacted_posts_ids = set()
    
    # Liked posts - get IDs first, then add to set
    liked_posts_ids = list(Post.objects.filter(
        likes=request.user,
        status='published'
    ).values_list('id', flat=True)[:20])
    interacted_posts_ids.update(liked_posts_ids)
    
    # Commented posts - get IDs first, then add to set
    commented_posts_ids = list(Post.objects.filter(
        comments__user=request.user,
        status='published'
    ).distinct().values_list('id', flat=True)[:20])
    interacted_posts_ids.update(commented_posts_ids)
    
    # Reposted posts - get IDs first, then add to set
    reposted_posts_ids = list(Post.objects.filter(
        repost_instances__user=request.user,
        status='published'
    ).values_list('id', flat=True)[:20])
    interacted_posts_ids.update(reposted_posts_ids)
    
    # Get interacted posts with interaction flags
    interacted_posts = []
    if interacted_posts_ids:
        # Convert set to list and slice to limit
        interacted_id_list = list(interacted_posts_ids)[:20]
        
        posts_qs = Post.objects.filter(
            id__in=interacted_id_list,
            status='published'
        ).order_by('-published_at')
        
        # Create a dictionary of flags for quick lookup
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
    
    # Get user's recent activities
    recent_activities = UserActivity.objects.filter(
        user=request.user
    ).select_related('post', 'comment', 'target_user').order_by('-created_at')[:20]
    
    # Get suggested users (who to follow) - WITHOUT subquery LIMIT
    suggested_users = []
    
    # First, get users with posts
    users_with_posts = User.objects.exclude(
        Q(id=request.user.id) | Q(id__in=following_ids)
    ).filter(
        is_active=True,
        posts__isnull=False
    ).annotate(
        posts_count=Count('posts')
    ).order_by('-posts_count')[:10]
    
    # Convert to list and add to suggested users
    for user in users_with_posts:
        if len(suggested_users) < 5:
            suggested_users.append(user)
    
    # If not enough, add random active users
    if len(suggested_users) < 5:
        # Get IDs of already suggested users
        suggested_ids = [u.id for u in suggested_users]
        
        additional_users = User.objects.exclude(
            Q(id=request.user.id) | 
            Q(id__in=following_ids) | 
            Q(id__in=suggested_ids)
        ).filter(
            is_active=True
        ).order_by('?')[:5 - len(suggested_users)]
        
        suggested_users.extend(additional_users)
    
    # Get user stats
    total_posts = Post.objects.filter(author=request.user, status='published').count()
    total_likes_given = Post.objects.filter(likes=request.user, status='published').count()
    total_comments = Comment.objects.filter(user=request.user, is_active=True).count()
    total_reposts = Repost.objects.filter(user=request.user).count()
    
    # Get followers and following counts
    followers_count = Follow.objects.filter(following=request.user).count()
    following_count = len(following_ids)
    
    # Get unread notifications count
    unread_notifications_count = Notification.objects.filter(
        user=request.user,
        is_read=False
    ).count()
    
    context = {
        'user_posts': user_posts,
        'feed_posts': feed_posts,
        'interacted_posts': interacted_posts,
        'recent_activities': recent_activities,
        'suggested_users': suggested_users,
        'total_posts': total_posts,
        'total_likes_given': total_likes_given,
        'total_comments': total_comments,
        'total_reposts': total_reposts,
        'unread_notifications_count': unread_notifications_count,
        'following_count': following_count,
        'followers_count': followers_count,
        'title': f"{request.user.username}'s Home",
    }
    
    return render(request, 'index.html', context)


def online_news(request):
    """General news page - shows only news posts, accessible to guests"""
    # Get filter from query params
    filter_type = request.GET.get('filter', 'latest')
    category_slug = request.GET.get('category', 'all')
    search_query = request.GET.get('q', '')
    
    # Base queryset - Only news posts (auto-fetched OR user-submitted news)
    news_posts = Post.objects.filter(
        status='published',
        post_type__in=['news', 'user_news'],  # Only news posts
        is_auto_fetched=True  # Auto-fetched news
    ) | Post.objects.filter(
        status='published',
        post_type='user_news',  # User-submitted news
        is_approved=True  # Only approved user news
    )
    
    # If no auto-fetched posts, try to fetch some
    if news_posts.filter(is_auto_fetched=True).count() == 0:
        from .news_fetcher import NewsFetcher
        fetcher = NewsFetcher()
        saved_count = fetcher.fetch_all_news()
        
        # Refresh the queryset
        news_posts = Post.objects.filter(
            status='published',
            post_type__in=['news', 'user_news'],
            is_auto_fetched=True
        ) | Post.objects.filter(
            status='published',
            post_type='user_news',
            is_approved=True
        )
    
    # Apply category filter
    if category_slug != 'all':
        try:
            category = Category.objects.get(slug=category_slug)
            news_posts = news_posts.filter(category=category)
        except Category.DoesNotExist:
            category_slug = 'all'
    
    # Apply search
    if search_query:
        news_posts = news_posts.filter(
            Q(title__icontains=search_query) |
            Q(content__icontains=search_query) |
            Q(external_source__icontains=search_query)
        )
    
    # Apply time filter
    if filter_type == 'today':
        today = timezone.now().date()
        news_posts = news_posts.filter(published_at__date=today)
    elif filter_type == 'week':
        week_ago = timezone.now() - timedelta(days=7)
        news_posts = news_posts.filter(published_at__gte=week_ago)
    elif filter_type == 'month':
        month_ago = timezone.now() - timedelta(days=30)
        news_posts = news_posts.filter(published_at__gte=month_ago)
    elif filter_type == 'trending':
        time_threshold = timezone.now() - timedelta(hours=48)
        news_posts = news_posts.filter(
            created_at__gte=time_threshold
        ).annotate(
            like_count=Count('likes'),
            comment_count_val=Count('comments', filter=Q(comments__is_active=True))
        ).annotate(
            engagement_score_calc=models.F('like_count') + 
                                  models.F('comment_count_val') * 2 + 
                                  models.F('views') / 100
        ).order_by('-engagement_score_calc')
    elif filter_type == 'popular':
        news_posts = news_posts.order_by('-views', '-published_at')
    else:  # latest
        news_posts = news_posts.order_by('-published_at')
    
    # Get banner posts (featured news)
    banner_posts = Post.objects.filter(
        status='published',
        is_featured=True,
        post_type__in=['news', 'user_news']
    )[:4]
    
    # If not enough featured posts, add trending ones
    if banner_posts.count() < 4:
        trending = Post.objects.filter(
            status='published',
            post_type__in=['news', 'user_news'],
            created_at__gte=timezone.now() - timedelta(days=7)
        ).annotate(
            like_count=Count('likes'),
            comment_count_val=Count('comments', filter=Q(comments__is_active=True))
        ).annotate(
            engagement=models.F('like_count') + models.F('comment_count_val') * 2 + models.F('views') / 100
        ).order_by('-engagement')[:4 - banner_posts.count()]
        
        banner_posts_list = list(banner_posts)
        for post in trending:
            banner_posts_list.append(post)
        banner_posts = banner_posts_list
    
    # Get sponsored posts for online news page
    sponsored_posts = Post.objects.filter(
        is_sponsored=True,
        status='published',
        post_type__in=['news', 'user_news', 'sponsored'],
        advertisement__is_active=True,
        advertisement__start_date__lte=timezone.now(),
        advertisement__end_date__gte=timezone.now()
    ).order_by('?')[:3]
    
    # Pagination
    paginator = Paginator(news_posts, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # Get categories for news posts
    categories = Category.objects.filter(
        post__status='published',
        post__post_type__in=['news', 'user_news']
    ).annotate(
        news_count=Count('post', filter=Q(
            post__status='published',
            post__post_type__in=['news', 'user_news']
        ))
    ).filter(news_count__gt=0).distinct().order_by('-news_count')[:10]
    
    # Get top sources
    top_sources = Post.objects.filter(
        post_type__in=['news', 'user_news'],
        status='published'
    ).exclude(external_source__isnull=True).exclude(external_source='').values('external_source').annotate(
        count=Count('id')
    ).order_by('-count')[:10]
    
    # Get trending news for sidebar
    trending_news = Post.objects.filter(
        status='published',
        post_type__in=['news', 'user_news'],
        created_at__gte=timezone.now() - timedelta(hours=48)
    ).annotate(
        like_count=Count('likes'),
        actual_comment_count=Count('comments', filter=Q(comments__is_active=True))
    ).annotate(
        engagement=models.F('like_count') + models.F('actual_comment_count') * 2 + models.F('views') / 100
    ).order_by('-engagement')[:5]
    
    # Get breaking news (banner posts)
    breaking_news = Post.objects.filter(
        is_banner=True,
        status='published',
        post_type__in=['news', 'user_news']
    ).order_by('-published_at')[:3]
    
    # Get stats
    total_users = User.objects.filter(is_active=True).count()
    total_news = Post.objects.filter(
        status='published',
        post_type__in=['news', 'user_news']
    ).count()
    total_comments = Comment.objects.filter(is_active=True).count()
    
    context = {
        'posts': page_obj,
        'page_obj': page_obj,
        'categories': categories,
        'top_sources': top_sources,
        'trending_news': trending_news,
        'breaking_news': breaking_news,
        'banner_posts': banner_posts,
        'sponsored_posts': sponsored_posts,
        'filter_type': filter_type,
        'current_category': category_slug,
        'search_query': search_query,
        'total_users': total_users,
        'total_news': total_news,
        'total_comments': total_comments,
    }
    
    return render(request, 'online_news.html', context)

@login_required
def force_fetch_news(request):
    """Force fetch news with improved image extraction"""
    from .news_fetcher import NewsFetcher
    fetcher = NewsFetcher()
    saved_count = fetcher.fetch_all_news()
    
    # Show what was fetched
    recent_news = Post.objects.filter(
        is_auto_fetched=True
    ).order_by('-created_at')[:10]
    
    news_list = []
    for news in recent_news:
        news_list.append({
            'title': news.title,
            'image_url': news.image_url,
            'has_image': bool(news.image_url),
            'source': news.external_source
        })
    
    messages.success(request, f'Fetched {saved_count} new articles with improved image extraction!')
    return render(request, 'admin/fetch_result.html', {
        'count': saved_count,
        'recent_news': news_list
    })

@login_required
def fetch_news(request):
    """Manually trigger news fetching"""
    from .news_fetcher import NewsFetcher
    
    fetcher = NewsFetcher()
    saved_count = fetcher.fetch_all_news()
    
    if saved_count > 0:
        messages.success(request, f'Successfully fetched {saved_count} new articles!')
    else:
        messages.info(request, 'No new articles found.')
    
    # Redirect back to online news page
    return redirect('online_news')

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

def news_detail(request, post_id):
    """View individual news/discussion with social media features"""
    post = get_object_or_404(Post, id=post_id, status='published')
    
    # Increment view count
    post.views += 1
    post.save()
    
    # Get comments with replies
    comments = post.comments.filter(parent__isnull=True, is_active=True).order_by('-created_at')
    
    # Get related posts
    related_posts = Post.objects.filter(
        category=post.category
    ).exclude(id=post.id).order_by('-published_at')[:4]
    
    # Check if user has liked/bookmarked/reposted
    user_liked = False
    user_bookmarked = False
    user_reposted = False
    
    if request.user.is_authenticated:
        user_liked = post.likes.filter(id=request.user.id).exists()
        user_bookmarked = post.bookmarks.filter(id=request.user.id).exists()
        user_reposted = Repost.objects.filter(user=request.user, original_post=post).exists()
    
    # Handle comment submission
    if request.method == 'POST' and request.user.is_authenticated:
        if 'comment' in request.POST:
            content = request.POST.get('content', '').strip()
            parent_id = request.POST.get('parent_id')
            
            if content:
                comment = Comment.objects.create(
                    post=post,
                    user=request.user,
                    content=content,
                    parent_id=parent_id if parent_id else None
                )
                
                # Create notification if not commenting on own post
                if post.author != request.user:
                    Notification.objects.create(
                        user=post.author,
                        from_user=request.user,
                        notification_type='comment',
                        message=f'{request.user.username} commented on your post',
                        post=post,
                        comment=comment
                    )
                
                messages.success(request, 'Comment added successfully!')
                return redirect('news_detail', post_id=post_id)
        
        elif 'repost' in request.POST:
            # Handle repost
            content = request.POST.get('repost_content', '').strip()
            repost, created = Repost.objects.get_or_create(
                user=request.user,
                original_post=post,
                defaults={'content': content}
            )
            
            if created:
                post.reposts += 1
                post.save()
                messages.success(request, 'Post reposted!')
            else:
                repost.delete()
                post.reposts = max(0, post.reposts - 1)
                post.save()
                messages.info(request, 'Repost removed')
            
            return redirect('news_detail', post_id=post_id)
    
    context = {
        'post': post,
        'comments': comments,
        'related_posts': related_posts,
        'user_liked': user_liked,
        'user_bookmarked': user_bookmarked,
        'user_reposted': user_reposted,
    }
    
    return render(request, 'news_detail.html', context)

def post_detail(request, post_id):
    """View individual post with privacy check"""
    post = get_object_or_404(Post, id=post_id, status='published')
    
    # Check if user can view this post
    if not can_view_post(request.user, post):
        messages.error(request, 'You do not have permission to view this post')
        if request.user.is_authenticated:
            return redirect('home')
        else:
            return redirect('online_news')
    
    # Increment view count
    post.views = F('views') + 1
    post.save()
    post.refresh_from_db()
    
    # Get comments with replies
    comments = Comment.objects.filter(
        post=post, 
        parent__isnull=True, 
        is_active=True
    ).select_related('user', 'user__profile').order_by('-created_at')
    
    # Check user interactions
    user_liked = False
    user_bookmarked = False
    user_reposted = False
    
    if request.user.is_authenticated:
        user_liked = post.likes.filter(id=request.user.id).exists()
        user_bookmarked = post.bookmarks.filter(id=request.user.id).exists()
        user_reposted = Repost.objects.filter(
            user=request.user, 
            original_post=post
        ).exists()
    
    # Get related posts
    related_posts = Post.objects.filter(
        Q(category=post.category) | Q(is_auto_fetched=True),
        status='published'
    ).exclude(id=post.id).order_by('-published_at')[:5]
    
    # Get trending in category
    trending_in_category = Post.objects.filter(
        category=post.category,
        status='published',
        created_at__gte=timezone.now() - timedelta(days=7)
    ).exclude(id=post.id).annotate(
        like_count=Count('likes')
    ).order_by('-like_count', '-views')[:5]
    
    # Handle comment submission
    if request.method == 'POST':
        if request.user.is_authenticated:
            if 'content' in request.POST:  # Comment submission
                content = request.POST.get('content', '').strip()
                parent_id = request.POST.get('parent_id')
                
                if content:
                    comment = Comment.objects.create(
                        post=post,
                        user=request.user,
                        content=content,
                        parent_id=parent_id if parent_id else None
                    )
                    
                    # Update comment count
                    post.comments_count = F('comments_count') + 1
                    post.save()
                    
                    # Create notification if not commenting on own post
                    if post.author != request.user:
                        Notification.objects.create(
                            user=post.author,
                            from_user=request.user,
                            notification_type='comment',
                            message=f'{request.user.username} commented on your post',
                            post=post,
                            comment=comment
                        )
                    
                    # Also notify parent comment author if replying
                    if parent_id:
                        try:
                            parent_comment = Comment.objects.get(id=parent_id)
                            if parent_comment.user != request.user:
                                Notification.objects.create(
                                    user=parent_comment.user,
                                    from_user=request.user,
                                    notification_type='reply',
                                    message=f'{request.user.username} replied to your comment',
                                    post=post,
                                    comment=comment
                                )
                        except Comment.DoesNotExist:
                            pass
                    
                    messages.success(request, 'Comment added successfully!')
                    return redirect('post_detail', post_id=post_id)
            
            elif 'like' in request.POST:  # Like/unlike
                return redirect('like_post', post_id=post_id)
            
            elif 'bookmark' in request.POST:  # Bookmark/unbookmark
                return redirect('bookmark_post', post_id=post_id)
            
            elif 'repost' in request.POST:  # Repost
                content = request.POST.get('repost_content', '').strip()
                repost, created = Repost.objects.get_or_create(
                    user=request.user,
                    original_post=post,
                    defaults={'content': content}
                )
                
                if created:
                    post.repost_count = F('repost_count') + 1
                    messages.success(request, 'Post reposted!')
                else:
                    repost.delete()
                    post.repost_count = F('repost_count') - 1
                    messages.info(request, 'Repost removed')
                
                post.save()
                return redirect('post_detail', post_id=post_id)
    
    context = {
        'post': post,
        'comments': comments,
        'related_posts': related_posts,
        'trending_in_category': trending_in_category,
        'user_liked': user_liked,
        'user_bookmarked': user_bookmarked,
        'user_reposted': user_reposted,
        'title': post.title,
    }
    
    return render(request, 'post/post_detail.html', context)


@login_required
def create_post(request):
    """Create a new post with privacy settings"""
    categories = Category.objects.all()
    
    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            
            # Set status based on post type
            if post.post_type == 'user_news':
                post.status = 'draft'  # Needs admin approval
                post.is_auto_fetched = False
                messages.info(request, 'Your news post has been submitted for approval')
            elif post.post_type == 'profile_post':
                post.status = 'published'
                post.profile_only = True
                post.privacy = 'private'  # Profile posts are private by default
                post.category = None  # Profile posts don't have categories
            else:  # discussion
                post.status = 'published'
                post.is_auto_fetched = False
            
            post.save()
            
            # Save many-to-many fields
            form.save_m2m()
            
            # Create activity
            UserActivity.objects.create(
                user=request.user,
                activity_type='post_created',
                post=post,
                details={
                    'post_type': post.post_type,
                    'privacy': post.privacy
                }
            )
            
            messages.success(request, 'Post created successfully!')
            
            # Redirect based on post type
            if post.post_type == 'profile_post':
                return redirect('profile_posts', username=request.user.username)
            else:
                return redirect('post_detail', post_id=post.id)
    else:
        form = PostForm(user=request.user)
        
        # Pre-fill post type from URL parameter
        post_type = request.GET.get('type')
        if post_type in ['discussion', 'user_news', 'profile_post']:
            form.fields['post_type'].initial = post_type
    
    context = {
        'form': form,
        'categories': categories,
        'followers_count': Follow.objects.filter(following=request.user).count(),
        'title': 'Create Post',
    }
    return render(request, 'create_post.html', context)

def can_view_post(user, post):
    """Check if a user can view a specific post based on privacy settings"""
    # Admin/staff can view everything
    if user.is_authenticated and (user.is_staff or user.is_superuser):
        return True
    
    # Author can always view their own posts
    if user.is_authenticated and post.author == user:
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



@login_required
def like_post(request, post_id):
    """Like/Unlike a post"""
    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        post = get_object_or_404(Post, id=post_id)
        
        if request.user in post.likes.all():
            post.likes.remove(request.user)
            liked = False
        else:
            post.likes.add(request.user)
            liked = True
            
            # Create notification if not liking own post
            if post.author != request.user:
                Notification.objects.create(
                    user=post.author,
                    from_user=request.user,
                    notification_type='like',
                    message=f'{request.user.username} liked your post',
                    post=post
                )
        
        return JsonResponse({
            'liked': liked,
            'like_count': post.like_count()
        })
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

def category_view(request, category_slug):
    """View posts by category"""
    category = get_object_or_404(Category, slug=category_slug)
    
    # Get posts in this category and subcategories
    subcategories = category.subcategories.all()
    posts = Post.objects.filter(
        Q(category=category) | Q(category__in=subcategories),
        status='published'
    ).order_by('-published_at')
    
    paginator = Paginator(posts, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    context = {
        'category': category,
        'page_obj': page_obj,
        'posts': page_obj,
        'subcategories': subcategories,
    }
    
    return render(request, 'category.html', context)

def register_view(request):
    """User registration"""
    if request.user.is_authenticated:
        return redirect('home')
    
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

from django.views.decorators.cache import never_cache

@never_cache
def login_view(request):
    """User login with admin detection"""
    if request.user.is_authenticated:
        return redirect('home')
    
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
                    next_page = request.GET.get('next', 'home')
                
                return redirect(next_page)
            else:
                messages.error(request, 'Invalid username or password.')
        else:
            messages.error(request, 'Invalid username or password.')
    else:
        form = AuthenticationForm()
    
    context = {'form': form}
    return render(request, 'registration/login.html', context)


def logout_view(request):
    """User logout"""
    auth_logout(request)
    messages.success(request, 'You have been logged out successfully!')
    return redirect('home')


@login_required
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
    activities = UserActivity.objects.filter(user=user).order_by('-created_at')[:50]
    
    # Get user's posts - filter by privacy
    user_posts = Post.objects.filter(
        author=user, 
        status='published'
    )
    
    # Filter posts based on viewer permissions
    if request.user != user:
        filtered_posts = []
        for post in user_posts:
            if can_view_post(request.user, post):
                filtered_posts.append(post.id)
        user_posts = user_posts.filter(id__in=filtered_posts)
    
    user_posts = user_posts.order_by('-published_at')
    
    # Get user's comments
    comments = Comment.objects.filter(user=user, is_active=True).order_by('-created_at')
    
    # Get liked posts
    liked_posts = Post.objects.filter(likes=user, status='published')
    
    # Get followers and following - FIXED: Get User objects directly
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
        'followers': followers,  # Now these are User objects
        'following': following,  # Now these are User objects
        'followers_count': followers_count,
        'following_count': following_count,
        'is_following': is_following,
        'is_own_profile': user == request.user,
        'can_view_posts': True,
    }
    
    return render(request, 'profile/profile.html', context)

@login_required
def edit_profile(request):
    """Profile editing functionality"""
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
            # FIX THIS LINE - Change 'profile' to 'profile_view'
            return redirect('profile_view', username=request.user.username)  # <-- FIX HERE
    else:
        user_form = UserUpdateForm(instance=request.user)
        profile_form = UserProfileForm(instance=request.user.profile)
    
    context = {
        'user_form': user_form,
        'profile_form': profile_form,
    }
    
    return render(request, 'profile/edit_profile.html', context)

@login_required
def update_profile_pic(request):
    if request.method == 'POST' and request.FILES.get('profile_pic'):
        profile = request.user.profile
        profile.profile_pic = request.FILES['profile_pic']
        profile.save()
        
        return JsonResponse({
            'success': True,
            'image_url': profile.profile_pic.url
        })
    return JsonResponse({'success': False}, status=400)

@login_required
def update_cover_photo(request):
    if request.method == 'POST' and request.FILES.get('cover_photo'):
        profile = request.user.profile
        profile.cover_photo = request.FILES['cover_photo']
        profile.save()
        
        return JsonResponse({
            'success': True,
            'image_url': profile.cover_photo.url
        })
    return JsonResponse({'success': False}, status=400)

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
            message = f'Unfollowed {user_to_follow.username}'
        else:
            # Follow
            followed = True
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
        
        # Check if current user is following (for button state)
        is_following = Follow.objects.filter(
            follower=request.user,
            following=user_to_follow
        ).exists()
        
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
def activity_feed(request):
    """User's activity feed"""
    activities = UserActivity.objects.filter(user=request.user).order_by('-created_at')
    
    # Pagination
    paginator = Paginator(activities, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'activities': page_obj,
    }
    
    return render(request, 'profile/activity_feed.html', context)

@csrf_exempt
@require_POST
def api_fetch_news(request):
    """API endpoint to trigger news fetching"""
    from .news_fetcher import NewsFetcher
    fetcher = NewsFetcher()
    saved_count = fetcher.fetch_all_news()
    
    return JsonResponse({
        'success': True,
        'count': saved_count,
        'message': f'Fetched {saved_count} new articles'
    })


@login_required
@require_POST
def api_feature_post(request, post_id):
    """Feature/unfeature a post for homepage (admin only)"""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    post = get_object_or_404(Post, id=post_id)
    post.is_featured = not post.is_featured
    post.save()
    
    return JsonResponse({
        'featured': post.is_featured,
        'message': 'Post featured on homepage' if post.is_featured else 'Post removed from featured'
    })

    
@login_required
def business_registration(request):
    """Business account registration/upgrade"""
    if request.user.profile.account_type == 'business':
        messages.info(request, 'You already have a business account')
        return redirect('profile')
    
    if request.method == 'POST':
        form = BusinessProfileForm(request.POST, request.FILES, instance=request.user.profile)
        if form.is_valid():
            profile = form.save(commit=False)
            profile.account_type = 'business'
            
            # Upload business documents
            if 'business_docs' in request.FILES:
                # Handle document upload
                pass
            
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
            return redirect('profile')
    else:
        initial_data = {
            'business_name': request.user.get_full_name() or request.user.username,
            'business_email': request.user.email,
        }
        form = BusinessProfileForm(instance=request.user.profile, initial=initial_data)
    
    context = {
        'form': form,
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
    
    if request.method == 'POST':
        form = AdSubmissionForm(request.POST, request.FILES)
        if form.is_valid():
            ad = form.save(commit=False)
            ad.business = request.user
            
            # Check budget against remaining credits
            if ad.budget > remaining_credits:
                messages.error(request, f'Budget exceeds remaining credits (₦{remaining_credits:.2f})')
                return render(request, 'ads/submit.html', {'form': form})
            
            # Set initial status based on system settings
            settings = SystemSettings.objects.first()
            if settings.ad_approval_required:
                ad.status = 'pending'
            else:
                ad.status = 'approved'
                ad.is_active = True
                ad.approved_by = request.user
                ad.approved_at = timezone.now()
            
            ad.save()
            form.save_m2m()  # Save many-to-many relations
            
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
        'title': 'Submit Advertisement',
    }
    return render(request, 'ads/submit.html', context)

@login_required
def ad_manage(request):
    """Manage user's advertisements"""
    ads = Advertisement.objects.filter(business=request.user).order_by('-created_at')
    
    context = {
        'ads': ads,
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
    
    context = {
        'ad': ad,
        'analytics': analytics,
        'total_impressions': total_impressions,
        'total_clicks': total_clicks,
        'total_cost': total_cost,
        'title': ad.title,
    }
    return render(request, 'ads/detail.html', context)

@staff_member_required
def ad_approval_queue(request):
    """Admin view for approving ads"""
    pending_ads = Advertisement.objects.filter(status='pending').order_by('-created_at')
    
    if request.method == 'POST':
        ad_id = request.POST.get('ad_id')
        action = request.POST.get('action')
        reason = request.POST.get('reason', '')
        
        try:
            ad = Advertisement.objects.get(id=ad_id)
            
            if action == 'approve':
                ad.status = 'approved'
                ad.is_active = True
                ad.approved_by = request.user
                ad.approved_at = timezone.now()
                ad.rejection_reason = ''
                
                messages.success(request, f'Ad "{ad.title}" approved successfully')
            elif action == 'reject':
                ad.status = 'rejected'
                ad.is_active = False
                ad.rejection_reason = reason
                
                messages.warning(request, f'Ad "{ad.title}" rejected')
            
            ad.save()
            
            # Create notification for business owner
            Notification.objects.create(
                user=ad.business,
                from_user=request.user,
                notification_type='ad_approval',
                message=f'Your ad "{ad.title}" has been {action}d',
                details={'ad_id': ad.id, 'action': action, 'reason': reason}
            )
            
        except Advertisement.DoesNotExist:
            messages.error(request, 'Advertisement not found')
        
        return redirect('ad_approval_queue')
    
    context = {
        'pending_ads': pending_ads,
        'title': 'Ad Approval Queue',
    }
    return render(request, 'admin/ads/approval_queue.html', context)

def groups_list(request):
    """Browse public groups"""
    groups = Group.objects.filter(is_active=True, group_type='public').order_by('-member_count')
    
    # Search
    search_query = request.GET.get('q', '')
    if search_query:
        groups = groups.filter(
            Q(name__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    paginator = Paginator(groups, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    context = {
        'groups': page_obj,
        'page_obj': page_obj,
        'search_query': search_query,
        'title': 'Browse Groups',
    }
    return render(request, 'groups/list.html', context)

@login_required
def business_verification(request):
    """View for business verification status"""
    if request.user.profile.account_type != 'business':
        messages.error(request, 'You do not have a business account')
        return redirect('profile')
    
    profile = request.user.profile
    
    context = {
        'profile': profile,
        'is_verified': profile.is_verified_business,
        'verified_at': profile.business_verified_at,
        'verified_by': profile.business_verified_by,
        'title': 'Business Verification Status',
    }
    
    return render(request, 'business/verification.html', context)

# Add this missing view
@login_required
def ad_edit(request, uuid):
    """Edit an existing advertisement"""
    ad = get_object_or_404(Advertisement, uuid=uuid, business=request.user)
    
    # Can only edit pending or paused ads
    if ad.status not in ['pending', 'paused', 'rejected']:
        messages.error(request, 'You can only edit pending, paused, or rejected ads')
        return redirect('ad_detail', uuid=uuid)
    
    if request.method == 'POST':
        form = AdSubmissionForm(request.POST, request.FILES, instance=ad)
        if form.is_valid():
            updated_ad = form.save(commit=False)
            
            # Reset status to pending if it was rejected
            if updated_ad.status == 'rejected':
                updated_ad.status = 'pending'
                updated_ad.rejection_reason = ''
            
            updated_ad.save()
            form.save_m2m()
            
            messages.success(request, 'Advertisement updated successfully!')
            return redirect('ad_detail', uuid=uuid)
    else:
        form = AdSubmissionForm(instance=ad)
    
    context = {
        'form': form,
        'ad': ad,
        'title': f'Edit {ad.title}',
    }
    return render(request, 'ads/edit.html', context)

# Add these group-related views
def group_members(request, slug):
    """View group members"""
    group = get_object_or_404(Group, slug=slug, is_active=True)
    
    # Check permissions
    if group.group_type == 'secret':
        if not request.user.is_authenticated:
            messages.error(request, 'This is a secret group')
            return redirect('groups_list')
        
        is_member = GroupMember.objects.filter(group=group, user=request.user).exists()
        if not is_member and not request.user.is_staff:
            messages.error(request, 'You need an invitation to view this group')
            return redirect('groups_list')
    
    # Get members
    members = GroupMember.objects.filter(group=group, is_banned=False).select_related('user')
    
    # Check if user is admin
    is_admin = False
    if request.user.is_authenticated:
        membership = GroupMember.objects.filter(group=group, user=request.user).first()
        if membership:
            is_admin = membership.role == 'admin'
    
    context = {
        'group': group,
        'members': members,
        'is_admin': is_admin,
        'title': f'{group.name} - Members',
    }
    return render(request, 'groups/members.html', context)

@login_required
def group_settings(request, slug):
    """Group settings (admin only)"""
    group = get_object_or_404(Group, slug=slug, is_active=True)
    
    # Check if user is admin
    membership = GroupMember.objects.filter(group=group, user=request.user).first()
    if not membership or membership.role != 'admin':
        messages.error(request, 'Only group admins can access settings')
        return redirect('group_detail', slug=slug)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'delete_group':
            # Delete group
            confirm_name = request.POST.get('confirm_name', '')
            if confirm_name == group.name:
                group.delete()
                messages.success(request, f'Group "{group.name}" has been deleted')
                return redirect('groups_list')
            else:
                messages.error(request, 'Group name does not match')
                return redirect('group_settings', slug=slug)
        
        elif action == 'remove_admin':
            # Remove admin
            admin_id = request.POST.get('admin_id')
            if admin_id:
                try:
                    admin = User.objects.get(id=admin_id)
                    if admin != request.user:  # Cannot remove yourself
                        group.admins.remove(admin)
                        # Update membership role
                        member = GroupMember.objects.get(group=group, user=admin)
                        member.role = 'member'
                        member.save()
                        messages.success(request, f'{admin.username} removed as admin')
                except (User.DoesNotExist, GroupMember.DoesNotExist):
                    messages.error(request, 'User not found')
        
        elif action == 'remove_moderator':
            # Remove moderator
            moderator_id = request.POST.get('moderator_id')
            if moderator_id:
                try:
                    moderator = User.objects.get(id=moderator_id)
                    group.moderators.remove(moderator)
                    # Update membership role
                    member = GroupMember.objects.get(group=group, user=moderator)
                    member.role = 'member'
                    member.save()
                    messages.success(request, f'{moderator.username} removed as moderator')
                except (User.DoesNotExist, GroupMember.DoesNotExist):
                    messages.error(request, 'User not found')
        
        elif action == 'add_admin':
            # Add new admin
            username = request.POST.get('username', '').strip()
            if username:
                try:
                    new_admin = User.objects.get(username=username)
                    # Check if user is a member
                    member, created = GroupMember.objects.get_or_create(
                        group=group,
                        user=new_admin,
                        defaults={'role': 'admin'}
                    )
                    if not created:
                        member.role = 'admin'
                        member.save()
                    
                    group.admins.add(new_admin)
                    messages.success(request, f'{new_admin.username} added as admin')
                except User.DoesNotExist:
                    messages.error(request, f'User "{username}" not found')
        
        else:
            # Regular form submission
            form = GroupForm(request.POST, request.FILES, instance=group)
            if form.is_valid():
                updated_group = form.save(commit=False)
                
                # Handle image clearing
                if 'clear_icon' in request.POST:
                    updated_group.icon.delete(save=False)
                    updated_group.icon = None
                
                if 'clear_cover' in request.POST:
                    updated_group.cover_image.delete(save=False)
                    updated_group.cover_image = None
                
                updated_group.save()
                
                # Handle new admins
                new_admins = request.POST.get('new_admins', '').strip()
                if new_admins:
                    for username in new_admins.split(','):
                        username = username.strip()
                        if username:
                            try:
                                user = User.objects.get(username=username)
                                group.admins.add(user)
                                
                                # Update membership
                                member, created = GroupMember.objects.get_or_create(
                                    group=group,
                                    user=user,
                                    defaults={'role': 'admin'}
                                )
                                if not created:
                                    member.role = 'admin'
                                    member.save()
                            except User.DoesNotExist:
                                pass  # Silently skip invalid usernames
                
                messages.success(request, 'Group settings updated!')
                return redirect('group_settings', slug=slug)
            else:
                # Form errors will be displayed
                pass
    else:
        form = GroupForm(instance=group)
    
    # Get current admins and moderators
    admins = group.admins.all()
    moderators = group.moderators.all()
    
    context = {
        'group': group,
        'form': form,
        'admins': admins,
        'moderators': moderators,
        'title': f'{group.name} - Settings',
    }
    return render(request, 'groups/settings.html', context)

@login_required
def group_create(request):
    """Create a new group"""
    # Check system settings
    settings = SystemSettings.objects.first()
    if not settings.allow_group_creation:
        messages.error(request, 'Group creation is currently disabled')
        return redirect('groups_list')
    
    # Check user's group count
    user_groups = Group.objects.filter(created_by=request.user).count()
    if user_groups >= settings.max_groups_per_user:
        messages.error(request, f'You can only create up to {settings.max_groups_per_user} groups')
        return redirect('groups_list')
    
    if request.method == 'POST':
        form = GroupForm(request.POST, request.FILES)
        if form.is_valid():
            group = form.save(commit=False)
            group.created_by = request.user
            
            # Auto-add creator as admin
            group.save()
            group.admins.add(request.user)
            group.save()
            
            # Create membership
            GroupMember.objects.create(
                group=group,
                user=request.user,
                role='admin'
            )
            
            # Update member count
            group.member_count = 1
            group.save()
            
            # Create activity
            UserActivity.objects.create(
                user=request.user,
                activity_type='group_created',
                details={'group_name': group.name}
            )
            
            messages.success(request, f'Group "{group.name}" created successfully!')
            return redirect('group_detail', slug=group.slug)
    else:
        form = GroupForm()
    
    context = {
        'form': form,
        'title': 'Create Group',
    }
    return render(request, 'groups/create.html', context)

def group_detail(request, slug):
    """View group details and posts"""
    group = get_object_or_404(Group, slug=slug, is_active=True)
    
    # Check if user can view group
    if group.group_type == 'secret':
        if not request.user.is_authenticated:
            messages.error(request, 'This is a secret group')
            return redirect('groups_list')
        
        is_member = GroupMember.objects.filter(group=group, user=request.user).exists()
        if not is_member and not request.user.is_staff:
            messages.error(request, 'You need an invitation to view this group')
            return redirect('groups_list')
    
    # Get group posts
    group_posts = GroupPost.objects.filter(group=group, is_approved=True).select_related('post').order_by('-created_at')
    
    # Check if user is member
    is_member = False
    is_admin = False
    is_moderator = False
    
    if request.user.is_authenticated:
        membership = GroupMember.objects.filter(group=group, user=request.user).first()
        if membership:
            is_member = True
            is_admin = membership.role == 'admin'
            is_moderator = membership.role in ['admin', 'moderator']
    
    paginator = Paginator(group_posts, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    context = {
        'group': group,
        'posts': page_obj,
        'page_obj': page_obj,
        'is_member': is_member,
        'is_admin': is_admin,
        'is_moderator': is_moderator,
        'title': group.name,
    }
    return render(request, 'groups/detail.html', context)

@login_required
def group_join(request, slug):
    """Join a group"""
    group = get_object_or_404(Group, slug=slug, is_active=True)
    
    if group.group_type == 'secret':
        messages.error(request, 'This group requires an invitation')
        return redirect('group_detail', slug=slug)
    
    # Check if already member
    existing = GroupMember.objects.filter(group=group, user=request.user).first()
    if existing:
        if existing.is_banned:
            messages.error(request, 'You are banned from this group')
            return redirect('group_detail', slug=slug)
        messages.info(request, 'You are already a member')
        return redirect('group_detail', slug=slug)
    
    # Create membership
    if group.group_type == 'public':
        GroupMember.objects.create(
            group=group,
            user=request.user,
            role='member'
        )
        
        # Update member count
        group.member_count = F('member_count') + 1
        group.save()
        
        messages.success(request, f'Joined {group.name}!')
    
    elif group.group_type == 'private':
        # Create pending membership request
        # You could create a GroupJoinRequest model for this
        messages.info(request, 'Join request sent. Waiting for approval.')
    
    return redirect('group_detail', slug=slug)

@login_required
def group_post_create(request, slug):
    """Create a post in a group"""
    group = get_object_or_404(Group, slug=slug, is_active=True)
    
    # Check permissions
    membership = GroupMember.objects.filter(group=group, user=request.user).first()
    if not membership or membership.is_banned:
        messages.error(request, 'You cannot post in this group')
        return redirect('group_detail', slug=slug)
    
    if not group.allow_member_posts and membership.role == 'member':
        messages.error(request, 'Only admins and moderators can post in this group')
        return redirect('group_detail', slug=slug)
    
    if request.method == 'POST':
        post_form = PostForm(request.POST, request.FILES)
        if post_form.is_valid():
            post = post_form.save(commit=False)
            post.author = request.user
            post.group = group
            
            # Set status based on group settings
            if group.require_post_approval and membership.role == 'member':
                post.status = 'draft'  # Needs approval
            else:
                post.status = 'published'
            
            post.save()
            
            # Create group post
            group_post = GroupPost.objects.create(
                group=group,
                post=post,
                posted_by=request.user,
                is_approved=(not group.require_post_approval or membership.role != 'member')
            )
            
            # Update group post count
            group.post_count = F('post_count') + 1
            group.save()
            
            messages.success(request, 'Post created successfully!')
            return redirect('group_detail', slug=slug)
    else:
        post_form = PostForm()
    
    context = {
        'group': group,
        'form': post_form,
        'title': f'Create Post in {group.name}',
    }
    return render(request, 'groups/create_post.html', context)

@require_GET
def api_banners(request):
    """API endpoint for banner ads"""
    banners = Post.objects.filter(
        is_banner=True,
        status='published',
        banner_expires_at__gt=timezone.now()
    ).order_by('-banner_priority', '?')[:10]  # Randomize for rotation
    
    # Also get active banner ads
    banner_ads = Advertisement.objects.filter(
        ad_type='banner',
        status='active',
        is_active=True,
        start_date__lte=timezone.now(),
        end_date__gte=timezone.now()
    ).order_by('?')[:5]
    
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
        })
    
    for ad in banner_ads:
        data['ads'].append({
            'id': ad.uuid,
            'title': ad.title,
            'image_url': ad.image.url if ad.image else ad.image_url,
            'target_url': ad.target_url,
            'type': 'advertisement',
            'business': ad.business.username,
        })
    
    return JsonResponse(data)

@login_required
def profile_posts(request, username):
    """View only profile posts of a user"""
    user = get_object_or_404(User, username=username)
    posts = Post.objects.filter(
        author=user,
        post_type='profile_post',
        status='published'
    ).order_by('-published_at')
    
    paginator = Paginator(posts, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    context = {
        'profile_user': user,
        'posts': page_obj,
        'page_obj': page_obj,
        'tab': 'profile_posts',
        'title': f'{user.username}\'s Profile Posts',
    }
    return render(request, 'profile/posts.html', context)

@staff_member_required
def admin_system_settings(request):
    """Admin system settings control panel"""
    settings, created = SystemSettings.objects.get_or_create()
    
    if request.method == 'POST':
        form = SystemSettingsForm(request.POST, instance=settings)
        if form.is_valid():
            form.save()
            messages.success(request, 'System settings updated successfully!')
            return redirect('admin_system_settings')
    else:
        form = SystemSettingsForm(instance=settings)
    
    context = {
        'form': form,
        'title': 'System Settings',
    }
    return render(request, 'admin/system_settings.html', context)

@staff_member_required
def admin_business_verification(request):
    """Verify business accounts"""
    pending_businesses = UserProfile.objects.filter(
        account_type='business',
        is_verified_business=False
    ).exclude(business_name='').order_by('-user__date_joined')
    
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        action = request.POST.get('action')
        
        try:
            profile = UserProfile.objects.get(user__id=user_id, account_type='business')
            
            if action == 'verify':
                profile.is_verified_business = True
                profile.business_verified_at = timezone.now()
                profile.business_verified_by = request.user
                
                # Add initial ad credits
                profile.ad_credits = 10000  # ₦10,000 initial credits
                
                messages.success(request, f'{profile.business_name} verified successfully!')
            
            elif action == 'reject':
                profile.account_type = 'individual'  # Downgrade to individual
                messages.warning(request, f'{profile.business_name} verification rejected')
            
            profile.save()
            
            # Create notification
            Notification.objects.create(
                user=profile.user,
                from_user=request.user,
                notification_type='business_verification',
                message=f'Your business account has been {action}ed',
                details={'action': action}
            )
            
        except UserProfile.DoesNotExist:
            messages.error(request, 'Business profile not found')
        
        return redirect('admin_business_verification')
    
    context = {
        'pending_businesses': pending_businesses,
        'title': 'Business Verification',
    }
    return render(request, 'admin/business_verification.html', context)

@login_required
def ad_credits(request):
    """View and purchase ad credits"""
    if request.user.profile.account_type != 'business':
        messages.error(request, 'Only business accounts can purchase ad credits')
        return redirect('profile')
    
    if request.method == 'POST':
        amount = request.POST.get('amount')
        payment_method = request.POST.get('payment_method')
        
        # In a real app, integrate with payment gateway
        # For now, just add credits
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
        'title': 'Purchase Ad Credits',
    }
    return render(request, 'ads/credits.html', context)

def trending_posts(request):
    """View trending posts"""
    posts = Post.objects.filter(
        status='published',
        created_at__gte=timezone.now() - timedelta(days=7)
    ).annotate(
        engagement=Count('likes') + Count('comments') * 2 + F('views') / 100
    ).order_by('-engagement')[:50]
    
    return render(request, 'trending.html', {'posts': posts})

def bookmarks(request):
    """View bookmarked posts"""
    if not request.user.is_authenticated:
        return redirect('login')
    
    bookmarks = Post.objects.filter(bookmarks=request.user)
    return render(request, 'bookmarks.html', {'bookmarks': bookmarks})


@login_required
def notifications(request):
    """View user notifications"""
    user_notifications = Notification.objects.filter(user=request.user).order_by('-created_at')
    
    # Mark as read when viewing
    user_notifications.filter(is_read=False).update(is_read=True)
    
    return render(request, 'notifications/notifications.html', {
        'notifications': user_notifications
    })

@login_required
def messages_view(request):
    """View messages (placeholder)"""
    return render(request, 'messages/messages.html', {
        'title': 'Messages'
    })

@login_required
def bookmarks(request):
    """View bookmarked posts"""
    bookmarked_posts = Post.objects.filter(bookmarks=request.user)
    return render(request, 'bookmarks/bookmarks.html', {
        'bookmarks': bookmarked_posts,
        'title': 'Bookmarks'
    })

def trending_posts(request):
    """View trending posts"""
    trending = Post.objects.filter(
        status='published',
        created_at__gte=timezone.now() - timedelta(days=2)
    ).annotate(
        engagement=Count('likes') + Count('comments') * 2
    ).order_by('-engagement')[:50]
    
    return render(request, 'trending/trending.html', {
        'trending_posts': trending,
        'title': 'Trending'
    })

def discover(request):
    """Discover new content and users"""
    # Get suggested users (excluding self and already followed)
    if request.user.is_authenticated:
        following_ids = Follow.objects.filter(follower=request.user).values_list('following_id', flat=True)
        suggested_users = User.objects.exclude(
            Q(id=request.user.id) | Q(id__in=following_ids)
        ).order_by('?')[:10]
    else:
        suggested_users = User.objects.order_by('?')[:10]
    
    # Get trending posts
    trending = Post.objects.filter(
        status='published',
        created_at__gte=timezone.now() - timedelta(days=1)
    ).order_by('-views')[:20]
    
    return render(request, 'discover/discover.html', {
        'suggested_users': suggested_users,
        'trending_posts': trending,
        'title': 'Discover'
    })

def search(request):
    """Search functionality"""
    query = request.GET.get('q', '')
    results = []
    
    if query:
        # Search posts
        post_results = Post.objects.filter(
            Q(title__icontains=query) | 
            Q(content__icontains=query) |
            Q(author__username__icontains=query)
        ).filter(status='published')[:50]
        
        # Search users
        user_results = User.objects.filter(
            Q(username__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query)
        )[:20]
        
        # Search categories
        category_results = Category.objects.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query)
        )[:10]
        
        results = {
            'posts': post_results,
            'users': user_results,
            'categories': category_results,
            'query': query
        }
    
    return render(request, 'search/search.html', {
        'results': results,
        'query': query,
        'title': f'Search: {query}' if query else 'Search'
    })
    
@require_POST
@login_required
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
        messages.success(request, 'Post reposted!')
    else:
        repost.delete()
        post.repost_count = F('repost_count') - 1
        messages.info(request, 'Repost removed')
    
    post.save()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'reposted': created,
            'repost_count': post.repost_count
        })
    
    return redirect('post_detail', post_id=post_id)


def settings(request):
    """User settings page"""
    if not request.user.is_authenticated:
        return redirect('login')
    
    return render(request, 'settings/settings.html', {
        'title': 'Settings'
    })

def privacy_policy(request):
    """Privacy policy page"""
    return render(request, 'legal/privacy.html', {
        'title': 'Privacy Policy'
    })

def terms_of_service(request):
    """Terms of service page"""
    return render(request, 'legal/terms.html', {
        'title': 'Terms of Service'
    })

def about(request):
    """About page"""
    return render(request, 'about/about.html', {
        'title': 'About Ojukaye'
    })

def contact(request):
    """Contact page"""
    return render(request, 'contact/contact.html', {
        'title': 'Contact Us'
    })

def help_center(request):
    """Help center"""
    return render(request, 'help/help.html', {
        'title': 'Help Center'
    })
    
@require_POST
@login_required
def like_post(request, post_id):
    """Like/Unlike a post"""
    post = get_object_or_404(Post, id=post_id)
    
    if request.user in post.likes.all():
        post.likes.remove(request.user)
        liked = False
    else:
        post.likes.add(request.user)
        liked = True
        
        # Create notification if not liking own post
        if post.author != request.user:
            Notification.objects.create(
                user=post.author,
                from_user=request.user,
                notification_type='like',
                message=f'{request.user.username} liked your post',
                post=post
            )
    
    # Return JSON for AJAX requests
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'liked': liked,
            'like_count': post.likes.count()
        })
    
    return redirect('post_detail', post_id=post_id)

@require_POST
@login_required
def bookmark_post(request, post_id):
    """Bookmark/Unbookmark a post"""
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
            'bookmarked': bookmarked,
            'bookmark_count': post.bookmarks.count()
        })
    
    return redirect('post_detail', post_id=post_id)

@require_POST
@login_required
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

@require_POST
@login_required
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