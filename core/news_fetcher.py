# core/news_fetcher.py
import requests
import feedparser
import json
from datetime import datetime, timedelta
from django.utils import timezone
from django.conf import settings
from .models import Post, Category, User
import logging
import re
from bs4 import BeautifulSoup
import random
from time import sleep
from urllib.parse import urlparse, urljoin
import hashlib

logger = logging.getLogger(__name__)

class NewsFetcher:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        self.articles = []
        
    def fetch_all_news(self):
        """Fetch news using multiple methods with full content scraping"""
        logger.info("Starting hybrid news fetch...")
        
        # Define all fetching methods with weights
        methods = [
            (self.fetch_google_news_scrape, 3),
            (self.fetch_african_news, 3),
            (self.fetch_rss_feeds, 2),
            (self.fetch_newsapi_general, 2),
            (self.fetch_web_scrape_detailed, 2),
            (self.fetch_reddit_news, 1),
        ]
        
        # Execute methods
        for method, weight in methods:
            try:
                logger.info(f"Executing: {method.__name__}")
                sleep(random.uniform(1, 2))  # Delay to avoid rate limiting
                method()
                logger.info(f"Completed: {method.__name__}")
            except Exception as e:
                logger.error(f"Error in {method.__name__}: {e}")
                continue
        
        # Remove duplicates
        unique_articles = self.remove_duplicates(self.articles)
        logger.info(f"Found {len(unique_articles)} unique articles out of {len(self.articles)} total")
        
        # Save to database with full content
        saved_count = self.save_articles_with_full_content(unique_articles)
        
        logger.info(f"Total articles found: {len(unique_articles)}")
        logger.info(f"Articles saved: {saved_count}")
        
        return saved_count

    def fetch_newsapi_general(self):
        """Fetch news from NewsAPI.org using your API key"""
        api_key = getattr(settings, 'NEWS_API_KEY', '')
        
        if not api_key:
            logger.warning("NewsAPI key not found. Skipping NewsAPI fetch.")
            return
        
        try:
            # Multiple queries to get more news
            queries = [
                {'country': 'ng', 'pageSize': 100},  # Nigeria headlines
                {'country': 'us', 'category': 'general', 'pageSize': 50},  # International
                {'country': 'gb', 'category': 'general', 'pageSize': 50},  # UK
                {'category': 'technology', 'country': 'ng', 'pageSize': 50},
                {'category': 'business', 'country': 'ng', 'pageSize': 50},
                {'category': 'sports', 'country': 'ng', 'pageSize': 50},
                {'category': 'entertainment', 'country': 'ng', 'pageSize': 50},
                {'category': 'health', 'country': 'ng', 'pageSize': 50},
                {'category': 'science', 'country': 'ng', 'pageSize': 50},
                {'q': 'Nigeria', 'pageSize': 100},  # Specific Nigeria search
                {'q': 'Lagos', 'pageSize': 50},
                {'q': 'Abuja', 'pageSize': 50},
                {'q': 'Africa', 'pageSize': 100},
            ]
            
            for params in queries:
                try:
                    url = "https://newsapi.org/v2/top-headlines"
                    if 'q' in params:
                        url = "https://newsapi.org/v2/everything"  # Use everything endpoint for search
                    
                    params['apiKey'] = api_key
                    params['language'] = 'en'
                    
                    response = requests.get(url, params=params, timeout=15)
                    if response.status_code == 200:
                        data = response.json()
                        articles = data.get('articles', [])
                        
                        for article in articles[:20]:  # Limit per query
                            self._process_newsapi_article(article)
                        
                        logger.info(f"Fetched {len(articles)} articles from NewsAPI with params: {params}")
                    else:
                        logger.warning(f"NewsAPI returned {response.status_code}: {response.text}")
                    
                    sleep(0.5)  # Rate limiting
                    
                except Exception as e:
                    logger.error(f"Error in NewsAPI query {params}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error in NewsAPI fetch: {e}")
        
        # Also fetch technology news
        try:
            params = {
                'category': 'technology',
                'country': 'ng',
                'apiKey': api_key,
                'pageSize': 20
            }
            response = requests.get(url, params=params, timeout=15)
            if response.status_code == 200:
                data = response.json()
                articles = data.get('articles', [])
                
                for article in articles[:10]:
                    # Similar processing as above
                    self._process_newsapi_article(article, 'Technology')
                    
        except Exception as e:
            logger.error(f"Error in NewsAPI tech fetch: {e}")
        
        # Fetch business news
        try:
            params = {
                'category': 'business',
                'country': 'ng',
                'apiKey': api_key,
                'pageSize': 20
            }
            response = requests.get(url, params=params, timeout=15)
            if response.status_code == 200:
                data = response.json()
                articles = data.get('articles', [])
                
                for article in articles[:10]:
                    self._process_newsapi_article(article, 'Business')
                    
        except Exception as e:
            logger.error(f"Error in NewsAPI business fetch: {e}")
            
        # Fetch sports news
        try:
            params = {
                'category': 'sports',
                'country': 'ng',
                'apiKey': api_key,
                'pageSize': 20
            }
            response = requests.get(url, params=params, timeout=15)
            if response.status_code == 200:
                data = response.json()
                articles = data.get('articles', [])
                
                for article in articles[:10]:
                    self._process_newsapi_article(article, 'Sports')
                    
        except Exception as e:
            logger.error(f"Error in NewsAPI sports fetch: {e}")
    
    def _process_newsapi_article(self, article, default_category='News'):
        """Helper method to process NewsAPI articles"""
        try:
            title = article.get('title', '').strip()
            url = article.get('url', '')
            
            if not title or not url or '[Removed]' in title:
                return
            
            external_id = hashlib.md5(url.encode()).hexdigest()
            
            if Post.objects.filter(external_id=external_id).exists():
                return
            
            content = article.get('content', '') or article.get('description', '')
            
            # Try to extract full content
            if not content or len(content) < 200:
                full_content = self.extract_full_content(url)
                if full_content:
                    content = full_content
            
            if content:
                content = self.clean_html(content)
            
            source_name = article.get('source', {}).get('name', 'NewsAPI')
            image_url = article.get('urlToImage', '')
            
            if not image_url:
                image_url = self.scrape_page_image(url)
            
            published_at = self.parse_date(article.get('publishedAt', ''))
            
            self.articles.append({
                'title': title,
                'content': content or title[:500],
                'url': url,
                'source': f"NewsAPI: {source_name}",
                'image_url': image_url,
                'published_at': published_at,
                'category': default_category,
                'external_id': external_id,
                'method': 'newsapi',
                'is_banner': self.is_trending_title(title),
                'full_content_scraped': bool(content and len(content) > 500),
            })
            
        except Exception as e:
            logger.error(f"Error processing NewsAPI article in helper: {e}")
    
    def fetch_reddit_news(self):
        """Fetch news from Reddit"""
        try:
            # Nigeria subreddits
            subreddits = ['Nigeria', 'Africa', 'worldnews', 'technology', 'business']
            
            for subreddit in subreddits:
                try:
                    url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit=15"
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                    
                    response = requests.get(url, headers=headers, timeout=10)
                    if response.status_code == 200:
                        data = response.json()
                        posts = data.get('data', {}).get('children', [])
                        
                        for post in posts:
                            try:
                                post_data = post.get('data', {})
                                title = post_data.get('title', '').strip()
                                url = post_data.get('url', '')
                                
                                if not title or not url:
                                    continue
                                
                                # Filter for Nigeria/Africa if in international subreddits
                                if subreddit in ['worldnews', 'technology', 'business']:
                                    title_lower = title.lower()
                                    if not any(k in title_lower for k in ['nigeria', 'africa', 'nigerian', 'lagos', 'abuja']):
                                        continue
                                
                                external_id = hashlib.md5(url.encode()).hexdigest()
                                
                                if Post.objects.filter(external_id=external_id).exists():
                                    continue
                                
                                # Get content
                                content = post_data.get('selftext', '') or title
                                
                                # Try to extract full content for external links
                                if not post_data.get('is_self', False):
                                    full_content = self.extract_full_content(url)
                                    if full_content:
                                        content = full_content
                                
                                # Clean content
                                if content:
                                    content = self.clean_html(content)
                                
                                # Get image
                                image_url = ''
                                if not post_data.get('is_self', False):
                                    if url.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                                        image_url = url
                                    else:
                                        image_url = self.scrape_page_image(url)
                                
                                if not image_url and 'thumbnail' in post_data:
                                    thumb = post_data.get('thumbnail', '')
                                    if thumb and thumb not in ['self', 'default', 'nsfw']:
                                        image_url = thumb
                                
                                # Detect category
                                category = self.detect_category_from_content(title, content)
                                if subreddit == 'technology':
                                    category = 'Technology'
                                elif subreddit == 'business':
                                    category = 'Business'
                                
                                self.articles.append({
                                    'title': title,
                                    'content': content[:5000],
                                    'url': url,
                                    'source': f"Reddit r/{subreddit}",
                                    'image_url': image_url,
                                    'published_at': timezone.now(),
                                    'category': category or 'News',
                                    'external_id': external_id,
                                    'method': 'reddit',
                                    'is_banner': self.is_trending_title(title),
                                    'full_content_scraped': bool(content and len(content) > 500),
                                })
                                
                            except Exception as e:
                                logger.error(f"Error processing Reddit post: {e}")
                                continue
                                
                    sleep(1)  # Be nice to Reddit
                    
                except Exception as e:
                    logger.error(f"Error fetching from r/{subreddit}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error in Reddit fetch: {e}")

    def fetch_african_news(self):
        """Fetch African news with full content scraping"""
        african_sources = [
            ('Premium Times', 'https://www.premiumtimesng.com/feed/', 'Nigeria', 'Politics'),
            ('Vanguard', 'https://www.vanguardngr.com/feed/', 'Nigeria', 'News'),
            ('Punch', 'https://punchng.com/feed/', 'Nigeria', 'News'),
            ('Daily Trust', 'https://dailytrust.com/feed/', 'Nigeria', 'News'),
            ('Leadership', 'https://leadership.ng/feed/', 'Nigeria', 'News'),
            ('Independent NG', 'https://independent.ng/feed/', 'Nigeria', 'News'),
            ('Nairametrics', 'https://nairametrics.com/feed/', 'Nigeria', 'Economy'),
            ('Business Day', 'https://businessday.ng/feed/', 'Nigeria', 'Business'),
            ('TechCabal', 'https://techcabal.com/feed/', 'Africa', 'Technology'),
            ('Africa News', 'https://www.africanews.com/feed/rss', 'Africa', 'News'),
            ('Sahara Reporters', 'https://saharareporters.com/feeds/latest/feed', 'Nigeria', 'News'),
            ('The Guardian NG', 'https://guardian.ng/feed/', 'Nigeria', 'News'),
            ('Tribune', 'https://tribuneonlineng.com/feed/', 'Nigeria', 'News'),
            ('ThisDay', 'https://www.thisdaylive.com/index.php/feed/', 'Nigeria', 'News'),
            ('The Cable', 'https://www.thecable.ng/feed', 'Nigeria', 'News'),
        ]
        
        for source_name, feed_url, country, default_category in african_sources:
            try:
                logger.info(f"Fetching from {source_name}...")
                feed = feedparser.parse(feed_url)
                
                for entry in feed.entries[:15]:  # Get 15 from each source
                    try:
                        title = entry.get('title', '').strip()
                        if not title:
                            continue
                        
                        url = entry.get('link', '')
                        if not url:
                            continue
                        
                        # Generate external_id from URL hash
                        external_id = hashlib.md5(url.encode()).hexdigest()
                        
                        # Check if already exists
                        if Post.objects.filter(external_id=external_id).exists():
                            continue
                        
                        # Extract content
                        content = self.extract_full_content(url)
                        
                        # If content extraction failed, use summary
                        if not content and 'summary' in entry:
                            content = entry.summary
                        elif not content and 'description' in entry:
                            content = entry.description
                        
                        # Clean HTML from content
                        if content:
                            content = self.clean_html(content)
                        
                        # Extract image
                        image_url = self.extract_image(entry, url, content)
                        
                        # Detect category
                        category = self.detect_category_from_content(title, content or '')
                        
                        # Get published date
                        published_at = self.parse_date(entry.get('published', ''))
                        
                        # Mark as trending if relevant
                        is_trending = self.is_trending_title(title)
                        
                        self.articles.append({
                            'title': title,
                            'content': content or title[:500],
                            'url': url,
                            'source': source_name,
                            'image_url': image_url,
                            'published_at': published_at,
                            'category': category or default_category,
                            'external_id': external_id,
                            'method': 'rss_africa',
                            'is_banner': is_trending,
                            'full_content_scraped': bool(content and len(content) > 500),
                        })
                        
                        sleep(0.5)  # Small delay between articles
                        
                    except Exception as e:
                        logger.error(f"Error processing article from {source_name}: {e}")
                        continue
                        
            except Exception as e:
                logger.error(f"Error fetching {source_name}: {e}")
                continue

    def extract_full_content(self, url):
        """Extract full article content from URL"""
        try:
            response = self.session.get(url, timeout=15, allow_redirects=True)
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Remove unwanted elements
            for element in soup.find_all(['script', 'style', 'nav', 'footer', 'aside', 'form', 'header', 'iframe']):
                element.decompose()
            
            # Try to find article content using common selectors
            content_selectors = [
                'article', 
                '.article-content', 
                '.post-content', 
                '.entry-content',
                '.story-content', 
                '.content-area', 
                '#content', 
                '.main-content',
                '[itemprop="articleBody"]', 
                '.article-body', 
                '.article-text',
                '.post-body',
                '.entry',
                '.story',
                '.news-detail',
                '.detail-content'
            ]
            
            article_content = None
            for selector in content_selectors:
                article_content = soup.select_one(selector)
                if article_content:
                    break
            
            # If no specific selector found, try to get the main content
            if not article_content:
                # Get all paragraphs and headers
                main_content = soup.find('main') or soup.find('div', {'role': 'main'})
                if main_content:
                    article_content = main_content
                else:
                    # Get all paragraphs from body
                    paragraphs = soup.find_all('p')
                    if len(paragraphs) > 3:
                        # Join meaningful paragraphs
                        article_text = []
                        for p in paragraphs[:20]:  # First 20 paragraphs
                            text = p.get_text(strip=True)
                            if len(text) > 50:  # Only meaningful paragraphs
                                article_text.append(text)
                        
                        if article_text:
                            return '\n\n'.join(article_text)
            
            if article_content:
                # Extract text
                text = article_content.get_text(separator='\n', strip=True)
                
                # Clean up text
                lines = [line.strip() for line in text.split('\n') if line.strip()]
                lines = [line for line in lines if len(line) > 40]  # Remove short lines
                
                # Join lines and limit to reasonable length
                full_text = '\n\n'.join(lines[:75])  # First 75 paragraphs
                
                if len(full_text) > 800:  # Ensure we have substantial content
                    return full_text[:15000]  # Limit to 15k chars
            
            return None
            
        except Exception as e:
            logger.error(f"Error extracting content from {url}: {e}")
            return None

    def clean_html(self, text):
        """Clean HTML from text"""
        if not text:
            return text
        
        # Remove HTML tags
        clean = re.sub(r'<[^>]+>', '', text)
        # Remove multiple spaces and newlines
        clean = re.sub(r'\s+', ' ', clean).strip()
        # Remove special characters but keep basic punctuation
        clean = re.sub(r'[^\w\s.,!?-]', '', clean)
        
        return clean

    def extract_image(self, entry, url, content):
        """Extract image from various sources"""
        image_url = ''
        
        # 1. Check RSS media content
        if hasattr(entry, 'media_content'):
            for media in entry.media_content:
                if media.get('medium') == 'image' and media.get('url'):
                    image_url = media.get('url')
                    break
        
        # 2. Check enclosures
        if not image_url and hasattr(entry, 'enclosures'):
            for enc in entry.enclosures:
                if enc.get('type', '').startswith('image/'):
                    image_url = enc.get('href', '')
                    break
        
        # 3. Check content for images
        if not image_url and content:
            # Look for image URLs in content
            img_pattern = r'https?://[^\s]+\.(?:jpg|jpeg|png|gif|webp)'
            matches = re.findall(img_pattern, content)
            if matches:
                image_url = matches[0]
        
        # 4. Scrape page for images
        if not image_url:
            image_url = self.scrape_page_image(url)
        
        # 5. Use default based on category
        if not image_url:
            # Generate a placeholder based on category
            category = self.detect_category_from_content(entry.get('title', ''), content or '')
            image_url = self.get_category_placeholder(category)
        
        return image_url

    def scrape_page_image(self, url):
        """Scrape image from webpage"""
        try:
            response = self.session.get(url, timeout=10, allow_redirects=True)
            if response.status_code != 200:
                return ''
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Try Open Graph image first
            og_image = soup.find('meta', property='og:image')
            if og_image and og_image.get('content'):
                return og_image['content']
            
            # Try Twitter image
            twitter_image = soup.find('meta', attrs={'name': 'twitter:image'})
            if twitter_image and twitter_image.get('content'):
                return twitter_image['content']
            
            # Try to find large content images
            images = soup.find_all('img')
            for img in images:
                src = img.get('src') or img.get('data-src') or img.get('data-original')
                if not src:
                    continue
                
                # Check if it's likely a content image
                classes = ' '.join(img.get('class', [])).lower()
                alt = (img.get('alt') or '').lower()
                width = img.get('width')
                height = img.get('height')
                
                # Skip small images and icons
                if any(word in classes for word in ['icon', 'logo', 'avatar', 'thumb', 'spinner']):
                    continue
                if any(word in alt for word in ['icon', 'logo', 'avatar']):
                    continue
                if width and int(width or 0) < 200:
                    continue
                if height and int(height or 0) < 200:
                    continue
                
                # Make URL absolute
                if src.startswith('//'):
                    src = 'https:' + src
                elif src.startswith('/'):
                    parsed_url = urlparse(url)
                    src = f"{parsed_url.scheme}://{parsed_url.netloc}{src}"
                elif not src.startswith('http'):
                    src = urljoin(url, src)
                
                return src
            
            return ''
            
        except Exception as e:
            logger.error(f"Error scraping image from {url}: {e}")
            return ''

    def get_category_placeholder(self, category):
        """Get placeholder image based on category"""
        placeholders = {
            'Politics': 'https://images.unsplash.com/photo-1551135049-8a33b2fb2f7f?w=800&q=80',
            'Economy': 'https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=800&q=80',
            'Sports': 'https://images.unsplash.com/photo-1461896836934-ffe607ba8211?w=800&q=80',
            'Technology': 'https://images.unsplash.com/photo-1518709268805-4e9042af2176?w=800&q=80',
            'Entertainment': 'https://images.unsplash.com/photo-1493225457124-a3eb161ffa5f?w=800&q=80',
            'Business': 'https://images.unsplash.com/photo-1665686306577-32e6bfa1d1d1?w=800&q=80',
            'Health': 'https://images.unsplash.com/photo-1576091160399-112ba8d25d1f?w=800&q=80',
            'Education': 'https://images.unsplash.com/photo-1523050854058-8df90110c9f1?w=800&q=80',
            'Crime': 'https://images.unsplash.com/photo-1589571894960-20bbe2828d0a?w=800&q=80',
            'News': 'https://images.unsplash.com/photo-1588681664899-f142ff2dc9b1?w=800&q=80',
        }
        return placeholders.get(category, placeholders['News'])

    def detect_category_from_content(self, title, content):
        """Detect category from title and content"""
        text = (title + ' ' + content).lower()
        
        categories = {
            'Politics': ['president', 'senate', 'governor', 'election', 'politic', 'minister', 'assembly', 'vote', 'campaign', 'party', 'government', 'parliament', 'tinubu', 'buhari', 'obia', 'atiku', 'apc', 'pdp', 'labour'],
            'Economy': ['naira', 'dollar', 'economy', 'inflation', 'budget', 'finance', 'market', 'stock', 'investment', 'business', 'bank', 'cbn', 'exchange', 'tax', 'revenue', 'trade', 'import', 'export'],
            'Sports': ['sport', 'football', 'basketball', 'athlete', 'match', 'league', 'championship', 'goal', 'player', 'super eagles', 'nfl', 'nba', 'super falcons', 'world cup'],
            'Technology': ['tech', 'digital', 'app', 'software', 'internet', 'phone', 'computer', 'startup', 'ai', 'artificial intelligence', 'data', 'cyber', '5g', 'mobile', 'innovation'],
            'Entertainment': ['music', 'movie', 'actor', 'actress', 'celebrity', 'nollywood', 'film', 'show', 'award', 'bobrisky', 'davido', 'burna boy', 'wizkid', 'tiwa savage'],
            'Health': ['health', 'hospital', 'doctor', 'medical', 'disease', 'vaccine', 'treatment', 'patient', 'covid', 'malaria', 'fever', 'medicine', 'clinic'],
            'Education': ['school', 'university', 'student', 'teacher', 'education', 'exam', 'learning', 'college', 'polytechnic', 'waec', 'neco', 'jamb'],
            'Crime': ['crime', 'robber', 'kill', 'murder', 'police', 'arrest', 'court', 'judge', 'law', 'theft', 'fraud', 'kidnap', 'bandit', 'terrorist'],
            'Business': ['business', 'company', 'entrepreneur', 'ceo', 'startup', 'enterprise', 'corporate', 'industry', 'manufacturing'],
            'World': ['world', 'international', 'global', 'foreign', 'united nations', 'usa', 'uk', 'china', 'russia', 'europe'],
        }
        
        for category, keywords in categories.items():
            if any(keyword in text for keyword in keywords):
                return category
        
        return 'News'

    def is_trending_title(self, title):
        """Check if title indicates trending/breaking news"""
        if not title:
            return False
        
        title_lower = title.lower()
        trending_keywords = [
            'breaking', 'exclusive', 'latest', 'just in',
            'urgent', 'alert', 'crisis', 'emergency',
            'shocking', 'unbelievable', 'amazing',
            'happening now', 'live', 'developing',
            'updated', 'update', 'confirmed', 'report'
        ]
        return any(keyword in title_lower for keyword in trending_keywords)

    def parse_date(self, date_str):
        """Parse various date formats"""
        if not date_str:
            return timezone.now()
        
        try:
            # Try common formats
            for fmt in [
                '%a, %d %b %Y %H:%M:%S %z',
                '%a, %d %b %Y %H:%M:%S %Z',
                '%Y-%m-%dT%H:%M:%SZ',
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d',
                '%d %b %Y',
                '%B %d, %Y',
            ]:
                try:
                    parsed = datetime.strptime(date_str, fmt)
                    if parsed.tzinfo is None:
                        return timezone.make_aware(parsed)
                    return parsed
                except:
                    continue
            
            # Try parsing with dateutil if available
            try:
                from dateutil import parser
                return parser.parse(date_str)
            except:
                pass
            
        except Exception as e:
            logger.error(f"Error parsing date {date_str}: {e}")
        
        return timezone.now()

    def fetch_google_news_scrape(self):
        """Scrape Google News for Nigeria news"""
        try:
            search_terms = [
                'Nigeria+news',
                'Nigeria+politics',
                'Nigeria+economy',
                'Nigeria+technology',
                'Lagos+news',
                'Abuja+news',
                'Nigeria+sports',
                'Nigeria+entertainment',
                'Nigeria+business',
                'Nigeria+crime',
                'Africa+news',
            ]
            
            for term in search_terms:
                try:
                    url = f"https://news.google.com/rss/search?q={term}&hl=en-NG&gl=NG&ceid=NG:en"
                    feed = feedparser.parse(url)
                    
                    for entry in feed.entries[:12]:  # Limit per term
                        try:
                            title = entry.get('title', '').strip()
                            if not title:
                                continue
                            
                            # Remove source from title (Google News format)
                            if ' - ' in title:
                                title_parts = title.split(' - ')
                                title = ' - '.join(title_parts[:-1]) if len(title_parts) > 1 else title_parts[0]
                            
                            url = entry.get('link', '')
                            if not url:
                                continue
                            
                            # Generate external_id
                            external_id = hashlib.md5(url.encode()).hexdigest()
                            
                            if Post.objects.filter(external_id=external_id).exists():
                                continue
                            
                            # Extract content
                            content = self.extract_full_content(url)
                            
                            # If no content, use summary
                            if not content and 'summary' in entry:
                                content = entry.summary
                            
                            # Clean content
                            if content:
                                content = self.clean_html(content)
                            
                            # Extract image
                            image_url = self.extract_image(entry, url, content)
                            
                            # Detect category
                            category = self.detect_category_from_content(title, content or '')
                            
                            # Get published date
                            published_at = self.parse_date(entry.get('published', ''))
                            
                            # Mark as trending
                            is_trending = self.is_trending_title(title)
                            
                            self.articles.append({
                                'title': title,
                                'content': content or title[:500],
                                'url': url,
                                'source': 'Google News',
                                'image_url': image_url,
                                'published_at': published_at,
                                'category': category,
                                'external_id': external_id,
                                'method': 'google',
                                'is_banner': is_trending,
                                'full_content_scraped': bool(content and len(content) > 500),
                            })
                            
                            sleep(0.5)  # Delay between articles
                            
                        except Exception as e:
                            logger.error(f"Error processing Google News article: {e}")
                            continue
                            
                except Exception as e:
                    logger.error(f"Error with search term {term}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error in Google News scrape: {e}")

    def fetch_rss_feeds(self):
        """Fetch from international RSS feeds"""
        rss_feeds = [
            ('BBC Africa', 'http://feeds.bbci.co.uk/news/world/africa/rss.xml', 'Africa'),
            ('Reuters Africa', 'http://feeds.reuters.com/reuters/AFRICAfricaNews', 'Africa'),
            ('CNN Africa', 'http://rss.cnn.com/rss/edition_africa.rss', 'International'),
            ('Al Jazeera', 'https://www.aljazeera.com/xml/rss/all.xml', 'International'),
            ('France24 Africa', 'https://www.france24.com/en/africa/rss', 'Africa'),
        ]
        
        for source_name, feed_url, default_category in rss_feeds:
            try:
                feed = feedparser.parse(feed_url)
                
                for entry in feed.entries[:15]:
                    try:
                        title = entry.get('title', '').strip()
                        
                        # Filter for Nigeria/Africa relevance
                        title_lower = title.lower()
                        if source_name in ['CNN Africa', 'Al Jazeera']:
                            if not any(keyword in title_lower for keyword in ['nigeria', 'africa', 'nigerian', 'lagos', 'abuja']):
                                continue
                        
                        url = entry.get('link', '')
                        if not url:
                            continue
                        
                        # Generate external_id
                        external_id = hashlib.md5(url.encode()).hexdigest()
                        
                        if Post.objects.filter(external_id=external_id).exists():
                            continue
                        
                        # Extract content
                        content = self.extract_full_content(url)
                        
                        # If no content, use summary
                        if not content and 'summary' in entry:
                            content = entry.summary
                        
                        # Clean content
                        if content:
                            content = self.clean_html(content)
                        
                        # Extract image
                        image_url = self.extract_image(entry, url, content)
                        
                        # Detect category
                        category = self.detect_category_from_content(title, content or '')
                        
                        # Get published date
                        published_at = self.parse_date(entry.get('published', ''))
                        
                        self.articles.append({
                            'title': title,
                            'content': content or title[:500],
                            'url': url,
                            'source': source_name,
                            'image_url': image_url,
                            'published_at': published_at,
                            'category': category or default_category,
                            'external_id': external_id,
                            'method': 'rss_international',
                            'full_content_scraped': bool(content and len(content) > 500),
                        })
                        
                        sleep(0.5)  # Delay between articles
                        
                    except Exception as e:
                        logger.error(f"Error processing {source_name} article: {e}")
                        continue
                        
            except Exception as e:
                logger.error(f"Error fetching {source_name}: {e}")
                continue

    def fetch_web_scrape_detailed(self):
        """Direct website scraping for detailed content"""
        newspapers = [
            {
                'name': 'Premium Times',
                'url': 'https://www.premiumtimesng.com/news/headlines',
                'base_url': 'https://www.premiumtimesng.com',
                'article_selector': 'article',
                'title_selector': 'h2 a',
                'link_selector': 'h2 a',
            },
            {
                'name': 'Vanguard',
                'url': 'https://www.vanguardngr.com/category/news',
                'base_url': 'https://www.vanguardngr.com',
                'article_selector': '.rtp-latest-news-list li',
                'title_selector': 'h3 a',
                'link_selector': 'h3 a',
            },
            {
                'name': 'Punch',
                'url': 'https://punchng.com/topics/news',
                'base_url': 'https://punchng.com',
                'article_selector': 'article',
                'title_selector': 'h2 a',
                'link_selector': 'h2 a',
            },
            {
                'name': 'Daily Trust',
                'url': 'https://dailytrust.com/category/news/',
                'base_url': 'https://dailytrust.com',
                'article_selector': 'article',
                'title_selector': 'h3 a',
                'link_selector': 'h3 a',
            },
        ]
        
        for paper in newspapers:
            try:
                logger.info(f"Scraping {paper['name']}...")
                response = self.session.get(paper['url'], timeout=20)
                if response.status_code != 200:
                    continue
                
                soup = BeautifulSoup(response.content, 'html.parser')
                articles = soup.select(paper['article_selector'])[:8]
                
                for article in articles:
                    try:
                        title_elem = article.select_one(paper['title_selector'])
                        if not title_elem:
                            continue
                        
                        title = title_elem.text.strip()
                        link = title_elem.get('href', '')
                        
                        if not title or not link:
                            continue
                        
                        # Make URL absolute
                        if link.startswith('/'):
                            link = paper['base_url'] + link
                        elif not link.startswith('http'):
                            link = urljoin(paper['url'], link)
                        
                        # Generate external_id
                        external_id = hashlib.md5(link.encode()).hexdigest()
                        
                        if Post.objects.filter(external_id=external_id).exists():
                            continue
                        
                        # Extract full content
                        content = self.extract_full_content(link)
                        
                        # Extract image
                        image_url = self.scrape_page_image(link)
                        
                        # Detect category
                        category = self.detect_category_from_content(title, content or '')
                        
                        self.articles.append({
                            'title': title,
                            'content': content or title[:500],
                            'url': link,
                            'source': paper['name'],
                            'image_url': image_url,
                            'published_at': timezone.now(),
                            'category': category or 'News',
                            'external_id': external_id,
                            'method': 'web_scrape',
                            'full_content_scraped': bool(content and len(content) > 500),
                        })
                        
                        sleep(1)  # Longer delay for web scraping
                        
                    except Exception as e:
                        logger.error(f"Error parsing {paper['name']} article: {e}")
                        continue
                        
            except Exception as e:
                logger.error(f"Error scraping {paper['name']}: {e}")
                continue

    def remove_duplicates(self, articles):
        """Remove duplicate articles"""
        unique_articles = []
        seen_urls = set()
        seen_titles = set()
        
        for article in articles:
            url = article.get('url', '')
            title = article.get('title', '').lower().strip()
            external_id = article.get('external_id', '')
            
            # Skip if no URL or title
            if not url or not title:
                continue
            
            # Check by external_id first
            if external_id:
                if external_id in seen_urls:
                    continue
                seen_urls.add(external_id)
            # Then check by URL
            elif url in seen_urls:
                continue
            else:
                seen_urls.add(url)
            
            # Check title similarity
            is_similar = False
            for seen_title in seen_titles:
                similarity = self.calculate_similarity(title, seen_title)
                if similarity > 0.6:  # 60% similarity threshold
                    is_similar = True
                    break
            
            if not is_similar:
                seen_titles.add(title)
                unique_articles.append(article)
        
        return unique_articles

    def calculate_similarity(self, text1, text2):
        """Calculate text similarity"""
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        if not words1 or not words2:
            return 0
        
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union if union > 0 else 0

    def save_articles_with_full_content(self, articles):
        """Save articles with full content to database"""
        logger.info(f"Saving {len(articles)} articles...")
        
        # Get or create system user
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
        
        saved_count = 0
        
        for i, article in enumerate(articles, 1):
            try:
                title = article.get('title', '').strip()
                url = article.get('url', '')
                external_id = article.get('external_id', '')
                
                if not title or not url:
                    continue
                
                # Truncate title if too long
                if len(title) > 200:
                    title = title[:197] + '...'
                
                # Check if already exists by external_id or URL
                if external_id and Post.objects.filter(external_id=external_id).exists():
                    continue
                
                # Check by URL
                if Post.objects.filter(external_url=url).exists():
                    continue
                
                # Get or create category
                category_name = article.get('category', 'News')
                category, created = Category.objects.get_or_create(
                    name=category_name,
                    defaults={
                        'slug': category_name.lower().replace(' ', '-'),
                        'description': f'{category_name} news'
                    }
                )
                
                # Prepare content
                content = article.get('content', title)
                
                # If content is too short, try to fetch more
                if len(content) < 800 and not article.get('full_content_scraped', False):
                    more_content = self.extract_full_content(url)
                    if more_content and len(more_content) > len(content):
                        content = more_content
                
                # Clean and truncate content
                content = self.clean_html(content)
                content = content[:15000]  # Limit to 15,000 chars
                
                # If content is still too short, use title with some filler
                if len(content) < 200:
                    content = f"{title}\n\nRead more at: {url}"
                
                # Get source
                source = article.get('source', 'Unknown')[:100]
                
                # Get image URL
                image_url = article.get('image_url', '')[:1000]
                
                # Parse date
                published_at = article.get('published_at', timezone.now())
                
                # Create the post
                post = Post.objects.create(
                    title=title,
                    content=content,
                    post_type='news',
                    category=category,
                    author=system_user,
                    external_source=source,
                    external_url=url,
                    external_id=external_id,
                    image_url=image_url,
                    published_at=published_at,
                    status='published',
                    is_auto_fetched=True,
                    is_approved=True,
                    verification_status='verified',
                    meta_description=content[:160] if content else title[:160],
                    views=random.randint(10, 100),  # Random starting views
                )
                
                saved_count += 1
                logger.info(f"✓ Saved ({saved_count}): {title[:50]}...")
                
                # Update category count
                category.update_post_count()
                
            except Exception as e:
                logger.error(f"✗ Error saving article {i}: {str(e)}")
                continue
        
        logger.info(f"Complete! Saved {saved_count} articles")
        return saved_count