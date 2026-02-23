# news_auto_fetcher_service.py
# This runs as a background service on Windows

import subprocess
import schedule
import time
import logging
import os
import sys
from datetime import datetime
import win32serviceutil
import win32service
import win32event
import servicemanager

class NewsFetcherService(win32serviceutil.ServiceFramework):
    """Windows Service for auto-fetching news"""
    
    _svc_name_ = "OjukayeNewsFetcher"
    _svc_display_name_ = "Ojukaye News Auto Fetcher"
    _svc_description_ = "Automatically fetches news every 12 hours"
    
    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.running = True
        
    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)
        self.running = False
        
    def SvcDoRun(self):
        servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE,
                              servicemanager.PYS_SERVICE_STARTED,
                              (self._svc_name_, ''))
        self.main()
    
    def main(self):
        """Main service loop"""
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(message)s',
            handlers=[
                logging.FileHandler('C:\\Users\\DELL\\Desktop\\NewsBlog\\ojukaye\\news_fetcher.log'),
                logging.StreamHandler()
            ]
        )
        
        # Get the project path
        project_path = r'C:\Users\DELL\Desktop\NewsBlog\ojukaye'
        venv_python = r'C:\Users\DELL\Desktop\NewsBlog\newsenv\Scripts\python.exe'
        
        def run_fetch():
            """Run the fetch command"""
            try:
                logging.info("🚀 Auto-fetching news...")
                
                # Run the fetch command
                result = subprocess.run([
                    venv_python, 'manage.py', 'fetch_news',
                    '--days', '14',      # Last 14 days
                    '--limit', '200',    # 200 per query
                    '--workers', '15',   # 15 threads
                    '--quiet'            # Quiet mode
                ], cwd=project_path, capture_output=True, text=True)
                
                if result.returncode == 0:
                    logging.info(f"✅ Fetch completed at {datetime.now()}")
                else:
                    logging.error(f"❌ Fetch failed: {result.stderr}")
                    
            except Exception as e:
                logging.error(f"❌ Error: {e}")
        
        # Schedule: Run every 12 hours
        schedule.every(12).hours.do(run_fetch)
        
        # Run immediately on start
        run_fetch()
        
        # Keep running
        while self.running:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
            
            # Also check if we should stop
            if win32event.WaitForSingleObject(self.hWaitStop, 0) == win32event.WAIT_OBJECT_0:
                break

if __name__ == '__main__':
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(NewsFetcherService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(NewsFetcherService)