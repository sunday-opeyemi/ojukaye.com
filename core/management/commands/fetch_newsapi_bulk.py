# core/management/commands/fetch_newsapi_bulk.py

from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from core.models import Post, Category, User
from core.news_fetcher import NewsFetcher, ContentExtractor, MediaExtractor, ImageExtractor
import requests
from datetime import datetime, timedelta
import hashlib
import logging
from time import sleep
import random
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Advanced bulk fetch from NewsAPI with full content and media extraction'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=100,
            help='Number of articles per query (max 100 for free plan)',
        )
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='Days back to fetch (default: 7)',
        )
        parser.add_argument(
            '--timeout',
            type=int,
            default=30,
            help='Timeout in seconds for API requests (default: 30)',
        )
        parser.add_argument(
            '--retries',
            type=int,
            default=3,
            help='Number of retries on failure (default: 3)',
        )
        parser.add_argument(
            '--threads',
            type=int,
            default=5,
            help='Number of threads for content extraction (default: 5)',
        )
        parser.add_argument(
            '--extract-full',
            action='store_true',
            default=True,
            help='Extract full content from article URLs',
        )
        parser.add_argument(
            '--verify',
            action='store_true',
            help='Verify articles after fetching',
        )
        parser.add_argument(
            '--categories',
            type=str,
            default='all',
            help='Comma-separated categories to fetch (politics,business,sports,etc)',
        )
    
    def handle(self, *args, **options):
        # Get arguments
        limit = min(options['limit'], 100)
        days = options['days']
        timeout = options['timeout']
        max_retries = options['retries']
        threads = options['threads']
        extract_full = options['extract_full']
        should_verify = options['verify']
        categories_filter = options['categories'].split(',') if options['categories'] != 'all' else None
        
        self.stdout.write(self.style.SUCCESS('🚀 Starting Advanced NewsAPI Bulk Fetch'))
        self.stdout.write(f'📅 Fetching from last {days} days')
        self.stdout.write(f'📄 {limit} articles per query')
        self.stdout.write(f'🔧 Threads: {threads}, Extract Full: {extract_full}')
        self.stdout.write(f'⏱️  Timeout: {timeout}s, Retries: {max_retries}')
        
        # Get API key
        api_key = getattr(settings, 'NEWS_API_KEY', '')
        if not api_key:
            self.stdout.write(self.style.ERROR('❌ NEWS_API_KEY not found in settings!'))
            return
        
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
        
        # Calculate date range
        from_date = (timezone.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        to_date = timezone.now().strftime('%Y-%m-%d')
        
        # Define comprehensive search queries
        queries = self._build_queries(limit, categories_filter)
        
        total_saved = 0
        total_found = 0
        all_articles = []
        
        # Fetch articles from NewsAPI
        for query_params in queries:
            q = query_params['q']
            self.stdout.write(f'\n🔍 Searching: "{q}"')
            
            articles = self._fetch_from_newsapi(
                api_key, q, limit, from_date, timeout, max_retries
            )
            
            if articles:
                self.stdout.write(f'  Found {len(articles)} articles')
                all_articles.extend(articles)
                total_found += len(articles)
            
            sleep(1)  # Rate limiting
        
        self.stdout.write(f'\n📊 Total articles fetched: {total_found}')
        
        if not all_articles:
            self.stdout.write(self.style.WARNING('No articles found'))
            return
        
        # Remove duplicates
        unique_articles = self._remove_duplicates(all_articles)
        self.stdout.write(f'📊 Unique articles: {len(unique_articles)}')
        
        # Extract full content in parallel if requested
        if extract_full and unique_articles:
            self.stdout.write('\n🔍 Extracting full content and media...')
            unique_articles = self._extract_full_content_parallel(unique_articles, threads)
        
        # Save articles
        saved_count = self._save_articles(unique_articles, system_user)
        
        # Verify if requested
        if should_verify and saved_count > 0:
            self.stdout.write('\n🔎 Verifying articles...')
            self._verify_articles()
        
        self.stdout.write(self.style.SUCCESS(
            f'\n🎉 COMPLETE! Articles saved: {saved_count} out of {len(unique_articles)}'
        ))
    
    def _build_queries(self, limit, categories_filter=None):
        """Build comprehensive search queries"""
        
        # Base queries
        base_queries = [
            # Nigeria-specific
            {'q': 'Nigeria', 'pageSize': limit},
            {'q': 'Lagos', 'pageSize': limit},
            {'q': 'Abuja', 'pageSize': limit},
            {'q': '"Nigerian government"', 'pageSize': limit},
            {'q': '"Nigerian economy" OR naira', 'pageSize': limit},
            {'q': '"Super Eagles" OR "Nigerian football"', 'pageSize': limit},
            {'q': 'Nollywood OR "Nigerian movies"', 'pageSize': limit},
            {'q': 'Tinubu', 'pageSize': limit},
            {'q': 'APC OR PDP', 'pageSize': limit},
            {'q': '"Nigerian music" OR Afrobeats', 'pageSize': limit},
            {'q': '"Nigerian technology" OR "Nigerian startup"', 'pageSize': limit},
            
            # African news
            {'q': 'Africa', 'pageSize': limit},
            {'q': 'Ghana', 'pageSize': limit},
            {'q': 'Kenya', 'pageSize': limit},
            {'q': '"South Africa"', 'pageSize': limit},
            {'q': '"African Union" OR AU', 'pageSize': limit},
        ]
        
        # Category-specific queries
        category_queries = {
            'politics': [
                {'q': 'politics Nigeria', 'pageSize': limit},
                {'q': 'election Nigeria', 'pageSize': limit},
                {'q': 'government Nigeria', 'pageSize': limit},
            ],
            'business': [
                {'q': 'business Nigeria', 'pageSize': limit},
                {'q': 'economy Nigeria', 'pageSize': limit},
                {'q': 'naira dollar', 'pageSize': limit},
            ],
            'sports': [
                {'q': 'sports Nigeria', 'pageSize': limit},
                {'q': 'football Nigeria', 'pageSize': limit},
                {'q': 'Super Eagles', 'pageSize': limit},
            ],
            'technology': [
                {'q': 'technology Nigeria', 'pageSize': limit},
                {'q': 'tech Nigeria', 'pageSize': limit},
                {'q': 'startup Nigeria', 'pageSize': limit},
            ],
            'entertainment': [
                {'q': 'entertainment Nigeria', 'pageSize': limit},
                {'q': 'Nollywood', 'pageSize': limit},
                {'q': 'music Nigeria', 'pageSize': limit},
            ],
            'health': [
                {'q': 'health Nigeria', 'pageSize': limit},
                {'q': 'medical Nigeria', 'pageSize': limit},
            ],
            'education': [
                {'q': 'education Nigeria', 'pageSize': limit},
                {'q': 'university Nigeria', 'pageSize': limit},
            ],
            'crime': [
                {'q': 'crime Nigeria', 'pageSize': limit},
                {'q': 'police Nigeria', 'pageSize': limit},
            ],
        }
        
        # Add category-specific queries if filtering
        if categories_filter:
            queries = []
            for category in categories_filter:
                if category in category_queries:
                    queries.extend(category_queries[category])
        else:
            queries = base_queries.copy()
            for cat_queries in category_queries.values():
                queries.extend(cat_queries)
        
        return queries
    
    def _fetch_from_newsapi(self, api_key, query, limit, from_date, timeout, max_retries):
        """Fetch articles from NewsAPI with retry logic"""
        
        for attempt in range(max_retries):
            try:
                url = "https://newsapi.org/v2/everything"
                params = {
                    'q': query,
                    'apiKey': api_key,
                    'pageSize': limit,
                    'page': 1,
                    'language': 'en',
                    'sortBy': 'publishedAt',
                    'from': from_date,
                }
                
                response = requests.get(url, params=params, timeout=timeout)
                
                if response.status_code == 200:
                    data = response.json()
                    return data.get('articles', [])
                    
                elif response.status_code == 426:
                    self.stdout.write(self.style.WARNING(
                        f'  ⚠️ Upgrade required for more results'
                    ))
                    return []
                else:
                    self.stdout.write(self.style.ERROR(
                        f'  ❌ Error {response.status_code}: {response.text[:100]}'
                    ))
                    if attempt < max_retries - 1:
                        sleep(2 ** attempt)
                        
            except requests.exceptions.Timeout:
                self.stdout.write(self.style.ERROR(f'  ⚠️ Timeout on attempt {attempt + 1}'))
                if attempt < max_retries - 1:
                    sleep(2 ** attempt)
                    
            except requests.exceptions.ConnectionError as e:
                self.stdout.write(self.style.ERROR(f'  ⚠️ Connection error'))
                if attempt < max_retries - 1:
                    sleep(2 ** attempt)
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  ❌ Unexpected error: {e}'))
                if attempt < max_retries - 1:
                    sleep(2)
        
        return []
    
    def _extract_full_content_parallel(self, articles, max_workers):
        """Extract full content in parallel"""
        
        fetcher = NewsFetcher()  # Use the enhanced fetcher
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all extraction tasks
            future_to_article = {
                executor.submit(self._extract_single_article, article, fetcher): article 
                for article in articles
            }
            
            # Process results as they complete
            completed = 0
            for future in as_completed(future_to_article):
                try:
                    article = future.result(timeout=60)
                    completed += 1
                    if completed % 10 == 0:
                        self.stdout.write(f'    Progress: {completed}/{len(articles)}', ending='\r')
                except Exception as e:
                    logger.error(f"Error extracting content: {e}")
                    continue
            
            self.stdout.write(f'    Completed: {completed}/{len(articles)}')
        
        return articles
    
    def _extract_single_article(self, article, fetcher):
        """Extract content for a single article"""
        try:
            url = article.get('url')
            if not url:
                return article
            
            # Extract full content and media
            content, videos, audios, image = fetcher.extract_full_content_with_media(url)
            
            if content:
                article['full_content'] = content
            if videos:
                article['videos'] = videos
            if audios:
                article['audios'] = audios
            if image:
                article['extracted_image'] = image
                
        except Exception as e:
            logger.error(f"Error extracting {url}: {e}")
        
        return article
    
    def _remove_duplicates(self, articles):
        """Remove duplicate articles"""
        unique = []
        seen_urls = set()
        seen_titles = set()
        
        for article in articles:
            url = article.get('url', '')
            title = article.get('title', '').lower().strip()
            
            if not url or not title:
                continue
            
            # Check URL
            if url in seen_urls:
                continue
            seen_urls.add(url)
            
            # Check title similarity
            is_duplicate = False
            for seen_title in seen_titles:
                if self._title_similarity(title, seen_title) > 0.7:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                seen_titles.add(title)
                unique.append(article)
        
        return unique
    
    def _title_similarity(self, title1, title2):
        """Calculate title similarity"""
        words1 = set(title1.split())
        words2 = set(title2.split())
        
        if not words1 or not words2:
            return 0
        
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union if union > 0 else 0
    
    def _save_articles(self, articles, system_user):
        """Save articles to database"""
        saved_count = 0
        
        for article in articles:
            try:
                # Basic validation
                title = article.get('title', '').strip()
                url = article.get('url', '')
                
                if not title or not url or title == '[Removed]':
                    continue
                
                # Generate ID
                external_id = hashlib.md5(url.encode()).hexdigest()
                
                # Check if exists
                if Post.objects.filter(external_id=external_id).exists():
                    continue
                
                # Get content
                content = article.get('full_content') or article.get('content') or article.get('description') or title
                if content:
                    content = self.clean_html(str(content))
                
                # Get source
                source_obj = article.get('source', {})
                source = source_obj.get('name', 'Unknown') if source_obj else 'Unknown'
                source = source.replace('NewsAPI:', '').replace('NewsAPI', '').strip()
                
                # Get image
                image_url = article.get('extracted_image') or article.get('urlToImage') or ''
                
                # Get media
                videos = article.get('videos', [])
                audios = article.get('audios', [])
                
                # Detect category
                category_name = self.detect_category(article.get('search_query', ''), title)
                category, _ = Category.objects.get_or_create(
                    name=category_name,
                    defaults={'slug': category_name.lower().replace(' ', '-')}
                )
                
                # Parse date
                published_at = self.parse_date(article.get('publishedAt'))
                
                # Create post
                post = Post.objects.create(
                    title=title[:200],
                    content=content[:15000] if content else title[:500],
                    post_type='news',
                    category=category,
                    author=system_user,
                    external_source=source[:100],
                    external_url=url[:500],
                    external_id=external_id,
                    image_url=str(image_url)[:1000] if image_url else '',
                    published_at=published_at,
                    status='published',
                    is_auto_fetched=True,
                    is_approved=True,
                    verification_status='pending',
                    meta_description=content[:160] if content else title[:160],
                    views=random.randint(5, 50),
                    video_urls=videos if videos else None,
                    audio_urls=audios if audios else None,
                    has_media=bool(videos or audios),
                )
                
                saved_count += 1
                
                if saved_count % 10 == 0:
                    self.stdout.write(f'    Saved: {saved_count}', ending='\r')
                
            except Exception as e:
                logger.error(f"Error saving article: {e}")
                continue
        
        return saved_count
    
    def _verify_articles(self):
        """Run verification on saved articles"""
        try:
            from core.management.commands.verify_news import Command as VerifyCommand
            
            verify_cmd = VerifyCommand()
            verify_cmd.handle(limit=100, auto_approve=True)
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Verification failed: {e}'))
    
    def clean_html(self, text):
        """Clean HTML from text"""
        if not text:
            return text
        clean = re.sub(r'<[^>]+>', '', str(text))
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean
    
    def detect_category(self, search_query, title):
        """Detect category from search query and title"""
        text = (str(search_query) + ' ' + str(title)).lower()
        
        categories = {
            'Sports': ['sport', 'football', 'basketball', 'super eagles', 'match', 'league', 'player', 'goal', 'athlete'],
            'Technology': ['technolog', 'ai', 'digital', 'software', 'tech', 'computer', 'internet', 'app', 'startup', 'cyber'],
            'Business': ['business', 'finance', 'economy', 'market', 'naira', 'stock', 'investment', 'bank', 'company', 'trade'],
            'Health': ['health', 'medical', 'vaccine', 'hospital', 'disease', 'doctor', 'patient', 'covid', 'treatment'],
            'Entertainment': ['entertainment', 'music', 'movie', 'nollywood', 'actor', 'actress', 'celebrity', 'film', 'award'],
            'Politics': ['politic', 'president', 'government', 'tinubu', 'apc', 'pdp', 'senate', 'governor', 'election', 'minister'],
            'Education': ['educat', 'school', 'university', 'student', 'teacher', 'college', 'exam', 'academic'],
            'Crime': ['crime', 'police', 'arrest', 'court', 'judge', 'robbery', 'murder', 'kidnap', 'bandit'],
        }
        
        for category, keywords in categories.items():
            if any(keyword in text for keyword in keywords):
                return category
        
        return 'News'
    
    def parse_date(self, date_str):
        """Parse date string"""
        if not date_str:
            return timezone.now()
        
        try:
            from dateutil import parser
            return parser.parse(str(date_str))
        except:
            return timezone.now()