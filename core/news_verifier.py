# core/news_verifier.py (Enhanced)

import re
import requests
import json
import hashlib
import logging
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
from urllib.parse import urlparse
from django.utils import timezone
from django.conf import settings
from django.core.cache import cache
import nltk
from nltk.sentiment import SentimentIntensityAnalyzer
from textblob import TextBlob
import spacy

logger = logging.getLogger(__name__)

# Download NLTK data if needed
try:
    nltk.data.find('vader_lexicon')
except LookupError:
    nltk.download('vader_lexicon')

class EnhancedNewsVerifier:
    """Advanced news verification with multiple checks"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        # Initialize sentiment analyzer
        self.sentiment_analyzer = SentimentIntensityAnalyzer()
        
        # Load spaCy model if available
        try:
            self.nlp = spacy.load('en_core_web_sm')
        except:
            self.nlp = None
            logger.warning("spaCy model not available - run: python -m spacy download en_core_web_sm")
        
        # Known fact-checking websites
        self.fact_check_sites = [
            'factcheck.org',
            'politifact.com',
            'snopes.com',
            'africacheck.org',
            'fullfact.org',
            'apnews.com/fact-checking',
            'reuters.com/fact-check',
            'bbc.com/news/fact-check'
        ]
        
        # Known reliable sources (Nigerian focus)
        self.reliable_sources = [
            # Nigerian sources
            'premiumtimesng.com', 'punchng.com', 'vanguardngr.com',
            'guardian.ng', 'thisdaylive.com', 'thenationonlineng.net',
            'sunnewsonline.com', 'tribuneonlineng.com', 'dailytrust.com',
            'leadership.ng', 'independent.ng', 'businessday.ng',
            'channelstv.com', 'arise.tv', 'tv360nigeria.com',
            'thecable.ng', 'saharareporters.com', 'pmnewsnigeria.com',
            # International sources
            'reuters.com', 'bbc.com', 'cnn.com', 'aljazeera.com',
            'apnews.com', 'afp.com', 'nytimes.com', 'wsj.com',
            'bloomberg.com', 'ft.com', 'economist.com'
        ]
        
        # Known unreliable sources
        self.unreliable_sources = [
            'naijanews.com', 'gistmania.com', 'nairaland.com',
            'trendingnaija.com', 'infonigeria.com', 'naijagists.com',
            'lindaikejisblog.com', 'naijaloaded.com.ng', 'gistlover.com',
            'naijagossip.com', 'trendybeatz.com'
        ]
        
        # Sensationalist keywords
        self.sensationalist_keywords = [
            ('shocking', 0.2), ('unbelievable', 0.2), ('you won\'t believe', 0.3),
            ('mind-blowing', 0.2), ('jaw-dropping', 0.2), ('incredible', 0.1),
            ('amazing', 0.1), ('epic', 0.1), ('massive', 0.1), ('huge', 0.1),
            ('explosive', 0.2), ('revealed', 0.1), ('exposed', 0.2),
            ('conspiracy', 0.3), ('cover-up', 0.3), ('they don\'t want you to know', 0.4),
            ('what happens next', 0.3), ('will shock you', 0.3), ('goes viral', 0.2),
            ('breaking news', 0.1), ('just in', 0.1), ('urgent', 0.1),
            ('must read', 0.1), ('share this', 0.1), ('forward this', 0.1),
            ('prophet reveals', 0.3), ('prophecy', 0.2), ('miracle', 0.2),
            ('supernatural', 0.2), ('pastor says', 0.2), ('imam reveals', 0.2),
            ('cleric predicts', 0.2), ('end time', 0.2), ('manifest', 0.2)
        ]
        
        # URL shorteners
        self.url_shorteners = [
            'bit.ly', 'tinyurl.com', 'goo.gl', 'ow.ly', 'is.gd',
            'buff.ly', 'tiny.cc', 'tr.im', 'short.link'
        ]
        
        # Suspicious TLDs
        self.suspicious_tlds = ['.tk', '.ml', '.ga', '.cf', '.gq', '.xyz', '.top', '.loan']
        
        # Official domains (higher trust)
        self.official_domains = ['.gov', '.edu', '.org', '.int', '.mil']
        
        # Cache timeout for API calls
        self.cache_timeout = 3600  # 1 hour
    
    def verify_article(self, article: Dict) -> Dict:
        """Comprehensive article verification"""
        
        title = article.get('title', '')
        content = article.get('content', '')
        url = article.get('url', '')
        source = article.get('source', '')
        
        if not title or not url:
            return {
                'score': 0.0,
                'status': 'fake',
                'error': 'Missing required fields',
                'checks': {},
                'verification_time': timezone.now().isoformat()
            }
        
        # Run all verification checks
        checks = {}
        
        # 1. Source credibility check
        source_check = self._check_source_credibility(source, url)
        checks['source'] = source_check
        
        # 2. URL structure check
        url_check = self._check_url_structure(url)
        checks['url'] = url_check
        
        # 3. Content quality check
        content_check = self._check_content_quality(title, content)
        checks['content'] = content_check
        
        # 4. Sensationalism check
        sensationalism_check = self._check_sensationalism(title, content)
        checks['sensationalism'] = sensationalism_check
        
        # 5. Language analysis
        language_check = self._analyze_language(title + ' ' + content)
        checks['language'] = language_check
        
        # 6. External verification if enabled
        if getattr(settings, 'ENABLE_EXTERNAL_VERIFICATION', False):
            external_check = self._check_external_sources(title)
            checks['external'] = external_check
        
        # 7. Consistency check
        consistency_check = self._check_consistency(title, content, url)
        checks['consistency'] = consistency_check
        
        # 8. Duplicate detection
        duplicate_check = self._check_duplicates(title, content)
        checks['duplicate'] = duplicate_check
        
        # Calculate weighted average
        weights = {
            'source': 0.25,
            'url': 0.10,
            'content': 0.15,
            'sensationalism': 0.15,
            'language': 0.10,
            'external': 0.10,
            'consistency': 0.10,
            'duplicate': 0.05
        }
        
        weighted_score = 0
        total_weight = 0
        warnings = []
        strengths = []
        
        for check_name, check_result in checks.items():
            weight = weights.get(check_name, 0.1)
            weighted_score += check_result['score'] * weight
            total_weight += weight
            
            # Collect warnings and strengths
            for reason in check_result.get('reasons', []):
                if check_result['score'] < 0.5:
                    warnings.append(f"{check_name.title()}: {reason}")
                elif check_result['score'] > 0.7:
                    strengths.append(f"{check_name.title()}: {reason}")
        
        final_score = weighted_score / total_weight if total_weight > 0 else 0.5
        
        # Determine status
        if final_score >= 0.8:
            status = 'verified'
        elif final_score >= 0.6:
            status = 'questionable'
        elif final_score >= 0.4:
            status = 'pending'
        else:
            status = 'fake'
        
        # Generate recommendations
        recommendations = []
        if final_score >= 0.8:
            recommendations.append("Article appears to be legitimate news - can be auto-approved")
        elif final_score >= 0.6:
            recommendations.append("Article requires human review before approval")
        elif final_score >= 0.4:
            recommendations.append("Article shows multiple concerns - investigate thoroughly")
        else:
            recommendations.append("Article likely contains fake news - consider rejection")
        
        return {
            'overall_score': round(final_score, 2),
            'score_percentage': round(final_score * 100, 1),
            'status': status,
            'checks': checks,
            'warnings': warnings[:5],  # Limit to top 5 warnings
            'strengths': strengths[:5],  # Limit to top 5 strengths
            'recommendations': recommendations,
            'verified_at': timezone.now().isoformat(),
            'method': 'ai_assisted'
        }
    
    def _check_source_credibility(self, source: str, url: str) -> Dict:
        """Check source credibility"""
        source_lower = source.lower()
        url_lower = url.lower()
        
        score = 0.5  # Neutral start
        reasons = []
        
        # Extract domain from URL
        domain = self._extract_domain(url)
        
        # Check against reliable sources
        for reliable in self.reliable_sources:
            if reliable in source_lower or reliable in url_lower or reliable in domain:
                score = 0.95
                reasons.append(f"Known reliable source: {reliable}")
                break
        
        # Check against unreliable sources
        if not reasons:  # Only if not already marked reliable
            for unreliable in self.unreliable_sources:
                if unreliable in source_lower or unreliable in url_lower or unreliable in domain:
                    score = 0.1
                    reasons.append(f"Known unreliable source: {unreliable}")
                    break
        
        # Check for official domains
        for official in self.official_domains:
            if official in domain:
                score = max(score, 0.85)
                reasons.append(f"Official domain: {official}")
                break
        
        # Check domain age (using cache)
        domain_age = self._get_domain_age(domain)
        if domain_age:
            if domain_age < 30:  # Less than 30 days
                score -= 0.2
                reasons.append(f"Very new domain (less than {domain_age} days)")
            elif domain_age < 365:  # Less than 1 year
                score -= 0.1
                reasons.append(f"Domain less than 1 year old ({domain_age} days)")
            elif domain_age > 3650:  # More than 10 years
                score += 0.1
                reasons.append(f"Established domain (over 10 years old)")
        
        # Check for HTTPS
        if url.startswith('https://'):
            score += 0.05
            reasons.append("Secure HTTPS connection")
        else:
            score -= 0.05
            reasons.append("No HTTPS - insecure connection")
        
        # Check if source is provided
        if not source:
            score -= 0.1
            reasons.append("No source attribution provided")
        
        return {
            'score': max(0.0, min(1.0, score)),
            'reasons': reasons,
            'domain': domain
        }
    
    def _check_url_structure(self, url: str) -> Dict:
        """Check URL for suspicious patterns"""
        score = 0.8  # Start high
        reasons = []
        
        # Extract domain
        domain = self._extract_domain(url)
        
        # Check for URL shorteners
        for shortener in self.url_shorteners:
            if shortener in url:
                score -= 0.3
                reasons.append(f"URL shortener detected: {shortener}")
                break
        
        # Check for IP address instead of domain
        if re.match(r'https?://\d+\.\d+\.\d+\.\d+', url):
            score -= 0.4
            reasons.append("IP address used instead of domain name - suspicious")
        
        # Check for suspicious TLDs
        for tld in self.suspicious_tlds:
            if domain.endswith(tld):
                score -= 0.2
                reasons.append(f"Suspicious top-level domain: {tld}")
                break
        
        # Check for excessive subdomains
        subdomain_count = domain.count('.')
        if subdomain_count > 3:
            score -= 0.1
            reasons.append(f"Excessive subdomains: {subdomain_count} levels")
        
        # Check for misspelled domain names (typosquatting)
        common_domains = ['google', 'facebook', 'twitter', 'youtube', 'instagram']
        for common in common_domains:
            if common in domain and not any(reliable in domain for reliable in self.reliable_sources):
                # Check if it's a close match but not exact
                if self._levenshtein_distance(common, domain) < 3:
                    score -= 0.3
                    reasons.append(f"Possible typosquatting: {domain} looks like {common}.com")
                    break
        
        # Check for numeric domain
        if re.match(r'^[0-9-]+$', domain.replace('.', '')):
            score -= 0.2
            reasons.append("Numeric domain - suspicious")
        
        return {
            'score': max(0.0, min(1.0, score)),
            'reasons': reasons,
            'domain': domain
        }
    
    def _check_content_quality(self, title: str, content: str) -> Dict:
        """Check content quality and completeness"""
        score = 0.6
        reasons = []
        
        # Check content length
        content_length = len(content)
        if content_length < 100:
            score -= 0.3
            reasons.append(f"Very short content ({content_length} chars)")
        elif content_length < 300:
            score -= 0.1
            reasons.append(f"Short content ({content_length} chars)")
        elif content_length > 1000:
            score += 0.1
            reasons.append(f"Good content length ({content_length} chars)")
        
        # Check word count
        words = content.split()
        word_count = len(words)
        if word_count < 20:
            score -= 0.2
            reasons.append(f"Very few words ({word_count} words)")
        elif word_count > 200:
            score += 0.1
            reasons.append(f"Substantial word count ({word_count} words)")
        
        # Check for quotes
        quotes = re.findall(r'"([^"]*)"', content)
        if len(quotes) > 2:
            score += 0.1
            reasons.append(f"Contains multiple quotes ({len(quotes)} quotes)")
        elif len(quotes) > 0:
            score += 0.05
            reasons.append("Contains quotes")
        
        # Check for attribution
        attribution_keywords = [
            'according to', 'said', 'stated', 'reported', 'source said',
            'told', 'confirmed', 'announced', 'revealed'
        ]
        for keyword in attribution_keywords:
            if keyword in content.lower():
                score += 0.1
                reasons.append(f"Has proper attribution: '{keyword}'")
                break
        
        # Check for statistics and data
        statistics = re.findall(r'\d+%|\d+ percent|\d+\.\d+|\d+\s*(?:million|billion|thousand)', content.lower())
        if len(statistics) > 2:
            score += 0.1
            reasons.append(f"Contains multiple statistics ({len(statistics)} stats)")
        elif statistics:
            score += 0.05
            reasons.append("Contains statistics")
        
        # Check for dates
        dates = re.findall(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}\b', content)
        if dates:
            score += 0.05
            reasons.append("Contains specific dates")
        
        # Check for paragraph structure
        paragraphs = content.split('\n\n')
        if len(paragraphs) > 3:
            score += 0.05
            reasons.append("Good paragraph structure")
        
        return {
            'score': max(0.0, min(1.0, score)),
            'reasons': reasons,
            'stats': {
                'word_count': word_count,
                'char_count': content_length,
                'paragraphs': len(paragraphs),
                'quotes': len(quotes),
                'statistics': len(statistics)
            }
        }
    
    def _check_sensationalism(self, title: str, content: str) -> Dict:
        """Check for sensationalist language"""
        text = (title + ' ' + content).lower()
        score = 0.8  # Start high
        reasons = []
        detected_keywords = []
        
        for keyword, penalty in self.sensationalist_keywords:
            if keyword in text:
                score -= penalty
                detected_keywords.append(keyword)
                reasons.append(f"Sensationalist language: '{keyword}'")
        
        # Check for excessive punctuation
        exclamation_count = title.count('!')
        question_count = title.count('?')
        
        if exclamation_count > 1:
            score -= 0.1
            reasons.append(f"Excessive exclamation marks in title ({exclamation_count})")
        if question_count > 2:
            score -= 0.1
            reasons.append(f"Excessive question marks in title ({question_count})")
        
        # Check ALL CAPS words
        words = title.split()
        caps_words = [w for w in words if w.isupper() and len(w) > 3]
        if caps_words:
            score -= 0.1
            reasons.append(f"ALL CAPS words in title: {', '.join(caps_words)}")
        
        # Check for clickbait patterns
        clickbait_patterns = [
            (r'what happens next', 0.2), (r'you won\'t believe', 0.2),
            (r'this is what', 0.1), (r'here\'s why', 0.1),
            (r'the reason why', 0.1), (r'number \d+ will shock', 0.2),
            (r'doctors hate this', 0.3), (r'one weird trick', 0.3)
        ]
        
        for pattern, penalty in clickbait_patterns:
            if re.search(pattern, text):
                score -= penalty
                reasons.append(f"Clickbait pattern: '{pattern}'")
        
        # Check for emotional language
        emotional_words = ['heartbreaking', 'devastating', 'miraculous', 'horrifying',
                          'terrifying', 'incredible', 'amazing', 'epic', 'legendary']
        emotional_count = sum(1 for word in emotional_words if word in text)
        if emotional_count > 3:
            score -= 0.1
            reasons.append(f"Excessive emotional language ({emotional_count} words)")
        
        return {
            'score': max(0.0, min(1.0, score)),
            'reasons': reasons,
            'detected_keywords': detected_keywords[:5]
        }
    
    def _analyze_language(self, text: str) -> Dict:
        """Analyze language for emotional content and bias"""
        score = 0.6
        reasons = []
        
        # Sentiment analysis
        try:
            sentiment = self.sentiment_analyzer.polarity_scores(text)
            
            # Extreme sentiment can indicate bias
            if sentiment['compound'] > 0.7:
                score -= 0.1
                reasons.append("Extremely positive sentiment - possible bias")
            elif sentiment['compound'] < -0.7:
                score -= 0.1
                reasons.append("Extremely negative sentiment - possible bias")
            elif -0.2 <= sentiment['compound'] <= 0.2:
                score += 0.1
                reasons.append("Neutral sentiment - objective tone")
            
            # High emotional content
            if sentiment['pos'] > 0.4:
                score -= 0.05
                reasons.append("High positive emotional content")
            if sentiment['neg'] > 0.4:
                score -= 0.05
                reasons.append("High negative emotional content")
        except Exception as e:
            logger.error(f"Sentiment analysis error: {e}")
            sentiment = {'compound': 0, 'pos': 0, 'neg': 0, 'neu': 1}
        
        # Subjectivity analysis with TextBlob
        try:
            blob = TextBlob(text[:1000])  # Limit for performance
            subjectivity = blob.sentiment.subjectivity
            
            if subjectivity > 0.7:
                score -= 0.1
                reasons.append("Highly subjective language")
            elif subjectivity < 0.3:
                score += 0.1
                reasons.append("Objective, factual language")
        except:
            pass
        
        # Readability score (simplified Flesch-Kincaid)
        try:
            sentences = nltk.sent_tokenize(text[:1000])
            words = nltk.word_tokenize(text[:1000])
            
            if sentences and words:
                avg_words_per_sentence = len(words) / len(sentences)
                if avg_words_per_sentence > 30:
                    score -= 0.05
                    reasons.append("Very complex sentence structure")
                elif avg_words_per_sentence < 10:
                    score -= 0.05
                    reasons.append("Very simple sentence structure")
        except:
            pass
        
        return {
            'score': max(0.0, min(1.0, score)),
            'sentiment': sentiment,
            'reasons': reasons
        }
    
    def _check_external_sources(self, title: str) -> Dict:
        """Check external fact-checking sources"""
        score = 0.5
        reasons = []
        fact_checks = []
        
        # Check cache first
        cache_key = f'fact_check_{hashlib.md5(title.encode()).hexdigest()}'
        cached_result = cache.get(cache_key)
        
        if cached_result:
            return cached_result
        
        # Simplified check - in production, you'd use APIs
        # For now, we'll just note that external check is not implemented
        
        reasons.append("External fact-checking not configured")
        
        result = {
            'score': score,
            'reasons': reasons,
            'fact_checks': fact_checks
        }
        
        # Cache the result
        cache.set(cache_key, result, self.cache_timeout)
        
        return result
    
    def _check_consistency(self, title: str, content: str, url: str) -> Dict:
        """Check for internal consistency"""
        score = 0.7
        reasons = []
        
        # Check if title appears in content
        title_words = set(title.lower().split())
        content_lower = content.lower()
        
        # Remove common stopwords for better matching
        stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
                    'of', 'with', 'by', 'from', 'as', 'is', 'was', 'were', 'has', 'have'}
        title_words = {w for w in title_words if w not in stopwords and len(w) > 2}
        
        if title_words:
            title_in_content = sum(1 for word in title_words if word in content_lower)
            title_coverage = title_in_content / len(title_words)
            
            if title_coverage < 0.3:
                score -= 0.2
                reasons.append(f"Title not well represented in content (only {title_coverage:.0%} match)")
            elif title_coverage < 0.5:
                score -= 0.1
                reasons.append(f"Title partially represented in content ({title_coverage:.0%} match)")
            else:
                score += 0.1
                reasons.append(f"Title well represented in content ({title_coverage:.0%} match)")
        
        # Check for date consistency
        current_year = timezone.now().year
        years_mentioned = re.findall(r'\b20\d{2}\b', content)
        future_years = [y for y in years_mentioned if int(y) > current_year + 1]
        if future_years:
            score -= 0.1
            reasons.append(f"Future dates mentioned: {', '.join(future_years)}")
        
        # Check for contradictory statements (simplified)
        contradiction_pairs = [
            ('true', 'false'), ('yes', 'no'), ('accept', 'reject'),
            ('support', 'oppose'), ('increase', 'decrease'), ('rise', 'fall'),
            ('confirm', 'deny'), ('approve', 'reject'), ('win', 'lose')
        ]
        
        contradictions = 0
        for word1, word2 in contradiction_pairs:
            if word1 in content_lower and word2 in content_lower:
                if abs(content_lower.index(word1) - content_lower.index(word2)) < 500:
                    contradictions += 1
        
        if contradictions > 2:
            score -= 0.1
            reasons.append(f"Potential contradictory statements detected ({contradictions} pairs)")
        
        return {
            'score': max(0.0, min(1.0, score)),
            'reasons': reasons
        }
    
    def _check_duplicates(self, title: str, content: str) -> Dict:
        """Check for duplicate or very similar content"""
        from .models import Post
        
        score = 1.0
        reasons = []
        similar_posts = []
        
        # Create content hash
        content_hash = hashlib.md5(content.encode()).hexdigest()
        
        # Look for similar posts in last 30 days
        time_threshold = timezone.now() - timedelta(days=30)
        
        # Search by title similarity
        title_words = set(title.lower().split())
        stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
                    'of', 'with', 'by', 'from', 'as', 'is', 'was', 'were', 'has', 'have'}
        title_keywords = {w for w in title_words if w not in stopwords and len(w) > 3}
        
        if title_keywords:
            # Find posts with similar keywords
            similar_posts_qs = Post.objects.filter(
                status='published',
                created_at__gte=time_threshold
            ).exclude(id=0)  # Will filter later
            
            for post in similar_posts_qs[:20]:
                post_title_words = set(post.title.lower().split())
                post_keywords = {w for w in post_title_words if w not in stopwords and len(w) > 3}
                
                if title_keywords and post_keywords:
                    # Calculate Jaccard similarity
                    intersection = title_keywords.intersection(post_keywords)
                    union = title_keywords.union(post_keywords)
                    similarity = len(intersection) / len(union) if union else 0
                    
                    if similarity > 0.7:
                        score -= 0.3
                        similar_posts.append({
                            'id': post.id,
                            'title': post.title,
                            'similarity': round(similarity, 2)
                        })
                        reasons.append(f"Very similar to existing post: {post.title[:50]}")
                    elif similarity > 0.5:
                        score -= 0.1
                        similar_posts.append({
                            'id': post.id,
                            'title': post.title,
                            'similarity': round(similarity, 2)
                        })
                        reasons.append(f"Similar to existing post: {post.title[:50]}")
        
        return {
            'score': max(0.0, min(1.0, score)),
            'reasons': reasons,
            'similar_posts': similar_posts[:3]
        }
    
    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc or parsed.path
            # Remove www.
            domain = domain.replace('www.', '')
            # Remove port if present
            domain = domain.split(':')[0]
            return domain.lower()
        except:
            return url.lower()
    
    def _get_domain_age(self, domain: str) -> Optional[int]:
        """Get domain age in days (using cache)"""
        cache_key = f'domain_age_{domain}'
        age = cache.get(cache_key)
        
        if age is not None:
            return age
        
        # Try WHOIS lookup
        try:
            import whois
            w = whois.whois(domain)
            if w.creation_date:
                if isinstance(w.creation_date, list):
                    creation_date = w.creation_date[0]
                else:
                    creation_date = w.creation_date
                
                if isinstance(creation_date, datetime):
                    age = (datetime.now() - creation_date).days
                    # Cache for 1 week (domain age doesn't change often)
                    cache.set(cache_key, age, 604800)
                    return age
        except:
            pass
        
        # If WHOIS fails, return None
        return None
    
    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Calculate Levenshtein distance between two strings"""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)
        
        if len(s2) == 0:
            return len(s1)
        
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1]
    
    def verify_batch(self, articles: List[Dict]) -> List[Dict]:
        """Verify multiple articles"""
        results = []
        for article in articles:
            try:
                result = self.verify_article(article)
                article['verification'] = result
                results.append(article)
            except Exception as e:
                logger.error(f"Error verifying article: {e}")
                article['verification'] = {
                    'overall_score': 0.0,
                    'status': 'pending',
                    'error': str(e),
                    'verified_at': timezone.now().isoformat()
                }
                results.append(article)
        
        return results


# Helper function to integrate with admin workflow
def process_news_submission(post):
    """Process a news submission through AI verification"""
    from .models import SystemSettings
    
    verifier = EnhancedNewsVerifier()
    
    article = {
        'title': post.title,
        'content': post.content,
        'url': post.external_url or '',
        'source': post.external_source or ''
    }
    
    verification_result = verifier.verify_article(article)
    
    # Update post with verification results
    post.verification_score = verification_result['overall_score']
    post.verification_status = verification_result['status']
    post.verification_details = verification_result
    post.verification_method = 'ai_assisted'
    
    # Check for auto-approval based on system settings
    settings = SystemSettings.objects.first()
    auto_approve_threshold = settings.auto_approve_threshold if settings else 0.8
    
    if verification_result['overall_score'] >= auto_approve_threshold:
        post.submission_status = 'approved'
        post.status = 'published'
        post.save()
        
        from .models import Notification, UserActivity
        Notification.objects.create(
            user=post.author,
            notification_type='news_approved',
            message=f'Your news article "{post.title}" has been automatically approved (AI score: {verification_result["overall_score"]})',
            post=post
        )
        
        UserActivity.objects.create(
            user=post.author,
            activity_type='news_approved',
            post=post,
            details={'auto_approved': True, 'score': verification_result['overall_score']}
        )
        
    elif verification_result['overall_score'] < 0.3:
        # Auto-reject very low quality submissions
        post.submission_status = 'rejected'
        post.status = 'draft'
        post.rejection_reason = f'AI verification indicates this may not be legitimate news (score: {verification_result["overall_score"]})'
        post.save()
        
        from .models import Notification
        Notification.objects.create(
            user=post.author,
            notification_type='news_rejected',
            message=f'Your news article "{post.title}" was automatically rejected (AI score: {verification_result["overall_score"]})',
            post=post
        )
    else:
        post.save()
    
    return post


# Function to verify existing posts
def verify_existing_posts():
    """Run verification on existing unverified news posts"""
    from .models import Post
    
    unverified_posts = Post.objects.filter(
        is_news_submission=True,
        verification_status='pending'
    ).exclude(verification_status='verified')[:50]
    
    verifier = EnhancedNewsVerifier()
    results = []
    
    for post in unverified_posts:
        try:
            article = {
                'title': post.title,
                'content': post.content,
                'url': post.external_url or '',
                'source': post.external_source or ''
            }
            
            result = verifier.verify_article(article)
            post.verification_score = result['overall_score']
            post.verification_status = result['status']
            post.verification_details = result
            post.save()
            
            results.append({
                'id': post.id,
                'title': post.title,
                'score': result['overall_score'],
                'status': result['status']
            })
        except Exception as e:
            logger.error(f"Error verifying post {post.id}: {e}")
    
    return results