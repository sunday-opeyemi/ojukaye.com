# core/management/commands/fetch_news_bulk.py (Enhanced)

from django.core.management.base import BaseCommand
from django.utils import timezone
from core.news_fetcher import NewsFetcher
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Bulk fetch thousands of news articles with full content and media'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--target',
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
            '--sources',
            type=str,
            default='all',
            help='Comma-separated list of sources (newsapi, rss, web)',
        )
        parser.add_argument(
            '--threads',
            type=int,
            default=5,
            help='Number of threads for parallel fetching (default: 5)',
        )
        parser.add_argument(
            '--delay',
            type=float,
            default=1.0,
            help='Delay between requests in seconds (default: 1.0)',
        )
        parser.add_argument(
            '--verify',
            action='store_true',
            help='Verify articles after fetching',
        )
    
    def handle(self, *args, **options):
        target = options['target']
        days = options['days']
        sources = options['sources'].split(',') if options['sources'] != 'all' else ['all']
        threads = options['threads']
        delay = options['delay']
        should_verify = options['verify']
        
        self.stdout.write(self.style.SUCCESS(f'🚀 Starting bulk news fetch - Target: {target} articles'))
        self.stdout.write(f'📅 Fetching articles from last {days} days')
        self.stdout.write(f'🔧 Threads: {threads}, Delay: {delay}s')
        self.stdout.write(f'📡 Sources: {", ".join(sources)}')
        
        from core.models import Post
        import random
        
        fetcher = NewsFetcher()
        total_saved = 0
        batch = 1
        max_batches = 10  # Prevent infinite loops
        
        while total_saved < target and batch <= max_batches:
            self.stdout.write(f'\n📦 Batch {batch} - Current total: {total_saved}/{target}')
            
            # Clear articles for new batch
            fetcher.articles = []
            
            # Fetch based on selected sources
            if 'all' in sources or 'newsapi' in sources:
                self.stdout.write('  Fetching from NewsAPI...')
                fetcher.fetch_newsapi_detailed()
            
            if 'all' in sources or 'rss' in sources:
                self.stdout.write('  Fetching from RSS feeds...')
                fetcher.fetch_rss_feeds_detailed()
            
            if 'all' in sources or 'web' in sources:
                self.stdout.write('  Fetching from web scraping...')
                fetcher.fetch_web_scrape_detailed()
            
            # Remove duplicates
            unique_articles = fetcher.remove_duplicates(fetcher.articles)
            self.stdout.write(f'  Found {len(unique_articles)} unique articles')
            
            # Verify if requested
            if should_verify and unique_articles:
                self.stdout.write('  Verifying articles...')
                from core.news_verifier import EnhancedNewsVerifier
                verifier = EnhancedNewsVerifier()
                
                verified_articles = []
                for article in unique_articles:
                    result = verifier.verify_article(article)
                    article['verification_score'] = result['score']
                    article['verification_status'] = result['status']
                    if result['score'] >= 0.5:  # Only keep if not clearly fake
                        verified_articles.append(article)
                
                self.stdout.write(f'  Verified: {len(verified_articles)} passed')
                unique_articles = verified_articles
            
            # Save articles
            saved = fetcher.save_articles(unique_articles)
            total_saved += saved
            
            self.stdout.write(self.style.SUCCESS(f'  ✅ Batch {batch} saved: {saved} articles'))
            
            batch += 1
            
            # Stop if no new articles
            if saved == 0:
                self.stdout.write(self.style.WARNING('⚠️ No new articles found. Stopping.'))
                break
            
            # Wait between batches
            if total_saved < target:
                wait_time = random.uniform(5, 10)
                self.stdout.write(f'⏳ Waiting {wait_time:.1f} seconds before next batch...')
                time.sleep(wait_time)
        
        # Final report
        self.stdout.write(self.style.SUCCESS(f'\n🎉 COMPLETE! Total articles saved: {total_saved}'))
        
        if should_verify:
            # Count verified vs fake
            verified_count = Post.objects.filter(
                is_auto_fetched=True,
                verification_status='verified'
            ).count()
            fake_count = Post.objects.filter(
                is_auto_fetched=True,
                verification_status='fake'
            ).count()
            
            self.stdout.write(f' Statistics:')
            self.stdout.write(f'  • Verified: {verified_count}')
            self.stdout.write(f'  • Pending: {Post.objects.filter(verification_status="pending").count()}')
            self.stdout.write(f'  • Fake: {fake_count}')