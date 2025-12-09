import React from 'react';
import { Box, Typography, TextField, Grid } from '@mui/material';

function ManualOddsInput({ matches, manualOdds, onOddsChange }) {
  return (
    <Box sx={{ mb: 4 }}>
      <Typography variant="h6" sx={{ mb: 2, color: '#fafafa', fontWeight: 700 }}>
        ✍️ Manual Odds (optional)
      </Typography>
      <Typography variant="caption" sx={{ display: 'block', mb: 2, color: '#a0aec0' }}>
        Enter decimal odds for each matchup. Leave blank (0.00) to use AI only.
      </Typography>

      {matches.map((match) => {
        const matchDate = match.date_event ? match.date_event.split('T')[0] : new Date().toISOString().split('T')[0];
        // Support both ID-based and name-based keys (matching Streamlit)
        const idKey = `manual_odds_by_ids::${match.home_team_id || ''}::${match.away_team_id || ''}::${matchDate}`;
        const nameKey = `${match.home_team}::${match.away_team}::${matchDate}`;
        const existingOdds = manualOdds[idKey] || manualOdds[nameKey] || { home: 0, away: 0 };
        const odds = { home: existingOdds.home || 0, away: existingOdds.away || 0 };

        return (
          <Box key={match.id || idKey || nameKey} sx={{ mb: 2, p: 2, backgroundColor: '#1f2937', borderRadius: 2 }}>
            <Grid container spacing={2} alignItems="center" justifyContent={{ xs: 'center', md: 'flex-start' }}>
              <Grid item xs={12} md={6} sx={{ display: 'flex', justifyContent: { xs: 'center', md: 'flex-start' } }}>
                <Typography sx={{ 
                  color: '#fafafa', 
                  fontWeight: 600,
                  textAlign: { xs: 'center', md: 'left' }
                }}>
                  {match.home_team} vs {match.away_team} — {matchDate}
                </Typography>
              </Grid>
              <Grid item xs={6} md={3} sx={{ display: 'flex', justifyContent: { xs: 'center', md: 'flex-start' } }}>
                <TextField
                  fullWidth
                  type="number"
                  label={match.home_team}
                  value={odds.home > 0 ? odds.home : ''}
                  onChange={(e) => {
                    const value = parseFloat(e.target.value) || 0;
                    const newOdds = { ...odds, home: value > 0 ? value : 0 };
                    // Update both keys (matching Streamlit)
                    onOddsChange(idKey, newOdds);
                    onOddsChange(nameKey, newOdds);
                  }}
                  inputProps={{ min: 1.01, step: 0.01 }}
                  size="small"
                  sx={{
                    width: { xs: '90%', md: '100%' },
                    maxWidth: { xs: '200px', md: 'none' },
                    '& .MuiOutlinedInput-root': {
                      color: '#fafafa',
                      '& fieldset': {
                        borderColor: '#4b5563',
                      },
                      '& input': {
                        textAlign: { xs: 'center', md: 'left' },
                      },
                    },
                    '& .MuiInputLabel-root': {
                      color: '#9ca3af',
                    },
                  }}
                />
              </Grid>
              <Grid item xs={6} md={3} sx={{ display: 'flex', justifyContent: { xs: 'center', md: 'flex-start' } }}>
                <TextField
                  fullWidth
                  type="number"
                  label={match.away_team}
                  value={odds.away > 0 ? odds.away : ''}
                  onChange={(e) => {
                    const value = parseFloat(e.target.value) || 0;
                    const newOdds = { ...odds, away: value > 0 ? value : 0 };
                    // Update both keys (matching Streamlit)
                    onOddsChange(idKey, newOdds);
                    onOddsChange(nameKey, newOdds);
                  }}
                  inputProps={{ min: 1.01, step: 0.01 }}
                  size="small"
                  sx={{
                    width: { xs: '90%', md: '100%' },
                    maxWidth: { xs: '200px', md: 'none' },
                    '& .MuiOutlinedInput-root': {
                      color: '#fafafa',
                      '& fieldset': {
                        borderColor: '#4b5563',
                      },
                      '& input': {
                        textAlign: { xs: 'center', md: 'left' },
                      },
                    },
                    '& .MuiInputLabel-root': {
                      color: '#9ca3af',
                    },
                  }}
                />
              </Grid>
            </Grid>
          </Box>
        );
      })}
    </Box>
  );
}

export default ManualOddsInput;

