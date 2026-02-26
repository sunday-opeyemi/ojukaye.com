import requests
import feedparser
import json
import re
import hashlib
import logging
import random
import time
import socket
from datetime import datetime, timedelta
from urllib.parse import urlparse, urljoin, parse_qs
from typing import Dict, List, Tuple, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from django.utils import timezone
from django.conf import settings
import trafilatura
from newspaper import Article, Config as NewspaperConfig
import cloudscraper

logger = logging.getLogger(__name__)

class UnifiedNewsFetcher:
    """
    ENHANCED fetcher that handles blocked sites, consent pages, and errors
    """
    
    def __init__(self):
        self.session = self._create_robust_session()
        self.cloudscraper = cloudscraper.create_scraper()  
        self.setup_newspaper_config()
        
        self.skip_domains = [
            'consent.yahoo.com',
            'consent.google.com',
            'cookieconsent',
            'privacy-policy',
            'terms-of-service'
        ]
        
        self.problematic_sites = {
            'thenewhumanitarian.org': {'skip_ssl': True, 'timeout': 30},
            'france24.com': {'use_cloudscraper': True},
            'nation.africa': {'use_cloudscraper': True},
            'theeastafrican.co.ke': {'use_cloudscraper': True},
        }
        
    def setup_newspaper_config(self):
        """Configure newspaper3k for better extraction"""
        self.newspaper_config = NewspaperConfig()
        self.newspaper_config.browser_user_agent = self._get_random_user_agent()
        self.newspaper_config.request_timeout = 15
        self.newspaper_config.memoize_articles = False
        
    def _get_random_user_agent(self):
        """Get random user agent"""
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        ]
        return random.choice(user_agents)
        
    def _create_robust_session(self):
        """Create session with retry strategy and rotating headers"""
        session = requests.Session()
        
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session
    
    def _get_headers(self):
        """Get random headers to avoid detection"""
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        ]
        
        accept_languages = [
            'en-US,en;q=0.9',
            'en-GB,en;q=0.8',
            'en-CA,en;q=0.8',
            'en-AU,en;q=0.8',
        ]
        
        return {
            'User-Agent': random.choice(user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': random.choice(accept_languages),
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
    
    def _check_internet(self):
        """Check internet connectivity"""
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            return True
        except OSError:
            return False
    
    def _is_consent_page(self, html: str) -> bool:
        """Check if the page is a consent/cookie page"""
        if not html:
            return False
        
        html_lower = html.lower()
        consent_indicators = [
            'consent',
            'cookie policy',
            'accept cookies',
            'privacy terms',
            'your privacy',
            'we use cookies',
            'cookie settings',
            'data privacy'
        ]
        
        # Check if it's clearly a consent page
        consent_score = 0
        for indicator in consent_indicators:
            if indicator in html_lower:
                consent_score += 1
        
        # Also check for form/button patterns
        if 'accept' in html_lower and ('cookie' in html_lower or 'privacy' in html_lower):
            consent_score += 2
        
        return consent_score >= 3
    
    def _get_site_config(self, url: str) -> Dict:
        """Get special configuration for problematic sites"""
        domain = urlparse(url).netloc.replace('www.', '')
        
        for site, config in self.problematic_sites.items():
            if site in domain:
                return config
        
        return {}
    
    def fetch_url(self, url: str) -> Optional[str]:
        """Fetch URL with multiple fallback methods and consent page detection"""
        
        # Skip known problematic domains
        if any(skip in url for skip in self.skip_domains):
            logger.debug(f"Skipping known consent domain: {url}")
            return None
        
        site_config = self._get_site_config(url)
        use_cloudscraper = site_config.get('use_cloudscraper', False)
        skip_ssl = site_config.get('skip_ssl', False)
        timeout = site_config.get('timeout', 15)
        
        # Try cloudscraper first for known problematic sites
        if use_cloudscraper:
            try:
                response = self.cloudscraper.get(url, timeout=timeout)
                if response.status_code == 200:
                    html = response.text
                    # Check if it's a consent page
                    if self._is_consent_page(html):
                        logger.warning(f"Consent page detected for {url}")
                        return None
                    return html
            except Exception as e:
                logger.warning(f"Cloudscraper failed for {url}: {e}")
        
        # Try with regular session
        for attempt in range(3):
            try:
                headers = self._get_headers()
                
                # Add random delay
                time.sleep(random.uniform(0.5, 2))
                
                response = self.session.get(
                    url,
                    headers=headers,
                    timeout=timeout,
                    allow_redirects=True,
                    verify=not skip_ssl  # Skip SSL verification for problematic sites
                )
                
                if response.status_code == 200:
                    html = response.text
                    
                    # Check if it's a consent page
                    if self._is_consent_page(html):
                        logger.warning(f"Consent page detected for {url}")
                        return None
                    
                    return html
                    
                elif response.status_code == 403:
                    logger.warning(f"403 Forbidden for {url}")
                    # Try cloudscraper as fallback
                    if not use_cloudscraper:
                        try:
                            response = self.cloudscraper.get(url, timeout=timeout)
                            if response.status_code == 200:
                                html = response.text
                                if not self._is_consent_page(html):
                                    return html
                        except:
                            pass
                    return None
                    
                elif response.status_code == 429:
                    wait = 2 ** attempt + random.uniform(1, 3)
                    logger.warning(f"Rate limited for {url}, waiting {wait:.1f}s")
                    time.sleep(wait)
                    
                elif response.status_code in [401, 402]:
                    # Unauthorized - likely paywall or consent
                    logger.warning(f"Auth required for {url}")
                    return None
                    
                else:
                    logger.warning(f"HTTP {response.status_code} for {url}")
                    if attempt < 2:
                        time.sleep(2 ** attempt)
                        
            except requests.exceptions.SSLError as e:
                logger.warning(f"SSL Error for {url}: {e}")
                # Try without SSL verification
                if not skip_ssl:
                    site_config['skip_ssl'] = True
                    return self.fetch_url(url)
                return None
                
            except requests.exceptions.Timeout:
                logger.warning(f"Timeout for {url}")
                if attempt < 2:
                    time.sleep(2)
                    
            except requests.exceptions.ConnectionError:
                logger.warning(f"Connection error for {url}")
                if attempt < 2:
                    time.sleep(2)
                    
            except Exception as e:
                logger.error(f"Error fetching {url}: {e}")
                if attempt < 2:
                    time.sleep(1)
        
        return None
    
    def extract_media_from_html(self, html: str, base_url: str) -> Dict:
        """Extract all media (videos, audio, images) from HTML"""
        result = {
            'videos': [],
            'audios': [],
            'images': [],
            'main_image': None
        }
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract videos
            # 1. Video tags
            for video in soup.find_all('video'):
                src = video.get('src')
                if not src:
                    source = video.find('source')
                    if source:
                        src = source.get('src')
                if src:
                    result['videos'].append({
                        'url': self._make_absolute_url(src, base_url),
                        'type': 'html5_video',
                        'poster': self._make_absolute_url(video.get('poster', ''), base_url)
                    })
            
            # 2. YouTube embeds
            for iframe in soup.find_all('iframe'):
                src = iframe.get('src', '')
                # YouTube
                if 'youtube.com' in src or 'youtu.be' in src:
                    result['videos'].append({
                        'url': src,
                        'type': 'youtube',
                        'source': 'embed'
                    })
                # Vimeo
                elif 'vimeo.com' in src:
                    result['videos'].append({
                        'url': src,
                        'type': 'vimeo',
                        'source': 'embed'
                    })
            
            # 3. Video links
            for a in soup.find_all('a', href=True):
                href = a['href'].lower()
                if href.endswith(('.mp4', '.webm', '.ogg', '.mov')):
                    result['videos'].append({
                        'url': self._make_absolute_url(a['href'], base_url),
                        'type': 'direct_video',
                        'title': a.get_text(strip=True)
                    })
            
            # Extract audio
            # 1. Audio tags
            for audio in soup.find_all('audio'):
                src = audio.get('src')
                if not src:
                    source = audio.find('source')
                    if source:
                        src = source.get('src')
                if src:
                    result['audios'].append({
                        'url': self._make_absolute_url(src, base_url),
                        'type': 'html5_audio'
                    })
            
            # 2. Audio links
            for a in soup.find_all('a', href=True):
                href = a['href'].lower()
                if href.endswith(('.mp3', '.m4a', '.ogg', '.wav', '.aac')):
                    result['audios'].append({
                        'url': self._make_absolute_url(a['href'], base_url),
                        'type': 'audio_file',
                        'title': a.get_text(strip=True)
                    })
            
            # 3. Spotify/SoundCloud embeds
            spotify_pattern = r'spotify\.com/embed'
            soundcloud_pattern = r'soundcloud\.com'
            
            for iframe in soup.find_all('iframe'):
                src = iframe.get('src', '')
                if re.search(spotify_pattern, src):
                    result['audios'].append({
                        'url': src,
                        'type': 'spotify',
                        'source': 'embed'
                    })
                elif re.search(soundcloud_pattern, src):
                    result['audios'].append({
                        'url': src,
                        'type': 'soundcloud',
                        'source': 'embed'
                    })
            
            # Extract images
            # 1. Open Graph image (main)
            og_image = soup.find('meta', property='og:image')
            if og_image and og_image.get('content'):
                result['main_image'] = self._make_absolute_url(og_image['content'], base_url)
            
            # 2. Twitter image
            if not result['main_image']:
                twitter_image = soup.find('meta', attrs={'name': 'twitter:image'})
                if twitter_image and twitter_image.get('content'):
                    result['main_image'] = self._make_absolute_url(twitter_image['content'], base_url)
            
            # 3. All images
            for img in soup.find_all('img'):
                src = img.get('src') or img.get('data-src') or img.get('data-original')
                if src:
                    # Skip tiny images
                    width = img.get('width')
                    if width and width.isdigit() and int(width) < 100:
                        continue
                    
                    result['images'].append({
                        'url': self._make_absolute_url(src, base_url),
                        'alt': img.get('alt', ''),
                        'width': img.get('width'),
                        'height': img.get('height')
                    })
            
            # Deduplicate
            result['videos'] = self._deduplicate_by_url(result['videos'])
            result['audios'] = self._deduplicate_by_url(result['audios'])
            result['images'] = self._deduplicate_by_url(result['images'])
            
        except Exception as e:
            logger.error(f"Error extracting media: {e}")
        
        return result
    
    def _make_absolute_url(self, url: str, base_url: str) -> str:
        """Convert relative URL to absolute"""
        if not url:
            return url
        
        url = url.strip()
        
        if url.startswith('//'):
            return 'https:' + url
        elif url.startswith('/'):
            parsed = urlparse(base_url)
            return f"{parsed.scheme}://{parsed.netloc}{url}"
        elif not url.startswith(('http://', 'https://')):
            return urljoin(base_url, url)
        return url
    
    def _deduplicate_by_url(self, items: List[Dict]) -> List[Dict]:
        """Remove duplicates by URL"""
        seen = set()
        unique = []
        for item in items:
            url = item.get('url', '')
            if url and url not in seen:
                seen.add(url)
                unique.append(item)
        return unique
    
    def extract_content(self, url: str) -> Dict:
        """
        Extract full content and all media from a URL
        """
        result = {
            'title': None,
            'content': None,
            'main_image': None,
            'videos': [],
            'audios': [],
            'images': [],
            'success': False,
            'method': None,
            'error': None
        }
        
        # Skip consent domains
        if any(skip in url for skip in self.skip_domains):
            result['error'] = 'Skipped consent domain'
            return result
        
        # Try trafilatura first (best for text)
        try:
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                content = trafilatura.extract(
                    downloaded,
                    include_comments=False,
                    include_tables=True,
                    output_format='txt',
                    favor_precision=True
                )
                if content and len(content) > 200:
                    result['content'] = content
                    result['method'] = 'trafilatura'
                    result['success'] = True
                    
                    metadata = trafilatura.extract_metadata(downloaded)
                    if metadata and hasattr(metadata, 'title'):
                        result['title'] = metadata.title
        except Exception as e:
            logger.debug(f"Trafilatura failed for {url}: {e}")
        
        # If trafilatura failed, try newspaper3k
        if not result['success']:
            try:
                article = Article(url, config=self.newspaper_config)
                article.download()
                article.parse()
                
                if article.text and len(article.text) > 200:
                    result['content'] = article.text
                    result['title'] = article.title
                    result['main_image'] = article.top_image
                    result['method'] = 'newspaper3k'
                    result['success'] = True
                    
                    # Get videos from article
                    if hasattr(article, 'movies') and article.movies:
                        for movie in article.movies:
                            result['videos'].append({
                                'url': movie,
                                'type': 'video',
                                'source': 'newspaper3k'
                            })
            except Exception as e:
                logger.debug(f"Newspaper3k failed for {url}: {e}")
        
        # If both failed, try direct HTML parsing
        html = self.fetch_url(url)
        if html and not result['success']:
            try:
                soup = BeautifulSoup(html, 'html.parser')
                
                # Remove unwanted elements
                for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'form']):
                    tag.decompose()
                
                # Try to find main content
                main_content = None
                for selector in ['article', '.article-content', '.post-content', '.entry-content', 
                                '.story-content', '#content', '.main-content', '[itemprop="articleBody"]']:
                    main_content = soup.select_one(selector)
                    if main_content:
                        break
                
                if main_content:
                    paragraphs = main_content.find_all('p')
                    text = '\n\n'.join([p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 40])
                    if len(text) > 200:
                        result['content'] = text
                        result['method'] = 'bs4'
                        result['success'] = True
                
                # Get title
                if not result['title']:
                    title_tag = soup.find('title')
                    if title_tag:
                        result['title'] = title_tag.get_text(strip=True)
                
            except Exception as e:
                logger.debug(f"BS4 parsing failed for {url}: {e}")
        
        # Extract all media from HTML (even if content extraction failed)
        if html:
            media = self.extract_media_from_html(html, url)
            result['videos'].extend(media['videos'])
            result['audios'].extend(media['audios'])
            result['images'].extend(media['images'])
            if not result['main_image']:
                result['main_image'] = media['main_image']
        
        # Clean up
        result['videos'] = self._deduplicate_by_url(result['videos'])
        result['audios'] = self._deduplicate_by_url(result['audios'])
        result['images'] = self._deduplicate_by_url(result['images'])
        
        return result
    
    def fetch_from_newsapi(self, api_key: str, days: int = 1, limit: int = 50) -> List[Dict]:
            """Fetch articles from NewsAPI with proper limits"""
            articles = []
            from_date = (timezone.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            
            # Adjust pageSize based on limit
            page_size = min(limit, 100)  # NewsAPI max is 100
            
            # Focused queries for Nigerian/African news
            queries = [
                # Nigeria focus - primary
                {'q': 'Nigeria', 'pageSize': min(30, page_size)},
                {'q': 'Lagos', 'pageSize': min(15, page_size)},
                {'q': 'Abuja', 'pageSize': min(10, page_size)},
                
                # African news
                {'q': 'Africa', 'pageSize': min(20, page_size)},
                {'q': 'Ghana OR Kenya OR "South Africa"', 'pageSize': min(15, page_size)},
            ]
            
            # Adjust total queries based on limit
            if limit <= 30:
                queries = queries[:3]  # Only Nigeria-focused queries for small limits
            
            total_fetched = 0
            max_to_fetch = limit
            
            logger.info(f"📊 NewsAPI: Will fetch up to {max_to_fetch} articles total")
            
            for query in queries:
                if total_fetched >= max_to_fetch:
                    break
                    
                try:
                    url = "https://newsapi.org/v2/everything"
                    params = {
                        'q': query['q'],
                        'apiKey': api_key,
                        'pageSize': min(query['pageSize'], max_to_fetch - total_fetched),
                        'language': 'en',
                        'sortBy': 'publishedAt',
                        'from': from_date,
                    }
                    
                    logger.info(f"NewsAPI Query: {query['q']} (pageSize: {params['pageSize']})")
                    
                    response = requests.get(url, params=params, timeout=15)
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        if data.get('status') == 'ok':
                            fetched = 0
                            for item in data.get('articles', []):
                                if total_fetched >= max_to_fetch:
                                    break
                                    
                                if not item.get('title') or item['title'] == '[Removed]':
                                    continue
                                if not item.get('url'):
                                    continue
                                
                                articles.append({
                                    'title': item['title'],
                                    'url': item['url'],
                                    'description': item.get('description', ''),
                                    'content': item.get('content', ''),
                                    'image': item.get('urlToImage', ''),
                                    'source': item.get('source', {}).get('name', 'Unknown'),
                                    'published_at': item.get('publishedAt', ''),
                                    'author': item.get('author', ''),
                                    'source_type': 'newsapi',
                                    'search_query': query['q']
                                })
                                
                                total_fetched += 1
                                fetched += 1
                            
                            logger.info(f"  ✅ Found {fetched} articles")
                        else:
                            logger.error(f"  ❌ API Error: {data.get('message', 'Unknown error')}")
                            
                    elif response.status_code == 426:
                        logger.warning("  ⚠️ NewsAPI upgrade required")
                        break  # Stop if API key needs upgrade
                    else:
                        logger.error(f"  ❌ HTTP {response.status_code}")
                        
                except Exception as e:
                    logger.error(f"  ❌ Error: {e}")
                
                # Rate limiting - small delay between queries
                time.sleep(1)
            
            logger.info(f"📊 NewsAPI total: {len(articles)} articles fetched")
            return articles
    
    def fetch_from_rss(self, limit: int = 50) -> List[Dict]:
        """Fetch articles from RSS feeds with proper limits"""
        articles = []
        
        # Working RSS feeds
        rss_feeds = [
            ('BBC Africa', 'http://feeds.bbci.co.uk/news/world/africa/rss.xml'),
            ('Al Jazeera Africa', 'https://www.aljazeera.com/xml/rss/all.xml'),
            ('Reuters Africa', 'http://feeds.reuters.com/reuters/AFRICATopNews'),
            ('Premium Times', 'https://www.premiumtimesng.com/feed'),
            ('Vanguard', 'https://www.vanguardngr.com/feed'),
            ('Punch', 'https://punchng.com/feed'),
        ]
        
        total_fetched = 0
        max_to_fetch = limit
        per_feed_limit = max(5, min(15, limit // len(rss_feeds)))  # Distribute limit across feeds
        
        logger.info(f"📡 RSS: Will fetch up to {max_to_fetch} articles total ({per_feed_limit} per feed)")
        
        for name, url in rss_feeds:
            if total_fetched >= max_to_fetch:
                break
                
            try:
                logger.info(f"RSS Feed: {name}")
                
                headers = self._get_headers()
                feed_data = feedparser.parse(url, agent=headers['User-Agent'])
                
                # Calculate how many to take from this feed
                remaining = max_to_fetch - total_fetched
                take_from_feed = min(per_feed_limit, remaining, len(feed_data.entries))
                
                entries = feed_data.entries[:take_from_feed]
                fetched = 0
                
                for entry in entries:
                    title = entry.get('title', '')
                    if not title:
                        continue
                    
                    link = entry.get('link', '')
                    if not link:
                        continue
                    
                    # Skip consent domains
                    if any(skip in link for skip in self.skip_domains):
                        continue
                    
                    description = entry.get('description', '') or entry.get('summary', '')
                    if description:
                        # Clean HTML
                        description = re.sub(r'<[^>]+>', '', description)
                        description = description[:500]
                    
                    # Get image from media content
                    image = None
                    if hasattr(entry, 'media_content'):
                        for media in entry.media_content:
                            if media.get('medium') == 'image' and media.get('url'):
                                image = media['url']
                                break
                    
                    if not image and hasattr(entry, 'media_thumbnail'):
                        for thumb in entry.media_thumbnail:
                            if thumb.get('url'):
                                image = thumb['url']
                                break
                    
                    published = entry.get('published', '') or entry.get('pubDate', '')
                    
                    articles.append({
                        'title': title,
                        'url': link,
                        'description': description,
                        'content': '',
                        'image': image or '',
                        'source': name,
                        'published_at': published,
                        'author': entry.get('author', ''),
                        'source_type': 'rss'
                    })
                    
                    total_fetched += 1
                    fetched += 1
                
                logger.info(f"  ✅ Found {fetched} articles")
                
            except Exception as e:
                logger.error(f"  Error: {e}")
            
            # Small delay between feeds
            time.sleep(0.5)
        
        logger.info(f"📡 RSS total: {len(articles)} articles fetched")
        return articles
    
    def process_article(self, article: Dict, extract_full: bool = True) -> Dict:
        """Process a single article - extract full content and media"""
        try:
            url = article.get('url')
            if not url:
                return article
            
            # Skip if it's a social media site or consent domain
            skip_domains = ['youtube.com', 'twitter.com', 'facebook.com', 'instagram.com']
            skip_domains.extend(self.skip_domains)
            
            if any(domain in url for domain in skip_domains):
                article['full_content'] = article.get('description', article.get('title', ''))
                article['videos'] = []
                article['audios'] = []
                article['images'] = []
                article['has_video'] = False
                article['has_audio'] = False
                article['has_images'] = False
                return article
            
            if extract_full:
                # Extract everything
                extracted = self.extract_content(url)
                
                if extracted['success']:
                    article['full_content'] = extracted['content']
                    if extracted['title']:
                        article['title'] = extracted['title']
                    if extracted['main_image'] and not article.get('image'):
                        article['image'] = extracted['main_image']
                    
                    # Add all media
                    article['videos'] = extracted['videos']
                    article['audios'] = extracted['audios']
                    article['images'] = extracted['images']
                    article['has_video'] = len(extracted['videos']) > 0
                    article['has_audio'] = len(extracted['audios']) > 0
                    article['has_images'] = len(extracted['images']) > 0
                    article['extraction_method'] = extracted['method']
                else:
                    # Use description as fallback
                    article['full_content'] = article.get('description', article.get('title', ''))
                    article['videos'] = []
                    article['audios'] = []
                    article['images'] = []
                    article['has_video'] = False
                    article['has_audio'] = False
                    article['has_images'] = False
            
            return article
            
        except Exception as e:
            logger.error(f"Error processing {article.get('url', 'unknown')}: {e}")
            return article
    
    def process_articles_parallel(self, articles: List[Dict], max_workers: int = 5, extract_full: bool = True) -> List[Dict]:
        """Process multiple articles in parallel"""
        
        processed = []
        skipped = 0
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_article = {
                executor.submit(self.process_article, article, extract_full): article 
                for article in articles if article and article.get('url')
            }
            
            for i, future in enumerate(as_completed(future_to_article), 1):
                try:
                    result = future.result(timeout=60)
                    if result:
                        processed.append(result)
                    
                    if i % 10 == 0:
                        logger.info(f"Processed {i}/{len(future_to_article)} articles")
                        
                except Exception as e:
                    logger.error(f"Error processing article: {e}")
                    skipped += 1
                    article = future_to_article[future]
                    if article not in processed:
                        processed.append(article)
        
        logger.info(f"Processing complete: {len(processed)} processed, {skipped} skipped")
        return processed
    
    def remove_duplicates(self, articles: List[Dict]) -> List[Dict]:
        """Remove duplicate articles"""
        unique = []
        seen_urls = set()
        seen_titles = set()
        
        for article in articles:
            url = article.get('url', '')
            title = article.get('title', '').lower().strip()
            
            if not url or not title:
                continue
            
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
    
    def _title_similarity(self, title1: str, title2: str) -> float:
        """Calculate title similarity"""
        words1 = set(title1.split())
        words2 = set(title2.split())
        
        if not words1 or not words2:
            return 0
        
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union if union > 0 else 0
    
    def detect_category(self, title: str, content: str = '') -> str:
        """Detect category from title and content"""
        text = (title + ' ' + content).lower()
        
        categories = {
            'Politics': ['politics', 'government', 'president', 'election', 'senate', 'minister', 'tinubu', 'apc', 'pdp', 'obia', 'atiku'],
            'Business': ['business', 'economy', 'naira', 'market', 'stock', 'finance', 'bank', 'investment', 'trade', 'cbn'],
            'Sports': ['sports', 'football', 'super eagles', 'super falcons', 'soccer', 'basketball', 'match', 'league', 'player', 'goal'],
            'Technology': ['technology', 'tech', 'digital', 'ai', 'internet', 'software', 'app', 'startup', 'cyber', 'computer'],
            'Entertainment': ['entertainment', 'music', 'movie', 'nollywood', 'actor', 'actress', 'celebrity', 'film', 'davido', 'wizkid'],
            'Health': ['health', 'medical', 'hospital', 'doctor', 'vaccine', 'disease', 'covid', 'treatment', 'patient'],
            'Education': ['education', 'school', 'university', 'student', 'teacher', 'college', 'exam', 'academic'],
            'Crime': ['crime', 'police', 'arrest', 'court', 'judge', 'robbery', 'murder', 'kidnap', 'bandit'],
        }
        
        for category, keywords in categories.items():
            if any(keyword in text for keyword in keywords):
                return category
        
        return 'News'
    
    def parse_date(self, date_str: str):
        """Parse date string"""
        if not date_str:
            return timezone.now()
        
        try:
            from dateutil import parser
            parsed = parser.parse(date_str)
            if parsed.tzinfo is None:
                return timezone.make_aware(parsed)
            return parsed
        except:
            return timezone.now()
    
    def clean_html(self, text: str) -> str:
        """Clean HTML from text"""
        if not text:
            return text
        text = str(text)
        clean = re.sub(r'<[^>]+>', '', text)
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean
    
    def fetch_all(self, api_key: str, days: int = 1, limit: int = 50, workers: int = 5, extract_full: bool = True) -> Dict:
        """Fetch from all sources and return stats - NOW WITH PROPER LIMITS"""
        
        if not self._check_internet():
            logger.error("No internet connection")
            return {'error': 'No internet connection'}
        
        logger.info("="*60)
        logger.info(f"📰 FETCHING NEWS - Last {days} day(s), Max {limit} articles")
        logger.info("="*60)
        
        stats = {
            'newsapi': 0,
            'rss': 0,
            'unique': 0,
            'saved': 0,
            'videos': 0,
            'audio': 0,
            'images': 0,
            'skipped': 0
        }
        
        all_articles = []
        remaining_limit = limit
        
        # Fetch from NewsAPI (50% of limit)
        newsapi_limit = min(limit // 2, 50)
        logger.info(f"\n📰 Fetching from NewsAPI (limit: {newsapi_limit})...")
        newsapi_articles = self.fetch_from_newsapi(api_key, days=days, limit=newsapi_limit)
        all_articles.extend(newsapi_articles)
        stats['newsapi'] = len(newsapi_articles)
        remaining_limit -= len(newsapi_articles)
        
        # Fetch from RSS (remaining limit)
        rss_limit = min(remaining_limit, 50)
        if rss_limit > 0:
            logger.info(f"\n📡 Fetching from RSS feeds (limit: {rss_limit})...")
            rss_articles = self.fetch_from_rss(limit=rss_limit)
            all_articles.extend(rss_articles)
            stats['rss'] = len(rss_articles)
        
        logger.info(f"\n📊 TOTAL RAW: {len(all_articles)} articles")
        
        # Remove duplicates
        unique_articles = self.remove_duplicates(all_articles)
        stats['unique'] = len(unique_articles)
        logger.info(f"🔍 UNIQUE: {len(unique_articles)} (removed {len(all_articles) - len(unique_articles)} duplicates)")
        
        # Process articles (extract content and media)
        if unique_articles:
            logger.info(f"\n🔧 Processing {len(unique_articles)} articles...")
            processed_articles = self.process_articles_parallel(
                unique_articles, 
                max_workers=workers,
                extract_full=extract_full
            )
            
            # Count media
            for article in processed_articles:
                stats['videos'] += len(article.get('videos', []))
                stats['audio'] += len(article.get('audios', []))
                stats['images'] += len(article.get('images', []))
            
            logger.info(f"\n📊 MEDIA FOUND:")
            logger.info(f"   📹 Videos: {stats['videos']}")
            logger.info(f"   🎵 Audio: {stats['audio']}")
            logger.info(f"   🖼️  Images: {stats['images']}")
        
        stats['processed'] = len(processed_articles) if 'processed_articles' in locals() else 0
        
        return stats, processed_articles if 'processed_articles' in locals() else []