# core/autostart.py - THIS RUNS AUTOMATICALLY WHEN DJANGO STARTS
import threading
import time
import logging
from datetime import datetime, timedelta
from django.core.management import call_command
from django.db import connection
from django.conf import settings
import sys
import os

logger = logging.getLogger(__name__)

class AutoNewsFetcher:
    """Runs automatically when Django starts - no commands needed!"""
    
    _instance = None
    _lock = threading.Lock()
    _running = False
    fetch_count = 0
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        # ============================================================
        # SIMPLE CONFIGURATION SWITCH - CHANGE THESE VALUES ONLY
        # ============================================================
        
        # MASTER SWITCH: False = Production Mode, True = Test Mode
        self.TEST_MODE = False  
        
        # TEST MODE SETTINGS (when TEST_MODE = True)
        self.test_interval = 5     
        self.test_unit = 'minutes'   
        self.test_days = 1           
        self.test_limit = 20         
        self.test_workers = 2        
        
        # PRODUCTION MODE SETTINGS (when TEST_MODE = False)
        self.prod_interval = 12      
        self.prod_unit = 'hours'     
        self.prod_days = 1           
        self.prod_limit = 100        
        self.prod_workers = 5        
        
        # ============================================================
        # DON'T CHANGE ANYTHING BELOW THIS LINE
        # ============================================================
        
        # Apply settings based on mode
        if self.TEST_MODE:
            self.fetch_interval = self._convert_to_seconds(self.test_interval, self.test_unit)
            self.days_to_fetch = self.test_days
            self.limit = self.test_limit
            self.workers = self.test_workers
            self.mode_name = "🧪 TEST MODE"
        else:
            self.fetch_interval = self._convert_to_seconds(self.prod_interval, self.prod_unit)
            self.days_to_fetch = self.prod_days
            self.limit = self.prod_limit
            self.workers = self.prod_workers
            self.mode_name = "🚀 PRODUCTION MODE"
        
        self.last_fetch_time = None
    
    def _convert_to_seconds(self, value, unit):
        """Convert interval to seconds"""
        unit = unit.lower()
        if unit == 'seconds' or unit == 'second' or unit == 'sec':
            return value
        elif unit == 'minutes' or unit == 'minute' or unit == 'min':
            return value * 60
        elif unit == 'hours' or unit == 'hour':
            return value * 3600
        else:
            # Default to minutes if unknown unit
            return value * 60
    
    def _format_interval(self, seconds):
        """Format seconds into readable string"""
        if seconds < 60:
            return f"{seconds} seconds"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f} minutes"
        else:
            hours = seconds / 3600
            return f"{hours:.1f} hours"
    
    def start(self):
        """Start the auto-fetcher in a background thread"""
        with self._lock:
            if self._running:
                return
            self._running = True
        
        thread = threading.Thread(target=self._run_forever, daemon=True)
        thread.start()
        
        # Display configuration
        interval_display = self._format_interval(self.fetch_interval)
        
        print("\n" + "="*70)
        print(f"AUTO NEWS FETCHER - CONFIGURATION")
        print("="*70)
        print(f"Mode: {self.mode_name}")
        print(f" Interval: Every {interval_display}")
        print(f"Fetching: Last {self.days_to_fetch} day(s)")
        print(f"Article limit: {self.limit}")
        print(f"Workers: {self.workers}")
        print("="*70)
        print()
        
        # Show how to change settings
        print("TO CHANGE SETTINGS:")
        print("   Open core/autostart.py and modify the values in the CONFIGURATION section")
        print()
    
    def _run_forever(self):
        """Run forever, fetching news at configured interval"""
        while True:
            try:
                # Wait for database to be ready
                self._wait_for_db()
                
                # Check if it's time to fetch
                current_time = datetime.now()
                
                # Respect the interval
                if self.last_fetch_time:
                    time_since_last = (current_time - self.last_fetch_time).total_seconds()
                    if time_since_last < self.fetch_interval:
                        # Not time yet, sleep a bit and check again
                        sleep_time = min(60, self.fetch_interval - time_since_last)
                        time.sleep(sleep_time)
                        continue
                
                # Fetch news
                self.fetch_count += 1
                self.last_fetch_time = current_time
                current_time_str = current_time.strftime('%Y-%m-%d %H:%M:%S')
                
                mode_icon = "🧪" if self.TEST_MODE else "🚀"
                print(f"\n[{current_time_str}] {mode_icon} FETCH #{self.fetch_count} starting...")
                print(f"📡 Fetching {self.limit} articles from last {self.days_to_fetch} day(s)...")
                
                # Run the fetch command
                call_command(
                    'fetch_news', 
                    f'--days={self.days_to_fetch}',
                    f'--limit={self.limit}',
                    f'--workers={self.workers}'
                )
                
                print(f"✅ {mode_icon} FETCH #{self.fetch_count} complete at {current_time_str}")
                
                # Calculate next fetch time
                next_fetch = current_time + timedelta(seconds=self.fetch_interval)
                next_fetch_str = next_fetch.strftime('%Y-%m-%d %H:%M:%S')
                interval_display = self._format_interval(self.fetch_interval)
                
                print(f"⏰ Next fetch in {interval_display} at approximately {next_fetch_str}")
                
                # Sleep for the interval
                if self.TEST_MODE and self.fetch_interval < 60:
                    # For short test intervals, show countdown
                    print(f"💤 Countdown: ", end='', flush=True)
                    for i in range(self.fetch_interval, 0, -1):
                        if not self._running:
                            return
                        if i % 2 == 0 or i <= 3:
                            print(f"{i}... ", end='', flush=True)
                        time.sleep(1)
                    print("GO! 🚀")
                else:
                    # For longer intervals, just sleep
                    time.sleep(self.fetch_interval)
                
            except Exception as e:
                print(f"\n❌ ERROR in auto-fetcher: {e}")
                logger.error(f"❌ Error in auto-fetcher: {e}")
                
                # Wait before retry
                wait_time = 30 if self.TEST_MODE else 60
                print(f"💤 Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
    
    def _wait_for_db(self):
        """Wait for database to be ready"""
        max_attempts = 30
        for i in range(max_attempts):
            try:
                connection.ensure_connection()
                return
            except:
                if i < max_attempts - 1:
                    time.sleep(2)
                else:
                    raise
    
    def stop(self):
        """Stop the auto-fetcher"""
        self._running = False
        print("🛑 Auto News Fetcher stopped")

# Create a single instance
auto_fetcher = AutoNewsFetcher()