import React, { useState, useEffect } from 'react';
import { Box, Typography, CircularProgress } from '@mui/material';
import { getLiveMatches } from '../firebase';

function LiveMatches({ leagueId }) {
  const [matches, setMatches] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!leagueId) return;

    const fetchMatches = async () => {
      setLoading(true);
      try {
        const result = await getLiveMatches({ league_id: leagueId });
        // Handle both success and error responses
        if (result && result.data) {
          if (result.data.matches) {
            setMatches(result.data.matches);
          } else if (result.data.error) {
            console.warn('Live matches API error:', result.data.error);
            setMatches([]);
          } else {
            setMatches([]);
          }
        } else {
          setMatches([]);
        }
      } catch (err) {
        // Silently handle errors - live matches are optional
        console.warn('Live matches not available:', err.message || err);
        setMatches([]);
      } finally {
        setLoading(false);
      }
    };

    fetchMatches();
    // Refresh every 60 seconds (only if component is still mounted)
    const interval = setInterval(() => {
      fetchMatches().catch(() => {
        // Silently handle interval errors
      });
    }, 60000);
    return () => clearInterval(interval);
  }, [leagueId]);

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (matches.length === 0 && !loading) {
    // Don't show anything if there are no matches - matches are optional
    return null;
  }

  return (
    <Box sx={{ mb: 4 }}>
      <Typography variant="h6" sx={{ mb: 2, color: '#fafafa', fontWeight: 700 }}>
        🔴 Live Matches (Next 24 Hours)
      </Typography>
      <Typography variant="caption" sx={{ display: 'block', mb: 2, color: '#a0aec0' }}>
        💾 Live scores update every minute from Highlightly API
      </Typography>

      {matches.slice(0, 15).map((match) => {
        const liveState = match.state || 'Not started';
        const stateClass = liveState.toLowerCase().replace(/\s+/g, '-');
        const homeScore = match.home_score || 0;
        const awayScore = match.away_score || 0;
        const formattedDate = match.formatted_date || match.date_event?.split('T')[0] || 'TBD';
        const startTime = match.start_time || 'TBD';
        const gameTime = match.game_time;

        return (
          <Box key={match.match_id || match.id} className="live-match-card">
            <Box className="live-match-header">
              <Typography className="live-match-title">
                🏉 {match.home_team} vs {match.away_team}
              </Typography>
              <Box className={`live-match-status ${stateClass}`}>
                {liveState}
              </Box>
            </Box>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
              <Typography sx={{ color: '#6c757d', fontSize: '0.9rem' }}>
                📅 {formattedDate}
              </Typography>
              <Box className={gameTime ? 'live-game-time' : 'match-start-time'}>
                {gameTime ? `⏱️ ${gameTime}'` : `🕐 ${startTime}`}
              </Box>
            </Box>

            <Box sx={{ display: 'grid', gridTemplateColumns: '2fr 1fr 2fr', gap: 2, alignItems: 'center' }}>
              <Box>
                <Typography className="live-team-name">{match.home_team}</Typography>
                <Typography className="live-score">🔴 Live: {homeScore}</Typography>
              </Box>
              <Box sx={{ textAlign: 'center' }}>
                <Typography className="live-vs-text">VS</Typography>
              </Box>
              <Box>
                <Typography className="live-team-name">{match.away_team}</Typography>
                <Typography className="live-score">🔴 Live: {awayScore}</Typography>
              </Box>
            </Box>
          </Box>
        );
      })}
    </Box>
  );
}

export default LiveMatches;
