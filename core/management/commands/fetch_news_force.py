# core/management/commands/fetch_news_force.py

from django.core.management.base import BaseCommand
from django.core.management import call_command

class Command(BaseCommand):
    help = 'Alias for fetch_news with force parameters'
    
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
        self.stdout.write(self.style.WARNING(
            '⚠️  This command is deprecated. Use `python manage.py fetch_news` instead.'
        ))
        self.stdout.write('Running fetch_news with force settings...\n')
        
        # Call the main fetch_news command with force parameters
        call_command(
            'fetch_news',
            target=1000,
            days=14,
            threads=10,
            verify=True,
            fast=False
        )