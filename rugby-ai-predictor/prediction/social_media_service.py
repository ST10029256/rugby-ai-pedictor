"""
Social Media Embed Service
Handles embedding of Instagram, X/Twitter, and YouTube content
⚠️ IMPORTANT: We embed, never rehost content to avoid copyright issues
"""

import logging
import re
from typing import Dict, Optional, Any
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)


class SocialMediaService:
    """Service for handling social media embeds"""
    
    @staticmethod
    def parse_instagram_url(url: str) -> Optional[Dict[str, Any]]:
        """Parse Instagram URL and return embed info
        
        Supports:
        - https://www.instagram.com/p/{shortcode}/
        - https://www.instagram.com/reel/{shortcode}/
        """
        try:
            parsed = urlparse(url)
            if 'instagram.com' not in parsed.netloc:
                return None
            
            # Extract shortcode from path
            path_parts = [p for p in parsed.path.split('/') if p]
            if len(path_parts) >= 2:
                post_type = path_parts[0]  # 'p' or 'reel'
                shortcode = path_parts[1]
                
                return {
                    "platform": "instagram",
                    "type": "post" if post_type == "p" else "reel",
                    "shortcode": shortcode,
                    "url": url,
                    "embed_url": f"https://www.instagram.com/{post_type}/{shortcode}/embed/"
                }
        except Exception as e:
            logger.error(f"Error parsing Instagram URL: {e}")
        return None
    
    @staticmethod
    def parse_twitter_url(url: str) -> Optional[Dict[str, Any]]:
        """Parse X/Twitter URL and return embed info
        
        Supports:
        - https://twitter.com/{username}/status/{tweet_id}
        - https://x.com/{username}/status/{tweet_id}
        """
        try:
            parsed = urlparse(url)
            if 'twitter.com' not in parsed.netloc and 'x.com' not in parsed.netloc:
                return None
            
            path_parts = [p for p in parsed.path.split('/') if p]
            if len(path_parts) >= 3 and path_parts[1] == 'status':
                username = path_parts[0]
                tweet_id = path_parts[2]
                
                return {
                    "platform": "twitter",
                    "username": username,
                    "tweet_id": tweet_id,
                    "url": url,
                    "embed_url": f"https://platform.twitter.com/embed/Tweet.html?id={tweet_id}"
                }
        except Exception as e:
            logger.error(f"Error parsing Twitter URL: {e}")
        return None
    
    @staticmethod
    def parse_youtube_url(url: str) -> Optional[Dict[str, Any]]:
        """Parse YouTube URL and return embed info
        
        Supports:
        - https://www.youtube.com/watch?v={video_id}
        - https://youtu.be/{video_id}
        - https://www.youtube.com/embed/{video_id}
        """
        try:
            parsed = urlparse(url)
            
            # Standard watch URL
            if 'youtube.com' in parsed.netloc and '/watch' in parsed.path:
                video_id = parse_qs(parsed.query).get('v', [None])[0]
                if video_id:
                    return {
                        "platform": "youtube",
                        "video_id": video_id,
                        "url": url,
                        "embed_url": f"https://www.youtube.com/embed/{video_id}"
                    }
            
            # Short URL
            elif 'youtu.be' in parsed.netloc:
                video_id = parsed.path.lstrip('/')
                if video_id:
                    return {
                        "platform": "youtube",
                        "video_id": video_id,
                        "url": url,
                        "embed_url": f"https://www.youtube.com/embed/{video_id}"
                    }
            
            # Embed URL
            elif 'youtube.com' in parsed.netloc and '/embed/' in parsed.path:
                video_id = parsed.path.split('/embed/')[-1]
                return {
                    "platform": "youtube",
                    "video_id": video_id,
                    "url": url,
                    "embed_url": f"https://www.youtube.com/embed/{video_id}"
                }
        except Exception as e:
            logger.error(f"Error parsing YouTube URL: {e}")
        return None
    
    @staticmethod
    def parse_social_url(url: str) -> Optional[Dict[str, Any]]:
        """Parse any social media URL and return embed info"""
        # Try each platform
        for parser in [
            SocialMediaService.parse_instagram_url,
            SocialMediaService.parse_twitter_url,
            SocialMediaService.parse_youtube_url
        ]:
            result = parser(url)
            if result:
                return result
        return None
    
    @staticmethod
    def create_embed_object(url: str, context: Optional[str] = None, 
                           ai_explanation: Optional[str] = None) -> Dict[str, Any]:
        """Create embed object for social media content"""
        embed_info = SocialMediaService.parse_social_url(url)
        if not embed_info:
            return {
                "type": "unsupported",
                "url": url,
                "error": "Unsupported social media platform"
            }
        
        return {
            "type": "embed",
            "platform": embed_info["platform"],
            "url": url,
            "embed_url": embed_info.get("embed_url"),
            "context": context,  # e.g., "Team lineup announcement"
            "ai_explanation": ai_explanation,  # AI-generated explanation of why this matters
            **embed_info
        }
    
    @staticmethod
    def extract_team_mentions(text: str, team_names: list) -> list:
        """Extract team mentions from text"""
        mentions = []
        text_lower = text.lower()
        for team in team_names:
            if team.lower() in text_lower:
                mentions.append(team)
        return mentions
    
    @staticmethod
    def generate_ai_explanation(embed_type: str, context: str, 
                               related_data: Optional[Dict[str, Any]] = None) -> str:
        """Generate AI explanation for why embedded content matters"""
        explanations = {
            "lineup": "This lineup announcement affects our win probability calculations. Key players in or out can shift predictions significantly.",
            "injury": "Injury updates directly impact team strength ratings and match predictions.",
            "announcement": "Official team announcements provide the latest information for accurate predictions.",
            "highlight": "Recent match highlights show current form and team performance trends."
        }
        
        base_explanation = explanations.get(context.lower(), "This content provides important context for match predictions.")
        
        if related_data:
            if 'win_prob_change' in related_data:
                change = related_data['win_prob_change']
                if abs(change) > 0.05:
                    base_explanation += f" This update shifts win probability by {change*100:+.1f}%."
        
        return base_explanation

