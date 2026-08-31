import React, { memo } from 'react';
import { Box, Typography, TextField, Grid } from '@mui/material';
import { getLocalYYYYMMDD, getKickoffAtFromMatch, formatKickoffSAST, formatSASTDateYMD, hasMeaningfulTime } from '../utils/date';
import { predictionsWidgetSx } from '../utils/predictionsLayout';

const oddsFieldSx = {
  width: '100%',
  '& .MuiOutlinedInput-root': {
    color: '#fafafa',
    height: { xs: '40px', md: 'auto' },
    display: 'flex',
    alignItems: 'center',
    '& fieldset': {
      borderColor: '#4b5563',
    },
    '& input': {
      textAlign: 'center',
      padding: { xs: '10px 8px', md: '16.5px 14px' },
      fontSize: { xs: '0.9rem', md: '1rem' },
    },
    '& legend': {
      display: 'none',
    },
  },
  '& .MuiInputLabel-root': {
    color: '#9ca3af',
    fontSize: { xs: '0.85rem', md: '1rem' },
    left: { xs: '8px', md: '14px' },
    top: '50%',
    transform: 'translateY(-50%)',
    transformOrigin: 'left center',
    pointerEvents: 'none',
  },
  '& .MuiInputLabel-shrink': {
    transform: 'translateY(-130%) scale(0.75)',
    transformOrigin: 'left top',
  },
};

const ManualOddsInput = memo(function ManualOddsInput({ matches, selectedLeague, manualOdds, onOddsChange }) {
  return (
    <Box sx={{ 
      mb: 4, 
      ...predictionsWidgetSx,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'stretch',
    }}>
      {matches.map((match) => {
        const kickoffAt = getKickoffAtFromMatch(match, selectedLeague);
        const fixtureDate =
          (match.date_event && match.date_event.split('T')[0]) ||
          (match.dateEvent && String(match.dateEvent).split('T')[0]) ||
          getLocalYYYYMMDD();
        const matchDate = fixtureDate || (kickoffAt && formatSASTDateYMD(kickoffAt)) || getLocalYYYYMMDD();
        const kickoffLabel =
          kickoffAt && hasMeaningfulTime(kickoffAt) ? formatKickoffSAST(kickoffAt) : null;
        // Support both ID-based and name-based keys (matching Streamlit)
        const idKey = `manual_odds_by_ids::${match.home_team_id || ''}::${match.away_team_id || ''}::${matchDate}`;
        const nameKey = `${match.home_team}::${match.away_team}::${matchDate}`;
        const existingOdds = manualOdds[idKey] || manualOdds[nameKey] || { home: 0, away: 0 };
        const odds = { home: existingOdds.home || 0, away: existingOdds.away || 0 };

        return (
          <Box key={match.id || idKey || nameKey} className="manual-odds-match-box" sx={{ mb: 2, p: 2, backgroundColor: '#1f2937', borderRadius: 2, width: '100%' }}>
            <Grid container spacing={2} alignItems="center" justifyContent="center">
              <Grid
                item
                xs={12}
                md={6}
                sx={{
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'center',
                  alignItems: 'center',
                  mb: { xs: 1, md: 0 },
                  textAlign: 'center',
                }}
              >
                <Typography sx={{
                  color: '#fafafa',
                  fontWeight: 600,
                  textAlign: 'center',
                  width: '100%',
                }}>
                  {match.home_team} vs {match.away_team} — {matchDate}
                </Typography>
                {kickoffLabel && (
                  <Typography
                    sx={{
                      mt: 0.35,
                      color: '#93c5fd',
                      fontWeight: 700,
                      fontSize: { xs: '0.82rem', md: '0.9rem' },
                      letterSpacing: 0.4,
                      textAlign: 'center',
                      width: '100%',
                    }}
                  >
                    Kickoff {kickoffLabel}
                  </Typography>
                )}
              </Grid>
              <Grid
                item
                xs={6}
                md={3}
                sx={{
                  display: 'flex',
                  justifyContent: 'center',
                  alignItems: 'center',
                  paddingLeft: { xs: '8px !important', md: '16px' },
                  paddingRight: { xs: '8px !important', md: '16px' },
                }}
              >
                <TextField
                  fullWidth
                  type="number"
                  label={match.home_team}
                  value={odds.home > 0 ? odds.home : ''}
                  onChange={(e) => {
                    const value = parseFloat(e.target.value) || 0;
                    const newOdds = { ...odds, home: value > 0 ? value : 0 };
                    onOddsChange(idKey, newOdds);
                    onOddsChange(nameKey, newOdds);
                  }}
                  inputProps={{ min: 1.01, step: 0.01 }}
                  size="small"
                  sx={oddsFieldSx}
                />
              </Grid>
              <Grid
                item
                xs={6}
                md={3}
                sx={{
                  display: 'flex',
                  justifyContent: 'center',
                  alignItems: 'center',
                  paddingLeft: { xs: '8px !important', md: '16px' },
                  paddingRight: { xs: '8px !important', md: '16px' },
                }}
              >
                <TextField
                  fullWidth
                  type="number"
                  label={match.away_team}
                  value={odds.away > 0 ? odds.away : ''}
                  onChange={(e) => {
                    const value = parseFloat(e.target.value) || 0;
                    const newOdds = { ...odds, away: value > 0 ? value : 0 };
                    onOddsChange(idKey, newOdds);
                    onOddsChange(nameKey, newOdds);
                  }}
                  inputProps={{ min: 1.01, step: 0.01 }}
                  size="small"
                  sx={oddsFieldSx}
                />
              </Grid>
            </Grid>
          </Box>
        );
      })}
    </Box>
  );
});

export default ManualOddsInput;

