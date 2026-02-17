# core/news_verifier.py

import requests
import re
import json
import time
from typing import Dict, List, Optional
from django.conf import settings
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class NewsVerifier:
    """Verify news articles for authenticity"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
    def verify_article(self, article: Dict) -> Dict:
        """Verify a single article"""
        try:
            title = article.get('title', '')
            content = article.get('content', '')
            url = article.get('url', '')
            source = article.get('source', '')
            
            if not title or not url:
                return {
                    'score': 0.0,
                    'status': 'fake',
                    'details': {'error': 'Missing title or URL'}
                }
            
            # Initialize scores
            scores = []
            details = {}
            
            # 1. Check source credibility
            source_score = self._check_source_credibility(source)
            scores.append(source_score['score'])
            details['source_check'] = source_score
            
            # 2. Check URL credibility
            url_score = self._check_url_credibility(url)
            scores.append(url_score['score'])
            details['url_check'] = url_score
            
            # 3. Check content for red flags
            content_score = self._check_content_red_flags(title + ' ' + content)
            scores.append(content_score['score'])
            details['content_check'] = content_score
            
            # 4. Check for clickbait patterns
            clickbait_score = self._check_clickbait(title)
            scores.append(clickbait_score['score'])
            details['clickbait_check'] = clickbait_score
            
            # 5. Check external verification (if enabled)
            if getattr(settings, 'ENABLE_EXTERNAL_VERIFICATION', False):
                external_score = self._external_verification(title, url)
                scores.append(external_score['score'])
                details['external_check'] = external_score
            
            # Calculate average score
            avg_score = sum(scores) / len(scores)
            
            # Determine status
            if avg_score >= 0.7:
                status = 'verified'
            elif avg_score >= 0.4:
                status = 'pending'
            else:
                status = 'fake'
            
            return {
                'score': avg_score,
                'status': status,
                'details': details,
                'verification_time': timezone.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error verifying article: {e}")
            return {
                'score': 0.0,
                'status': 'pending',
                'details': {'error': str(e)}
            }
    
    def _check_source_credibility(self, source: str) -> Dict:
        """Check if source is credible"""
        credible_sources = [
            'premiumtimesng.com', 'punchng.com', 'vanguardngr.com',
            'guardian.ng', 'thisdaylive.com', 'thenationonlineng.net',
            'bbc.com', 'reuters.com', 'aljazeera.com', 'cnn.com'
        ]
        
        source_lower = source.lower()
        score = 0.5  # Default neutral score
        
        for credible in credible_sources:
            if credible in source_lower:
                score = 0.9
                break
        
        # Check for known fake news sources
        fake_sources = ['fakenews', 'satire', 'parody', 'theonion', 'clickhole']
        for fake in fake_sources:
            if fake in source_lower:
                score = 0.1
                break
        
        return {
            'score': score,
            'is_credible': score > 0.7,
            'reason': f"Source credibility check: {source}"
        }
    
    def _check_url_credibility(self, url: str) -> Dict:
        """Check URL for credibility indicators"""
        if not url:
            return {'score': 0.0, 'reason': 'No URL provided'}
        
        score = 0.5
        reasons = []
        
        # Check for suspicious URL patterns
        suspicious_patterns = [
            r'\d{10}',  # Random numbers
            r'bit\.ly|tinyurl|goo\.gl',  # URL shorteners
            r'free-?money|win-?prize|click-?here',  # Scam indicators
        ]
        
        for pattern in suspicious_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                score -= 0.2
                reasons.append(f"Suspicious pattern found: {pattern}")
        
        # Check for HTTPS
        if url.startswith('https://'):
            score += 0.1
            reasons.append("Uses HTTPS")
        else:
            score -= 0.1
            reasons.append("Does not use HTTPS")
        
        # Ensure score is between 0 and 1
        score = max(0.1, min(1.0, score))
        
        return {
            'score': score,
            'reasons': reasons
        }
    
    def _check_content_red_flags(self, text: str) -> Dict:
        """Check content for fake news red flags"""
        if not text:
            return {'score': 0.5, 'reasons': ['No content to analyze']}
        
        text_lower = text.lower()
        score = 0.7  # Start with neutral-positive
        red_flags = []
        green_flags = []
        
        # Red flags
        red_flag_patterns = [
            (r'100% guaranteed|guaranteed results', 0.3),
            (r'miracle cure|secret remedy', 0.4),
            (r'government is hiding|they don\'t want you to know', 0.3),
            (r'shocking|you won\'t believe|mind-blowing', 0.2),
            (r'click here|subscribe now|limited time offer', 0.2),
            (r'all doctors hate this|big pharma conspiracy', 0.4),
        ]
        
        for pattern, penalty in red_flag_patterns:
            if re.search(pattern, text_lower):
                score -= penalty
                red_flags.append(pattern)
        
        # Green flags (indicators of credible content)
        green_flag_patterns = [
            (r'sources? said|according to', 0.1),
            (r'study shows|research indicates', 0.1),
            (r'officials? confirmed|authorities said', 0.1),
            (r'in an interview|spokesperson said', 0.1),
        ]
        
        for pattern, bonus in green_flag_patterns:
            if re.search(pattern, text_lower):
                score += bonus
                green_flags.append(pattern)
        
        # Check for excessive punctuation (clickbait)
        if text.count('!') > 3 or text.count('?') > 5:
            score -= 0.2
            red_flags.append("Excessive punctuation")
        
        # Check for all caps (sensationalism)
        words = text.split()
        caps_words = [w for w in words if w.isupper() and len(w) > 2]
        if len(caps_words) > 3:
            score -= 0.2
            red_flags.append("Excessive ALL CAPS")
        
        # Ensure score is within bounds
        score = max(0.1, min(1.0, score))
        
        return {
            'score': score,
            'red_flags': red_flags,
            'green_flags': green_flags
        }
    
    def _check_clickbait(self, title: str) -> Dict:
        """Check if title is clickbait"""
        if not title:
            return {'score': 0.5, 'is_clickbait': False}
        
        title_lower = title.lower()
        clickbait_patterns = [
            r'you won\'t believe what happened next',
            r'this (?:will|is going to) blow your mind',
            r'the secret (?:they|doctors) don\'t want you to know',
            r'number \d+ will shock you',
            r'what happens next is (?:shocking|amazing)',
            r'can you spot the.*\?',
            r'these \d+ things',
            r'before (?:and|vs) after',
        ]
        
        is_clickbait = False
        for pattern in clickbait_patterns:
            if re.search(pattern, title_lower):
                is_clickbait = True
                break
        
        # Check for listicles and questions
        if title.startswith(('Top ', '10 ', '5 ', '7 ', 'This is ', 'How to ')):
            is_clickbait = True
        
        if title.endswith('?'):
            is_clickbait = True
        
        score = 0.3 if is_clickbait else 0.8
        
        return {
            'score': score,
            'is_clickbait': is_clickbait,
            'patterns_found': clickbait_patterns if is_clickbait else []
        }
    
    def _external_verification(self, title: str, url: str) -> Dict:
        """External verification using fact-checking APIs"""
        return {
            'score': 0.5,
            'method': 'external_api',
            'note': 'External verification not configured'
        }
    
    def verify_batch(self, articles: List[Dict]) -> List[Dict]:
        """Verify multiple articles"""
        results = []
        for article in articles:
            result = self.verify_article(article)
            article['verification'] = result
            results.append(article)
            
            # Rate limiting
            time.sleep(0.1)
        
        return results