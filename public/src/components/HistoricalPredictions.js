import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Card,
  CardContent,
  CircularProgress,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Chip,
  Grid,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Paper,
  Divider,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import CancelIcon from '@mui/icons-material/Cancel';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import { getHistoricalPredictions, getHistoricalBacktest } from '../firebase';
import RugbyBallLoader from './RugbyBallLoader';

const HistoricalPredictions = ({ leagueId, leagueName }) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);
  const [selectedYear, setSelectedYear] = useState(null);
  const [availableYears, setAvailableYears] = useState([]);
  const [evaluationMode, setEvaluationMode] = useState('backtest'); // 'backtest' | 'replay'
  const [expandedWeeks, setExpandedWeeks] = useState(new Set());

  useEffect(() => {
    // Reset selection when league changes
    setSelectedYear(null);
    setExpandedWeeks(new Set());
    fetchHistoricalData();
  }, [leagueId]);

  const fetchHistoricalData = async (yearOverride = null, modeOverride = null) => {
    if (!leagueId) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const payload = { league_id: leagueId };
      if (yearOverride) payload.year = yearOverride;
      const mode = modeOverride || evaluationMode;

      const result = mode === 'backtest'
        ? await getHistoricalBacktest(payload)
        : await getHistoricalPredictions(payload);
      if (result?.data) {
        setData(result.data);

        if (Array.isArray(result.data.available_years)) {
          setAvailableYears(result.data.available_years);
        } else {
          setAvailableYears([]);
        }
        
        // Prefer backend-selected year (prevents loading everything at once)
        if (result.data.selected_year) {
          setSelectedYear(result.data.selected_year);
        } else if (result.data.matches_by_year_week) {
          // Fallback: derive from payload
          const years = Object.keys(result.data.matches_by_year_week).sort().reverse();
          if (years.length > 0) setSelectedYear(years[0]);
        }
      } else {
        setError('No data returned from server');
      }
    } catch (err) {
      console.error('Error fetching historical predictions:', err);
      setError(err.message || 'Failed to load historical predictions');
    } finally {
      setLoading(false);
    }
  };

  const handleWeekToggle = (weekKey) => {
    setExpandedWeeks(prev => {
      const newSet = new Set(prev);
      if (newSet.has(weekKey)) {
        newSet.delete(weekKey);
      } else {
        newSet.add(weekKey);
      }
      return newSet;
    });
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '400px', gap: 2 }}>
        <RugbyBallLoader size={100} color="#10b981" />
        <Typography sx={{ color: '#fafafa' }}>Loading historical predictions...</Typography>
      </Box>
    );
  }

  if (error) {
    return (
      <Box sx={{ p: 3, textAlign: 'center' }}>
        <Typography color="error" variant="h6" gutterBottom>
          Error Loading Data
        </Typography>
        <Typography color="text.secondary">{error}</Typography>
      </Box>
    );
  }

  if (!data || !data.matches_by_year_week) {
    return (
      <Box sx={{ p: 3, textAlign: 'center' }}>
        <Typography color="text.secondary">No historical data available</Typography>
      </Box>
    );
  }

  const years = (availableYears && availableYears.length > 0)
    ? availableYears
    : Object.keys(data.matches_by_year_week).sort().reverse();
  const stats = data.statistics || {};
  const leagueStats = data.by_league?.[leagueId] || {};

  return (
    <Box sx={{ width: '100%', maxWidth: '1400px', mx: 'auto', p: { xs: 2, sm: 3, md: 4 } }}>
      {/* Statistics Summary */}
      <Paper
        elevation={3}
        sx={{
          p: 3,
          mb: 4,
          background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(31, 41, 55, 0.8) 100%)',
          border: '1px solid rgba(16, 185, 129, 0.2)',
        }}
      >
        <Typography variant="h5" sx={{ mb: 3, color: '#fafafa', fontWeight: 700 }}>
          📊 Historical Predictions Performance
        </Typography>
        <Typography variant="caption" sx={{ color: '#9ca3af', display: 'block', mb: 2 }}>
          Mode: <strong style={{ color: '#fafafa' }}>{evaluationMode === 'backtest' ? 'True backtest (unseen)' : 'Replay (current model)'}</strong>
        </Typography>

        <Grid container spacing={3}>
          <Grid item xs={12} sm={6} md={3}>
            <Box sx={{ textAlign: 'center' }}>
              <Typography variant="h4" sx={{ color: '#10b981', fontWeight: 800 }}>
                {stats.total_matches || 0}
              </Typography>
              <Typography variant="body2" sx={{ color: '#9ca3af', mt: 0.5 }}>
                Total Matches
              </Typography>
            </Box>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Box sx={{ textAlign: 'center' }}>
              <Typography variant="h4" sx={{ color: '#10b981', fontWeight: 800 }}>
                {stats.correct_predictions || 0}
              </Typography>
              <Typography variant="body2" sx={{ color: '#9ca3af', mt: 0.5 }}>
                Correct Predictions
              </Typography>
            </Box>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Box sx={{ textAlign: 'center' }}>
              <Typography variant="h4" sx={{ color: '#10b981', fontWeight: 800 }}>
                {stats.accuracy_percentage?.toFixed(1) || '0.0'}%
              </Typography>
              <Typography variant="body2" sx={{ color: '#9ca3af', mt: 0.5 }}>
                Overall Accuracy
              </Typography>
            </Box>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Box sx={{ textAlign: 'center' }}>
              <Typography variant="h4" sx={{ color: '#10b981', fontWeight: 800 }}>
                {stats.average_score_error?.toFixed(1) || 'N/A'}
              </Typography>
              <Typography variant="body2" sx={{ color: '#9ca3af', mt: 0.5 }}>
                Avg Score Error
              </Typography>
            </Box>
          </Grid>
        </Grid>

        {leagueStats.accuracy_percentage && (
          <Box sx={{ mt: 3, pt: 3, borderTop: '1px solid rgba(16, 185, 129, 0.2)' }}>
            <Typography variant="body2" sx={{ color: '#9ca3af' }}>
              <strong style={{ color: '#fafafa' }}>{leagueName}</strong> specific accuracy: {' '}
              <strong style={{ color: '#10b981' }}>{leagueStats.accuracy_percentage.toFixed(1)}%</strong>
              {' '}({leagueStats.correct_predictions} correct out of {leagueStats.total_predictions} predictions)
            </Typography>
          </Box>
        )}
      </Paper>

      {/* Mode Selector */}
      <FormControl fullWidth sx={{ mb: 2, maxWidth: 360 }}>
        <InputLabel sx={{ color: '#9ca3af' }}>Evaluation Mode</InputLabel>
        <Select
          value={evaluationMode}
          onChange={(e) => {
            const newMode = e.target.value;
            setEvaluationMode(newMode);
            setExpandedWeeks(new Set());
            fetchHistoricalData(selectedYear, newMode);
          }}
          sx={{
            color: '#fafafa',
            '& .MuiOutlinedInput-notchedOutline': {
              borderColor: 'rgba(16, 185, 129, 0.3)',
            },
            '&:hover .MuiOutlinedInput-notchedOutline': {
              borderColor: 'rgba(16, 185, 129, 0.5)',
            },
            '& .MuiSvgIcon-root': {
              color: '#10b981',
            },
          }}
        >
          <MenuItem value="backtest">True backtest (unseen)</MenuItem>
          <MenuItem value="replay">Replay (current model)</MenuItem>
        </Select>
      </FormControl>

      {/* Year Selector */}
      {years.length > 1 && (
        <FormControl fullWidth sx={{ mb: 3, maxWidth: 300 }}>
          <InputLabel sx={{ color: '#9ca3af' }}>Select Year</InputLabel>
          <Select
            value={selectedYear || ''}
            onChange={(e) => {
              const newYear = e.target.value;
              setSelectedYear(newYear);
              setExpandedWeeks(new Set());
              fetchHistoricalData(newYear);
            }}
            sx={{
              color: '#fafafa',
              '& .MuiOutlinedInput-notchedOutline': {
                borderColor: 'rgba(16, 185, 129, 0.3)',
              },
              '&:hover .MuiOutlinedInput-notchedOutline': {
                borderColor: 'rgba(16, 185, 129, 0.5)',
              },
              '& .MuiSvgIcon-root': {
                color: '#10b981',
              },
            }}
          >
            {years.map((year) => (
              <MenuItem key={year} value={year}>
                {year}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      )}

      {/* Matches by Year-Week */}
      {(selectedYear ? [selectedYear] : years).map((year) => {
        const yearData = data.matches_by_year_week[year];
        if (!yearData) return null;

        const weekKeys = Object.keys(yearData).sort().reverse();

        return (
          <Box key={year} sx={{ mb: 4 }}>
            <Typography
              variant="h4"
              sx={{
                mb: 3,
                color: '#fafafa',
                fontWeight: 700,
                pb: 2,
                borderBottom: '2px solid rgba(16, 185, 129, 0.3)',
              }}
            >
              {year}
            </Typography>

            {weekKeys.map((weekKey) => {
              const matches = yearData[weekKey];
              if (!matches || matches.length === 0) return null;

              const isExpanded = expandedWeeks.has(weekKey);

              return (
                <Accordion
                  key={weekKey}
                  expanded={isExpanded}
                  onChange={() => handleWeekToggle(weekKey)}
                  sx={{
                    mb: 2,
                    background: 'rgba(31, 41, 55, 0.8)',
                    border: '1px solid rgba(16, 185, 129, 0.2)',
                    borderRadius: '8px !important',
                    '&:before': { display: 'none' },
                    '&.Mui-expanded': {
                      background: 'rgba(31, 41, 55, 0.95)',
                    },
                  }}
                >
                  <AccordionSummary
                    expandIcon={<ExpandMoreIcon sx={{ color: '#10b981' }} />}
                    sx={{
                      '& .MuiAccordionSummary-content': {
                        alignItems: 'center',
                      },
                    }}
                  >
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, width: '100%' }}>
                      <Typography variant="h6" sx={{ color: '#fafafa', fontWeight: 600 }}>
                        {weekKey}
                      </Typography>
                      <Chip
                        label={`${matches.length} match${matches.length !== 1 ? 'es' : ''}`}
                        size="small"
                        sx={{
                          backgroundColor: 'rgba(16, 185, 129, 0.2)',
                          color: '#10b981',
                          fontWeight: 600,
                        }}
                      />
                      {matches[0]?.date && (
                        <Typography variant="body2" sx={{ color: '#9ca3af', ml: 'auto' }}>
                          {new Date(matches[0].date).toLocaleDateString('en-US', {
                            month: 'short',
                            day: 'numeric',
                          })}
                        </Typography>
                      )}
                    </Box>
                  </AccordionSummary>
                  <AccordionDetails>
                    <Grid container spacing={2}>
                      {matches.map((match) => (
                        <Grid item xs={12} sm={6} md={4} key={match.match_id}>
                          <MatchCard match={match} />
                        </Grid>
                      ))}
                    </Grid>
                  </AccordionDetails>
                </Accordion>
              );
            })}
          </Box>
        );
      })}
    </Box>
  );
};

const MatchCard = ({ match }) => {
  const {
    date,
    home_team,
    away_team,
    actual_home_score,
    actual_away_score,
    predicted_home_score,
    predicted_away_score,
    predicted_winner,
    prediction_correct,
    prediction_confidence,
    prediction_error,
    league_name,
  } = match;

  const actualWinner = actual_home_score > actual_away_score ? home_team : actual_away_score > actual_home_score ? away_team : 'Draw';
  const predictedWinnerTeam = predicted_winner === 'Home' ? home_team : predicted_winner === 'Away' ? away_team : 'Draw';

  return (
    <Card
      sx={{
        background: 'rgba(15, 23, 42, 0.8)',
        border: `1px solid ${prediction_correct ? 'rgba(16, 185, 129, 0.3)' : prediction_correct === false ? 'rgba(239, 68, 68, 0.3)' : 'rgba(148, 163, 184, 0.2)'}`,
        borderRadius: '8px',
        transition: 'all 0.3s ease',
        '&:hover': {
          transform: 'translateY(-2px)',
          boxShadow: `0 8px 24px ${prediction_correct ? 'rgba(16, 185, 129, 0.2)' : prediction_correct === false ? 'rgba(239, 68, 68, 0.2)' : 'rgba(148, 163, 184, 0.1)'}`,
        },
      }}
    >
      <CardContent>
        {/* Header */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', mb: 2 }}>
          <Typography variant="body2" sx={{ color: '#9ca3af' }}>
            {new Date(date).toLocaleDateString('en-US', {
              month: 'short',
              day: 'numeric',
              year: 'numeric',
            })}
          </Typography>
          {prediction_correct !== null && (
            <Box sx={{ display: 'flex', alignItems: 'center' }}>
              {prediction_correct ? (
                <CheckCircleIcon sx={{ color: '#10b981', fontSize: 20 }} />
              ) : (
                <CancelIcon sx={{ color: '#ef4444', fontSize: 20 }} />
              )}
            </Box>
          )}
        </Box>

        {/* Teams and Scores */}
        <Box sx={{ mb: 2 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
            <Typography variant="body1" sx={{ color: '#fafafa', fontWeight: 600, flex: 1 }}>
              {home_team}
            </Typography>
            <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
              <Typography variant="h6" sx={{ color: '#10b981', fontWeight: 700, minWidth: 30, textAlign: 'right' }}>
                {actual_home_score ?? '?'}
              </Typography>
              {predicted_home_score !== null && (
                <Typography variant="body2" sx={{ color: '#9ca3af', minWidth: 30, textAlign: 'right' }}>
                  ({Math.round(predicted_home_score)})
                </Typography>
              )}
            </Box>
          </Box>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="body1" sx={{ color: '#fafafa', fontWeight: 600, flex: 1 }}>
              {away_team}
            </Typography>
            <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
              <Typography variant="h6" sx={{ color: '#10b981', fontWeight: 700, minWidth: 30, textAlign: 'right' }}>
                {actual_away_score ?? '?'}
              </Typography>
              {predicted_away_score !== null && (
                <Typography variant="body2" sx={{ color: '#9ca3af', minWidth: 30, textAlign: 'right' }}>
                  ({Math.round(predicted_away_score)})
                </Typography>
              )}
            </Box>
          </Box>
        </Box>

        <Divider sx={{ my: 1.5, borderColor: 'rgba(148, 163, 184, 0.1)' }} />

        {/* Prediction Info */}
        {predicted_winner && predicted_winner !== 'Error' && (
          <Box>
            <Typography variant="caption" sx={{ color: '#9ca3af', display: 'block', mb: 0.5 }}>
              AI Predicted:
            </Typography>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
              <Typography variant="body2" sx={{ color: '#fafafa', fontWeight: 500 }}>
                {predictedWinnerTeam}
              </Typography>
              {prediction_confidence && (
                <Chip
                  label={`${(prediction_confidence * 100).toFixed(0)}%`}
                  size="small"
                  sx={{
                    height: 20,
                    fontSize: '0.7rem',
                    backgroundColor: 'rgba(16, 185, 129, 0.2)',
                    color: '#10b981',
                  }}
                />
              )}
            </Box>
            {prediction_error !== null && (
              <Typography variant="caption" sx={{ color: '#9ca3af' }}>
                Score error: {prediction_error.toFixed(1)} points
              </Typography>
            )}
          </Box>
        )}

        {predicted_winner === 'Error' && (
          <Typography variant="caption" sx={{ color: '#ef4444' }}>
            Could not generate prediction
          </Typography>
        )}
      </CardContent>
    </Card>
  );
};

export default HistoricalPredictions;

