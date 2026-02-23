# core/management/commands/schedule_news.py (Enhanced)

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.core.management import call_command
from datetime import datetime, timedelta
import schedule
import time
import logging
import signal
import sys
import os
from threading import Event

from core.news_fetcher import NewsFetcher
from core.news_verifier import EnhancedNewsVerifier
from core.models import Post, SystemLog

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Advanced news scheduler with monitoring and recovery'
    
    def __init__(self):
        super().__init__()
        self.shutdown_event = Event()
        self.current_job = None
        
    def add_arguments(self, parser):
        parser.add_argument(
            '--interval',
            type=int,
            default=8,
            help='Fetch interval in hours (default: 8)',
        )
        parser.add_argument(
            '--target',
            type=int,
            default=500,
            help='Target articles per fetch (default: 500)',
        )
        parser.add_argument(
            '--verify',
            action='store_true',
            help='Enable auto-verification',
        )
        parser.add_argument(
            '--auto-approve',
            action='store_true',
            help='Auto-approve verified news',
        )
    
    def handle(self, *args, **options):
        interval = options['interval']
        target = options['target']
        auto_verify = options['verify']
        auto_approve = options['auto_approve']
        
        self.stdout.write(self.style.SUCCESS('🚀 Starting advanced news scheduler...'))
        self.stdout.write(f'📊 Interval: Every {interval} hours')
        self.stdout.write(f'🎯 Target per fetch: {target} articles')
        self.stdout.write(f'✅ Auto-verify: {auto_verify}')
        self.stdout.write(f'👍 Auto-approve: {auto_approve}')
        
        # Set up signal handlers
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        # Schedule jobs
        schedule.every(interval).hours.do(
            self.run_fetch_job, 
            target=target,
            auto_verify=auto_verify,
            auto_approve=auto_approve
        )
        
        # Schedule verification if enabled
        if auto_verify:
            schedule.every(2).hours.do(self.run_verification_job)
        
        # Schedule cleanup job
        schedule.every(24).hours.do(self.run_cleanup_job)
        
        # Run initial fetch
        self.stdout.write('Running initial fetch...')
        self.run_fetch_job(target, auto_verify, auto_approve)
        
        self.stdout.write(self.style.SUCCESS('Scheduler running. Press Ctrl+C to stop.'))
        
        # Main loop
        while not self.shutdown_event.is_set():
            try:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"Error in scheduler main loop: {e}")
                self.stdout.write(self.style.ERROR(f'Error: {e}'))
                time.sleep(60)
    
    def run_fetch_job(self, target=500, auto_verify=False, auto_approve=False):
        """Run fetch job with monitoring"""
        self.current_job = 'fetch'
        start_time = time.time()
        
        try:
            self.stdout.write(f"\n[{timezone.now()}] 📰 Starting fetch job...")
            
            # Create system log entry
            log = SystemLog.objects.create(
                action='news_fetch_start',
                details={'target': target}
            )
            
            # Run fetch command
            call_command(
                'fetch_news_bulk',
                target=target,
                sources='all',
                threads=5,
                verify=auto_verify
            )
            
            # Run verification if enabled
            if auto_verify:
                self.stdout.write(f"[{timezone.now()}] 🔍 Running auto-verification...")
                
                # Get recent unverified news
                recent_news = Post.objects.filter(
                    is_auto_fetched=True,
                    verification_status='pending',
                    created_at__gte=timezone.now() - timedelta(hours=24)
                )
                
                if recent_news.exists():
                    verifier = EnhancedNewsVerifier()
                    
                    for post in recent_news:
                        article = {
                            'title': post.title,
                            'content': post.content,
                            'url': post.external_url,
                            'source': post.external_source
                        }
                        
                        result = verifier.verify_article(article)
                        
                        post.verification_score = result['score']
                        post.verification_status = result['status']
                        post.verification_details = result['checks']
                        
                        if auto_approve and result['score'] >= 0.7:
                            post.is_approved = True
                        
                        post.save()
                    
                    self.stdout.write(f"Verified {recent_news.count()} articles")
            
            duration = time.time() - start_time
            log.details.update({
                'status': 'success',
                'duration': duration
            })
            log.save()
            
            self.stdout.write(self.style.SUCCESS(
                f"[{timezone.now()}] ✅ Fetch job completed in {duration:.1f}s"
            ))
            
        except Exception as e:
            logger.error(f"Error in fetch job: {e}")
            self.stdout.write(self.style.ERROR(f"❌ Fetch job failed: {e}"))
            
            # Log error
            SystemLog.objects.create(
                action='news_fetch_error',
                details={'error': str(e)}
            )
        
        self.current_job = None
    
    def run_verification_job(self):
        """Run verification job"""
        self.current_job = 'verify'
        
        try:
            self.stdout.write(f"[{timezone.now()}] 🔍 Running verification job...")
            
            # Get unverified posts
            unverified = Post.objects.filter(
                verification_status='pending',
                created_at__gte=timezone.now() - timedelta(days=7)
            )[:200]
            
            if unverified.exists():
                call_command('verify_news', limit=200)
                
        except Exception as e:
            logger.error(f"Error in verification job: {e}")
        
        self.current_job = None
    
    def run_cleanup_job(self):
        """Run cleanup job"""
        self.current_job = 'cleanup'
        
        try:
            self.stdout.write(f"[{timezone.now()}] 🧹 Running cleanup job...")
            
            # Remove old duplicate content
            cutoff = timezone.now() - timedelta(days=30)
            
            # Archive old fake news
            fake_news = Post.objects.filter(
                verification_status='fake',
                created_at__lte=cutoff
            )
            
            fake_news.update(status='archived')
            
            self.stdout.write(f"Archived {fake_news.count()} old fake news items")
            
            # Clean up old logs
            old_logs = SystemLog.objects.filter(
                created_at__lte=timezone.now() - timedelta(days=90)
            )
            old_logs.delete()
            
        except Exception as e:
            logger.error(f"Error in cleanup job: {e}")
        
        self.current_job = None
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.stdout.write(self.style.WARNING('\nShutting down scheduler...'))
        
        if self.current_job:
            self.stdout.write(f"Waiting for current job ({self.current_job}) to complete...")
            # Give current job time to complete
            time.sleep(10)
        
        self.shutdown_event.set()
        sys.exit(0)