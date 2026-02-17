from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime, timedelta
import schedule
import time
from core.news_fetcher import NewsFetcher
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Schedule news fetching and verification'
    
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting news scheduler...'))
        
        def fetch_and_verify():
            self.stdout.write(f"[{timezone.now()}] Starting news fetch...")
            
            # Fetch news
            fetcher = NewsFetcher()
            saved_count = fetcher.fetch_all_news()
            self.stdout.write(f"[{timezone.now()}] Saved {saved_count} articles")
            
            # Verify newly fetched news if auto-verify is enabled
            system_post = Post.objects.filter(is_auto_fetched=True).first()
            if system_post and system_post.auto_verify_news:
                self.stdout.write(f"[{timezone.now()}] Auto-verifying news...")
                verifier = NewsVerifier()
                
                # Get unverified news from last hour
                recent_news = Post.objects.filter(
                    is_auto_fetched=True,
                    verification_status='pending',
                    created_at__gte=timezone.now() - timedelta(hours=1)
                )
                
                for post in recent_news:
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
                        
                        # Auto-approve if score is high
                        if result['score'] >= 0.7:
                            post.is_approved = True
                            post.is_verified = True
                        
                        # Auto-archive fake news if enabled
                        if (result['status'] == 'fake' and 
                            system_post.auto_delete_fake):
                            post.status = 'archived'
                        
                        post.save()
                        
                    except Exception as e:
                        logger.error(f"Error auto-verifying post {post.id}: {e}")
                        continue
                
                self.stdout.write(f"[{timezone.now()}] Auto-verification complete")
            
            return saved_count
        
        # Schedule every 8 hours
        schedule.every(8).hours.do(fetch_and_verify)
        
        # Initial fetch
        fetch_and_verify()
        
        # Keep running
        try:
            while True:
                schedule.run_pending()
                time.sleep(60)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('Scheduler stopped'))