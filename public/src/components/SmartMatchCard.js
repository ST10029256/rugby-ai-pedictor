import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Box,
  Typography,
  LinearProgress,
  Chip,
  IconButton,
  Collapse,
  Grid,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import LocationOnIcon from '@mui/icons-material/LocationOn';
import AccessTimeIcon from '@mui/icons-material/AccessTime';

const SmartMatchCard = ({ matchId, newsItem = null }) => {
  const [expanded, setExpanded] = useState(false);
  const [matchData, setMatchData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // In a real implementation, fetch match data from API
    // For now, use data from newsItem if available
    if (newsItem && newsItem.match_id) {
      const stats = newsItem.related_stats || {};
      
      // Log detailed match data for debugging
      if (stats.home_team && stats.away_team) {
        console.log(`\n🎯 SmartMatchCard: ${stats.home_team} vs ${stats.away_team}`);
        console.log(`   Match ID: ${newsItem.match_id}`);
        console.log(`   Win Probability: ${(stats.win_probability * 100).toFixed(1)}% (Home)`);
        if (stats.home_form) {
          const homeWins = stats.home_form.filter(g => g[0] > g[1]).length;
          const homeWinRate = (homeWins / stats.home_form.length * 100).toFixed(1);
          console.log(`   ${stats.home_team} Form: ${stats.home_form.length} games, ${homeWinRate}% win rate`);
        }
        if (stats.away_form) {
          const awayWins = stats.away_form.filter(g => g[0] > g[1]).length;
          const awayWinRate = (awayWins / stats.away_form.length * 100).toFixed(1);
          console.log(`   ${stats.away_team} Form: ${stats.away_form.length} games, ${awayWinRate}% win rate`);
        }
      }
      
      setMatchData({
        id: newsItem.match_id,
        home_team: stats.home_team || 'Team A',
        away_team: stats.away_team || 'Team B',
        date: stats.date_event || newsItem.timestamp,
        venue: stats.venue || 'Stadium',
        win_probability: stats.win_probability || 0.65,
      });
    }
    setLoading(false);
  }, [matchId, newsItem]);

  if (loading) {
    return <Box sx={{ p: 2 }}>Loading match card...</Box>;
  }

  const homeWinProb = matchData?.win_probability || 0.5;
  const awayWinProb = 1 - homeWinProb;

  return (
    <Card
      sx={{
        mb: 2,
        backgroundColor: '#1f2937',
        border: '1px solid rgba(255, 255, 255, 0.1)',
        borderRadius: 2,
        transition: 'all 0.3s ease',
        '&:hover': {
          borderColor: '#10b981',
          boxShadow: '0 4px 12px rgba(16, 185, 129, 0.2)',
        },
      }}
    >
      <CardContent>
        {/* Match Header */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Box sx={{ flex: 1 }}>
            <Typography variant="h6" sx={{ color: '#fafafa', fontWeight: 600, mb: 1 }}>
              {matchData?.home_team || 'Home Team'} vs {matchData?.away_team || 'Away Team'}
            </Typography>
            <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                <AccessTimeIcon sx={{ fontSize: 16, color: '#9ca3af' }} />
                <Typography variant="caption" sx={{ color: '#9ca3af' }}>
                  {matchData?.date ? new Date(matchData.date).toLocaleString() : 'TBD'}
                </Typography>
              </Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                <LocationOnIcon sx={{ fontSize: 16, color: '#9ca3af' }} />
                <Typography variant="caption" sx={{ color: '#9ca3af' }}>
                  {matchData?.venue || 'Venue TBD'}
                </Typography>
              </Box>
            </Box>
          </Box>
          <IconButton
            onClick={() => setExpanded(!expanded)}
            sx={{ color: '#9ca3af' }}
            size="small"
          >
            {expanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
          </IconButton>
        </Box>

        {/* Win Probability Meter */}
        <Box sx={{ mb: 2 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
            <Typography variant="body2" sx={{ color: '#fafafa', fontWeight: 600 }}>
              {matchData?.home_team || 'Home'}
            </Typography>
            <Typography variant="body2" sx={{ color: '#fafafa', fontWeight: 600 }}>
              {matchData?.away_team || 'Away'}
            </Typography>
          </Box>
          <Box sx={{ position: 'relative' }}>
            <LinearProgress
              variant="determinate"
              value={homeWinProb * 100}
              sx={{
                height: 8,
                borderRadius: 4,
                backgroundColor: 'rgba(255, 255, 255, 0.1)',
                '& .MuiLinearProgress-bar': {
                  backgroundColor: '#10b981',
                  borderRadius: 4,
                },
              }}
            />
            <Box
              sx={{
                position: 'absolute',
                left: `${homeWinProb * 100}%`,
                top: '50%',
                transform: 'translate(-50%, -50%)',
                width: 20,
                height: 20,
                borderRadius: '50%',
                backgroundColor: '#10b981',
                border: '2px solid #1f2937',
                boxShadow: '0 2px 8px rgba(16, 185, 129, 0.4)',
              }}
            />
          </Box>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 1 }}>
            <Typography variant="caption" sx={{ color: '#10b981' }}>
              {(homeWinProb * 100).toFixed(1)}%
            </Typography>
            <Typography variant="caption" sx={{ color: '#10b981' }}>
              {(awayWinProb * 100).toFixed(1)}%
            </Typography>
          </Box>
        </Box>

        {/* Form Indicators */}
        {newsItem?.related_stats && (
          <Box sx={{ display: 'flex', gap: 1, mb: 2, flexWrap: 'wrap' }}>
            {newsItem.related_stats.home_form && newsItem.related_stats.home_form.length > 0 && (
              <Chip
                label={`${matchData?.home_team || 'Home'} Form: ${newsItem.related_stats.home_form.length} games`}
                size="small"
                sx={{
                  backgroundColor: 'rgba(16, 185, 129, 0.2)',
                  color: '#10b981',
                }}
              />
            )}
            {newsItem.related_stats.away_form && newsItem.related_stats.away_form.length > 0 && (
              <Chip
                label={`${matchData?.away_team || 'Away'} Form: ${newsItem.related_stats.away_form.length} games`}
                size="small"
                sx={{
                  backgroundColor: 'rgba(16, 185, 129, 0.2)',
                  color: '#10b981',
                }}
              />
            )}
          </Box>
        )}

        {/* News Content */}
        {newsItem && (
          <Box sx={{ mb: 2 }}>
            <Typography variant="body2" sx={{ color: '#d1d5db' }}>
              {newsItem.content}
            </Typography>
          </Box>
        )}

        {/* Expanded AI Insights */}
        <Collapse in={expanded}>
          <Box sx={{ mt: 2, pt: 2, borderTop: '1px solid rgba(255, 255, 255, 0.1)' }}>
            <Typography variant="subtitle2" sx={{ color: '#9ca3af', mb: 2 }}>
              🤖 AI Insights
            </Typography>
            <Grid container spacing={2}>
              <Grid item xs={12} sm={6}>
                <Box
                  sx={{
                    p: 2,
                    backgroundColor: 'rgba(255, 255, 255, 0.05)',
                    borderRadius: 1,
                  }}
                >
                  <Typography variant="caption" sx={{ color: '#9ca3af', display: 'block', mb: 1 }}>
                    Prediction Confidence
                  </Typography>
                  <Typography variant="h6" sx={{ color: '#fafafa' }}>
                    {Math.round(Math.max(homeWinProb, awayWinProb) * 100)}%
                  </Typography>
                </Box>
              </Grid>
              <Grid item xs={12} sm={6}>
                <Box
                  sx={{
                    p: 2,
                    backgroundColor: 'rgba(255, 255, 255, 0.05)',
                    borderRadius: 1,
                  }}
                >
                  <Typography variant="caption" sx={{ color: '#9ca3af', display: 'block', mb: 1 }}>
                    Expected Score Difference
                  </Typography>
                  <Typography variant="h6" sx={{ color: '#fafafa' }}>
                    {Math.abs((homeWinProb - awayWinProb) * 20).toFixed(1)} points
                  </Typography>
                </Box>
              </Grid>
            </Grid>

            {/* Clickable Stats */}
            {newsItem?.clickable_stats && newsItem.clickable_stats.length > 0 && (
              <Box sx={{ mt: 2 }}>
                <Typography variant="subtitle2" sx={{ color: '#9ca3af', mb: 1 }}>
                  Key Statistics
                </Typography>
                {newsItem.clickable_stats.map((stat, idx) => (
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
          </Box>
        </Collapse>
      </CardContent>
    </Card>
  );
};

export default SmartMatchCard;

