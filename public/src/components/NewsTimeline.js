import React from 'react';
import {
  Box,
  Typography,
  Card,
  CardContent,
  Chip,
  Divider,
  Avatar,
  Stack,
  Paper,
} from '@mui/material';
import EventIcon from '@mui/icons-material/Event';
import SportsIcon from '@mui/icons-material/Sports';
import NotificationsIcon from '@mui/icons-material/Notifications';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import TrendingDownIcon from '@mui/icons-material/TrendingDown';
import ScheduleIcon from '@mui/icons-material/Schedule';
import LocationOnIcon from '@mui/icons-material/LocationOn';

const NewsTimeline = ({ newsItems = [], leagueId = null }) => {
  // 🎯 LEAGUE-SPECIFIC: Filter timeline by league if provided
  let filteredItems = newsItems;
  if (leagueId) {
    filteredItems = newsItems.filter((item) => item.league_id === leagueId);
  }
  
  // Group news items by match and sort by timestamp (newest first)
  const timelineItems = filteredItems
    .filter((item) => item.match_id || item.type === 'match_preview' || item.type === 'match_recap')
    .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
    .slice(0, 20); // Limit to 20 most recent items

  const getTimelineIcon = (type) => {
    switch (type) {
      case 'match_preview':
        return <SportsIcon sx={{ fontSize: '1.2rem' }} />;
      case 'match_recap':
        return <EventIcon sx={{ fontSize: '1.2rem' }} />;
      case 'lineup_change':
      case 'injury_update':
        return <NotificationsIcon sx={{ fontSize: '1.2rem' }} />;
      case 'form_analysis':
        return <TrendingUpIcon sx={{ fontSize: '1.2rem' }} />;
      default:
        return <EventIcon sx={{ fontSize: '1.2rem' }} />;
    }
  };

  const getTimelineColor = (type) => {
    const colors = {
      match_preview: '#3b82f6',
      match_recap: '#8b5cf6',
      lineup_change: '#10b981',
      injury_update: '#ef4444',
      selection_surprise: '#f59e0b',
      form_analysis: '#8b5cf6',
      prediction_shift: '#ec4899',
    };
    return colors[type] || '#6b7280';
  };

  const getTeamLogos = (item) => {
    const stats = item.related_stats || {};
    return {
      homeLogo: stats.home_logo || stats.home_team_logo,
      awayLogo: stats.away_logo || stats.away_team_logo,
      homeTeam: stats.home_team,
      awayTeam: stats.away_team,
    };
  };

  const formatTimeAgo = (timestamp) => {
    const now = new Date();
    const time = new Date(timestamp);
    const diffMs = now - time;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return time.toLocaleDateString();
  };

  if (timelineItems.length === 0) {
    return (
      <Box sx={{ textAlign: 'center', py: 8 }}>
        <EventIcon sx={{ fontSize: '4rem', color: '#4b5563', mb: 2 }} />
        <Typography variant="h6" sx={{ color: '#6b7280', mb: 2 }}>
          No timeline events available
        </Typography>
        <Typography variant="body2" sx={{ color: '#4b5563' }}>
          Timeline shows squad announcements, lineup confirmations, and match updates
        </Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ 
      width: '100%', 
      maxWidth: '100%',
      mx: 'auto', 
      px: 0,
    }}>
      <Box sx={{ mb: 4, textAlign: 'left' }}>
        <Typography 
          variant="h5" 
          sx={{ 
            color: '#fafafa', 
            mb: 1, 
            fontWeight: 700,
            background: 'linear-gradient(135deg, #10b981 0%, #3b82f6 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            textAlign: 'left',
          }}
        >
          Match Timeline
        </Typography>
        <Typography variant="body2" sx={{ color: '#9ca3af', textAlign: 'left' }}>
          Latest updates, announcements, and match events
        </Typography>
      </Box>

      <Box sx={{ position: 'relative', pl: { xs: 1, sm: 2 }, ml: 0 }}>
        {/* Main timeline line */}
        <Box
          sx={{
            position: 'absolute',
            left: { xs: '8px', sm: '12px' },
            top: 0,
            bottom: 0,
            width: '3px',
            background: 'linear-gradient(180deg, #10b981 0%, #3b82f6 50%, rgba(59, 130, 246, 0.3) 100%)',
            borderRadius: '2px',
          }}
        />

        <Stack spacing={3}>
          {timelineItems.map((item, idx) => {
            const logos = getTeamLogos(item);
            const isMatchPreview = item.type === 'match_preview' || item.type === 'match_recap';
            
            return (
              <Box key={item.id} sx={{ position: 'relative' }}>
                {/* Timeline dot with glow effect */}
                <Box
                  sx={{
                    position: 'absolute',
                    left: { xs: '-20px', sm: '-24px' },
                    top: 0,
                    width: { xs: '20px', sm: '28px' },
                    height: { xs: '20px', sm: '28px' },
                    borderRadius: '50%',
                    background: `linear-gradient(135deg, ${getTimelineColor(item.type)} 0%, ${getTimelineColor(item.type)}cc 100%)`,
                    color: '#fff',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    zIndex: 2,
                    boxShadow: `0 0 20px ${getTimelineColor(item.type)}40, 0 4px 12px rgba(0, 0, 0, 0.3)`,
                    border: '3px solid #0f172a',
                  }}
                >
                  {getTimelineIcon(item.type)}
                </Box>

                {/* Timeline card */}
                <Paper
                  elevation={0}
                  sx={{
                    ml: { xs: 1.5, sm: 2.5 },
                    width: '100%',
                    maxWidth: '100%',
                    background: 'linear-gradient(135deg, #1e293b 0%, #0f172a 100%)',
                    border: `1px solid ${getTimelineColor(item.type)}30`,
                    borderRadius: 3,
                    overflow: 'hidden',
                  }}
                >
                  {/* Header with gradient */}
                  <Box
                    sx={{
                      background: `linear-gradient(135deg, ${getTimelineColor(item.type)}20 0%, ${getTimelineColor(item.type)}05 100%)`,
                      p: 2,
                      borderBottom: `1px solid ${getTimelineColor(item.type)}20`,
                    }}
                  >
                    <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap">
                      <Chip
                        icon={getTimelineIcon(item.type)}
                        label={item.type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                        size="small"
                        sx={{
                          backgroundColor: `${getTimelineColor(item.type)}30`,
                          color: getTimelineColor(item.type),
                          fontWeight: 700,
                          fontSize: '0.75rem',
                          height: '28px',
                          border: `1px solid ${getTimelineColor(item.type)}40`,
                        }}
                      />
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, ml: 'auto' }}>
                        <ScheduleIcon sx={{ fontSize: '0.875rem', color: '#9ca3af' }} />
                        <Typography variant="caption" sx={{ color: '#9ca3af', fontWeight: 500 }}>
                          {formatTimeAgo(item.timestamp)}
                        </Typography>
                      </Box>
                    </Stack>
                  </Box>

                  <CardContent sx={{ p: 3 }}>
                    {/* Match preview with team logos */}
                    {isMatchPreview && (logos.homeTeam || logos.awayTeam) && (
                      <Box sx={{ mb: 2, p: 2, backgroundColor: 'rgba(255, 255, 255, 0.03)', borderRadius: 2 }}>
                        <Stack direction="row" spacing={2} alignItems="center" justifyContent="center">
                          {/* Home team */}
                          <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1 }}>
                            {logos.homeLogo ? (
                              <Avatar
                                src={logos.homeLogo}
                                alt={logos.homeTeam}
                                sx={{
                                  width: 56,
                                  height: 56,
                                  border: '2px solid rgba(255, 255, 255, 0.1)',
                                  boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)',
                                }}
                              >
                                {logos.homeTeam?.[0] || 'H'}
                              </Avatar>
                            ) : (
                              <Avatar
                                sx={{
                                  width: 56,
                                  height: 56,
                                  backgroundColor: '#3b82f6',
                                  border: '2px solid rgba(255, 255, 255, 0.1)',
                                }}
                              >
                                {logos.homeTeam?.[0] || 'H'}
                              </Avatar>
                            )}
                            <Typography variant="body2" sx={{ color: '#fafafa', fontWeight: 600, textAlign: 'center', maxWidth: '120px' }}>
                              {logos.homeTeam || 'Home'}
                            </Typography>
                          </Box>

                          {/* VS */}
                          <Typography variant="h6" sx={{ color: '#6b7280', fontWeight: 700, px: 2 }}>
                            VS
                          </Typography>

                          {/* Away team */}
                          <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1 }}>
                            {logos.awayLogo ? (
                              <Avatar
                                src={logos.awayLogo}
                                alt={logos.awayTeam}
                                sx={{
                                  width: 56,
                                  height: 56,
                                  border: '2px solid rgba(255, 255, 255, 0.1)',
                                  boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)',
                                }}
                              >
                                {logos.awayTeam?.[0] || 'A'}
                              </Avatar>
                            ) : (
                              <Avatar
                                sx={{
                                  width: 56,
                                  height: 56,
                                  backgroundColor: '#ef4444',
                                  border: '2px solid rgba(255, 255, 255, 0.1)',
                                }}
                              >
                                {logos.awayTeam?.[0] || 'A'}
                              </Avatar>
                            )}
                            <Typography variant="body2" sx={{ color: '#fafafa', fontWeight: 600, textAlign: 'center', maxWidth: '120px' }}>
                              {logos.awayTeam || 'Away'}
                            </Typography>
                          </Box>
                        </Stack>
                      </Box>
                    )}

                    {/* Title */}
                    <Typography 
                      variant="h6" 
                      sx={{ 
                        color: '#fafafa', 
                        mb: 1.5, 
                        fontWeight: 700,
                        fontSize: '1.1rem',
                        lineHeight: 1.4,
                      }}
                    >
                      {item.title}
                    </Typography>

                    {/* Content */}
                    <Typography 
                      variant="body2" 
                      sx={{ 
                        color: '#d1d5db', 
                        lineHeight: 1.7,
                        mb: item.win_probability_change ? 2 : 0,
                      }}
                    >
                      {item.content}
                    </Typography>

                    {/* Win probability change */}
                    {item.win_probability_change && (
                      <Box 
                        sx={{ 
                          mt: 2, 
                          p: 2, 
                          background: item.win_probability_change > 0 
                            ? 'linear-gradient(135deg, rgba(16, 185, 129, 0.15) 0%, rgba(16, 185, 129, 0.05) 100%)'
                            : 'linear-gradient(135deg, rgba(239, 68, 68, 0.15) 0%, rgba(239, 68, 68, 0.05) 100%)',
                          borderRadius: 2,
                          border: `1px solid ${item.win_probability_change > 0 ? '#10b981' : '#ef4444'}30`,
                        }}
                      >
                        <Stack direction="row" spacing={1} alignItems="center">
                          {item.win_probability_change > 0 ? (
                            <TrendingUpIcon sx={{ color: '#10b981', fontSize: '1.25rem' }} />
                          ) : (
                            <TrendingDownIcon sx={{ color: '#ef4444', fontSize: '1.25rem' }} />
                          )}
                          <Typography 
                            variant="body2" 
                            sx={{ 
                              color: item.win_probability_change > 0 ? '#10b981' : '#ef4444', 
                              fontWeight: 700,
                            }}
                          >
                            Win Probability: {item.win_probability_change > 0 ? '+' : ''}
                            {(item.win_probability_change * 100).toFixed(1)}%
                          </Typography>
                        </Stack>
                      </Box>
                    )}

                    {/* Match date if available */}
                    {item.related_stats?.date_event && (
                      <Box sx={{ mt: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                        <LocationOnIcon sx={{ fontSize: '1rem', color: '#6b7280' }} />
                        <Typography variant="caption" sx={{ color: '#9ca3af' }}>
                          {new Date(item.related_stats.date_event).toLocaleDateString('en-US', {
                            weekday: 'long',
                            year: 'numeric',
                            month: 'long',
                            day: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </Typography>
                      </Box>
                    )}
                  </CardContent>
                </Paper>
              </Box>
            );
          })}
        </Stack>
      </Box>
    </Box>
  );
};

export default NewsTimeline;

