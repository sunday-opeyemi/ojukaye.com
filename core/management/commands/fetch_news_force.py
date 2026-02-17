# core/management/commands/fetch_news_force.py
from django.core.management.base import BaseCommand
from core.news_fetcher import NewsFetcher
import time

class Command(BaseCommand):
    help = 'Force fetch news with full content scraping'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--categories',
            type=str,
            help='Comma-separated list of categories to fetch',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=0,
            help='Limit number of articles per source',
        )
    
    def handle(self, *args, **options):
        self.stdout.write('Force fetching news with full content...')
        self.stdout.write('This may take several minutes...')
        
        fetcher = NewsFetcher()
        
        # Clear existing articles if needed
        fetcher.articles = []
        
        # Fetch news
        saved_count = fetcher.fetch_all_news()
        
        if saved_count > 0:
            self.stdout.write(
                self.style.SUCCESS(f'Successfully saved {saved_count} news articles with full content!')
            )
        else:
            self.stdout.write(
                self.style.WARNING('No new articles were saved')
            )