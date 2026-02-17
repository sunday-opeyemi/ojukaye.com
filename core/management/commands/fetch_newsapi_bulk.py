from django.core.management.base import BaseCommand
from django.conf import settings
from core.models import Post, Category, User
import requests
from datetime import datetime, timedelta
from django.utils import timezone
import hashlib
import logging
from time import sleep
import random

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Fetch news day by day to work around API limits'
    
    def handle(self, *args, **options):
        api_key = getattr(settings, 'NEWS_API_KEY', '')
        
        # Get system user
        try:
            system_user = User.objects.get(username='news_bot')
        except User.DoesNotExist:
            system_user = User.objects.create_user(
                username='news_bot',
                email='news@ojukaye.com',
                password='unusablepassword123',
                first_name='News',
                last_name='Bot',
                is_active=False
            )
        
        total_saved = 0
        
        # Fetch for each of the last 30 days, one day at a time
        for days_ago in range(1, 31):
            date = timezone.now() - timedelta(days=days_ago)
            date_str = date.strftime('%Y-%m-%d')
            
            self.stdout.write(f'\n📅 Fetching news for {date_str}...')
            
            # Queries for this day
            queries = [
                f'Nigeria',
                f'Lagos',
                f'Abuja',
                f'Super Eagles',
                f'Nollywood',
            ]
            
            day_saved = 0
            
            for query in queries:
                try:
                    url = "https://newsapi.org/v2/everything"
                    params = {
                        'q': query,
                        'apiKey': api_key,
                        'pageSize': 100,
                        'language': 'en',
                        'from': date_str,
                        'to': date_str,
                        'sortBy': 'popularity',
                    }
                    
                    response = requests.get(url, params=params, timeout=30)
                    
                    if response.status_code == 200:
                        data = response.json()
                        articles = data.get('articles', [])
                        
                        if articles:
                            saved = self.save_articles(articles, system_user, query)
                            day_saved += saved
                            self.stdout.write(f'  {query}: {saved} articles', ending='  ')
                    
                    sleep(1)  # Rate limiting
                    
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'  Error: {e}'))
                    continue
            
            total_saved += day_saved
            self.stdout.write(self.style.SUCCESS(f'Day complete: {day_saved} articles (Total: {total_saved})'))
            sleep(2)  # Delay between days
        
        self.stdout.write(self.style.SUCCESS(f'\n TOTAL: {total_saved} articles saved!'))
    
    def save_articles(self, articles, system_user, query):
        saved = 0
        for article in articles:
            try:
                title = article.get('title', '').strip()
                if not title or '[Removed]' in title:
                    continue
                
                url = article.get('url', '')
                if not url:
                    continue
                
                external_id = hashlib.md5(url.encode()).hexdigest()
                
                if Post.objects.filter(external_id=external_id).exists():
                    continue
                
                # Get content
                content = article.get('content', '') or article.get('description', '')
                content = self.clean_html(content) if content else title
                
                # Get source
                source = article.get('source', {}).get('name', 'NewsAPI')
                
                # Get image
                image_url = article.get('urlToImage', '')
                
                # Detect category from search query and title
                category_name = self.detect_category(search_query, title)
                category, _ = Category.objects.get_or_create(
                    name=category_name,
                    defaults={'slug': category_name.lower().replace(' ', '-')}
                )
                
                # Parse date
                published_at = self.parse_date(article.get('publishedAt', ''))
                
                # Create post
                Post.objects.create(
                    title=title[:200],
                    content=content[:15000] if content else title[:500],
                    post_type='news',
                    category=category,
                    author=system_user,
                    external_source=f"NewsAPI: {source}",
                    external_url=url,
                    external_id=external_id,
                    image_url=image_url[:1000] if image_url else '',
                    published_at=published_at,
                    status='published',
                    is_auto_fetched=True,
                    is_approved=True,
                    verification_status='verified',
                    meta_description=content[:160] if content else title[:160],
                    views=random.randint(5, 50),
                )
                
                saved_count += 1
                
            except Exception as e:
                logger.error(f"Error saving article: {e}")
                continue
        
        return saved_count
    
    def clean_html(self, text):
        """Clean HTML from text"""
        import re
        if not text:
            return text
        clean = re.sub(r'<[^>]+>', '', text)
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean
    
    def detect_category(self, search_query, title):
        """Detect category from search query and title"""
        text = (search_query + ' ' + title).lower()
        
        if 'sport' in text or 'football' in text or 'basketball' in text:
            return 'Sports'
        elif 'technolog' in text or 'ai ' in text or 'digital' in text or 'software' in text:
            return 'Technology'
        elif 'business' in text or 'finance' in text or 'economy' in text or 'market' in text:
            return 'Business'
        elif 'health' in text or 'medical' in text or 'vaccine' in text or 'hospital' in text:
            return 'Health'
        elif 'entertainment' in text or 'music' in text or 'movie' in text or 'nollywood' in text:
            return 'Entertainment'
        elif 'politic' in text or 'president' in text or 'government' in text or 'tinubu' in text:
            return 'Politics'
        elif 'educat' in text or 'school' in text or 'university' in text:
            return 'Education'
        else:
            return 'Others News'
    
    def parse_date(self, date_str):
        """Parse date string"""
        if not date_str:
            return timezone.now()
        
        try:
            from dateutil import parser
            return parser.parse(date_str)
        except:
            return timezone.now()