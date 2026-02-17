# core/management/commands/fetch_news_bulk.py
from django.core.management.base import BaseCommand
from core.news_fetcher import NewsFetcher
import time
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Bulk fetch thousands of news articles from multiple sources'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--count',
            type=int,
            default=1000,
            help='Target number of articles to fetch (default: 1000)',
        )
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='Fetch articles from last N days (default: 7)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force refetch even if articles exist',
        )
    
    def handle(self, *args, **options):
        target = options['count']
        days = options['days']
        force = options['force']
        
        self.stdout.write(self.style.SUCCESS(f'🚀 Starting bulk news fetch - Target: {target} articles'))
        self.stdout.write(f'📅 Fetching articles from last {days} days')
        
        from core.models import Post
        import random
        
        fetcher = NewsFetcher()
        
        # Clear existing articles if force
        if force:
            fetcher.articles = []
        
        total_saved = 0
        batch = 1
        
        while total_saved < target:
            self.stdout.write(f'\n📦 Batch {batch} - Current total: {total_saved}/{target}')
            
            # Fetch news with different parameters
            fetcher.fetch_all_news()
            
            # Get unique count
            unique_articles = fetcher.remove_duplicates(fetcher.articles)
            
            # Save articles
            saved = fetcher.save_articles_with_full_content(unique_articles)
            total_saved += saved
            
            self.stdout.write(self.style.SUCCESS(f'✅ Batch {batch} saved: {saved} articles'))
            
            # Clear articles for next batch
            fetcher.articles = []
            
            batch += 1
            
            # Break if no new articles
            if saved == 0:
                self.stdout.write(self.style.WARNING('⚠️ No new articles found. Stopping.'))
                break
            
            # Wait between batches
            if total_saved < target:
                self.stdout.write('⏳ Waiting 10 seconds before next batch...')
                time.sleep(10)
        
        self.stdout.write(self.style.SUCCESS(f'\n🎉 COMPLETE! Total articles saved: {total_saved}'))