import React, { useState, useEffect } from 'react';
import { Box, Paper, Typography, CircularProgress, Alert, Card, CardContent } from '@mui/material';
import { getUpcomingMatches } from '../firebase';

function UpcomingMatches({ leagueId }) {
  const [matches, setMatches] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!leagueId) return;

    const fetchMatches = async () => {
      setLoading(true);
      setError(null);
      try {
        const result = await getUpcomingMatches({ league_id: leagueId, limit: 20 });
        setMatches(result.data.matches || []);
      } catch (err) {
        setError(err.message || 'Failed to load upcoming matches');
      } finally {
        setLoading(false);
      }
    };

    fetchMatches();
  }, [leagueId]);

  if (loading) {
    return (
      <Paper sx={{ p: 3 }}>
        <Typography variant="h6" gutterBottom>
          Upcoming Matches
        </Typography>
        <Box display="flex" justifyContent="center" p={3}>
          <CircularProgress />
        </Box>
      </Paper>
    );
  }

  if (error) {
    return (
      <Paper sx={{ p: 3 }}>
        <Typography variant="h6" gutterBottom>
          Upcoming Matches
        </Typography>
        <Alert severity="error">{error}</Alert>
      </Paper>
    );
  }

  return (
    <Paper sx={{ p: 3 }}>
      <Typography variant="h6" gutterBottom>
        Upcoming Matches
      </Typography>
      {matches.length === 0 ? (
        <Typography color="text.secondary">No upcoming matches</Typography>
      ) : (
        <Box sx={{ mt: 2 }}>
          {matches.map((match) => (
            <Card key={match.id} sx={{ mb: 2 }}>
              <CardContent>
                <Typography variant="h6">
                  {match.home_team} vs {match.away_team}
                </Typography>
                <Typography color="text.secondary">
                  {match.date_event}
                </Typography>
              </CardContent>
            </Card>
          ))}
        </Box>
      )}
    </Paper>
  );
}

export default UpcomingMatches;

