# core/management/commands/update_banners.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from core.models import Post

class Command(BaseCommand):
    help = 'Update banner posts based on engagement'
    
    def handle(self, *args, **options):
        self.stdout.write('Updating banner posts...')
        
        # Clear old banners
        Post.objects.filter(is_banner=True).update(is_banner=False)
        
        # Get trending posts from last 24 hours
        trending_posts = Post.objects.filter(
            status='published',
            published_at__gte=timezone.now() - timedelta(hours=24)
        ).annotate(
            engagement=models.Count('likes') + models.Count('comments') * 2 + models.F('views') / 100
        ).order_by('-engagement')[:5]
        
        # Mark as banners
        for post in trending_posts:
            post.is_banner = True
            post.banner_expires_at = timezone.now() + timedelta(days=1)
            post.save()
            self.stdout.write(f'Marked as banner: {post.title[:50]}...')
        
        self.stdout.write(self.style.SUCCESS(f'Updated {trending_posts.count()} banner posts'))