from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import Advertisement, AdAnalytics
from datetime import timedelta

class Command(BaseCommand):
    help = 'Update ad analytics from the last 24 hours'
    
    def handle(self, *args, **options):
        yesterday = timezone.now().date() - timedelta(days=1)
        
        # In a real app, you would pull from ad tracking logs
        # This is a placeholder implementation
        
        active_ads = Advertisement.objects.filter(
            status='active',
            is_active=True
        )
        
        for ad in active_ads:
            # Simulate some analytics data
            analytics, created = AdAnalytics.objects.get_or_create(
                advertisement=ad,
                date=yesterday,
                defaults={
                    'impressions': 100,
                    'clicks': 5,
                    'cost': 0.5,  # 500 impressions * 0.001 rate
                }
            )
            
            if not created:
                # Update existing
                analytics.impressions += 100
                analytics.clicks += 5
                analytics.cost += 0.5
                analytics.save()
        
        self.stdout.write(self.style.SUCCESS(f'Updated analytics for {active_ads.count()} ads'))