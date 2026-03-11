"""
Social Media Fetcher Service
Fetches posts from X/Twitter, Instagram, and Facebook for rugby teams
⚠️ Requires API access and authentication
"""

import logging
import os
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import requests

logger = logging.getLogger(__name__)


class SocialMediaFetcher:
    """Fetches social media posts from various platforms"""
    
    def __init__(self):
        # Twitter/X API v2 (requires Bearer Token)
        self.twitter_bearer_token = os.getenv("TWITTER_BEARER_TOKEN", "")
        self.twitter_api_key = os.getenv("TWITTER_API_KEY", "")
        self.twitter_api_secret = os.getenv("TWITTER_API_SECRET", "")
        
        # Instagram Graph API (requires Facebook App)
        self.instagram_access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
        self.facebook_app_id = os.getenv("FACEBOOK_APP_ID", "")
        self.facebook_app_secret = os.getenv("FACEBOOK_APP_SECRET", "")
        
        # Facebook Graph API
        self.facebook_access_token = os.getenv("FACEBOOK_ACCESS_TOKEN", "")
    
    def fetch_twitter_posts(self, username: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch recent tweets from a Twitter/X account
        
        Requires Twitter API v2 access (paid tier may be required)
        """
        if not self.twitter_bearer_token:
            logger.warning("Twitter Bearer Token not configured")
            return []
        
        try:
            # Twitter API v2 endpoint
            url = f"https://api.twitter.com/2/tweets/search/recent"
            headers = {
                "Authorization": f"Bearer {self.twitter_bearer_token}"
            }
            
            # Get user ID first
            user_url = f"https://api.twitter.com/2/users/by/username/{username}"
            user_response = requests.get(
                user_url,
                headers=headers,
                params={"user.fields": "name,username,profile_image_url,verified"},
                timeout=10,
            )
            
            if user_response.status_code != 200:
                logger.error(f"Twitter API error: {user_response.status_code}")
                return []
            
            user_data = user_response.json()
            user_obj = user_data.get("data", {}) if isinstance(user_data, dict) else {}
            user_id = user_obj.get("id")
            author_name = user_obj.get("name") or username
            author_handle = user_obj.get("username") or username
            author_avatar = user_obj.get("profile_image_url")
            author_verified = bool(user_obj.get("verified", False))
            
            if not user_id:
                logger.warning(f"User {username} not found on Twitter")
                return []
            
            # Fetch tweets
            params = {
                "query": f"from:{username}",
                "max_results": limit,
                "tweet.fields": "created_at,public_metrics,text,attachments",
                "expansions": "attachments.media_keys",
                "media.fields": "type,url,preview_image_url,duration_ms,variants"
            }
            
            response = requests.get(url, headers=headers, params=params, timeout=10)
            
            if response.status_code != 200:
                logger.error(f"Twitter API error: {response.status_code}")
                return []
            
            data = response.json()
            tweets = []
            media_index = {}
            includes = data.get("includes", {}) if isinstance(data, dict) else {}
            for media in includes.get("media", []) if isinstance(includes, dict) else []:
                key = media.get("media_key")
                if key:
                    media_index[key] = media
            
            for tweet in data.get("data", []):
                media_items: List[Dict[str, Any]] = []
                attachments = tweet.get("attachments", {}) if isinstance(tweet, dict) else {}
                media_keys = attachments.get("media_keys", []) if isinstance(attachments, dict) else []
                for mk in media_keys:
                    m = media_index.get(mk)
                    if m:
                        media_items.append(m)

                has_video = any((m.get("type") in {"video", "animated_gif"}) for m in media_items)
                video_url = None
                image_url = None
                media_urls: List[str] = []
                video_variants: List[str] = []

                for media in media_items:
                    m_type = media.get("type")
                    if m_type == "photo":
                        u = media.get("url")
                        if u:
                            media_urls.append(u)
                            if not image_url:
                                image_url = u
                    elif m_type in {"video", "animated_gif"}:
                        variants = media.get("variants", []) if isinstance(media.get("variants"), list) else []
                        mp4_variants = [v for v in variants if isinstance(v, dict) and "video/mp4" in str(v.get("content_type", ""))]
                        if mp4_variants:
                            # Keep all MP4 variants so frontend can retry lower bitrates if needed.
                            sorted_variants = sorted(
                                mp4_variants,
                                key=lambda v: int(v.get("bit_rate", 0) or 0),
                                reverse=True,
                            )
                            for variant in sorted_variants:
                                v_url = variant.get("url")
                                if v_url and v_url not in video_variants:
                                    video_variants.append(v_url)
                                    media_urls.append(v_url)
                            if video_variants and not video_url:
                                video_url = video_variants[0]
                        preview = media.get("preview_image_url")
                        if preview and not image_url:
                            image_url = preview

                tweets.append({
                    "platform": "twitter",
                    "id": tweet.get("id"),
                    "text": tweet.get("text", ""),
                    "created_at": tweet.get("created_at"),
                    "url": f"https://twitter.com/{username}/status/{tweet.get('id')}",
                    "metrics": tweet.get("public_metrics", {}),
                    "media": media_items,
                    "is_video": has_video,
                    "video_url": video_url,
                    "video_variants": video_variants,
                    "image_url": image_url,
                    "media_urls": media_urls,
                    "author_name": author_name,
                    "author_handle": author_handle,
                    "author_avatar": author_avatar,
                    "author_verified": author_verified,
                })
            
            return tweets
            
        except Exception as e:
            logger.error(f"Error fetching Twitter posts: {e}")
            return []
    
    def fetch_instagram_posts(self, username: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch recent posts from an Instagram Business/Creator account
        
        Requires:
        - Instagram Business/Creator account
        - Facebook Page linked to Instagram account
        - Instagram Graph API access token
        - Facebook App ID and App Secret
        """
        if not self.instagram_access_token:
            logger.warning("Instagram Access Token not configured")
            return []
        
        try:
            # Step 1: Get Instagram Business Account ID from username
            # This requires the Instagram account to be linked to a Facebook Page
            search_url = f"https://graph.facebook.com/v18.0/{username}"
            params = {
                "fields": "id,username",
                "access_token": self.instagram_access_token
            }
            
            # Try to get user ID (this works if username is the Instagram Business Account ID)
            # Otherwise, we need to search via Facebook Page
            try:
                response = requests.get(search_url, params=params, timeout=10)
                if response.status_code == 200:
                    user_data = response.json()
                    ig_user_id = user_data.get("id")
                else:
                    # If direct lookup fails, try alternative method
                    logger.warning(f"Direct Instagram lookup failed, trying alternative method")
                    # You may need to use Facebook Page ID to get Instagram Business Account ID
                    ig_user_id = None
            except Exception as e:
                logger.warning(f"Error getting Instagram user ID: {e}")
                ig_user_id = None
            
            if not ig_user_id:
                # Alternative: Use username as ID if it's numeric (Instagram Business Account ID)
                if username.isdigit():
                    ig_user_id = username
                else:
                    logger.error(f"Could not find Instagram Business Account ID for {username}")
                    logger.info("Note: Instagram username must be the Business Account ID, or linked via Facebook Page")
                    return []
            
            # Step 2: Get media (posts) from Instagram Business Account
            media_url = f"https://graph.facebook.com/v18.0/{ig_user_id}/media"
            media_params = {
                "fields": "id,caption,media_type,media_url,permalink,thumbnail_url,timestamp,like_count,comments_count",
                "limit": limit,
                "access_token": self.instagram_access_token
            }
            
            response = requests.get(media_url, params=media_params, timeout=10)
            
            if response.status_code != 200:
                error_data = response.json() if response.content else {}
                logger.error(f"Instagram API error {response.status_code}: {error_data}")
                return []
            
            data = response.json()
            posts = []
            
            for item in data.get("data", []):
                # Extract caption (first 200 chars)
                caption = item.get("caption", "")
                if len(caption) > 200:
                    caption = caption[:200] + "..."
                
                posts.append({
                    "platform": "instagram",
                    "id": item.get("id"),
                    "text": caption,
                    "media_type": item.get("media_type", "IMAGE"),  # IMAGE, VIDEO, CAROUSEL_ALBUM
                    "media_url": item.get("media_url") or item.get("thumbnail_url"),
                    "video_url": item.get("media_url") if item.get("media_type") == "VIDEO" else None,
                    "image_url": item.get("media_url") if item.get("media_type") in {"IMAGE", "CAROUSEL_ALBUM"} else item.get("thumbnail_url"),
                    "created_at": item.get("timestamp"),
                    "url": item.get("permalink", f"https://www.instagram.com/p/{item.get('id', '')}/"),
                    "metrics": {
                        "likes": item.get("like_count", 0),
                        "comments": item.get("comments_count", 0)
                    }
                })
            
            logger.info(f"Fetched {len(posts)} Instagram posts for {username}")
            return posts
            
        except Exception as e:
            logger.error(f"Error fetching Instagram posts: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def fetch_facebook_posts(self, page_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch recent posts from a Facebook Page
        
        Requires Facebook Graph API access
        """
        if not self.facebook_access_token:
            logger.warning("Facebook Access Token not configured")
            return []
        
        try:
            url = f"https://graph.facebook.com/v18.0/{page_id}/posts"
            params = {
                "access_token": self.facebook_access_token,
                "fields": "id,message,created_time,permalink_url",
                "limit": limit
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code != 200:
                logger.error(f"Facebook API error: {response.status_code}")
                return []
            
            data = response.json()
            posts = []
            
            for post in data.get("data", []):
                posts.append({
                    "platform": "facebook",
                    "id": post.get("id"),
                    "message": post.get("message", ""),
                    "created_at": post.get("created_time"),
                    "url": post.get("permalink_url")
                })
            
            return posts
            
        except Exception as e:
            logger.error(f"Error fetching Facebook posts: {e}")
            return []
    
    def fetch_team_social_posts(self, team_name: str, social_handles: Dict[str, str], 
                                limit_per_platform: int = 5) -> List[Dict[str, Any]]:
        """Fetch posts from all social media platforms for a team
        
        Args:
            team_name: Name of the team
            social_handles: Dict with keys 'twitter', 'instagram', 'facebook'
            limit_per_platform: Number of posts to fetch per platform
        """
        all_posts = []
        
        # Twitter/X
        if "twitter" in social_handles:
            twitter_posts = self.fetch_twitter_posts(
                social_handles["twitter"], 
                limit=limit_per_platform
            )
            all_posts.extend(twitter_posts)
        
        # Instagram
        if "instagram" in social_handles:
            instagram_posts = self.fetch_instagram_posts(
                social_handles["instagram"],
                limit=limit_per_platform
            )
            all_posts.extend(instagram_posts)
        
        # Facebook
        if "facebook" in social_handles:
            facebook_posts = self.fetch_facebook_posts(
                social_handles["facebook"],
                limit=limit_per_platform
            )
            all_posts.extend(facebook_posts)
        
        # Sort by date (newest first)
        all_posts.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
        return all_posts


# Team social media handles mapping
# You can add your teams' social media accounts here
TEAM_SOCIAL_HANDLES = {
    "Leicester Tigers": {
        "twitter": "LeicesterTigers",
        "instagram": "leicestertigers",
        "facebook": "LeicesterTigers"
    },
    "Bath Rugby": {
        "twitter": "bathrugby",
        "instagram": "bathrugby",
        "facebook": "BathRugby"
    },
    # URC and common aliases
    "Leinster": {"twitter": "leinsterrugby"},
    "Leinster Rugby": {"twitter": "leinsterrugby"},
    "Munster": {"twitter": "Munsterrugby"},
    "Munster Rugby": {"twitter": "Munsterrugby"},
    "Ulster": {"twitter": "UlsterRugby"},
    "Ulster Rugby": {"twitter": "UlsterRugby"},
    "Connacht": {"twitter": "connachtrugby"},
    "Connacht Rugby": {"twitter": "connachtrugby"},
    "Glasgow": {"twitter": "GlasgowWarriors"},
    "Glasgow Warriors": {"twitter": "GlasgowWarriors"},
    "Edinburgh": {"twitter": "EdinburghRugby"},
    "Edinburgh Rugby": {"twitter": "EdinburghRugby"},
    "Ospreys": {"twitter": "ospreys"},
    "Scarlets": {"twitter": "scarlets_rugby"},
    "Cardiff Rugby": {"twitter": "Cardiff_Rugby"},
    "Cardiff Blues": {"twitter": "Cardiff_Rugby"},
    "Dragons": {"twitter": "dragonsrugby"},
    "Newport Gwent Dragons": {"twitter": "dragonsrugby"},
    "Benetton": {"twitter": "BenettonRugby"},
    "Benetton Treviso": {"twitter": "BenettonRugby"},
    "Benneton": {"twitter": "BenettonRugby"},
    "Zebre": {"twitter": "ZebreParma"},
    "Zebre Rugby": {"twitter": "ZebreParma"},
    "Bulls": {"twitter": "BlueBullsRugby"},
    "Blue Bulls": {"twitter": "BlueBullsRugby"},
    "The Sharks": {"twitter": "SharksRugby"},
    "Stormers": {"twitter": "THESTORMERS"},
    "Lions": {"twitter": "LionsRugbyCo"},
    "Lions Super Rugby": {"twitter": "LionsRugbyCo"},
    # Add more teams as needed
    # Format: "Team Name": {"twitter": "handle", "instagram": "handle", "facebook": "page_id"}
}

