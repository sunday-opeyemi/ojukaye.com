# core/management/commands/fetch_news.py - THE ONLY COMMAND YOU NEED

from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import Post, Category, User
from core.news_fetcher_unified import UnifiedNewsFetcher
import hashlib
import random
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'ONE COMMAND TO FETCH ALL NEWS - Videos, Audio, Images, Full Content'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=1,
            help='Days back to fetch (default: 7)'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=50,
            help='Articles per source (default: 100)'
        )
        parser.add_argument(
            '--workers',
            type=int,
            default=5,
            help='Number of worker threads (default: 5)'
        )
        parser.add_argument(
            '--sources',
            type=str,
            default='all',
            help='Sources: all, newsapi, rss (default: all)'
        )
        parser.add_argument(
            '--no-extract',
            action='store_true',
            help='Skip full content extraction (faster)'
        )
        parser.add_argument(
            '--quiet',
            action='store_true',
            help='Less verbose output'
        )
    
    def handle(self, *args, **options):
        days = options['days'] 
        limit = min(options['limit'], 100)
        workers = options['workers']
        sources = options['sources'].lower()
        extract_full = not options['no_extract']
        quiet = options['quiet']
        
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('🚀 UNIFIED NEWS FETCHER'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(f'📅 Days: {days}')  # This will show 1
        self.stdout.write(f'📊 Limit: {limit}')
        self.stdout.write(f'🔧 Workers: {workers}')
        self.stdout.write(f'📡 Sources: {sources}')
        self.stdout.write(f'🔍 Full extraction: {extract_full}')
        
        # Get API key
        from django.conf import settings
        api_key = getattr(settings, 'NEWS_API_KEY', '')
        if not api_key:
            self.stdout.write(self.style.ERROR('❌ NEWS_API_KEY not found in settings!'))
            return
        
        # Get or create system user
        try:
            system_user = User.objects.get(username='news_bot')
        except User.DoesNotExist:
            system_user = User.objects.create_user(
                username='news_bot',
                email='news@ojukaye.com',
                password='NewsBot123!',
                first_name='News',
                last_name='Bot',
                is_active=False
            )
        
        # Initialize fetcher
        fetcher = UnifiedNewsFetcher()
        
        all_articles = []
        
        # 1. Fetch from NewsAPI
        if sources in ['all', 'newsapi']:
            self.stdout.write('\n📰 Fetching from NewsAPI...')
            newsapi_articles = fetcher.fetch_from_newsapi(api_key, days=days, limit=limit)
            all_articles.extend(newsapi_articles)
            self.stdout.write(self.style.SUCCESS(f'   ✅ Found {len(newsapi_articles)} articles'))
        
        # 2. Fetch from RSS
        if sources in ['all', 'rss']:
            self.stdout.write('\n📡 Fetching from RSS feeds...')
            rss_articles = fetcher.fetch_from_rss()
            all_articles.extend(rss_articles)
            self.stdout.write(self.style.SUCCESS(f'   ✅ Found {len(rss_articles)} articles'))
        
        if not all_articles:
            self.stdout.write(self.style.WARNING('\n⚠️ No articles found from any source'))
            return
        
        # 3. Remove duplicates
        self.stdout.write('\n🔍 Removing duplicates...')
        unique_articles = fetcher.remove_duplicates(all_articles)
        self.stdout.write(self.style.SUCCESS(f'   ✅ {len(unique_articles)} unique articles (removed {len(all_articles) - len(unique_articles)} duplicates)'))
        
        # 4. Extract full content and media (if requested)
        if extract_full and unique_articles:
            self.stdout.write('\n🔍 Extracting full content and media...')
            self.stdout.write('   This may take a while depending on the number of articles...')
            
            processed_articles = fetcher.process_articles_parallel(
                unique_articles, 
                max_workers=workers,
                extract_full=True
            )
            
            # Count media
            total_videos = sum(len(a.get('videos', [])) for a in processed_articles)
            total_audio = sum(len(a.get('audios', [])) for a in processed_articles)
            total_images = sum(len(a.get('images', [])) for a in processed_articles)
            
            self.stdout.write(self.style.SUCCESS(
                f'   ✅ Extraction complete!\n'
                f'      📹 Videos: {total_videos}\n'
                f'      🎵 Audio: {total_audio}\n'
                f'      🖼️  Images: {total_images}'
            ))
        else:
            processed_articles = unique_articles
        
        # 5. Save to database
        self.stdout.write('\n💾 Saving to database...')
        saved_count = 0
        media_stats = {'videos': 0, 'audio': 0, 'images': 0}
        
        for article in processed_articles:
            try:
                title = article.get('title', '').strip()
                url = article.get('url', '').strip()
                
                if not title or not url:
                    continue
                
                # Check if exists
                if Post.objects.filter(external_url=url).exists():
                    continue
                
                # Generate ID
                external_id = hashlib.md5(url.encode()).hexdigest()
                
                # Get content
                content = article.get('full_content') or article.get('description') or article.get('content') or title
                content = fetcher.clean_html(content)[:15000]
                
                # Get category
                category_name = fetcher.detect_category(title, content)
                category, _ = Category.objects.get_or_create(
                    name=category_name,
                    defaults={'slug': category_name.lower().replace(' ', '-')}
                )
                
                # Parse date
                published_at = fetcher.parse_date(article.get('published_at'))
                
                # Get media
                videos = article.get('videos', [])
                audios = article.get('audios', [])
                images = article.get('images', [])
                main_image = article.get('image') or article.get('main_image') or (images[0]['url'] if images else '')
                
                # Create post
                post = Post.objects.create(
                    title=title[:200],
                    content=content,
                    post_type='news',
                    category=category,
                    author=system_user,
                    external_source=article.get('source', 'Unknown')[:100],
                    external_url=url[:500],
                    external_id=external_id,
                    image_url=main_image[:1000] if main_image else '',
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
                media_stats['videos'] += len(videos)
                media_stats['audio'] += len(audios)
                media_stats['images'] += len(images)
                
                if not quiet and saved_count % 10 == 0:
                    self.stdout.write(f'   Saved {saved_count} articles...')
                    
            except Exception as e:
                logger.error(f"Error saving article: {e}")
                continue
        
        # Final report
        self.stdout.write(self.style.SUCCESS('\n' + '=' * 60))
        self.stdout.write(self.style.SUCCESS('✅ FETCH COMPLETE!'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(f'📊 Articles saved: {saved_count}')
        self.stdout.write(f'📹 Total videos: {media_stats["videos"]}')
        self.stdout.write(f'🎵 Total audio: {media_stats["audio"]}')
        self.stdout.write(f'🖼️  Total images: {media_stats["images"]}')
        
        if saved_count > 0:
            self.stdout.write(self.style.SUCCESS('\n🎉 You can now view these articles on your site!'))