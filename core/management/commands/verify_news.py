# core/management/commands/verify_news.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import Post
from core.news_verifier import NewsVerifier
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Verify pending news articles'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--auto-approve',
            action='store_true',
            help='Auto-approve news with score ≥ 0.7',
        )
        parser.add_argument(
            '--delete-fake',
            action='store_true',
            help='Auto-delete fake news',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=50,
            help='Limit number of posts to verify',
        )
    
    def handle(self, *args, **options):
        self.stdout.write('Starting news verification...')
        
        # Get pending posts
        pending_posts = Post.objects.filter(
            is_auto_fetched=True,
            verification_status__in=['pending', 'checking']
        )[:options['limit']]
        
        if not pending_posts.exists():
            self.stdout.write('No pending posts to verify.')
            return
        
        verifier = NewsVerifier()
        verified_count = 0
        approved_count = 0
        fake_count = 0
        
        for post in pending_posts:
            try:
                article = {
                    'title': post.title,
                    'content': post.content,
                    'url': post.external_url,
                    'source': post.external_source
                }
                
                result = verifier.verify_article(article)
                
                post.verification_score = result['score']
                post.verification_status = result['status']
                post.verification_details = result['details']
                
                # Auto-approve if enabled and score is high
                if options['auto_approve'] and result['score'] >= 0.7:
                    post.is_approved = True
                    post.is_verified = True
                    approved_count += 1
                
                # Handle fake news
                if result['status'] == 'fake':
                    fake_count += 1
                    if options['delete_fake']:
                        post.status = 'archived'
                        self.stdout.write(f'Archived fake news: {post.title[:50]}...')
                
                post.save()
                verified_count += 1
                
                self.stdout.write(f'Verified: {post.title[:50]}... Score: {result["score"]:.2f}')
                
            except Exception as e:
                logger.error(f"Error verifying post {post.id}: {e}")
                continue
        
        self.stdout.write(self.style.SUCCESS(
            f'Verified {verified_count} posts. '
            f'Approved: {approved_count}, Fake: {fake_count}'
        ))