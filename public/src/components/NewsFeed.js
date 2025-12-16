import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  Box,
  Typography,
  Card,
  CardContent,
  Chip,
  IconButton,
  Collapse,
  Tabs,
  Tab,
  Grid,
  Divider,
  Stack,
  Paper,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import TrendingDownIcon from '@mui/icons-material/TrendingDown';
import SportsIcon from '@mui/icons-material/Sports';
import EventIcon from '@mui/icons-material/Event';
import WhatshotIcon from '@mui/icons-material/Whatshot';
import TimelineIcon from '@mui/icons-material/Timeline';
import ArticleIcon from '@mui/icons-material/Article';
import { getNewsFeed, getTrendingTopics } from '../firebase';
import SmartMatchCard from './SmartMatchCard';
import NewsTimeline from './NewsTimeline';
import RugbyBallLoader from './RugbyBallLoader';

// League name mapping (imported from App.js pattern)
const LEAGUE_CONFIGS = {
  4986: { name: "Rugby Championship" },
  4446: { name: "United Rugby Championship" },
  5069: { name: "Currie Cup" },
  4574: { name: "Rugby World Cup" },
  4551: { name: "Super Rugby" },
  4430: { name: "French Top 14" },
  4414: { name: "English Premiership Rugby" },
  4714: { name: "Six Nations Championship" },
  5479: { name: "Rugby Union International Friendlies" },
};

const NewsFeed = ({ userPreferences = {}, leagueId = null, leagueName = null }) => {
  const [newsItems, setNewsItems] = useState([]);
  const [trendingTopics, setTrendingTopics] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState(0);
  const [expandedItems, setExpandedItems] = useState(new Set());

  const twitterWidgetLoaded = useRef(false);

  // Get league name from prop or config
  const displayLeagueName = useMemo(() => {
    if (leagueName) return leagueName;
    if (leagueId && LEAGUE_CONFIGS[leagueId]) {
      return LEAGUE_CONFIGS[leagueId].name;
    }
    return leagueId ? `League ${leagueId}` : null;
  }, [leagueId, leagueName]);

  // Categorize news items
  const categorizedNews = useMemo(() => {
    const categories = {
      match_previews: [],
      match_recaps: [],
      lineup_changes: [],
      other: [],
    };

    newsItems.forEach(item => {
      if (item.type === 'match_preview') {
        categories.match_previews.push(item);
      } else if (item.type === 'match_recap') {
        categories.match_recaps.push(item);
      } else if (item.type === 'lineup_change' || item.type === 'injury_update') {
        categories.lineup_changes.push(item);
      } else {
        categories.other.push(item);
      }
    });

    return categories;
  }, [newsItems]);

  const loadNewsFeed = React.useCallback(async () => {
    try {
      setLoading(true);
      console.log('📰 Loading news feed...', { userPreferences, leagueId });
      console.log('🎯 LEAGUE FILTER: leagueId =', leagueId, typeof leagueId);
      console.log('📋 User preferences:', JSON.stringify(userPreferences, null, 2));
      console.log('🔢 League ID type check:', { 
        value: leagueId, 
        type: typeof leagueId, 
        isNumber: typeof leagueId === 'number',
        isString: typeof leagueId === 'string',
        parsed: leagueId ? parseInt(leagueId) : null
      });
      
      // 🎯 LEAGUE-SPECIFIC: Pass league_id to filter news for this specific league
      const requestData = {
        user_id: userPreferences.user_id,
        followed_teams: userPreferences.followed_teams || [],
        followed_leagues: userPreferences.followed_leagues || [],
        league_id: leagueId,  // NEW: Filter by specific league
        limit: 50,
      };
      console.log('📤 Request data:', requestData);
      
      const result = await getNewsFeed(requestData);

        console.log('📰 News feed response:', result);
        console.log('📊 News items received:', result?.data?.news?.length || 0);
        if (result?.data?.debug) {
          console.log('🔍 Debug info:', result.data.debug);
          console.log('   Database path:', result.data.debug.db_path);
          console.log('   Database exists:', result.data.debug.db_exists);
          console.log('   Predictor available:', result.data.debug.predictor_available);
          if (!result.data.debug.db_exists) {
            console.error('❌ Database file not found at:', result.data.debug.db_path);
            console.error('   This means Firebase Functions cannot access the database file!');
            console.error('   The database file needs to be in the rugby-ai-predictor/ directory.');
          }
        }
      
      // Check league_id of received items
      if (leagueId && result?.data?.news) {
        const mismatched = result.data.news.filter(item => item.league_id !== leagueId);
        if (mismatched.length > 0) {
          console.error(`🚨 FRONTEND ERROR: Received ${mismatched.length} items that don't match league ${leagueId}!`);
          console.error('Mismatched items:', mismatched.map(item => ({ id: item.id, league_id: item.league_id, type: item.type })));
        } else {
          console.log(`✅ All ${result.data.news.length} items match league ${leagueId}`);
        }
      }

      if (result.data) {
        if (result.data.success) {
          let news = result.data.news || [];
          
          // CRITICAL FRONTEND FILTER: Filter by league_id if specified
          // This is a safety measure in case backend filtering fails
          if (leagueId) {
            const initialCount = news.length;
            const leagueIdNum = typeof leagueId === 'string' ? parseInt(leagueId) : leagueId;
            news = news.filter(item => {
              const itemLeagueId = item.league_id;
              // Handle both string and number comparisons
              const matches = itemLeagueId === leagueIdNum || itemLeagueId === leagueId || 
                            (typeof itemLeagueId === 'string' && parseInt(itemLeagueId) === leagueIdNum) ||
                            (typeof leagueId === 'string' && itemLeagueId === parseInt(leagueId));
              if (!matches) {
                console.warn(`🚨 Frontend filter: Removing item ${item.id} (league_id=${itemLeagueId}, expected ${leagueIdNum})`);
              }
              return matches;
            });
            const removedCount = initialCount - news.length;
            if (removedCount > 0) {
              console.error(`🚨 Frontend filter removed ${removedCount} items that didn't match league ${leagueIdNum}`);
            }
            console.log(`✅ Frontend filter: ${news.length} items after filtering (removed ${removedCount})`);
          }
          
          console.log(`✅ Loaded ${news.length} news items`);
          
          // EXTENSIVE LOGGING: Log win rate calculation details for each match preview
          news.forEach((item, index) => {
            if (item.type === 'match_preview' && item.related_stats) {
              const stats = item.related_stats;
              console.log(`\n🏉 === MATCH PREVIEW ${index + 1}: ${stats.home_team} vs ${stats.away_team} ===`);
              console.log(`📅 Match Date: ${stats.date_event || item.timestamp}`);
              console.log(`🎯 Win Probability: ${(stats.win_probability * 100).toFixed(1)}% (Home)`);
              
              // Log home team form
              if (stats.home_form && stats.home_form.length > 0) {
                console.log(`\n📊 ${stats.home_team} FORM: ${stats.home_form.length} games`);
                let homeWins = 0, homeDraws = 0, homeLosses = 0;
                stats.home_form.forEach((game, idx) => {
                  const teamScore = game[0];
                  const oppScore = game[1];
                  const isWin = teamScore > oppScore;
                  const isDraw = teamScore === oppScore;
                  const result = isWin ? 'WIN' : (isDraw ? 'DRAW' : 'LOSS');
                  if (isWin) homeWins++;
                  else if (isDraw) homeDraws++;
                  else homeLosses++;
                  console.log(`  Game ${idx + 1}: ${teamScore}-${oppScore} (${result})`);
                });
                const homeWinRate = (homeWins / stats.home_form.length * 100).toFixed(1);
                console.log(`✅ ${stats.home_team} WIN RATE: ${homeWins}W/${homeDraws}D/${homeLosses}L = ${homeWinRate}%`);
              } else {
                console.log(`⚠️ ${stats.home_team}: NO FORM DATA`);
              }
              
              // Log away team form
              if (stats.away_form && stats.away_form.length > 0) {
                console.log(`\n📊 ${stats.away_team} FORM: ${stats.away_form.length} games`);
                let awayWins = 0, awayDraws = 0, awayLosses = 0;
                stats.away_form.forEach((game, idx) => {
                  const teamScore = game[0];
                  const oppScore = game[1];
                  const isWin = teamScore > oppScore;
                  const isDraw = teamScore === oppScore;
                  const result = isWin ? 'WIN' : (isDraw ? 'DRAW' : 'LOSS');
                  if (isWin) awayWins++;
                  else if (isDraw) awayDraws++;
                  else awayLosses++;
                  console.log(`  Game ${idx + 1}: ${teamScore}-${oppScore} (${result})`);
                });
                const awayWinRate = (awayWins / stats.away_form.length * 100).toFixed(1);
                console.log(`✅ ${stats.away_team} WIN RATE: ${awayWins}W/${awayDraws}D/${awayLosses}L = ${awayWinRate}%`);
              } else {
                console.log(`⚠️ ${stats.away_team}: NO FORM DATA`);
              }
              
              // Log head-to-head if available
              if (stats.head_to_head && stats.head_to_head.length > 0) {
                console.log(`\n⚔️ HEAD-TO-HEAD: ${stats.head_to_head.length} recent meetings`);
                let h2hHomeWins = 0;
                stats.head_to_head.forEach((game, idx) => {
                  const homeScore = game[0];
                  const awayScore = game[1];
                  if (homeScore > awayScore) h2hHomeWins++;
                  console.log(`  Meeting ${idx + 1}: ${homeScore}-${awayScore}`);
                });
                console.log(`✅ ${stats.home_team} won ${h2hHomeWins}/${stats.head_to_head.length} recent meetings`);
              }
              
              console.log(`\n📝 Content: ${item.content}`);
              console.log(`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n`);
            }
          });
          
          setNewsItems(news);
        } else {
          console.error('❌ News feed error:', result.data.error);
          setNewsItems([]);
        }
      } else {
        console.warn('⚠️ Unexpected response format:', result);
        setNewsItems([]);
      }
    } catch (error) {
      console.error('❌ Error loading news feed:', error);
      console.error('Error details:', error.message, error.stack);
      setNewsItems([]);
    } finally {
      setLoading(false);
    }
  }, [userPreferences, leagueId]);  // Reload when leagueId changes

  useEffect(() => {
    if (leagueId) {  // Only load if league is selected
      loadNewsFeed();
      loadTrendingTopics();
    }
    
    // Load Twitter widget script
    if (!twitterWidgetLoaded.current && typeof window !== 'undefined') {
      const script = document.createElement('script');
      script.src = 'https://platform.twitter.com/widgets.js';
      script.async = true;
      script.charset = 'utf-8';
      script.onload = () => {
        twitterWidgetLoaded.current = true;
        if (window.twttr && window.twttr.widgets) {
          window.twttr.widgets.load();
        }
      };
      document.body.appendChild(script);
      
      return () => {
        // Cleanup if needed
      };
    }
  }, [loadNewsFeed, leagueId]);  // Reload when leagueId changes


  const loadTrendingTopics = async () => {
    try {
      // 🎯 LEAGUE-SPECIFIC: Pass league_id to filter trending topics
      const result = await getTrendingTopics({ 
        limit: 10,
        league_id: leagueId  // NEW: Filter trending topics by league
      });
      if (result.data && result.data.success) {
        setTrendingTopics(result.data.topics || []);
      }
    } catch (error) {
      console.error('Error loading trending topics:', error);
    }
  };

  const toggleExpand = (itemId) => {
    const newExpanded = new Set(expandedItems);
    if (newExpanded.has(itemId)) {
      newExpanded.delete(itemId);
    } else {
      newExpanded.add(itemId);
    }
    setExpandedItems(newExpanded);
  };

  const getNewsTypeColor = (type) => {
    const colors = {
      match_preview: '#3b82f6',
      lineup_change: '#10b981',
      injury_update: '#ef4444',
      selection_surprise: '#f59e0b',
      form_analysis: '#8b5cf6',
      prediction_shift: '#ec4899',
    };
    return colors[type] || '#6b7280';
  };

  const getNewsTypeLabel = (type) => {
    const labels = {
      match_preview: 'Match Preview',
      lineup_change: 'Lineup Change',
      injury_update: 'Injury Update',
      selection_surprise: 'Selection Surprise',
      form_analysis: 'Form Analysis',
      prediction_shift: 'Prediction Shift',
    };
    return labels[type] || type;
  };

  const renderNewsItem = (item) => {
    const isExpanded = expandedItems.has(item.id);
    const hasImpact = item.impact_score !== null && item.impact_score !== 0;
    const impactColor = item.impact_score > 0 ? '#10b981' : '#ef4444';
    const ImpactIcon = item.impact_score > 0 ? TrendingUpIcon : TrendingDownIcon;

    return (
      <Card
        key={item.id}
        sx={{
          mb: 2,
          backgroundColor: '#1e293b',
          border: '1px solid rgba(255, 255, 255, 0.1)',
          borderRadius: 3,
          transition: 'all 0.3s ease',
          overflow: 'hidden',
          '&:hover': {
            borderColor: getNewsTypeColor(item.type),
            boxShadow: `0 8px 24px rgba(0, 0, 0, 0.4)`,
            transform: 'translateY(-2px)',
          },
        }}
      >
        <CardContent>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 1 }}>
            <Box sx={{ flex: 1 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1, flexWrap: 'wrap' }}>
                <Chip
                  label={getNewsTypeLabel(item.type)}
                  size="small"
                  sx={{
                    backgroundColor: `${getNewsTypeColor(item.type)}20`,
                    color: getNewsTypeColor(item.type),
                    fontWeight: 600,
                  }}
                />
                {item.league_id && (
                  <Chip
                    label={LEAGUE_CONFIGS[item.league_id]?.name || `League ${item.league_id}`}
                    size="small"
                    sx={{
                      backgroundColor: '#3b82f620',
                      color: '#3b82f6',
                      fontWeight: 600,
                      fontSize: '0.7rem',
                    }}
                  />
                )}
                {hasImpact && (
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                    <ImpactIcon sx={{ fontSize: 16, color: impactColor }} />
                    <Typography variant="caption" sx={{ color: impactColor, fontWeight: 600 }}>
                      {item.impact_score > 0 ? '+' : ''}
                      {(item.impact_score * 100).toFixed(1)}% impact
                    </Typography>
                  </Box>
                )}
              </Box>
              <Typography variant="h6" sx={{ color: '#fafafa', mb: 1, fontWeight: 600 }}>
                {item.title}
              </Typography>
              <Typography variant="body2" sx={{ color: '#d1d5db', mb: 2 }}>
                {item.content}
              </Typography>
            </Box>
            <IconButton
              onClick={() => toggleExpand(item.id)}
              sx={{ color: '#9ca3af' }}
              size="small"
            >
              {isExpanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
            </IconButton>
          </Box>

          <Collapse in={isExpanded}>
            <Box sx={{ mt: 2, pt: 2, borderTop: '1px solid rgba(255, 255, 255, 0.1)' }}>
              {/* Clickable Stats */}
              {item.clickable_stats && item.clickable_stats.length > 0 && (
                <Box sx={{ mb: 2 }}>
                  <Typography variant="subtitle2" sx={{ color: '#9ca3af', mb: 1 }}>
                    Key Stats
                  </Typography>
                  {item.clickable_stats.map((stat, idx) => (
                    <Box
                      key={idx}
                      sx={{
                        p: 1.5,
                        mb: 1,
                        backgroundColor: 'rgba(255, 255, 255, 0.05)',
                        borderRadius: 1,
                        cursor: 'pointer',
                        transition: 'all 0.2s ease',
                        '&:hover': {
                          backgroundColor: 'rgba(255, 255, 255, 0.1)',
                        },
                      }}
                    >
                      <Typography variant="body2" sx={{ color: '#fafafa', fontWeight: 600 }}>
                        {stat.label}
                      </Typography>
                      <Typography variant="caption" sx={{ color: '#9ca3af', mt: 0.5, display: 'block' }}>
                        {stat.explanation}
                      </Typography>
                    </Box>
                  ))}
                </Box>
              )}

              {/* Embedded Content */}
              {item.embedded_content && (
                <Box sx={{ mb: 2 }}>
                  <Typography variant="subtitle2" sx={{ color: '#9ca3af', mb: 1 }}>
                    Official Content
                  </Typography>
                  <Box
                    sx={{
                      p: 2,
                      backgroundColor: 'rgba(255, 255, 255, 0.05)',
                      borderRadius: 1,
                    }}
                  >
                    {item.embedded_content.platform === 'instagram' && (
                      <iframe
                        title={`Instagram post from ${item.embedded_content.context || 'official account'}`}
                        src={item.embedded_content.embed_url}
                        width="100%"
                        height="500"
                        frameBorder="0"
                        scrolling="no"
                        allowTransparency="true"
                        style={{ borderRadius: '8px' }}
                      />
                    )}
                    {item.embedded_content.platform === 'twitter' && (
                      <Box sx={{ mt: 2 }}>
                        <blockquote className="twitter-tweet" data-theme="dark">
                          <a href={item.embedded_content.url} aria-label="View tweet on Twitter">
                            View tweet
                          </a>
                        </blockquote>
                        {twitterWidgetLoaded.current && window.twttr && window.twttr.widgets && (
                          <script>{window.twttr.widgets.load()}</script>
                        )}
                      </Box>
                    )}
                    {item.embedded_content.ai_explanation && (
                      <Typography variant="caption" sx={{ color: '#10b981', mt: 1, display: 'block' }}>
                        💡 {item.embedded_content.ai_explanation}
                      </Typography>
                    )}
                  </Box>
                </Box>
              )}

              {/* Related Stats */}
              {item.related_stats && Object.keys(item.related_stats).length > 0 && (
                <Box>
                  <Typography variant="subtitle2" sx={{ color: '#9ca3af', mb: 1 }}>
                    Related Data
                  </Typography>
                  <Typography variant="caption" sx={{ color: '#6b7280' }}>
                    {JSON.stringify(item.related_stats, null, 2)}
                  </Typography>
                </Box>
              )}
            </Box>
          </Collapse>

          <Typography variant="caption" sx={{ color: '#6b7280', mt: 1, display: 'block' }}>
            {new Date(item.timestamp).toLocaleString()}
          </Typography>
        </CardContent>
      </Card>
    );
  };

  // Prevent body scroll when loading
  useEffect(() => {
    if (loading) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [loading]);

  if (loading) {
    return (
      <Box sx={{ 
        display: 'flex', 
        justifyContent: 'center', 
        alignItems: 'center', 
        minHeight: 'calc(100vh - 200px)', 
        height: '100vh',
        width: '100%',
        position: 'relative'
      }}>
        <RugbyBallLoader size={120} color="#10b981" />
      </Box>
    );
  }

  return (
    <Box sx={{ 
      width: '100%', 
      maxWidth: { xs: '100%', sm: '100%', md: '1400px' }, 
      mx: 'auto', 
      p: { xs: 2, sm: 3, md: 4 },
      backgroundColor: 'transparent', // Independent - no background dependency
      minHeight: 'calc(100vh - 200px)',
      position: 'relative',
      overflowX: 'hidden',
      overflowY: loading ? 'hidden' : 'visible',
      display: 'flex',
      boxSizing: 'border-box',
      flexDirection: 'column',
    }}>
      {/* Header Section - Independent and Clean */}
      <Paper
        elevation={0}
        sx={{
          background: 'linear-gradient(135deg, #1e293b 0%, #0f172a 100%)',
          borderRadius: 3,
          p: 3,
          mb: 4,
          border: '1px solid rgba(255, 255, 255, 0.1)',
          width: '100%',
          maxWidth: '100%',
        }}
      >
        <Stack direction="row" spacing={2} alignItems="center" justifyContent="flex-start" flexWrap="wrap">
          <Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
              <ArticleIcon 
                sx={{ 
                  fontSize: { xs: '2rem', sm: '2.5rem', md: '3rem' },
                  background: 'linear-gradient(135deg, #10b981 0%, #3b82f6 100%)',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                  color: '#10b981',
                }} 
              />
              <Typography 
                variant="h3" 
                sx={{ 
                  color: '#fafafa', 
                  fontWeight: 800,
                  fontSize: { xs: '1.75rem', sm: '2.25rem', md: '2.75rem' },
                  mb: 0.5,
                  background: 'linear-gradient(135deg, #10b981 0%, #3b82f6 100%)',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                }}
              >
                Rugby News Hub
              </Typography>
            </Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 1 }}>
              {displayLeagueName ? (
                <>
                  <Chip
                    icon={<SportsIcon sx={{ fontSize: '1rem !important' }} />}
                    label={displayLeagueName}
                    sx={{
                      backgroundColor: '#10b981',
                      color: '#fff',
                      fontWeight: 700,
                      fontSize: '0.875rem',
                      px: 1,
                      height: '32px',
                      '& .MuiChip-icon': {
                        color: '#fff',
                      },
                    }}
                  />
                  <Typography variant="body2" sx={{ color: '#94a3b8', ml: 1 }}>
                    League-specific news and updates
                  </Typography>
                </>
              ) : (
                <>
                  <Chip
                    icon={<SportsIcon sx={{ fontSize: '1rem !important' }} />}
                    label="All Leagues"
                    sx={{
                      backgroundColor: '#3b82f6',
                      color: '#fff',
                      fontWeight: 700,
                      fontSize: '0.875rem',
                      px: 1,
                      height: '32px',
                      '& .MuiChip-icon': {
                        color: '#fff',
                      },
                    }}
                  />
                  <Typography variant="body2" sx={{ color: '#94a3b8', ml: 1 }}>
                    News from all leagues
                  </Typography>
                </>
              )}
            </Box>
          </Box>
        </Stack>
      </Paper>

      {/* Enhanced Tabs with Icons */}
      <Box sx={{ width: '100%', maxWidth: '100%', mb: 4 }}>
        <Tabs
          value={activeTab}
          onChange={(e, newValue) => setActiveTab(newValue)}
          variant="scrollable"
          scrollButtons="auto"
          allowScrollButtonsMobile
          sx={{
            width: '100%',
            '& .MuiTab-root': {
              color: '#94a3b8',
              fontWeight: 600,
              fontSize: '0.95rem',
              textTransform: 'none',
              minHeight: 64,
              minWidth: { xs: 120, sm: 'auto' }, // Ensure tabs have minimum width on mobile
              '&.Mui-selected': {
                color: '#10b981',
              },
            },
            '& .MuiTabs-indicator': {
              backgroundColor: '#10b981',
              height: 3,
              borderRadius: '3px 3px 0 0',
            },
            '& .MuiTabs-scrollButtons': {
              color: '#94a3b8',
              '&.Mui-disabled': {
                opacity: 0.3,
              },
            },
          }}
        >
        <Tab 
          icon={<EventIcon sx={{ mb: 0.5 }} />} 
          iconPosition="start"
          label={displayLeagueName ? `${displayLeagueName} News` : "All Leagues News"} 
        />
        <Tab 
          icon={<WhatshotIcon sx={{ mb: 0.5 }} />} 
          iconPosition="start"
          label="Trending" 
        />
        <Tab 
          icon={<TimelineIcon sx={{ mb: 0.5 }} />} 
          iconPosition="start"
          label="Timeline" 
        />
        </Tabs>
      </Box>

      {activeTab === 0 && (
        <Box sx={{ 
          minHeight: 'calc(100vh - 300px)', 
          display: 'flex', 
          flexDirection: 'column',
          width: '100%',
          maxWidth: '100%',
          mx: 'auto',
          position: 'relative',
          overflowY: loading ? 'hidden' : 'auto',
          overflowX: 'hidden',
        }}>
          {loading ? (
            <Box sx={{ 
              display: 'flex', 
              justifyContent: 'center', 
              alignItems: 'center', 
              width: '100%',
              height: 'calc(100vh - 300px)',
              minHeight: 'calc(100vh - 300px)',
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              zIndex: 10,
            }}>
              <RugbyBallLoader size={100} color="#10b981" />
            </Box>
          ) : newsItems.length === 0 ? (
            <Paper
              elevation={0}
              sx={{
                textAlign: 'center',
                py: 8,
                px: 3,
                backgroundColor: '#1e293b',
                borderRadius: 3,
                border: '1px solid rgba(255, 255, 255, 0.1)',
              }}
            >
              <EventIcon sx={{ fontSize: 64, color: '#475569', mb: 2 }} />
              <Typography variant="h5" sx={{ color: '#cbd5e1', mb: 2, fontWeight: 600 }}>
                {displayLeagueName ? `No news for ${displayLeagueName}` : 'No news items found'}
              </Typography>
              <Typography variant="body1" sx={{ color: '#94a3b8', maxWidth: '500px', mx: 'auto' }}>
                {displayLeagueName 
                  ? `No upcoming matches or recent news for ${displayLeagueName} in the next 7 days. Check back later for updates.`
                  : 'No news items available from any league at the moment. This could mean no upcoming matches or a connection issue.'}
              </Typography>
            </Paper>
          ) : (
            <Stack spacing={4} sx={{ width: '100%', maxWidth: '100%' }}>
              {/* Match Previews Section */}
              {categorizedNews.match_previews.length > 0 && (
                <Box sx={{ width: '100%' }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 3 }}>
                    <SportsIcon sx={{ color: '#10b981', fontSize: 28 }} />
                    <Typography variant="h5" sx={{ color: '#fafafa', fontWeight: 700 }}>
                      Upcoming Matches
                    </Typography>
                    <Chip 
                      label={categorizedNews.match_previews.length} 
                      size="small" 
                      sx={{ 
                        backgroundColor: '#10b98120', 
                        color: '#10b981',
                        fontWeight: 600,
                      }} 
                    />
                  </Box>
                  <Grid container spacing={{ xs: 0, sm: 3 }} sx={{ width: '100%', mx: 0 }}>
                    {categorizedNews.match_previews.map((item) => (
                      <Grid item xs={12} key={item.id} sx={{ width: '100%', mb: { xs: 2, sm: 0 } }}>
                        {item.match_id ? (
                          <SmartMatchCard matchId={item.match_id} newsItem={item} />
                        ) : (
                          renderNewsItem(item)
                        )}
                      </Grid>
                    ))}
                  </Grid>
                </Box>
              )}

              {/* Match Recaps Section */}
              {categorizedNews.match_recaps.length > 0 && (
                <Box>
                  <Divider sx={{ my: 4, borderColor: 'rgba(255, 255, 255, 0.1)' }} />
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 3 }}>
                    <EventIcon sx={{ color: '#3b82f6', fontSize: 28 }} />
                    <Typography variant="h5" sx={{ color: '#fafafa', fontWeight: 700 }}>
                      Recent Results
                    </Typography>
                    <Chip 
                      label={categorizedNews.match_recaps.length} 
                      size="small" 
                      sx={{ 
                        backgroundColor: '#3b82f620', 
                        color: '#3b82f6',
                        fontWeight: 600,
                      }} 
                    />
                  </Box>
                  <Grid container spacing={{ xs: 0, sm: 2 }} sx={{ width: '100%', mx: 0 }}>
                    {categorizedNews.match_recaps.map((item) => (
                      <Grid item xs={12} sm={6} key={item.id} sx={{ width: '100%', mb: { xs: 2, sm: 0 } }}>
                        {renderNewsItem(item)}
                      </Grid>
                    ))}
                  </Grid>
                </Box>
              )}

              {/* Lineup Changes & Updates Section */}
              {categorizedNews.lineup_changes.length > 0 && (
                <Box>
                  <Divider sx={{ my: 4, borderColor: 'rgba(255, 255, 255, 0.1)' }} />
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 3 }}>
                    <WhatshotIcon sx={{ color: '#f59e0b', fontSize: 28 }} />
                    <Typography variant="h5" sx={{ color: '#fafafa', fontWeight: 700 }}>
                      Team Updates
                    </Typography>
                    <Chip 
                      label={categorizedNews.lineup_changes.length} 
                      size="small" 
                      sx={{ 
                        backgroundColor: '#f59e0b20', 
                        color: '#f59e0b',
                        fontWeight: 600,
                      }} 
                    />
                  </Box>
                  <Grid container spacing={{ xs: 0, sm: 2 }} sx={{ width: '100%', mx: 0 }}>
                    {categorizedNews.lineup_changes.map((item) => (
                      <Grid item xs={12} sm={6} md={4} key={item.id} sx={{ width: '100%', mb: { xs: 2, sm: 0 } }}>
                        {renderNewsItem(item)}
                      </Grid>
                    ))}
                  </Grid>
                </Box>
              )}

              {/* Other News Section */}
              {categorizedNews.other.length > 0 && (
                <Box>
                  <Divider sx={{ my: 4, borderColor: 'rgba(255, 255, 255, 0.1)' }} />
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 3 }}>
                    <Typography variant="h5" sx={{ color: '#fafafa', fontWeight: 700 }}>
                      More News
                    </Typography>
                    <Chip 
                      label={categorizedNews.other.length} 
                      size="small" 
                      sx={{ 
                        backgroundColor: '#8b5cf620', 
                        color: '#8b5cf6',
                        fontWeight: 600,
                      }} 
                    />
                  </Box>
                  <Grid container spacing={{ xs: 0, sm: 2 }} sx={{ width: '100%', mx: 0 }}>
                    {categorizedNews.other.map((item) => (
                      <Grid item xs={12} sm={6} key={item.id} sx={{ width: '100%', mb: { xs: 2, sm: 0 } }}>
                        {renderNewsItem(item)}
                      </Grid>
                    ))}
                  </Grid>
                </Box>
              )}
            </Stack>
          )}
        </Box>
      )}

      {activeTab === 1 && (
        <Box sx={{ 
          minHeight: 'calc(100vh - 300px)', 
          display: 'flex', 
          flexDirection: 'column',
          width: '100%',
          maxWidth: '100%',
          mx: 'auto',
          position: 'relative',
          overflowY: loading ? 'hidden' : 'auto',
          overflowX: 'hidden',
        }}>
          {loading ? (
            <Box sx={{ 
              display: 'flex', 
              justifyContent: 'center', 
              alignItems: 'center', 
              width: '100%',
              height: 'calc(100vh - 300px)',
              minHeight: 'calc(100vh - 300px)',
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              zIndex: 10,
            }}>
              <RugbyBallLoader size={100} color="#10b981" />
            </Box>
          ) : trendingTopics.length === 0 ? (
            <Paper
              elevation={0}
              sx={{
                textAlign: 'center',
                py: 8,
                px: 3,
                backgroundColor: '#1e293b',
                borderRadius: 3,
                border: '1px solid rgba(255, 255, 255, 0.1)',
              }}
            >
              <WhatshotIcon sx={{ fontSize: 64, color: '#475569', mb: 2 }} />
              <Typography variant="h5" sx={{ color: '#cbd5e1', mb: 2, fontWeight: 600 }}>
                {displayLeagueName ? `No trending topics for ${displayLeagueName}` : 'No trending topics'}
              </Typography>
              <Typography variant="body1" sx={{ color: '#94a3b8', maxWidth: '500px', mx: 'auto' }}>
                {displayLeagueName 
                  ? `Check back later for trending news and updates from ${displayLeagueName}.`
                  : 'No trending topics available at the moment.'}
              </Typography>
            </Paper>
          ) : (
            <Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 3 }}>
                <WhatshotIcon sx={{ color: '#f59e0b', fontSize: 28 }} />
                <Typography variant="h5" sx={{ color: '#fafafa', fontWeight: 700 }}>
                  Trending Now
                </Typography>
                <Chip 
                  label={trendingTopics.length} 
                  size="small" 
                  sx={{ 
                    backgroundColor: '#f59e0b20', 
                    color: '#f59e0b',
                    fontWeight: 600,
                  }} 
                />
              </Box>
              <Grid container spacing={{ xs: 0, sm: 3 }} sx={{ width: '100%', mx: 0 }}>
                {trendingTopics.map((topic, idx) => (
                  <Grid item xs={12} sm={6} md={4} key={idx} sx={{ width: '100%', mb: { xs: 2, sm: 0 } }}>
                    <Card
                      sx={{
                        backgroundColor: '#1e293b',
                        border: '1px solid rgba(255, 255, 255, 0.1)',
                        borderRadius: 3,
                        p: 3,
                        height: '100%',
                        transition: 'all 0.3s ease',
                        '&:hover': {
                          borderColor: '#f59e0b',
                          boxShadow: '0 8px 24px rgba(245, 158, 11, 0.2)',
                          transform: 'translateY(-4px)',
                        },
                      }}
                    >
                      <Typography variant="h6" sx={{ color: '#fafafa', mb: 2, fontWeight: 600, minHeight: 56 }}>
                        {topic.title}
                      </Typography>
                      {topic.description && (
                        <Typography variant="body2" sx={{ color: '#94a3b8', mb: 2 }}>
                          {topic.description}
                        </Typography>
                      )}
                      <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mt: 2 }}>
                        <Chip
                          label={topic.type?.replace('_', ' ') || 'Topic'}
                          size="small"
                          sx={{
                            backgroundColor: '#10b98120',
                            color: '#10b981',
                            fontWeight: 600,
                            textTransform: 'capitalize',
                          }}
                        />
                        {topic.league_id && (
                          <Chip
                            icon={<SportsIcon sx={{ fontSize: '0.875rem !important' }} />}
                            label={LEAGUE_CONFIGS[topic.league_id]?.name || `League ${topic.league_id}`}
                            size="small"
                            sx={{
                              backgroundColor: '#3b82f620',
                              color: '#3b82f6',
                              fontSize: '0.75rem',
                              fontWeight: 600,
                            }}
                          />
                        )}
                      </Box>
                    </Card>
                  </Grid>
                ))}
              </Grid>
            </Box>
          )}
        </Box>
      )}

      {activeTab === 2 && (
        <Box sx={{ width: '100%', maxWidth: '100%', mx: 'auto' }}>
          <NewsTimeline newsItems={newsItems} leagueId={leagueId} />
        </Box>
      )}
    </Box>
  );
};

export default NewsFeed;

