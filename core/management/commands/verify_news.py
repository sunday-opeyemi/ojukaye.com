# management/commands/verify_news.py

from django.core.management.base import BaseCommand
from core.news_verifier import verify_existing_posts
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Run AI verification on pending news submissions'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=50,
            help='Maximum number of posts to verify'
        )

    def handle(self, *args, **options):
        self.stdout.write('Starting news verification...')
        
        limit = options['limit']
        results = verify_existing_posts(limit)
        
        self.stdout.write(self.style.SUCCESS(f'Verified {len(results)} posts'))
        
        for result in results:
            self.stdout.write(f"  - {result['title']}: {result['score']} ({result['status']})")