from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import Advertisement
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Check and expire outdated ads'
    
    def handle(self, *args, **options):
        expired_ads = Advertisement.objects.filter(
            end_date__lt=timezone.now(),
            status__in=['active', 'approved']
        )
        
        count = expired_ads.count()
        expired_ads.update(status='expired', is_active=False)
        
        self.stdout.write(self.style.SUCCESS(f'Expired {count} ads'))
        logger.info(f'Expired {count} ads')