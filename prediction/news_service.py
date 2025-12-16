"""
AI-Generated News Service for Rugby
Generates interactive, data-driven news content based on match data, lineups, and predictions
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import sqlite3

logger = logging.getLogger(__name__)


@dataclass
class NewsItem:
    """Represents a single news item"""
    id: str
    type: str  # 'match_preview', 'lineup_change', 'injury_update', 'selection_surprise', 'form_analysis', 'prediction_shift', 'external_news'
    title: str
    content: str
    timestamp: str
    league_id: Optional[int] = None
    match_id: Optional[int] = None
    team_id: Optional[int] = None
    player_id: Optional[int] = None
    impact_score: Optional[float] = None  # -1.0 to 1.0, how much this affects predictions
    win_probability_change: Optional[float] = None  # Change in win probability
    related_stats: Optional[Dict[str, Any]] = None
    embedded_content: Optional[Dict[str, Any]] = None  # Instagram/X/YouTube embeds
    clickable_stats: Optional[List[Dict[str, str]]] = None  # Stats with explanations
    source_url: Optional[str] = None  # URL to original news source
    image_url: Optional[str] = None  # News image/thumbnail
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class NewsService:
    """Service for generating AI-powered rugby news"""
    
    def __init__(self, db_path: str, predictor=None, sportdevs_client=None, sportsdb_client=None, social_media_fetcher=None):
        self.db_path = db_path
        self.predictor = predictor
        self.sportdevs_client = sportdevs_client
        self.sportsdb_client = sportsdb_client
        self.social_media_fetcher = social_media_fetcher
    
    def _get_db_connection(self) -> sqlite3.Connection:
        """Get database connection"""
        return sqlite3.connect(self.db_path)
    
    def fetch_external_news(self, league_id: Optional[int] = None, 
                           team_id: Optional[int] = None,
                           limit: int = 20) -> List[NewsItem]:
        """Fetch external news from SportDevs API and convert to NewsItems"""
        news_items = []
        
        if not self.sportdevs_client:
            logger.warning("SportDevs client not available, skipping external news")
            return news_items
        
        try:
            # Fetch news from SportDevs
            if team_id:
                external_news = self.sportdevs_client.get_team_news(team_id, limit=limit)
            elif league_id:
                external_news = self.sportdevs_client.get_league_news(league_id, limit=limit)
            else:
                external_news = self.sportdevs_client.get_all_news(limit=limit)
            
            # Convert to NewsItems
            for item in external_news:
                try:
                    news_item = NewsItem(
                        id=f"external_{item.get('id', hash(str(item)))}",
                        type="external_news",
                        title=item.get('title', item.get('headline', 'Rugby News')),
                        content=item.get('content', item.get('description', '')),
                        timestamp=item.get('published_at', item.get('date', datetime.now().isoformat())),
                        league_id=item.get('league_id'),
                        team_id=item.get('team_id'),
                        source_url=item.get('url', item.get('link')),
                        image_url=item.get('image', item.get('thumbnail')),
                    )
                    news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error converting external news item: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error fetching external news: {e}")
        
        return news_items
    
    def fetch_social_media_news(self, followed_teams: Optional[List[int]] = None,
                                limit: int = 10) -> List[NewsItem]:
        """Fetch social media posts from X/Instagram/Facebook and convert to NewsItems"""
        news_items = []
        
        if not self.social_media_fetcher:
            logger.warning("Social media fetcher not available, skipping social media news")
            return news_items
        
        try:
            from prediction.social_media_fetcher import SocialMediaFetcher, TEAM_SOCIAL_HANDLES
            from prediction.social_media_service import SocialMediaService
            
            conn = self._get_db_connection()
            cursor = conn.cursor()
            
            # Get team names for followed teams
            team_names = []
            if followed_teams:
                placeholders = ','.join(['?'] * len(followed_teams))
                cursor.execute(f"""
                    SELECT id, name FROM team WHERE id IN ({placeholders})
                """, followed_teams)
                team_names = {row[1]: row[0] for row in cursor.fetchall()}
            
            # Fetch posts for each team
            for team_name, team_id in team_names.items():
                if team_name not in TEAM_SOCIAL_HANDLES:
                    continue
                
                social_handles = TEAM_SOCIAL_HANDLES[team_name]
                posts = self.social_media_fetcher.fetch_team_social_posts(
                    team_name, social_handles, limit_per_platform=3
                )
                
                # Convert posts to NewsItems
                for post in posts[:limit]:
                    try:
                        # Parse URL to create embed
                        embed_obj = SocialMediaService.create_embed_object(
                            url=post.get("url", ""),
                            context="team_update",
                            ai_explanation=SocialMediaService.generate_ai_explanation(
                                embed_type=post.get("platform", ""),
                                context="announcement",
                                related_data={"team": team_name}
                            )
                        )
                        
                        # Extract text content
                        text = post.get("text") or post.get("message", "")
                        if len(text) > 200:
                            text = text[:200] + "..."
                        
                        news_item = NewsItem(
                            id=f"social_{post.get('platform')}_{post.get('id', hash(str(post)))}",
                            type="social_media",
                            title=f"{team_name} - {post.get('platform', 'Social Media').title()} Update",
                            content=text,
                            timestamp=post.get("created_at", datetime.now().isoformat()),
                            team_id=team_id,
                            embedded_content=embed_obj if embed_obj.get("type") == "embed" else None,
                            source_url=post.get("url")
                        )
                        news_items.append(news_item)
                    except Exception as e:
                        logger.error(f"Error converting social media post: {e}")
                        continue
            
            conn.close()
            
        except Exception as e:
            logger.error(f"Error fetching social media news: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        return news_items
    
    def get_team_logo_url(self, team_id: int) -> Optional[str]:
        """Get team logo URL from TheSportsDB API"""
        if not self.sportsdb_client:
            return None
        
        try:
            # Get team details from TheSportsDB using lookup_team
            team = self.sportsdb_client.lookup_team(team_id)
            if team:
                # TheSportsDB returns logo in strTeamBadge field
                logo_url = team.get('strTeamBadge') or team.get('strTeamLogo')
                return logo_url
        except Exception as e:
            logger.error(f"Error fetching team logo for {team_id}: {e}")
        
        return None
    
    def generate_match_preview_optimized(self, match_id: int, home_team: str, away_team: str, 
                                        league_id: int, match_date: str,
                                        home_team_id: int, away_team_id: int,
                                        home_form: List[tuple], away_form: List[tuple]) -> Optional[NewsItem]:
        """Generate AI match preview news (optimized version with pre-fetched form data)"""
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            
            # Get match details (minimal query)
            cursor.execute("""
                SELECT e.id, e.date_event, e.venue,
                       t1.name as home_team_name, t2.name as away_team_name
                FROM event e
                LEFT JOIN team t1 ON e.home_team_id = t1.id
                LEFT JOIN team t2 ON e.away_team_id = t2.id
                WHERE e.id = ?
            """, (match_id,))
            
            match = cursor.fetchone()
            if not match:
                return None
            
            # Skip logo fetching for performance (can be added later if needed)
            home_logo = None
            away_logo = None
            
            # Get head-to-head (only if needed)
            h2h = []
            if home_team_id and away_team_id:
                h2h = self._get_head_to_head(cursor, home_team_id, away_team_id, limit=3)  # Reduced from 5
            
            # Skip prediction generation for performance (use form-based calculation)
            prediction = None
            home_prob = 0.5  # Default probability
            
            # Generate AI content
            # EXTENSIVE LOGGING for win rate calculation
            logger.info(f"=== WIN RATE CALCULATION DEBUG for {home_team} vs {away_team} ===")
            logger.info(f"Match ID: {match_id}, League ID: {league_id}")
            logger.info(f"Home Team ID: {home_team_id}, Away Team ID: {away_team_id}")
            
            # Calculate win rates correctly - handle empty form and ensure proper calculation
            if home_form and len(home_form) > 0:
                logger.info(f"📊 HOME TEAM ({home_team}) FORM DATA: {len(home_form)} games")
                for idx, (team_score, opp_score) in enumerate(home_form, 1):
                    is_win = team_score > opp_score
                    is_draw = team_score == opp_score
                    result = "WIN" if is_win else ("DRAW" if is_draw else "LOSS")
                    logger.info(f"  Game {idx}: {team_score}-{opp_score} ({result})")
                
                home_wins = sum(1 for r in home_form if r[0] > r[1])
                home_draws = sum(1 for r in home_form if r[0] == r[1])
                home_losses = len(home_form) - home_wins - home_draws
                home_win_rate = home_wins / len(home_form)
                logger.info(f"✅ HOME WIN RATE: {home_wins}W/{home_draws}D/{home_losses}L = {home_win_rate*100:.1f}%")
            else:
                home_win_rate = 0.0  # No data = 0%, not 50%
                logger.warning(f"⚠️ HOME TEAM ({home_team}): NO FORM DATA - Setting win rate to 0%")
            
            if away_form and len(away_form) > 0:
                logger.info(f"📊 AWAY TEAM ({away_team}) FORM DATA: {len(away_form)} games")
                for idx, (team_score, opp_score) in enumerate(away_form, 1):
                    is_win = team_score > opp_score
                    is_draw = team_score == opp_score
                    result = "WIN" if is_win else ("DRAW" if is_draw else "LOSS")
                    logger.info(f"  Game {idx}: {team_score}-{opp_score} ({result})")
                
                away_wins = sum(1 for r in away_form if r[0] > r[1])
                away_draws = sum(1 for r in away_form if r[0] == r[1])
                away_losses = len(away_form) - away_wins - away_draws
                away_win_rate = away_wins / len(away_form)
                logger.info(f"✅ AWAY WIN RATE: {away_wins}W/{away_draws}D/{away_losses}L = {away_win_rate*100:.1f}%")
            else:
                away_win_rate = 0.0  # No data = 0%, not 50%
                logger.warning(f"⚠️ AWAY TEAM ({away_team}): NO FORM DATA - Setting win rate to 0%")
            
            logger.info(f"=== FINAL WIN RATES: {home_team}={home_win_rate*100:.0f}%, {away_team}={away_win_rate*100:.0f}% ===")
            
            # Calculate average points scored (not conceded)
            home_score = sum(r[0] for r in home_form) / len(home_form) if home_form else 0
            away_score = sum(r[0] for r in away_form) / len(away_form) if away_form else 0
            
            # Calculate probability based on form
            if home_form or away_form:
                home_strength = (home_win_rate * 0.6) + (min(home_score / 50, 1.0) * 0.4) if home_form else 0.5
                away_strength = (away_win_rate * 0.6) + (min(away_score / 50, 1.0) * 0.4) if away_form else 0.5
                
                # Normalize to probability
                total_strength = home_strength + away_strength
                if total_strength > 0:
                    home_prob = home_strength / total_strength
                else:
                    home_prob = 0.5
            else:
                home_prob = 0.5
            
            # Build title and content
            if home_win_rate > 0.6:
                title = f"{home_team} in strong form ahead of {away_team} clash"
            elif away_win_rate > 0.6:
                title = f"{away_team} looking to extend winning streak"
            else:
                title = f"{home_team} vs {away_team}: Tight contest expected"
            
            content = f"{home_team} has won {home_win_rate*100:.0f}% of recent matches, "
            content += f"while {away_team} has a {away_win_rate*100:.0f}% win rate. "
            
            # Add form details
            if home_form:
                content += f"{home_team} averaging {home_score:.1f} points in recent games. "
            if away_form:
                content += f"{away_team} averaging {away_score:.1f} points. "
            
            if h2h:
                home_wins = sum(1 for m in h2h if m[0] > m[1])
                content += f"Head-to-head: {home_team} has won {home_wins}/{len(h2h)} recent meetings. "
            
            conn.close()
            
            # Get actual team names from database or use provided names
            db_home_team = match[3] if len(match) > 3 and match[3] else home_team
            db_away_team = match[4] if len(match) > 4 and match[4] else away_team
            
            # Use match date for timestamp
            match_timestamp = match_date if isinstance(match_date, str) else (match[1] if len(match) > 1 and match[1] else datetime.now().isoformat())
            
            return NewsItem(
                id=f"preview_{match_id}_{int(datetime.now().timestamp())}",
                type="match_preview",
                title=title,
                content=content,
                timestamp=match_timestamp,
                league_id=league_id,
                match_id=match_id,
                impact_score=0.0,
                related_stats={
                    "home_team": db_home_team,
                    "away_team": db_away_team,
                    "home_form": home_form[-5:] if home_form else [],
                    "away_form": away_form[-5:] if away_form else [],
                    "head_to_head": h2h[:3] if h2h else [],
                    "home_team_id": home_team_id,
                    "away_team_id": away_team_id,
                    "home_logo": home_logo,
                    "away_logo": away_logo,
                    "venue": match[2] if len(match) > 2 else None,
                    "date_event": match[1] if len(match) > 1 else match_date,
                    "win_probability": home_prob,
                },
                clickable_stats=[]
            )
        except Exception as e:
            logger.error(f"Error generating match preview: {e}")
            return None
    
    def generate_match_preview(self, match_id: int, home_team: str, away_team: str, 
                               league_id: int, match_date: str) -> Optional[NewsItem]:
        """Generate AI match preview news"""
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            
            # Get match details (including league_id for accurate form calculation)
            cursor.execute("""
                SELECT e.id, e.home_team_id, e.away_team_id, e.date_event, e.venue, e.league_id,
                       t1.name as home_team_name, t2.name as away_team_name
                FROM event e
                LEFT JOIN team t1 ON e.home_team_id = t1.id
                LEFT JOIN team t2 ON e.away_team_id = t2.id
                WHERE e.id = ?
            """, (match_id,))
            
            match = cursor.fetchone()
            if not match:
                return None
            
            home_team_id = match[1]
            away_team_id = match[2]
            match_league_id = match[5] if len(match) > 5 else league_id  # Use league_id from match or parameter
            
            # Get team logos if available
            home_logo = self.get_team_logo_url(home_team_id) if home_team_id else None
            away_logo = self.get_team_logo_url(away_team_id) if away_team_id else None
            
            # Get recent form for both teams - CRITICAL: Filter by league_id for accuracy
            home_form = self._get_team_form(cursor, home_team_id, limit=5, league_id=match_league_id) if home_team_id else []
            away_form = self._get_team_form(cursor, away_team_id, limit=5, league_id=match_league_id) if away_team_id else []
            
            # Get head-to-head
            h2h = []
            if home_team_id and away_team_id:
                h2h = self._get_head_to_head(cursor, home_team_id, away_team_id, limit=5)
            
            # Generate prediction if predictor available
            prediction = None
            home_prob = 0.5  # Default probability
            
            if self.predictor:
                try:
                    prediction = self.predictor.predict(
                        home_team, away_team, league_id, match_date
                    )
                    if prediction:
                        home_prob = prediction.get('home_win_prob', 0.5)
                except Exception as e:
                    logger.warning(f"Could not generate prediction for preview: {e}")
            
            # Generate AI content
            # EXTENSIVE LOGGING for win rate calculation
            logger.info(f"=== WIN RATE CALCULATION DEBUG for {home_team} vs {away_team} ===")
            logger.info(f"Match ID: {match_id}, League ID: {league_id}")
            logger.info(f"Home Team ID: {home_team_id}, Away Team ID: {away_team_id}")
            
            # Calculate win rates correctly - handle empty form and ensure proper calculation
            if home_form and len(home_form) > 0:
                logger.info(f"📊 HOME TEAM ({home_team}) FORM DATA: {len(home_form)} games")
                for idx, (team_score, opp_score) in enumerate(home_form, 1):
                    is_win = team_score > opp_score
                    is_draw = team_score == opp_score
                    result = "WIN" if is_win else ("DRAW" if is_draw else "LOSS")
                    logger.info(f"  Game {idx}: {team_score}-{opp_score} ({result})")
                
                home_wins = sum(1 for r in home_form if r[0] > r[1])
                home_draws = sum(1 for r in home_form if r[0] == r[1])
                home_losses = len(home_form) - home_wins - home_draws
                home_win_rate = home_wins / len(home_form)
                logger.info(f"✅ HOME WIN RATE: {home_wins}W/{home_draws}D/{home_losses}L = {home_win_rate*100:.1f}%")
            else:
                home_win_rate = 0.0  # No data = 0%, not 50%
                logger.warning(f"⚠️ HOME TEAM ({home_team}): NO FORM DATA - Setting win rate to 0%")
            
            if away_form and len(away_form) > 0:
                logger.info(f"📊 AWAY TEAM ({away_team}) FORM DATA: {len(away_form)} games")
                for idx, (team_score, opp_score) in enumerate(away_form, 1):
                    is_win = team_score > opp_score
                    is_draw = team_score == opp_score
                    result = "WIN" if is_win else ("DRAW" if is_draw else "LOSS")
                    logger.info(f"  Game {idx}: {team_score}-{opp_score} ({result})")
                
                away_wins = sum(1 for r in away_form if r[0] > r[1])
                away_draws = sum(1 for r in away_form if r[0] == r[1])
                away_losses = len(away_form) - away_wins - away_draws
                away_win_rate = away_wins / len(away_form)
                logger.info(f"✅ AWAY WIN RATE: {away_wins}W/{away_draws}D/{away_losses}L = {away_win_rate*100:.1f}%")
            else:
                away_win_rate = 0.0  # No data = 0%, not 50%
                logger.warning(f"⚠️ AWAY TEAM ({away_team}): NO FORM DATA - Setting win rate to 0%")
            
            logger.info(f"=== FINAL WIN RATES: {home_team}={home_win_rate*100:.0f}%, {away_team}={away_win_rate*100:.0f}% ===")
            
            # Calculate average points scored (not conceded)
            # For home_form: r[0] is points scored when home, r[1] is points conceded
            # For away_form: r[0] is points scored when away, r[1] is points conceded
            home_score = sum(r[0] for r in home_form) / len(home_form) if home_form else 0
            away_score = sum(r[0] for r in away_form) / len(away_form) if away_form else 0
            
            # If no prediction from model, calculate based on form
            if not prediction:
                # Simple form-based probability: combine win rate and scoring average
                home_strength = (home_win_rate * 0.6) + (min(home_score / 50, 1.0) * 0.4) if home_form else 0.5
                away_strength = (away_win_rate * 0.6) + (min(away_score / 50, 1.0) * 0.4) if away_form else 0.5
                
                # Normalize to probability
                total_strength = home_strength + away_strength
                if total_strength > 0:
                    home_prob = home_strength / total_strength
                else:
                    home_prob = 0.5
            
            # Build title and content
            if prediction:
                predicted_winner = home_team if home_prob > 0.5 else away_team
                confidence = max(home_prob, 1 - home_prob)
                
                title = f"{predicted_winner} favored with {confidence*100:.1f}% confidence"
                content = f"AI analysis predicts {predicted_winner} to win this matchup. "
            else:
                if home_win_rate > 0.6:
                    title = f"{home_team} in strong form ahead of {away_team} clash"
                elif away_win_rate > 0.6:
                    title = f"{away_team} looking to extend winning streak"
                else:
                    title = f"{home_team} vs {away_team}: Tight contest expected"
                
                content = f"{home_team} has won {home_win_rate*100:.0f}% of recent matches, "
                content += f"while {away_team} has a {away_win_rate*100:.0f}% win rate. "
            
            # Add form details
            if home_form:
                content += f"{home_team} averaging {home_score:.1f} points in recent games. "
            if away_form:
                content += f"{away_team} averaging {away_score:.1f} points. "
            
            if h2h:
                home_wins = sum(1 for m in h2h if m[0] > m[1])
                content += f"Head-to-head: {home_team} has won {home_wins}/{len(h2h)} recent meetings. "
            
            # Add clickable stats
            clickable_stats = []
            if prediction:
                clickable_stats.append({
                    "label": f"Win Probability: {prediction.get('home_win_prob', 0.5)*100:.1f}%",
                    "explanation": f"Based on recent form, head-to-head record, and team strength metrics"
                })
            
            conn.close()
            
            # Get actual team names from database or use provided names
            db_home_team = match[5] if len(match) > 5 and match[5] else home_team
            db_away_team = match[6] if len(match) > 6 and match[6] else away_team
            
            # Use match date for timestamp, not current time
            match_timestamp = match_date if isinstance(match_date, str) else (match[3] if len(match) > 3 and match[3] else datetime.now().isoformat())
            
            return NewsItem(
                id=f"preview_{match_id}_{int(datetime.now().timestamp())}",
                type="match_preview",
                title=title,
                content=content,
                timestamp=match_timestamp,
                league_id=league_id,
                match_id=match_id,
                impact_score=0.0,
                related_stats={
                    "home_team": db_home_team,
                    "away_team": db_away_team,
                    "home_form": home_form[-5:] if home_form else [],
                    "away_form": away_form[-5:] if away_form else [],
                    "head_to_head": h2h[:5] if h2h else [],
                    "home_team_id": home_team_id,
                    "away_team_id": away_team_id,
                    "home_logo": home_logo,
                    "away_logo": away_logo,
                    "venue": match[4] if len(match) > 4 else None,
                    "date_event": match[3] if len(match) > 3 else match_date,
                    "win_probability": home_prob,  # Always include calculated probability
                },
                clickable_stats=clickable_stats
            )
        except Exception as e:
            logger.error(f"Error generating match preview: {e}")
            return None
    
    def generate_lineup_impact_news(self, match_id: int, team_id: int, team_name: str,
                                    lineup_changes: List[Dict[str, Any]], 
                                    old_win_prob: float, new_win_prob: float) -> Optional[NewsItem]:
        """Generate news about lineup changes and their impact"""
        try:
            if not lineup_changes:
                return None
            
            prob_change = new_win_prob - old_win_prob
            prob_change_pct = prob_change * 100
            
            # Determine impact level
            if abs(prob_change_pct) > 5:
                impact_level = "significant"
            elif abs(prob_change_pct) > 2:
                impact_level = "moderate"
            else:
                impact_level = "minor"
            
            # Build title
            if prob_change < -0.05:
                title = f"{team_name} lineup changes: win probability drops {abs(prob_change_pct):.1f}%"
            elif prob_change > 0.05:
                title = f"{team_name} strengthens lineup: win probability up {prob_change_pct:.1f}%"
            else:
                title = f"{team_name} makes {len(lineup_changes)} lineup changes"
            
            # Build content
            content = f"{team_name} has made {len(lineup_changes)} change(s) to their lineup. "
            
            for change in lineup_changes[:3]:  # Top 3 changes
                player_name = change.get('player_name', 'Player')
                position = change.get('position', '')
                change_type = change.get('type', 'change')  # 'in', 'out', 'position_change'
                
                if change_type == 'in':
                    content += f"{player_name} comes in at {position}. "
                elif change_type == 'out':
                    content += f"{player_name} drops out. "
                else:
                    content += f"{player_name} moves to {position}. "
            
            if abs(prob_change_pct) > 2:
                direction = "drops" if prob_change < 0 else "rises"
                content += f"Win probability {direction} from {old_win_prob*100:.1f}% to {new_win_prob*100:.1f}%. "
            
            # Get team logo
            team_logo = self.get_team_logo_url(team_id) if team_id else None
            
            # Clickable stats
            clickable_stats = [
                {
                    "label": f"Win Probability Change: {prob_change_pct:+.1f}%",
                    "explanation": f"Lineup changes have {'reduced' if prob_change < 0 else 'increased'} {team_name}'s chances based on player impact ratings"
                }
            ]
            
            return NewsItem(
                id=f"lineup_{match_id}_{team_id}_{int(datetime.now().timestamp())}",
                type="lineup_change",
                title=title,
                content=content,
                timestamp=datetime.now().isoformat(),
                match_id=match_id,
                team_id=team_id,
                impact_score=prob_change,
                win_probability_change=prob_change,
                related_stats={
                    "lineup_changes": lineup_changes,
                    "old_win_prob": old_win_prob,
                    "new_win_prob": new_win_prob,
                    "team_logo": team_logo,
                },
                clickable_stats=clickable_stats
            )
        except Exception as e:
            logger.error(f"Error generating lineup impact news: {e}")
            return None
    
    def generate_prediction_shift_news(self, match_id: int, home_team: str, away_team: str,
                                      old_prediction: Dict[str, Any], 
                                      new_prediction: Dict[str, Any]) -> Optional[NewsItem]:
        """Generate news when predictions shift significantly"""
        try:
            old_home_prob = old_prediction.get('home_win_prob', 0.5)
            new_home_prob = new_prediction.get('home_win_prob', 0.5)
            
            prob_change = new_home_prob - old_home_prob
            
            # Only generate if change is significant (>3%)
            if abs(prob_change) < 0.03:
                return None
            
            prob_change_pct = prob_change * 100
            
            if prob_change < 0:
                winner_shift = f"{home_team}'s win chance drops from {old_home_prob*100:.1f}% to {new_home_prob*100:.1f}%"
                title = f"Prediction shift: {away_team} now favored"
            else:
                winner_shift = f"{home_team}'s win chance rises from {old_home_prob*100:.1f}% to {new_home_prob*100:.1f}%"
                title = f"Prediction shift: {home_team} gains edge"
            
            content = f"Latest updates have shifted the prediction. {winner_shift}. "
            
            # Add reason if available
            reason = new_prediction.get('shift_reason', '')
            if reason:
                content += f"Reason: {reason}"
            
            return NewsItem(
                id=f"shift_{match_id}_{int(datetime.now().timestamp())}",
                type="prediction_shift",
                title=title,
                content=content,
                timestamp=datetime.now().isoformat(),
                match_id=match_id,
                impact_score=prob_change,
                win_probability_change=prob_change,
                related_stats={
                    "old_prediction": old_prediction,
                    "new_prediction": new_prediction
                },
                clickable_stats=[
                    {
                        "label": f"Probability Change: {prob_change_pct:+.1f}%",
                        "explanation": "Prediction updated based on latest lineup changes, injuries, or form updates"
                    }
                ]
            )
        except Exception as e:
            logger.error(f"Error generating prediction shift news: {e}")
            return None
    
    def _get_team_form(self, cursor: sqlite3.Cursor, team_id: int, limit: int = 5, league_id: Optional[int] = None) -> List[tuple]:
        """Get recent form (scores) for a team in a specific league
        
        Returns list of tuples: (team_score, opponent_score) for each match
        This allows easy win calculation: team_score > opponent_score = win
        
        Strategy:
        1. First try to get games from the specific league (most accurate)
        2. If no games found in that league, fall back to ALL leagues (use historical data)
        3. This ensures we always use available historical data
        
        Args:
            cursor: Database cursor
            team_id: Team ID to get form for
            limit: Maximum number of games to return
            league_id: Optional league ID to filter by (preferred, but falls back to all leagues)
        """
        try:
            results = []
            used_fallback = False
            
            # Step 1: Try to get games from the specific league first (most accurate)
            if league_id:
                cursor.execute("""
                    SELECT e.home_score, e.away_score, e.home_team_id, e.away_team_id, e.date_event, e.league_id
                    FROM event e
                    WHERE (e.home_team_id = ? OR e.away_team_id = ?)
                    AND e.league_id = ?
                    AND e.home_score IS NOT NULL
                    AND e.away_score IS NOT NULL
                    AND e.date_event < date('now')
                    ORDER BY e.date_event DESC
                    LIMIT ?
                """, (team_id, team_id, league_id, limit))
                
                for row in cursor.fetchall():
                    home_score, away_score, home_id, away_id, date_event, game_league_id = row
                    # Normalize to (team_score, opponent_score) format
                    if home_id == team_id:
                        results.append((home_score, away_score))
                    else:
                        results.append((away_score, home_score))
            
            # Step 2: If no games found in specific league, fall back to ALL leagues (use historical data)
            if len(results) == 0:
                used_fallback = True
                logger.info(f"Team {team_id}: No games found in league {league_id}, falling back to all leagues")
                cursor.execute("""
                    SELECT e.home_score, e.away_score, e.home_team_id, e.away_team_id, e.date_event, e.league_id
                    FROM event e
                    WHERE (e.home_team_id = ? OR e.away_team_id = ?)
                    AND e.home_score IS NOT NULL
                    AND e.away_score IS NOT NULL
                    AND e.date_event < date('now')
                    ORDER BY e.date_event DESC
                    LIMIT ?
                """, (team_id, team_id, limit))
                
                for row in cursor.fetchall():
                    home_score, away_score, home_id, away_id, date_event, game_league_id = row
                    # Normalize to (team_score, opponent_score) format
                    if home_id == team_id:
                        results.append((home_score, away_score))
                    else:
                        results.append((away_score, home_score))
            
            # Enhanced logging for debugging
            if results:
                wins = sum(1 for r in results if r[0] > r[1])
                draws = sum(1 for r in results if r[0] == r[1])
                losses = len(results) - wins - draws
                win_rate = wins / len(results) * 100 if results else 0
                source = f"all leagues (fallback)" if used_fallback else (f"league {league_id}" if league_id else "all leagues")
                logger.info(f"Team {team_id}: {len(results)} games from {source} - {wins}W/{draws}D/{losses}L = {win_rate:.1f}% win rate")
            else:
                logger.warning(f"Team {team_id}: No games found in database at all (checked league {league_id} and all leagues)")
            
            return results
        except Exception as e:
            logger.error(f"Error getting team form for team {team_id} (league {league_id}): {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def _get_head_to_head(self, cursor: sqlite3.Cursor, team1_id: int, team2_id: int, limit: int = 5) -> List[tuple]:
        """Get head-to-head results between two teams"""
        try:
            cursor.execute("""
                SELECT e.home_score, e.away_score, e.home_team_id
                FROM event e
                WHERE ((e.home_team_id = ? AND e.away_team_id = ?)
                    OR (e.home_team_id = ? AND e.away_team_id = ?))
                AND e.home_score IS NOT NULL
                AND e.away_score IS NOT NULL
                ORDER BY e.date_event DESC
                LIMIT ?
            """, (team1_id, team2_id, team2_id, team1_id, limit))
            
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting head-to-head: {e}")
            return []
    
    def get_news_feed(self, user_id: Optional[str] = None, 
                     followed_teams: Optional[List[int]] = None,
                     followed_leagues: Optional[List[int]] = None,
                     league_id: Optional[int] = None,
                     limit: int = 50,
                     include_external: bool = True) -> List[NewsItem]:
        """Get personalized news feed - LEAGUE-SPECIFIC
        
        Args:
            league_id: Primary league to filter by. If provided, only shows news for this league.
                       This creates a focused, clean experience for users viewing a specific league.
        """
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            
            all_news_items = []
            
            # Logging for current date and date range
            today = datetime.now().strftime('%Y-%m-%d')
            next_7_days = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
            last_7_days = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            logger.info("="*80)
            logger.info("=== get_news_feed START ===")
            logger.info("="*80)
            logger.info(f"📅 Date range check: today={today}, next_7_days={next_7_days}, last_7_days={last_7_days}")
            
            # CRITICAL: Save the original league_id filter before any variable overwriting
            # Convert to int if it's a string or None
            filter_league_id = None
            if league_id is not None:
                try:
                    filter_league_id = int(league_id)
                    logger.info(f"🎯 LEAGUE-SPECIFIC MODE: Filtering news for league {filter_league_id} (converted from {league_id})")
                except (ValueError, TypeError):
                    logger.warning(f"⚠️ Invalid league_id: {league_id}, ignoring filter")
                    filter_league_id = None
            
            # LEAGUE-SPECIFIC: Filter by league_id if provided
            league_filter = ""
            league_params = []
            if filter_league_id:
                league_filter = "AND e.league_id = ?"
                league_params = [filter_league_id]
                logger.info(f"🎯 LEAGUE-SPECIFIC MODE: Filtering news for league {filter_league_id}")
            
            # 1. Get AI-generated news from upcoming matches (next 7 days)
            # OPTIMIZATION: Reduce limit to improve performance
            # CRITICAL: Build query with explicit league filter
            if filter_league_id:
                query = """
                    SELECT e.id, e.league_id, e.date_event, e.home_team_id, e.away_team_id,
                           t1.name as home_team, t2.name as away_team
                    FROM event e
                    LEFT JOIN team t1 ON e.home_team_id = t1.id
                    LEFT JOIN team t2 ON e.away_team_id = t2.id
                    WHERE e.date_event >= date('now')
                    AND e.date_event <= date('now', '+7 days')
                    AND e.home_team_id IS NOT NULL
                    AND e.away_team_id IS NOT NULL
                    AND e.league_id = ?
                    ORDER BY e.date_event ASC
                    LIMIT 15
                """
                league_params = [filter_league_id]
            else:
                query = """
                    SELECT e.id, e.league_id, e.date_event, e.home_team_id, e.away_team_id,
                           t1.name as home_team, t2.name as away_team
                    FROM event e
                    LEFT JOIN team t1 ON e.home_team_id = t1.id
                    LEFT JOIN team t2 ON e.away_team_id = t2.id
                    WHERE e.date_event >= date('now')
                    AND e.date_event <= date('now', '+7 days')
                    AND e.home_team_id IS NOT NULL
                    AND e.away_team_id IS NOT NULL
                    ORDER BY e.date_event ASC
                    LIMIT 15
                """
                league_params = []
            logger.info("="*80)
            logger.info("=== UPCOMING MATCHES QUERY ===")
            logger.info("="*80)
            logger.info(f"🔍 EXECUTING QUERY with filter_league_id={filter_league_id}")
            logger.info(f"🔍 Query: {query}")
            logger.info(f"🔍 Params: {league_params}")
            logger.info(f"🔍 Params type: {[type(p).__name__ for p in league_params]}")
            
            # Test the query first with a COUNT to see if any matches exist
            if filter_league_id:
                test_query = """
                    SELECT COUNT(*) FROM event e
                    WHERE e.date_event >= date('now')
                    AND e.date_event <= date('now', '+7 days')
                    AND e.home_team_id IS NOT NULL
                    AND e.away_team_id IS NOT NULL
                    AND e.league_id = ?
                """
                cursor.execute(test_query, [filter_league_id])
                test_count = cursor.fetchone()[0]
                logger.info(f"🔍 TEST COUNT QUERY: Found {test_count} total upcoming matches for league {filter_league_id}")
                
                # Also check what dates are in the database for this league
                date_query = """
                    SELECT MIN(date_event), MAX(date_event), COUNT(*) 
                    FROM event e
                    WHERE e.league_id = ?
                    AND e.home_team_id IS NOT NULL
                    AND e.away_team_id IS NOT NULL
                """
                cursor.execute(date_query, [filter_league_id])
                min_date, max_date, total_count = cursor.fetchone()
                logger.info(f"🔍 LEAGUE DATE RANGE: min={min_date}, max={max_date}, total_matches={total_count}")
            
            cursor.execute(query, league_params)
            matches = cursor.fetchall()
            logger.info(f"✅ Found {len(matches)} upcoming matches for news generation (filter_league_id={filter_league_id})")
            
            if len(matches) > 0:
                logger.info(f"📋 First 3 matches:")
                for i, m in enumerate(matches[:3], 1):
                    logger.info(f"   {i}. Match ID={m[0]}, league_id={m[1]}, date={m[2]}, home={m[4]}, away={m[5]}")
            logger.info("="*80)
            
            # DEBUG: Check current date/time for date filtering
            cursor.execute("SELECT date('now') as today, date('now', '+7 days') as next_week")
            date_info = cursor.fetchone()
            logger.info(f"📅 Date range check: today={date_info[0]}, next_7_days={date_info[1]}")
            
            # CRITICAL: Verify all matches match the filter - THIS IS THE SAFETY CHECK
            if filter_league_id:
                if matches:
                    # Log first few matches to debug
                    logger.info(f"🔍 First 3 matches from query:")
                    for i, m in enumerate(matches[:3]):
                        match_id, match_league_id, match_date = m[0], m[1], m[2]
                        logger.info(f"   Match {i+1}: ID={match_id}, league_id={match_league_id}, date={match_date}")
                    
                    mismatched = [m for m in matches if m[1] != filter_league_id]
                    if mismatched:
                        logger.error(f"🚨 CRITICAL ERROR: Found {len(mismatched)} matches that don't match filter_league_id={filter_league_id}!")
                        for m in mismatched[:5]:
                            logger.error(f"   Match {m[0]}: league_id={m[1]} (expected {filter_league_id})")
                        # Remove mismatched matches - THIS IS CRITICAL!
                        matches = [m for m in matches if m[1] == filter_league_id]
                        logger.error(f"🚨 REMOVED {len(mismatched)} mismatched matches! Only {len(matches)} matches remain.")
                    else:
                        logger.info(f"✅ All {len(matches)} matches correctly match filter_league_id={filter_league_id}")
                else:
                    logger.warning(f"⚠️ No matches found for league {filter_league_id}!")
                    logger.warning(f"   This could mean:")
                    logger.warning(f"   1. No upcoming matches in the next 7 days for this league")
                    logger.warning(f"   2. Date filtering issue (check date('now') vs actual dates)")
                    logger.warning(f"   3. Database doesn't have matches for this league")
                    # Check if there are ANY matches for this league (regardless of date)
                    cursor.execute("SELECT COUNT(*) FROM event WHERE league_id = ?", (filter_league_id,))
                    total_matches = cursor.fetchone()[0]
                    logger.info(f"   Total matches in database for league {filter_league_id}: {total_matches}")
            
            # OPTIMIZATION: Pre-fetch all team form data in batch to avoid repeated queries
            team_ids = set()
            for match in matches:
                if match[3]:  # home_id
                    team_ids.add(match[3])
                if match[4]:  # away_id
                    team_ids.add(match[4])
            
            # Batch fetch team form data - CRITICAL: Get league_id for each team from matches
            team_league_map = {}  # Map team_id to league_id
            for match in matches:
                match_id, match_league_id, match_date, home_id, away_id, home_team, away_team = match
                if home_id:
                    team_league_map[home_id] = match_league_id
                if away_id:
                    team_league_map[away_id] = match_league_id
            
            # Batch fetch team form data with league filtering for accuracy
            team_form_cache = {}
            for team_id in team_ids:
                league_id_for_form = team_league_map.get(team_id)
                team_form_cache[team_id] = self._get_team_form(cursor, team_id, limit=5, league_id=league_id_for_form)
            
            # Generate previews for matches (optimized - skip logo fetching for now)
            # CRITICAL: filter_league_id already saved at function start to avoid variable overwriting
            
            for match in matches:
                match_id, match_league_id, match_date, home_id, away_id, home_team, away_team = match
                
                # Skip if team names are missing
                if not home_team or not away_team:
                    logger.warning(f"Skipping match {match_id}: missing team names")
                    continue
                
                # CRITICAL: If filter_league_id is set, ONLY include items from that league
                # The SQL query already filtered by league_id, but double-check here as a safety measure
                if filter_league_id and match_league_id != filter_league_id:
                    logger.error(f"🚨 CRITICAL FILTER BUG: Match {match_id} has league_id={match_league_id} but filter is {filter_league_id} - SKIPPING!")
                    continue
                
                # Check if user follows this team/league (only if league_id filter is NOT active)
                # If filter_league_id is set, we show ALL items from that league regardless of follows
                include = True
                if not filter_league_id:  # Only apply follow logic when not filtering by specific league
                    if followed_teams and home_id not in followed_teams and away_id not in followed_teams:
                        include = False
                    if followed_leagues and match_league_id not in followed_leagues:
                        include = False
                    
                    # 70% followed content, 30% trending
                    if not include and len(all_news_items) > limit * 0.7:
                        continue
                
                # OPTIMIZATION: Use cached form data (skip logo fetching to avoid timeouts)
                # Logos can be fetched asynchronously on the frontend if needed
                preview = self.generate_match_preview_optimized(
                    match_id, home_team, away_team, match_league_id, match_date,
                    home_id, away_id, team_form_cache.get(home_id, []), 
                    team_form_cache.get(away_id, [])
                )
                
                # Note: Logo fetching removed here to prevent function timeouts
                # Logos can be added later via a separate endpoint or client-side fetching
                if preview:
                    all_news_items.append(preview)
            
            # 2. If no upcoming matches, generate news from recent completed matches (fallback)
            # CRITICAL: Only do fallback if filter_league_id is NOT set
            # If filter_league_id is set and we have 0 matches, DON'T show matches from other leagues!
            if len(all_news_items) == 0:
                if filter_league_id:
                    logger.info(f"⚠️ No upcoming matches found for league {filter_league_id} - NOT falling back to other leagues")
                    # Don't show matches from other leagues when a specific league is selected
                else:
                    logger.info("No upcoming matches found, generating news from recent completed matches")
                    query = f"""
                        SELECT e.id, e.league_id, e.date_event, e.home_team_id, e.away_team_id,
                               t1.name as home_team, t2.name as away_team, e.home_score, e.away_score
                        FROM event e
                        LEFT JOIN team t1 ON e.home_team_id = t1.id
                        LEFT JOIN team t2 ON e.away_team_id = t2.id
                        WHERE e.date_event >= date('now', '-7 days')
                        AND e.date_event < date('now')
                        AND e.home_score IS NOT NULL
                        AND e.away_score IS NOT NULL
                        AND e.home_team_id IS NOT NULL
                        AND e.away_team_id IS NOT NULL
                        {league_filter}
                        ORDER BY e.date_event DESC
                        LIMIT 10
                    """
                    logger.info("="*80)
                    logger.info("=== RECENT MATCHES QUERY ===")
                    logger.info("="*80)
                    logger.info(f"🔍 EXECUTING RECENT MATCHES QUERY with filter_league_id={filter_league_id}")
                    logger.info(f"🔍 Query: {query}")
                    logger.info(f"🔍 Params: {league_params}")
                    logger.info(f"🔍 Params type: {[type(p).__name__ for p in league_params]}")
                    
                    # Test the query first with a COUNT
                    if filter_league_id:
                        test_query = """
                            SELECT COUNT(*) FROM event e
                            WHERE e.date_event >= date('now', '-7 days')
                            AND e.date_event < date('now')
                            AND e.home_score IS NOT NULL
                            AND e.away_score IS NOT NULL
                            AND e.home_team_id IS NOT NULL
                            AND e.away_team_id IS NOT NULL
                            AND e.league_id = ?
                        """
                        cursor.execute(test_query, [filter_league_id])
                        test_count = cursor.fetchone()[0]
                        logger.info(f"🔍 TEST COUNT QUERY: Found {test_count} total recent matches for league {filter_league_id}")
                    
                    cursor.execute(query, league_params)
                    recent_matches = cursor.fetchall()
                    logger.info(f"✅ Found {len(recent_matches)} recent matches for news generation (filter_league_id={filter_league_id})")
                    
                    if len(recent_matches) > 0:
                        logger.info(f"📋 First 3 recent matches:")
                        for i, m in enumerate(recent_matches[:3], 1):
                            logger.info(f"   {i}. Match ID={m[0]}, league_id={m[1]}, date={m[2]}, home={m[4]} vs {m[5]}, score={m[6]}-{m[7]}")
                    logger.info("="*80)
                    
                    for match in recent_matches:
                        match_id, match_league_id, match_date, home_id, away_id, home_team, away_team, home_score, away_score = match
                        
                        if not home_team or not away_team:
                            continue
                        
                        # CRITICAL: If filter_league_id is set, ONLY include items from that league
                        if filter_league_id and match_league_id != filter_league_id:
                            logger.warning(f"🚨 Skipping match {match_id}: league_id {match_league_id} doesn't match filter {filter_league_id}")
                            continue
                    
                    # Create a recap/news item for completed match
                    winner = home_team if home_score > away_score else away_team
                    score_diff = abs(home_score - away_score)
                    
                    if score_diff > 15:
                        title = f"{winner} dominate with {max(home_score, away_score)}-{min(home_score, away_score)} victory"
                    elif score_diff > 7:
                        title = f"{winner} secure {max(home_score, away_score)}-{min(home_score, away_score)} win"
                    else:
                        title = f"{home_team} {home_score}-{away_score} {away_team}: Close contest"
                    
                    content = f"{home_team} {home_score} - {away_score} {away_team}. "
                    if score_diff <= 3:
                        content += "A nail-biting finish with the result decided in the final moments. "
                    elif score_diff <= 7:
                        content += "A competitive match with both teams showing strong performances. "
                    else:
                        content += f"{winner} showed their dominance with a convincing victory. "
                    
                    recap_item = NewsItem(
                        id=f"recap_{match_id}_{int(datetime.now().timestamp())}",
                        type="match_recap",
                        title=title,
                        content=content,
                        timestamp=match_date if isinstance(match_date, str) else datetime.now().isoformat(),
                        league_id=match_league_id,  # Use the match's league_id, not the filter
                        match_id=match_id,
                        related_stats={
                            "home_team": home_team,
                            "away_team": away_team,
                            "home_score": home_score,
                            "away_score": away_score,
                            "home_team_id": home_id,
                            "away_team_id": away_id,
                        }
                    )
                    all_news_items.append(recap_item)
            
            # 3. Fetch external news from SportDevs (if available) - ONLY if league_id matches
            if include_external and self.sportdevs_client:
                try:
                    # Use filter_league_id parameter instead of followed_leagues
                    external_news = self.fetch_external_news(
                        league_id=filter_league_id,  # FIXED: Use filter_league_id parameter
                        limit=min(10, limit - len(all_news_items))
                    )
                    # Filter external news by league_id if specified
                    if filter_league_id:
                        external_news = [item for item in external_news if item.league_id == filter_league_id]
                    all_news_items.extend(external_news)
                    logger.info(f"Added {len(external_news)} external news items (filtered by league_id={filter_league_id})")
                except Exception as e:
                    logger.warning(f"Could not fetch external news: {e}")
            
            # 4. Fetch social media posts - ONLY for teams in the selected league
            if include_external and self.social_media_fetcher:
                try:
                    # If filter_league_id is specified, get teams from that league only
                    league_teams = []
                    if filter_league_id:
                        cursor.execute("""
                            SELECT DISTINCT t.id
                            FROM team t
                            JOIN event e ON (e.home_team_id = t.id OR e.away_team_id = t.id)
                            WHERE e.league_id = ?
                            LIMIT 20
                        """, (filter_league_id,))
                        league_teams = [row[0] for row in cursor.fetchall()]
                        logger.info(f"Found {len(league_teams)} teams in league {filter_league_id} for social media")
                    
                    # Use league teams if available, otherwise use followed_teams
                    teams_for_social = league_teams if league_teams else (followed_teams or [])
                    
                    if teams_for_social:  # Only fetch if we have teams
                        social_news = self.fetch_social_media_news(
                            followed_teams=teams_for_social,
                            limit=min(10, limit - len(all_news_items))
                        )
                        # Filter social media news by league_id if specified
                        if filter_league_id:
                            social_news = [item for item in social_news if item.league_id == filter_league_id]
                        all_news_items.extend(social_news)
                        logger.info(f"Added {len(social_news)} social media news items (filtered by league_id={filter_league_id})")
                except Exception as e:
                    logger.warning(f"Could not fetch social media news: {e}")
            
            # FINAL FILTER: Ensure ALL news items match the league_id if specified
            # Use filter_league_id (saved at function start) to avoid variable overwriting issues
            if filter_league_id:
                initial_count = len(all_news_items)
                filtered_items = []
                removed_items = []
                for item in all_news_items:
                    # CRITICAL: Check if item has league_id attribute
                    item_league_id = getattr(item, 'league_id', None)
                    # Include items that match the league_id
                    if item_league_id == filter_league_id:
                        filtered_items.append(item)
                    else:
                        # Items that don't match - log and skip
                        removed_items.append(item)
                        logger.error(f"🚨 FINAL FILTER: REMOVING news item {item.id} (type: {item.type}) - league_id {item_league_id} doesn't match filter {filter_league_id}")
                
                all_news_items = filtered_items
                removed_count = initial_count - len(all_news_items)
                if removed_count > 0:
                    logger.error(f"🚨 FINAL FILTER REMOVED {removed_count} items that didn't match league {filter_league_id}")
                    removed_item_ids = [f'{item.id}(league={getattr(item, "league_id", None)})' for item in removed_items[:5]]
                    logger.error(f"🚨 Removed items: {removed_item_ids}")
                logger.info(f"🎯 FINAL FILTER: {len(all_news_items)} items after league_id={filter_league_id} filtering (removed {removed_count} items)")
                
                # CRITICAL: If we have 0 items after filtering, log a warning
                if len(all_news_items) == 0 and initial_count > 0:
                    logger.warning(f"⚠️ All {initial_count} news items were filtered out! League {filter_league_id} has no matches/news.")
            
            # Sort by timestamp (newest first)
            all_news_items.sort(key=lambda x: x.timestamp, reverse=True)
            
            logger.info("="*80)
            logger.info("=== get_news_feed COMPLETE ===")
            logger.info("="*80)
            logger.info(f"✅ Generated {len(all_news_items)} total news items (filter_league_id={filter_league_id})")
            if len(all_news_items) > 0:
                logger.info(f"📰 News item types breakdown:")
                type_counts = {}
                for item in all_news_items:
                    type_counts[item.type] = type_counts.get(item.type, 0) + 1
                for item_type, count in type_counts.items():
                    logger.info(f"   {item_type}: {count}")
            else:
                logger.warning("⚠️⚠️⚠️ NO NEWS ITEMS GENERATED! ⚠️⚠️⚠️")
                logger.warning(f"   This could mean:")
                logger.warning(f"   1. No upcoming matches found in next 7 days for league {filter_league_id}")
                logger.warning(f"   2. No recent matches found in last 7 days for league {filter_league_id}")
                logger.warning(f"   3. Date filtering is excluding all matches")
                logger.warning(f"   4. All match previews failed to generate")
            logger.info("="*80)
            conn.close()
            return all_news_items[:limit]
        except Exception as e:
            logger.error(f"Error getting news feed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def get_trending_topics(self, limit: int = 10, league_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get trending rugby topics (big wins, upcoming matches, form teams) - LEAGUE-SPECIFIC
        
        Args:
            league_id: If provided, only shows trending topics for this specific league
        """
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            topics = []
            
            # LEAGUE-SPECIFIC: Filter by league_id if provided
            league_filter = ""
            league_params = []
            if league_id:
                league_filter = "AND e.league_id = ?"
                league_params = [league_id]
                logger.info(f"🎯 LEAGUE-SPECIFIC TRENDING: Filtering for league {league_id}")
            
            # 1. Get recent big wins/upsets (last 30 days if no recent games)
            query = f"""
                SELECT e.id, e.league_id, e.date_event, 
                       t1.name as home_team, t2.name as away_team,
                       e.home_score, e.away_score
                FROM event e
                LEFT JOIN team t1 ON e.home_team_id = t1.id
                LEFT JOIN team t2 ON e.away_team_id = t2.id
                WHERE e.home_score IS NOT NULL
                AND e.away_score IS NOT NULL
                AND e.date_event >= date('now', '-30 days')
                AND e.date_event < date('now')
                AND t1.name IS NOT NULL
                AND t2.name IS NOT NULL
                {league_filter}
                ORDER BY ABS(e.home_score - e.away_score) DESC
                LIMIT 5
            """
            cursor.execute(query, league_params)
            
            for row in cursor.fetchall():
                match_id, league_id, date_event, home_team, away_team, home_score, away_score = row
                if not home_team or not away_team:
                    continue
                    
                score_diff = abs(home_score - away_score)
                winner = home_team if home_score > away_score else away_team
                loser = away_team if home_score > away_score else home_team
                
                # Include all significant wins, not just > 20 points
                if score_diff > 15:
                    topics.append({
                        "type": "big_win",
                        "title": f"{winner} dominate with {max(home_score, away_score)}-{min(home_score, away_score)} victory",
                        "description": f"{winner} secured a convincing {score_diff}-point victory over {loser}",
                        "match_id": match_id,
                        "league_id": league_id,
                        "timestamp": date_event if isinstance(date_event, str) else datetime.now().isoformat()
                    })
            
            # 2. Get upcoming high-stakes matches (next 7 days for better coverage)
            query = f"""
                SELECT e.id, e.league_id, e.date_event,
                       t1.name as home_team, t2.name as away_team
                FROM event e
                LEFT JOIN team t1 ON e.home_team_id = t1.id
                LEFT JOIN team t2 ON e.away_team_id = t2.id
                WHERE e.date_event >= date('now')
                AND e.date_event <= date('now', '+7 days')
                AND e.home_team_id IS NOT NULL
                AND e.away_team_id IS NOT NULL
                AND t1.name IS NOT NULL
                AND t2.name IS NOT NULL
                {league_filter}
                ORDER BY e.date_event ASC
                LIMIT 5
            """
            cursor.execute(query, league_params)
            
            for row in cursor.fetchall():
                match_id, league_id, date_event, home_team, away_team = row
                if not home_team or not away_team:
                    continue
                    
                # Format date for display
                try:
                    if isinstance(date_event, str):
                        date_obj = datetime.fromisoformat(date_event.replace('Z', '+00:00'))
                    else:
                        date_obj = date_event
                    date_str = date_obj.strftime('%d/%m/%Y')
                except:
                    date_str = str(date_event)
                    
                topics.append({
                    "type": "upcoming_match",
                    "title": f"{home_team} vs {away_team} - {date_str}",
                    "description": f"Key fixture coming up between {home_team} and {away_team} on {date_str}",
                    "match_id": match_id,
                    "league_id": league_id,
                    "timestamp": date_event if isinstance(date_event, str) else datetime.now().isoformat()
                })
            
            # 3. Get teams with strong recent form (last 30 days for better coverage)
            # LEAGUE-SPECIFIC: Filter by league_id if provided
            form_league_filter = ""
            form_league_params = []
            if league_id:
                form_league_filter = "AND e.league_id = ?"
                form_league_params = [league_id]
            
            query = f"""
                SELECT t.id, t.name, COUNT(*) as wins
                FROM team t
                JOIN event e ON (e.home_team_id = t.id OR e.away_team_id = t.id)
                WHERE e.date_event >= date('now', '-30 days')
                AND e.date_event < date('now')
                AND e.home_score IS NOT NULL
                AND e.away_score IS NOT NULL
                AND ((e.home_team_id = t.id AND e.home_score > e.away_score)
                     OR (e.away_team_id = t.id AND e.away_score > e.home_score))
                {form_league_filter}
                GROUP BY t.id, t.name
                HAVING wins >= 2
                ORDER BY wins DESC
                LIMIT 5
            """
            cursor.execute(query, form_league_params)
            
            for row in cursor.fetchall():
                team_id, team_name, wins = row
                topics.append({
                    "type": "form_team",
                    "title": f"{team_name} on fire - {wins} wins recently",
                    "description": f"{team_name} has been in excellent form with {wins} recent victories",
                    "team_id": team_id,
                    "timestamp": datetime.now().isoformat()
                })
            
            # Sort all topics by timestamp (newest first)
            topics.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            
            logger.info(f"Generated {len(topics)} trending topics")
            conn.close()
            return topics[:limit]
        except Exception as e:
            logger.error(f"Error getting trending topics: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
