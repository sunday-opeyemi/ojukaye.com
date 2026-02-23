# core/news_fetcher.py (Enhanced Version)

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
from urllib.parse import urlparse, urljoin
from typing import Dict, List, Tuple, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

import urllib3
from bs4 import BeautifulSoup
from django.utils import timezone
from django.conf import settings
from readability import Document
import trafilatura
from newspaper import Article
import yt_dlp
import cv2
import numpy as np

from .models import Post, Category, User

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

class ContentExtractor:
    """Advanced content extraction with multiple fallback methods"""
    
    @staticmethod
    def extract_with_trafilatura(url: str) -> Tuple[Optional[str], Dict]:
        """Extract content using trafilatura (best for text extraction)"""
        try:
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                text = trafilatura.extract(
                    downloaded,
                    include_comments=False,
                    include_tables=True,
                    no_fallback=False,
                    output_format='txt'
                )
                return text, {'method': 'trafilatura', 'success': bool(text)}
        except Exception as e:
            logger.error(f"Trafilatura extraction failed: {e}")
        return None, {'method': 'trafilatura', 'success': False}
    
    @staticmethod
    def extract_with_newspaper(url: str) -> Tuple[Optional[str], Dict, Optional[str], List, List]:
        """Extract using newspaper3k (good for metadata and basic content)"""
        try:
            article = Article(url)
            article.download()
            article.parse()
            article.nlp()
            
            content = article.text
            image_url = article.top_image
            
            # Extract videos from meta tags
            videos = []
            if article.movies:
                for movie in article.movies:
                    videos.append({
                        'url': movie,
                        'type': 'video',
                        'source': 'newspaper3k'
                    })
            
            # Extract audio if available
            audios = []
            if article.audio:
                audios.append({
                    'url': article.audio,
                    'type': 'audio',
                    'source': 'newspaper3k'
                })
            
            return content, {'method': 'newspaper3k', 'success': bool(content)}, image_url, videos, audios
        except Exception as e:
            logger.error(f"Newspaper3k extraction failed: {e}")
        return None, {'method': 'newspaper3k', 'success': False}, None, [], []
    
    @staticmethod
    def extract_with_readability(url: str, html: str) -> Tuple[Optional[str], Dict]:
        """Extract using readability-lxml (good for article text)"""
        try:
            doc = Document(html)
            content = doc.summary()
            # Convert HTML to text
            soup = BeautifulSoup(content, 'html.parser')
            text = soup.get_text(separator='\n', strip=True)
            return text, {'method': 'readability', 'success': bool(text)}
        except Exception as e:
            logger.error(f"Readability extraction failed: {e}")
        return None, {'method': 'readability', 'success': False}
    
    @staticmethod
    def extract_with_bs4_fallback(html: str) -> Tuple[Optional[str], Dict]:
        """Fallback extraction using BeautifulSoup"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Remove unwanted elements
            for element in soup.find_all(['script', 'style', 'nav', 'footer', 'header', 'aside']):
                element.decompose()
            
            # Try common article containers
            content_selectors = [
                'article', '.article-content', '.post-content', '.entry-content',
                '.story-content', '#content', '.main-content', '[itemprop="articleBody"]',
                '.article-body', '.post-body', '.entry', '.story'
            ]
            
            article_content = None
            for selector in content_selectors:
                article_content = soup.select_one(selector)
                if article_content:
                    break
            
            if article_content:
                # Get paragraphs
                paragraphs = article_content.find_all('p')
                if len(paragraphs) > 2:
                    text = '\n\n'.join([p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 40])
                    return text, {'method': 'bs4_fallback', 'success': True}
            
            # Fallback: get all paragraphs with substantial text
            paragraphs = soup.find_all('p')
            valid_paragraphs = []
            for p in paragraphs:
                text = p.get_text(strip=True)
                if len(text) > 100:  # Only take substantial paragraphs
                    valid_paragraphs.append(text)
            
            if len(valid_paragraphs) > 3:
                return '\n\n'.join(valid_paragraphs[:30]), {'method': 'bs4_fallback', 'success': True}
            
        except Exception as e:
            logger.error(f"BS4 fallback extraction failed: {e}")
        
        return None, {'method': 'bs4_fallback', 'success': False}


class MediaExtractor:
    """Advanced media extraction from web pages"""
    
    @staticmethod
    def extract_videos_from_html(soup: BeautifulSoup, base_url: str) -> List[Dict]:
        """Extract all video content from HTML"""
        videos = []
        
        # 1. Video tags
        for video in soup.find_all('video'):
            video_data = MediaExtractor._extract_video_tag(video, base_url)
            if video_data:
                videos.append(video_data)
        
        # 2. Iframe embeds (YouTube, Vimeo, etc.)
        for iframe in soup.find_all('iframe'):
            video_data = MediaExtractor._extract_iframe_video(iframe)
            if video_data:
                videos.append(video_data)
        
        # 3. Object/Embed tags
        for obj in soup.find_all(['object', 'embed']):
            video_data = MediaExtractor._extract_object_video(obj, base_url)
            if video_data:
                videos.append(video_data)
        
        # 4. Links to video files
        for a in soup.find_all('a', href=True):
            video_data = MediaExtractor._extract_video_link(a, base_url)
            if video_data:
                videos.append(video_data)
        
        # 5. Open Graph video
        og_video = soup.find('meta', property='og:video')
        if og_video and og_video.get('content'):
            videos.append({
                'url': og_video['content'],
                'type': 'og_video',
                'source': 'opengraph'
            })
        
        # 6. Twitter player
        twitter_player = soup.find('meta', attrs={'name': 'twitter:player'})
        if twitter_player and twitter_player.get('content'):
            videos.append({
                'url': twitter_player['content'],
                'type': 'twitter_player',
                'source': 'twitter_card'
            })
        
        # 7. JSON-LD data
        json_ld = soup.find('script', type='application/ld+json')
        if json_ld:
            try:
                data = json.loads(json_ld.string)
                video_data = MediaExtractor._extract_video_from_jsonld(data)
                if video_data:
                    videos.extend(video_data)
            except:
                pass
        
        return videos
    
    @staticmethod
    def _extract_video_tag(video, base_url):
        """Extract from video tag"""
        src = video.get('src')
        if not src:
            source = video.find('source')
            if source:
                src = source.get('src')
        
        if src:
            src = ContentExtractor.make_absolute_url(src, base_url)
            return {
                'url': src,
                'type': 'html5_video',
                'poster': video.get('poster', ''),
                'source': 'video_tag'
            }
        return None
    
    @staticmethod
    def _extract_iframe_video(iframe):
        """Extract from iframe (YouTube, Vimeo, etc.)"""
        src = iframe.get('src', '')
        
        # YouTube
        youtube_patterns = [
            r'youtube\.com/embed/([a-zA-Z0-9_-]+)',
            r'youtube\.com/watch\?v=([a-zA-Z0-9_-]+)',
            r'youtu\.be/([a-zA-Z0-9_-]+)'
        ]
        for pattern in youtube_patterns:
            match = re.search(pattern, src)
            if match:
                video_id = match.group(1)
                return {
                    'url': f'https://www.youtube.com/embed/{video_id}',
                    'type': 'youtube',
                    'id': video_id,
                    'source': 'iframe'
                }
        
        # Vimeo
        vimeo_match = re.search(r'vimeo\.com/(?:video/)?(\d+)', src)
        if vimeo_match:
            video_id = vimeo_match.group(1)
            return {
                'url': f'https://player.vimeo.com/video/{video_id}',
                'type': 'vimeo',
                'id': video_id,
                'source': 'iframe'
            }
        
        # Dailymotion
        dailymotion_match = re.search(r'dailymotion\.com/embed/video/([a-zA-Z0-9]+)', src)
        if dailymotion_match:
            video_id = dailymotion_match.group(1)
            return {
                'url': f'https://www.dailymotion.com/embed/video/{video_id}',
                'type': 'dailymotion',
                'id': video_id,
                'source': 'iframe'
            }
        
        return None
    
    @staticmethod
    def _extract_object_video(obj, base_url):
        """Extract from object/embed tags"""
        data = obj.get('data', '') or obj.get('src', '')
        if data:
            data = ContentExtractor.make_absolute_url(data, base_url)
            if data.lower().endswith(('.mp4', '.webm', '.ogg', '.mov')):
                return {
                    'url': data,
                    'type': 'direct_video',
                    'source': 'object_tag'
                }
        return None
    
    @staticmethod
    def _extract_video_link(a, base_url):
        """Extract from anchor tags pointing to video files"""
        href = a.get('href', '')
        href_lower = href.lower()
        
        video_extensions = ['.mp4', '.webm', '.ogg', '.mov', '.avi', '.mkv']
        for ext in video_extensions:
            if href_lower.endswith(ext):
                href = ContentExtractor.make_absolute_url(href, base_url)
                return {
                    'url': href,
                    'type': 'direct_video',
                    'source': 'link',
                    'title': a.get_text(strip=True)
                }
        
        # YouTube links
        if 'youtube.com/watch' in href_lower or 'youtu.be/' in href_lower:
            href = ContentExtractor.make_absolute_url(href, base_url)
            return {
                'url': href,
                'type': 'youtube_link',
                'source': 'link'
            }
        
        return None
    
    @staticmethod
    def _extract_video_from_jsonld(data):
        """Extract video from JSON-LD"""
        videos = []
        if isinstance(data, dict):
            if data.get('@type') == 'VideoObject':
                videos.append({
                    'url': data.get('contentUrl') or data.get('embedUrl'),
                    'type': 'video_object',
                    'source': 'jsonld',
                    'title': data.get('name'),
                    'description': data.get('description'),
                    'thumbnail': data.get('thumbnailUrl')
                })
            elif data.get('video'):
                video_data = data['video']
                if isinstance(video_data, dict):
                    videos.append({
                        'url': video_data.get('contentUrl') or video_data.get('embedUrl'),
                        'type': 'video_object',
                        'source': 'jsonld'
                    })
        return videos
    
    @staticmethod
    def extract_audios_from_html(soup: BeautifulSoup, base_url: str) -> List[Dict]:
        """Extract audio content"""
        audios = []
        
        # Audio tags
        for audio in soup.find_all('audio'):
            src = audio.get('src')
            if not src:
                source = audio.find('source')
                if source:
                    src = source.get('src')
            
            if src:
                src = ContentExtractor.make_absolute_url(src, base_url)
                audios.append({
                    'url': src,
                    'type': 'html5_audio',
                    'source': 'audio_tag'
                })
        
        # Podcast/audio links
        for a in soup.find_all('a', href=True):
            href = a['href'].lower()
            audio_extensions = ['.mp3', '.m4a', '.ogg', '.wav', '.aac', '.opus']
            for ext in audio_extensions:
                if href.endswith(ext):
                    href = ContentExtractor.make_absolute_url(a['href'], base_url)
                    audios.append({
                        'url': href,
                        'type': 'audio_file',
                        'source': 'link',
                        'title': a.get_text(strip=True)
                    })
                    break
        
        # Spotify embeds
        spotify_patterns = [
            r'open\.spotify\.com/embed/(track|episode|album)/([a-zA-Z0-9]+)',
            r'open\.spotify\.com/(track|episode|album)/([a-zA-Z0-9]+)'
        ]
        for pattern in spotify_patterns:
            matches = re.findall(pattern, str(soup))
            for match in matches:
                if isinstance(match, tuple):
                    item_type, item_id = match
                else:
                    continue
                    
                audios.append({
                    'url': f'https://open.spotify.com/embed/{item_type}/{item_id}',
                    'type': 'spotify',
                    'id': item_id,
                    'source': 'embed'
                })
        
        # SoundCloud embeds
        soundcloud_pattern = r'soundcloud\.com/(?:player/?\?url=)?([^\s"\'<>]+)'
        matches = re.findall(soundcloud_pattern, str(soup))
        for match in matches:
            audios.append({
                'url': f'https://w.soundcloud.com/player/?url=https://soundcloud.com/{match}',
                'type': 'soundcloud',
                'source': 'embed'
            })
        
        return audios


class ImageExtractor:
    """Advanced image extraction"""
    
    @staticmethod
    def extract_best_image(soup: BeautifulSoup, base_url: str, min_width: int = 600) -> Optional[str]:
        """Extract the best image from the page"""
        
        # Priority order for image sources
        
        # 1. Open Graph image
        og_image = soup.find('meta', property='og:image')
        if og_image and og_image.get('content'):
            return ContentExtractor.make_absolute_url(og_image['content'], base_url)
        
        # 2. Twitter image
        twitter_image = soup.find('meta', attrs={'name': 'twitter:image'})
        if twitter_image and twitter_image.get('content'):
            return ContentExtractor.make_absolute_url(twitter_image['content'], base_url)
        
        # 3. Article:image
        article_image = soup.find('meta', attrs={'property': 'article:image'})
        if article_image and article_image.get('content'):
            return ContentExtractor.make_absolute_url(article_image['content'], base_url)
        
        # 4. Schema.org image
        schema_image = soup.find('meta', attrs={'itemprop': 'image'})
        if schema_image and schema_image.get('content'):
            return ContentExtractor.make_absolute_url(schema_image['content'], base_url)
        
        # 5. Find largest content image
        images = []
        for img in soup.find_all('img'):
            src = img.get('src') or img.get('data-src') or img.get('data-original')
            if not src:
                continue
            
            # Skip small images
            width = img.get('width')
            height = img.get('height')
            
            # Try to parse dimensions
            try:
                if width and int(width) < min_width:
                    continue
                if height and int(height) < 400:
                    continue
            except:
                pass
            
            # Skip icons, logos, avatars
            classes = ' '.join(img.get('class', [])).lower()
            if any(word in classes for word in ['icon', 'logo', 'avatar', 'thumb', 'spinner', 'loading']):
                continue
            
            src = ContentExtractor.make_absolute_url(src, base_url)
            images.append({
                'src': src,
                'width': width,
                'height': height,
                'alt': img.get('alt', '')
            })
        
        if images:
            # Try to find the largest image by dimensions
            valid_images = [img for img in images if img['width']]
            if valid_images:
                return max(valid_images, key=lambda x: int(x['width'] or 0))['src']
            return images[0]['src']
        
        return None


class NewsFetcher:
    """Enhanced news fetcher with multiple extraction methods"""
    
    def __init__(self):
        self.session = self._create_session()
        self.articles = []
        self.internet_available = self._check_internet()
        self.content_extractor = ContentExtractor()
        self.media_extractor = MediaExtractor()
        self.image_extractor = ImageExtractor()
        
    def _create_session(self):
        """Create requests session with rotating user agents"""
        session = requests.Session()
        
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0'
        ]
        
        session.headers.update({
            'User-Agent': random.choice(user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        
        # Configure retry strategy
        retry_strategy = urllib3.Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = requests.adapters.HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session
    
    def _check_internet(self, host="8.8.8.8", port=53, timeout=3):
        """Check internet connectivity"""
        try:
            socket.setdefaulttimeout(timeout)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
            return True
        except Exception:
            return False
    
def fetch_url_with_retry(self, url: str, max_retries: int = 2) -> Optional[str]:
    for attempt in range(max_retries):
        try:
            # Rotate user agent
            if attempt > 0:
                user_agents = [
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
                    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
                ]
                self.session.headers.update({
                    'User-Agent': random.choice(user_agents)
                })
            
            # Add referer for sites that check it
            if attempt == 1:
                self.session.headers.update({
                    'Referer': 'https://www.google.com/'
                })
            
            response = self.session.get(
                url, 
                timeout=10,
                allow_redirects=True,
                verify=False
            )
            
            if response.status_code == 200:
                return response.text
            elif response.status_code == 403:
                logger.warning(f"403 Forbidden for {url} on attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                else:
                    return None
            elif response.status_code in [429, 503]:
                # Rate limited, wait longer
                wait_time = 2 ** (attempt + 1)
                logger.warning(f"Rate limited for {url}, waiting {wait_time}s")
                time.sleep(wait_time)
            else:
                time.sleep(1)
                
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            time.sleep(1)
    
    return None
    
    def extract_full_content_with_media(self, url: str) -> Tuple[Optional[str], List[Dict], List[Dict], Optional[str]]:
        """Extract full content and media using multiple methods"""
        
        # Fetch HTML
        html = self.fetch_url_with_retry(url)
        if not html:
            return None, [], [], None
        
        soup = BeautifulSoup(html, 'html.parser')
        base_url = url
        
        # Extract using multiple methods
        extraction_methods = [
            ('trafilatura', lambda: ContentExtractor.extract_with_trafilatura(url)),
            ('newspaper3k', lambda: ContentExtractor.extract_with_newspaper(url)),
            ('readability', lambda: ContentExtractor.extract_with_readability(url, html)),
            ('bs4', lambda: ContentExtractor.extract_with_bs4_fallback(html))
        ]
        
        content = None
        content_method = None
        
        for method_name, method_func in extraction_methods:
            try:
                if method_name == 'newspaper3k':
                    result, meta, img, videos, audios = method_func()
                    if result and len(result) > 200:
                        content = result
                        content_method = method_name
                        # Use these videos/audios if found
                        if videos or audios:
                            return content, videos, audios, img
                else:
                    result, meta = method_func()
                    if result and len(result) > 200:
                        content = result
                        content_method = method_name
                        break
            except Exception as e:
                logger.error(f"Method {method_name} failed: {e}")
                continue
        
        # If still no content, try basic paragraph extraction
        if not content:
            paragraphs = soup.find_all('p')
            valid_paragraphs = []
            for p in paragraphs:
                text = p.get_text(strip=True)
                if len(text) > 100:
                    valid_paragraphs.append(text)
            
            if len(valid_paragraphs) > 3:
                content = '\n\n'.join(valid_paragraphs[:30])
                content_method = 'basic_paragraphs'
        
        # Extract media
        videos = MediaExtractor.extract_videos_from_html(soup, base_url)
        audios = MediaExtractor.extract_audios_from_html(soup, base_url)
        image = ImageExtractor.extract_best_image(soup, base_url)
        
        return content, videos, audios, image
    
    @staticmethod
    def make_absolute_url(url: str, base_url: str) -> str:
        """Convert relative URL to absolute"""
        if not url:
            return url
        
        # Remove whitespace
        url = url.strip()
        
        if url.startswith('//'):
            return 'https:' + url
        elif url.startswith('/'):
            from urllib.parse import urlparse
            parsed = urlparse(base_url)
            return f"{parsed.scheme}://{parsed.netloc}{url}"
        elif url.startswith('./'):
            from urllib.parse import urlparse, urljoin
            return urljoin(base_url, url[2:])
        elif not url.startswith(('http://', 'https://')):
            from urllib.parse import urljoin
            return urljoin(base_url, url)
        return url

    # Update your fetch_url_with_retry method
    def fetch_url_with_retry(self, url: str, max_retries: int = 3) -> Optional[str]:
        """Fetch URL with retry logic and rotating user agents"""
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        ]
        
        for attempt in range(max_retries):
            try:
                # Rotate user agent on each attempt
                self.session.headers.update({
                    'User-Agent': random.choice(user_agents)
                })
                
                # Add referer for sites that check it
                if attempt > 0:
                    self.session.headers.update({
                        'Referer': 'https://www.google.com/',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    })
                
                response = self.session.get(
                    url, 
                    timeout=15,
                    allow_redirects=True,
                    verify=False
                )
                
                if response.status_code == 200:
                    return response.text
                elif response.status_code == 403:
                    logger.warning(f"403 Forbidden for {url} on attempt {attempt + 1}")
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt
                        time.sleep(wait_time)
                    else:
                        return None
                elif response.status_code in [429, 503]:
                    # Rate limited, wait longer
                    wait_time = (2 ** (attempt + 1)) + random.randint(1, 3)
                    logger.warning(f"Rate limited for {url}, waiting {wait_time}s")
                    time.sleep(wait_time)
                else:
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        
            except requests.exceptions.Timeout:
                logger.warning(f"Timeout on attempt {attempt + 1} for {url}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
            except requests.exceptions.ConnectionError:
                logger.warning(f"Connection error on attempt {attempt + 1} for {url}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
            except Exception as e:
                logger.error(f"Error fetching {url}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
        
        return None

    # Add this helper function for parsing HTML with multiple parsers
    def parse_html_safely(html: str) -> Optional[BeautifulSoup]:
        """Parse HTML with multiple parser fallbacks"""
        parsers = ['html.parser', 'lxml', 'html5lib']
        
        for parser in parsers:
            try:
                soup = BeautifulSoup(html, parser)
                # Quick check if parsing worked
                if soup.find() is not None:
                    return soup
            except Exception as e:
                logger.warning(f"Parser {parser} failed: {e}")
                continue
        
        # Ultimate fallback
        try:
            return BeautifulSoup(html, 'html.parser')
        except:
            return None
    
    def fetch_newsapi_detailed(self):
        """Enhanced NewsAPI fetching with better content extraction"""
        api_key = getattr(settings, 'NEWS_API_KEY', '')
        if not api_key:
            logger.warning("No NewsAPI key found")
            return
        
        # Expanded queries for more articles
        queries = [
            # Nigeria-specific queries
            {'q': 'Nigeria', 'pageSize': 100, 'language': 'en', 'sortBy': 'publishedAt'},
            {'q': 'Lagos', 'pageSize': 100, 'language': 'en', 'sortBy': 'publishedAt'},
            {'q': 'Abuja', 'pageSize': 100, 'language': 'en', 'sortBy': 'publishedAt'},
            {'q': '"Nigerian government"', 'pageSize': 100},
            {'q': '"Nigerian economy" OR naira', 'pageSize': 100},
            {'q': '"Super Eagles" OR "Nigerian football"', 'pageSize': 100},
            {'q': 'Nollywood OR "Nigerian movies"', 'pageSize': 100},
            {'q': 'Tinubu OR APC OR PDP', 'pageSize': 100},
            {'q': '"Nigerian music" OR Afrobeats', 'pageSize': 100},
            {'q': '"Nigerian technology" OR "Nigerian startup"', 'pageSize': 100},
            
            # African news
            {'q': 'Africa', 'pageSize': 100},
            {'q': 'Ghana', 'pageSize': 50},
            {'q': 'Kenya', 'pageSize': 50},
            {'q': 'South Africa', 'pageSize': 50},
            
            # International news with Africa angle
            {'q': '"African Union" OR AU', 'pageSize': 50},
            {'q': '"Africa trade" OR "AfCFTA"', 'pageSize': 50},
        ]
        
        # Date range for last 7 days
        from_date = (timezone.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for params in queries:
                future = executor.submit(self._fetch_newsapi_single, params, from_date)
                futures.append(future)
                time.sleep(0.2)  # Rate limiting
            
            for future in as_completed(futures):
                try:
                    articles = future.result(timeout=30)
                    for article in articles:
                        self.articles.append(article)
                except Exception as e:
                    logger.error(f"Error processing NewsAPI future: {e}")
    
    def _fetch_newsapi_single(self, params: Dict, from_date: str) -> List[Dict]:
        """Fetch single NewsAPI query"""
        articles = []
        api_key = getattr(settings, 'NEWS_API_KEY', '')
        
        try:
            url = "https://newsapi.org/v2/everything"
            params['apiKey'] = api_key
            params['from'] = from_date
            
            response = self.session.get(url, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                for item in data.get('articles', []):
                    try:
                        article_data = self._process_newsapi_article(item)
                        if article_data:
                            articles.append(article_data)
                    except Exception as e:
                        logger.error(f"Error processing article: {e}")
                        
        except Exception as e:
            logger.error(f"Error in NewsAPI query {params}: {e}")
        
        return articles
    
    def _process_newsapi_article(self, article: Dict) -> Optional[Dict]:
        """Process a single NewsAPI article"""
        try:
            title = article.get('title', '').strip()
            url = article.get('url', '')
            
            if not title or not url or '[Removed]' in title:
                return None
            
            external_id = hashlib.md5(url.encode()).hexdigest()
            
            # Check if already exists in DB
            if Post.objects.filter(external_id=external_id).exists():
                return None
            
            # Extract full content and media
            content, videos, audios, image = self.extract_full_content_with_media(url)
            
            # Get source name
            source_obj = article.get('source', {})
            source = source_obj.get('name', 'News Source') if source_obj else 'News Source'
            source = source.replace('NewsAPI:', '').replace('NewsAPI', '').strip()
            
            # Detect category
            category = self.detect_category_from_content(title, content or '')
            
            # Parse date
            published_at = self.parse_date(article.get('publishedAt', ''))
            
            return {
                'title': title,
                'content': content or title[:500],
                'url': url,
                'source': source,
                'image_url': image or article.get('urlToImage', ''),
                'published_at': published_at,
                'category': category,
                'external_id': external_id,
                'method': 'newsapi',
                'videos': videos,
                'audios': audios,
                'has_media': bool(videos or audios)
            }
            
        except Exception as e:
            logger.error(f"Error processing NewsAPI article: {e}")
            return None
    
    def fetch_rss_feeds_detailed(self):
        """Enhanced RSS feed fetching with better content extraction"""
        rss_feeds = [
            # Nigerian sources
            ('Premium Times Nigeria', 'https://www.premiumtimesng.com/feed', 'Nigeria'),
            ('Vanguard Nigeria', 'https://www.vanguardngr.com/feed', 'Nigeria'),
            ('Punch Nigeria', 'https://punchng.com/feed', 'Nigeria'),
            ('The Guardian Nigeria', 'https://guardian.ng/feed', 'Nigeria'),
            ('Daily Trust', 'https://dailytrust.com/feed', 'Nigeria'),
            ('Leadership Nigeria', 'https://leadership.ng/feed', 'Nigeria'),
            ('Nairametrics', 'https://nairametrics.com/feed', 'Nigeria'),
            ('TechCabal', 'https://techcabal.com/feed', 'Nigeria'),
            ('BusinessDay', 'https://businessday.ng/feed', 'Nigeria'),
            ('The Cable', 'https://www.thecable.ng/feed', 'Nigeria'),
            ('Sahara Reporters', 'https://saharareporters.com/feeds/latest/feed', 'Nigeria'),
            ('ThisDay', 'https://www.thisdaylive.com/index.php/feed', 'Nigeria'),
            ('Tribune', 'https://tribuneonlineng.com/feed', 'Nigeria'),
            ('Independent Nigeria', 'https://independent.ng/feed', 'Nigeria'),
            
            # African sources
            ('BBC Africa', 'http://feeds.bbci.co.uk/news/world/africa/rss.xml', 'Africa'),
            ('Al Jazeera Africa', 'https://www.aljazeera.com/xml/rss/all.xml', 'Africa'),
            ('Reuters Africa', 'http://feeds.reuters.com/reuters/AFRICAfricaNews', 'Africa'),
            ('France24 Africa', 'https://www.france24.com/en/africa/rss', 'Africa'),
            ('The East African', 'https://www.theeastafrican.co.ke/rss.xml', 'East Africa'),
            ('Daily Nation Kenya', 'https://nation.africa/kenya/rss.xml', 'Kenya'),
            ('MyJoyOnline Ghana', 'https://www.myjoyonline.com/feed', 'Ghana'),
            
            # International news with Africa sections
            ('CNN Africa', 'http://rss.cnn.com/rss/edition_africa.rss', 'Africa'),
            ('The Guardian Africa', 'https://www.theguardian.com/world/africa/rss', 'Africa'),
            ('NYT Africa', 'https://rss.nytimes.com/services/xml/rss/nyt/Africa.xml', 'Africa'),
        ]
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = []
            for name, url, region in rss_feeds:
                future = executor.submit(self._fetch_rss_single, name, url, region)
                futures.append(future)
                time.sleep(0.5)
            
            for future in as_completed(futures):
                try:
                    articles = future.result(timeout=60)
                    for article in articles:
                        self.articles.append(article)
                except Exception as e:
                    logger.error(f"Error processing RSS future: {e}")
    
    def _fetch_rss_single(self, name: str, feed_url: str, region: str) -> List[Dict]:
        """Fetch single RSS feed"""
        articles = []
        
        try:
            feed = feedparser.parse(feed_url)
            
            for entry in feed.entries[:20]:  # Get 20 from each source
                try:
                    title = entry.get('title', '').strip()
                    if not title:
                        continue
                    
                    url = entry.get('link', '')
                    if not url:
                        continue
                    
                    external_id = hashlib.md5(url.encode()).hexdigest()
                    
                    if Post.objects.filter(external_id=external_id).exists():
                        continue
                    
                    # Extract full content and media
                    content, videos, audios, image = self.extract_full_content_with_media(url)
                    
                    # If content extraction failed, use summary
                    if not content:
                        content = entry.get('summary', '') or entry.get('description', '')
                        content = self.clean_html(content)
                    
                    # Extract image from RSS if not found
                    if not image:
                        image = self._extract_image_from_rss(entry, url)
                    
                    # Detect category
                    category = self.detect_category_from_content(title, content or '')
                    
                    # Parse date
                    published_at = self.parse_date(entry.get('published', ''))
                    
                    articles.append({
                        'title': title,
                        'content': content or title[:500],
                        'url': url,
                        'source': name,
                        'image_url': image,
                        'published_at': published_at,
                        'category': category,
                        'external_id': external_id,
                        'method': 'rss',
                        'videos': videos,
                        'audios': audios,
                        'has_media': bool(videos or audios)
                    })
                    
                except Exception as e:
                    logger.error(f"Error processing RSS entry from {name}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error fetching RSS feed {name}: {e}")
        
        return articles
    
    def _extract_image_from_rss(self, entry, base_url):
        """Extract image from RSS entry"""
        # Check media:content
        if hasattr(entry, 'media_content'):
            for media in entry.media_content:
                if media.get('medium') == 'image' and media.get('url'):
                    return self.make_absolute_url(media['url'], base_url)
        
        # Check enclosures
        if hasattr(entry, 'enclosures'):
            for enc in entry.enclosures:
                if enc.get('type', '').startswith('image/'):
                    return self.make_absolute_url(enc.get('href', ''), base_url)
        
        # Check media:thumbnail
        if hasattr(entry, 'media_thumbnail'):
            for thumb in entry.media_thumbnail:
                if thumb.get('url'):
                    return self.make_absolute_url(thumb['url'], base_url)
        
        return None
    
    def fetch_web_scrape_detailed(self):
        """Direct website scraping with multiple sources"""
        websites = [
            {
                'name': 'Premium Times',
                'url': 'https://www.premiumtimesng.com',
                'article_selectors': ['article', '.post', '.article', '.entry'],
                'title_selectors': ['h1.entry-title', 'h2 a', 'h3 a'],
                'link_selectors': ['h2 a', 'h3 a', '.entry-title a'],
                'categories': ['news', 'headlines', 'politics', 'business', 'sports']
            },
            {
                'name': 'Vanguard',
                'url': 'https://www.vanguardngr.com',
                'article_selectors': ['article', '.post', '.rtp-latest-news-list li'],
                'title_selectors': ['h3 a', '.entry-title a'],
                'link_selectors': ['h3 a', '.entry-title a'],
                'categories': ['news', 'politics', 'business', 'sports']
            },
            {
                'name': 'Punch',
                'url': 'https://punchng.com',
                'article_selectors': ['article', '.post'],
                'title_selectors': ['h2 a', 'h3 a'],
                'link_selectors': ['h2 a', 'h3 a'],
                'categories': ['topics/news', 'topics/politics', 'topics/business']
            },
            {
                'name': 'Daily Trust',
                'url': 'https://dailytrust.com',
                'article_selectors': ['article', '.post'],
                'title_selectors': ['h3 a', 'h2 a'],
                'link_selectors': ['h3 a', 'h2 a'],
                'categories': ['category/news', 'category/politics', 'category/business']
            },
            {
                'name': 'The Guardian',
                'url': 'https://guardian.ng',
                'article_selectors': ['article', '.post'],
                'title_selectors': ['h2 a', 'h3 a'],
                'link_selectors': ['h2 a', 'h3 a'],
                'categories': ['category/news', 'category/politics', 'category/business']
            }
        ]
        
        for site in websites:
            try:
                articles = self._scrape_website(site)
                for article in articles:
                    self.articles.append(article)
            except Exception as e:
                logger.error(f"Error scraping {site['name']}: {e}")
    
    def _scrape_website(self, site: Dict) -> List[Dict]:
        """Scrape a single website"""
        articles = []
        
        for category in site.get('categories', ['']):
            try:
                # Try category page first
                if category:
                    url = f"{site['url']}/{category}"
                else:
                    url = site['url']
                
                html = self.fetch_url_with_retry(url)
                if not html:
                    continue
                
                soup = BeautifulSoup(html, 'html.parser')
                
                # Find articles using selectors
                article_elements = []
                for selector in site['article_selectors']:
                    article_elements = soup.select(selector)
                    if article_elements:
                        break
                
                for article_elem in article_elements[:10]:  # Limit per category
                    try:
                        # Extract title
                        title = None
                        for selector in site['title_selectors']:
                            title_elem = article_elem.select_one(selector)
                            if title_elem:
                                title = title_elem.get_text(strip=True)
                                break
                        
                        if not title:
                            continue
                        
                        # Extract link
                        link = None
                        for selector in site['link_selectors']:
                            link_elem = article_elem.select_one(selector)
                            if link_elem:
                                link = link_elem.get('href', '')
                                break
                        
                        if not link:
                            continue
                        
                        # Make absolute URL
                        link = self.make_absolute_url(link, site['url'])
                        
                        external_id = hashlib.md5(link.encode()).hexdigest()
                        
                        if Post.objects.filter(external_id=external_id).exists():
                            continue
                        
                        # Extract full content and media
                        content, videos, audios, image = self.extract_full_content_with_media(link)
                        
                        # Detect category
                        category_detected = self.detect_category_from_content(title, content or '')
                        
                        articles.append({
                            'title': title,
                            'content': content or title[:500],
                            'url': link,
                            'source': site['name'],
                            'image_url': image,
                            'published_at': timezone.now(),
                            'category': category_detected,
                            'external_id': external_id,
                            'method': 'web_scrape',
                            'videos': videos,
                            'audios': audios,
                            'has_media': bool(videos or audios)
                        })
                        
                    except Exception as e:
                        logger.error(f"Error scraping article from {site['name']}: {e}")
                        continue
                        
                time.sleep(random.uniform(2, 5))  # Be polite
                
            except Exception as e:
                logger.error(f"Error scraping {site['name']} category {category}: {e}")
                continue
        
        return articles
    
    def detect_category_from_content(self, title: str, content: str) -> str:
        """Improved category detection"""
        text = (title + ' ' + content).lower()
        
        # Weighted keyword matching
        categories = {
            'Politics': [
                ('president', 3), ('senate', 3), ('governor', 3), ('election', 3),
                ('politic', 2), ('minister', 3), ('assembly', 2), ('vote', 2),
                ('campaign', 2), ('party', 2), ('government', 2), ('parliament', 3),
                ('tinubu', 5), ('buhari', 5), ('obia', 5), ('atiku', 5),
                ('apc', 5), ('pdp', 5), ('labour', 2), ('legislature', 3),
                ('democracy', 2), ('constitution', 3), ('bill', 2), ('lawmaker', 3)
            ],
            'Economy': [
                ('naira', 5), ('dollar', 4), ('economy', 4), ('inflation', 4),
                ('budget', 4), ('finance', 3), ('market', 3), ('stock', 4),
                ('investment', 3), ('business', 2), ('bank', 3), ('cbn', 5),
                ('exchange', 3), ('tax', 3), ('revenue', 3), ('trade', 3),
                ('import', 3), ('export', 3), ('gdp', 5), ('economic', 3)
            ],
            'Sports': [
                ('sport', 3), ('football', 4), ('basketball', 4), ('athlete', 3),
                ('match', 3), ('league', 3), ('championship', 3), ('goal', 4),
                ('player', 3), ('super eagles', 5), ('super falcons', 5),
                ('world cup', 4), ('tournament', 3), ('stadium', 3),
                ('coach', 3), ('team', 2), ('win', 2), ('victory', 2)
            ],
            'Technology': [
                ('tech', 4), ('digital', 3), ('app', 4), ('software', 4),
                ('internet', 3), ('phone', 3), ('computer', 3), ('startup', 4),
                ('ai', 5), ('artificial intelligence', 5), ('data', 3),
                ('cyber', 4), ('5g', 4), ('mobile', 3), ('innovation', 3),
                ('gadget', 3), ('device', 3), ('technology', 4)
            ],
            'Entertainment': [
                ('music', 4), ('movie', 4), ('actor', 4), ('actress', 4),
                ('celebrity', 4), ('nollywood', 5), ('film', 4), ('show', 3),
                ('award', 3), ('davido', 5), ('burna boy', 5), ('wizkid', 5),
                ('tiwa savage', 5), ('entertainment', 3), ('concert', 3)
            ],
            'Health': [
                ('health', 3), ('hospital', 3), ('doctor', 3), ('medical', 3),
                ('disease', 3), ('vaccine', 4), ('treatment', 3), ('patient', 3),
                ('covid', 5), ('malaria', 4), ('fever', 3), ('medicine', 3),
                ('clinic', 3), ('healthcare', 3), ('wellness', 2)
            ],
            'Education': [
                ('school', 3), ('university', 4), ('student', 3), ('teacher', 3),
                ('education', 3), ('exam', 3), ('learning', 2), ('college', 3),
                ('polytechnic', 3), ('waec', 5), ('neco', 5), ('jamb', 5),
                ('academic', 2), ('scholarship', 3)
            ],
            'Crime': [
                ('crime', 4), ('robber', 4), ('kill', 4), ('murder', 4),
                ('police', 3), ('arrest', 3), ('court', 3), ('judge', 3),
                ('law', 2), ('theft', 3), ('fraud', 3), ('kidnap', 5),
                ('bandit', 5), ('terrorist', 5), ('attack', 3)
            ],
            'Business': [
                ('business', 3), ('company', 3), ('entrepreneur', 3),
                ('ceo', 3), ('enterprise', 2), ('corporate', 2),
                ('industry', 2), ('manufacturing', 2), ('market', 2)
            ]
        }
        
        # Calculate weighted scores
        scores = {}
        for category, keywords in categories.items():
            score = 0
            for keyword, weight in keywords:
                if keyword in text:
                    score += weight
            if score > 0:
                scores[category] = score
        
        if scores:
            return max(scores, key=scores.get)
        
        return 'News'
    
    def clean_html(self, text: str) -> str:
        """Clean HTML from text"""
        if not text:
            return text
        
        # Remove HTML tags
        clean = re.sub(r'<[^>]+>', '', text)
        # Remove multiple spaces and newlines
        clean = re.sub(r'\s+', ' ', clean).strip()
        # Remove excessive special characters
        clean = re.sub(r'[^\w\s.,!?\'"-]', '', clean)
        
        return clean
    
    def parse_date(self, date_str: str):
        """Parse various date formats"""
        if not date_str:
            return timezone.now()
        
        try:
            # Try dateutil if available
            from dateutil import parser
            parsed = parser.parse(date_str)
            if parsed.tzinfo is None:
                return timezone.make_aware(parsed)
            return parsed
        except:
            pass
        
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
        except:
            pass
        
        return timezone.now()
    
    def remove_duplicates(self, articles: List[Dict]) -> List[Dict]:
        """Remove duplicate articles"""
        unique_articles = []
        seen_urls = set()
        seen_titles = set()
        
        for article in articles:
            url = article.get('url', '')
            title = article.get('title', '').lower().strip()
            external_id = article.get('external_id', '')
            
            if not url or not title:
                continue
            
            # Check by external_id
            if external_id and external_id in seen_urls:
                continue
            if external_id:
                seen_urls.add(external_id)
            
            # Check by URL
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
                unique_articles.append(article)
        
        return unique_articles
    
    def _title_similarity(self, title1: str, title2: str) -> float:
        """Calculate title similarity"""
        words1 = set(title1.split())
        words2 = set(title2.split())
        
        if not words1 or not words2:
            return 0
        
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union if union > 0 else 0
    
    def save_articles(self, articles: List[Dict]) -> int:
        """Save articles to database"""
        saved_count = 0
        
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
        
        for article in articles:
            try:
                # Basic validation
                title = article.get('title', '').strip()
                url = article.get('url', '')
                external_id = article.get('external_id', '')
                
                if not title or not url:
                    continue
                
                # Truncate title if needed
                if len(title) > 200:
                    title = title[:197] + '...'
                
                # Check if already exists
                if external_id and Post.objects.filter(external_id=external_id).exists():
                    continue
                
                if Post.objects.filter(external_url=url).exists():
                    continue
                
                # Get or create category
                category_name = article.get('category', 'News')
                category, _ = Category.objects.get_or_create(
                    name=category_name,
                    defaults={
                        'slug': category_name.lower().replace(' ', '-'),
                        'description': f'{category_name} news'
                    }
                )
                
                # Prepare content
                content = article.get('content', title)
                if content:
                    content = self.clean_html(content)
                    content = content[:15000]  # Limit length
                
                # Get media
                videos = article.get('videos', [])
                audios = article.get('audios', [])
                
                # Create post
                post = Post.objects.create(
                    title=title,
                    content=content,
                    post_type='news',
                    category=category,
                    author=system_user,
                    external_source=article.get('source', 'Unknown')[:100],
                    external_url=url[:500],
                    external_id=external_id,
                    image_url=article.get('image_url', '')[:1000],
                    published_at=article.get('published_at', timezone.now()),
                    status='published',
                    is_auto_fetched=True,
                    is_approved=True,
                    verification_status='pending',  # Will be verified later
                    meta_description=content[:160] if content else title[:160],
                    views=random.randint(10, 100),
                    video_urls=videos if videos else None,
                    audio_urls=audios if audios else None,
                    has_media=bool(videos or audios),
                )
                
                saved_count += 1
                logger.info(f"Saved: {title[:50]}...")
                
                # Update category count
                category.update_post_count()
                
            except Exception as e:
                logger.error(f"Error saving article: {e}")
                continue
        
        return saved_count
    
    def fetch_all_news(self) -> int:
        """Fetch news from all sources"""
        logger.info("Starting comprehensive news fetch...")
        
        if not self.internet_available:
            logger.error("No internet connection")
            return 0
        
        self.articles = []
        
        # Fetch from all sources
        fetch_methods = [
            ('NewsAPI', self.fetch_newsapi_detailed),
            ('RSS Feeds', self.fetch_rss_feeds_detailed),
            ('Web Scrape', self.fetch_web_scrape_detailed),
        ]
        
        for name, method in fetch_methods:
            try:
                logger.info(f"Fetching from {name}...")
                method()
                logger.info(f"Found {len(self.articles)} articles from {name}")
            except Exception as e:
                logger.error(f"Error in {name} fetch: {e}")
        
        # Remove duplicates
        unique_articles = self.remove_duplicates(self.articles)
        logger.info(f"Unique articles: {len(unique_articles)} out of {len(self.articles)}")
        
        # Save articles
        saved_count = self.save_articles(unique_articles)
        
        logger.info(f"Total saved: {saved_count}")
        return saved_count