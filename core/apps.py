from django.apps import AppConfig

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
    
    # def ready(self):
    #     """This runs automatically when Django starts"""
    #     # Auto-start news fetcher when Django starts
    #     import os
    #     # Only start in main process, not in reloader
    #     if os.environ.get('RUN_MAIN') or not os.environ.get('RUN_MAIN'):
    #         from .autostart import auto_fetcher
    #         # Small delay to ensure Django is fully loaded
    #         import threading
    #         def delayed_start():
    #             import time
    #             time.sleep(2)  # Wait 2 seconds for Django to fully initialize
    #             auto_fetcher.start()
            
    #         thread = threading.Thread(target=delayed_start, daemon=True)
    #         thread.start()