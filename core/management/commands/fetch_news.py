# core/management/commands/fetch_news.py
from django.core.management.base import BaseCommand
from core.news_fetcher import NewsFetcher

class Command(BaseCommand):
    help = 'Fetch news using hybrid approach (scraping + APIs)'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--test',
            action='store_true',
            help='Test mode (fetch but don\'t save)',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=0,
            help='Limit number of sources to fetch',
        )
    
    def handle(self, *args, **options):
        self.stdout.write('Starting hybrid news fetch...')
        self.stdout.write('Methods: Google scrape + RSS + NewsAPI + Web scrape + Reddit')
        
        fetcher = NewsFetcher()
        
        if options['test']:
            # Test mode - just fetch and show
            self.stdout.write('Test mode - showing articles found:')
            
            # We'll manually call methods and show results
            test_methods = [
                ('Google News', fetcher.fetch_google_news_scrape),
                ('RSS Feeds', fetcher.fetch_rss_feeds),
                ('NewsAPI', fetcher.fetch_newsapi_general),
                ('Web Scrape', fetcher.fetch_web_scrape),
            ]
            
            for method_name, method_func in test_methods:
                self.stdout.write(f"\n Testing {method_name}...")
                try:
                    # Reset articles
                    fetcher.articles = []
                    method_func()
                    
                    self.stdout.write(f"  Found {len(fetcher.articles)} articles")
                    for i, article in enumerate(fetcher.articles[:3], 1):
                        self.stdout.write(f"  {i}. {article['title'][:60]}...")
                        self.stdout.write(f"     Source: {article['source']}")
                        self.stdout.write(f"     URL: {article['url'][:80]}...")
                except Exception as e:
                    self.stdout.write(f"Error: {e}")
            
        else:
            # Normal mode - fetch and save
            saved_count = fetcher.fetch_all_news()
            
            if saved_count > 0:
                self.stdout.write(
                    self.style.SUCCESS(f'Successfully saved {saved_count} news articles!')
                )
            else:
                self.stdout.write(
                    self.style.WARNING('No new articles were saved')
                )