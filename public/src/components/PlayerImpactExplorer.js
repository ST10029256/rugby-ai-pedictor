import React, { useState } from 'react';
import {
  Box,
  Typography,
  Card,
  CardContent,
  Grid,
  Chip,
  LinearProgress,
  Divider,
} from '@mui/material';
import PersonIcon from '@mui/icons-material/Person';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import TrendingDownIcon from '@mui/icons-material/TrendingDown';
import WarningIcon from '@mui/icons-material/Warning';

const PlayerImpactExplorer = ({ playerId, playerName, matchData, teamData }) => {
  const [selectedMetric, setSelectedMetric] = useState(null);

  // Mock data - in real implementation, fetch from API
  const playerData = {
    name: playerName || 'Player Name',
    position: 'Fly-half',
    selection_importance: 0.85,
    injury_risk: 0.15,
    replacement_downgrade: -0.12,
    historical_performance: {
      vs_opponent: 0.78,
      avg_score: 8.5,
      matches_played: 12,
    },
    impact_metrics: {
      attack_contribution: 0.72,
      defense_contribution: 0.65,
      set_piece_importance: 0.58,
    },
  };

  const getImpactColor = (value) => {
    if (value > 0.7) return '#10b981';
    if (value > 0.4) return '#f59e0b';
    return '#ef4444';
  };

  const getImpactLabel = (value) => {
    if (value > 0.7) return 'High';
    if (value > 0.4) return 'Medium';
    return 'Low';
  };

  return (
    <Card
      sx={{
        backgroundColor: '#1f2937',
        border: '1px solid rgba(255, 255, 255, 0.1)',
        borderRadius: 2,
        p: 3,
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 3 }}>
        <Box
          sx={{
            width: 60,
            height: 60,
            borderRadius: '50%',
            backgroundColor: '#10b98120',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <PersonIcon sx={{ fontSize: 32, color: '#10b981' }} />
        </Box>
        <Box>
          <Typography variant="h5" sx={{ color: '#fafafa', fontWeight: 700 }}>
            {playerData.name}
          </Typography>
          <Typography variant="body2" sx={{ color: '#9ca3af' }}>
            {playerData.position}
          </Typography>
        </Box>
      </Box>

      <Grid container spacing={3}>
        {/* Selection Importance */}
        <Grid item xs={12} md={6}>
          <Card
            sx={{
              backgroundColor: 'rgba(255, 255, 255, 0.05)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              borderRadius: 2,
              p: 2,
              cursor: 'pointer',
              transition: 'all 0.2s ease',
              '&:hover': {
                backgroundColor: 'rgba(255, 255, 255, 0.1)',
                borderColor: getImpactColor(playerData.selection_importance),
              },
            }}
            onClick={() => setSelectedMetric('selection')}
          >
            <Typography variant="subtitle2" sx={{ color: '#9ca3af', mb: 1 }}>
              Selection Importance
            </Typography>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1 }}>
              <LinearProgress
                variant="determinate"
                value={playerData.selection_importance * 100}
                sx={{
                  flex: 1,
                  height: 8,
                  borderRadius: 4,
                  backgroundColor: 'rgba(255, 255, 255, 0.1)',
                  '& .MuiLinearProgress-bar': {
                    backgroundColor: getImpactColor(playerData.selection_importance),
                  },
                }}
              />
              <Chip
                label={getImpactLabel(playerData.selection_importance)}
                size="small"
                sx={{
                  backgroundColor: `${getImpactColor(playerData.selection_importance)}20`,
                  color: getImpactColor(playerData.selection_importance),
                }}
              />
            </Box>
            <Typography variant="caption" sx={{ color: '#6b7280' }}>
              How critical this player is to team success
            </Typography>
          </Card>
        </Grid>

        {/* Injury Risk */}
        <Grid item xs={12} md={6}>
          <Card
            sx={{
              backgroundColor: 'rgba(255, 255, 255, 0.05)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              borderRadius: 2,
              p: 2,
              cursor: 'pointer',
              transition: 'all 0.2s ease',
              '&:hover': {
                backgroundColor: 'rgba(255, 255, 255, 0.1)',
                borderColor: playerData.injury_risk > 0.3 ? '#ef4444' : '#10b981',
              },
            }}
            onClick={() => setSelectedMetric('injury')}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
              <WarningIcon
                sx={{
                  fontSize: 18,
                  color: playerData.injury_risk > 0.3 ? '#ef4444' : '#10b981',
                }}
              />
              <Typography variant="subtitle2" sx={{ color: '#9ca3af' }}>
                Injury Risk
              </Typography>
            </Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1 }}>
              <LinearProgress
                variant="determinate"
                value={playerData.injury_risk * 100}
                sx={{
                  flex: 1,
                  height: 8,
                  borderRadius: 4,
                  backgroundColor: 'rgba(255, 255, 255, 0.1)',
                  '& .MuiLinearProgress-bar': {
                    backgroundColor: playerData.injury_risk > 0.3 ? '#ef4444' : '#f59e0b',
                  },
                }}
              />
              <Typography variant="body2" sx={{ color: '#fafafa', fontWeight: 600 }}>
                {(playerData.injury_risk * 100).toFixed(0)}%
              </Typography>
            </Box>
            <Typography variant="caption" sx={{ color: '#6b7280' }}>
              Current injury risk assessment
            </Typography>
          </Card>
        </Grid>

        {/* Replacement Impact */}
        <Grid item xs={12} md={6}>
          <Card
            sx={{
              backgroundColor: 'rgba(255, 255, 255, 0.05)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              borderRadius: 2,
              p: 2,
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
              {playerData.replacement_downgrade < 0 ? (
                <TrendingDownIcon sx={{ fontSize: 18, color: '#ef4444' }} />
              ) : (
                <TrendingUpIcon sx={{ fontSize: 18, color: '#10b981' }} />
              )}
              <Typography variant="subtitle2" sx={{ color: '#9ca3af' }}>
                Replacement Impact
              </Typography>
            </Box>
            <Typography
              variant="h6"
              sx={{
                color: playerData.replacement_downgrade < 0 ? '#ef4444' : '#10b981',
                mb: 1,
              }}
            >
              {playerData.replacement_downgrade > 0 ? '+' : ''}
              {(playerData.replacement_downgrade * 100).toFixed(1)}%
            </Typography>
            <Typography variant="caption" sx={{ color: '#6b7280' }}>
              Win probability change if replaced
            </Typography>
          </Card>
        </Grid>

        {/* Historical Performance */}
        <Grid item xs={12} md={6}>
          <Card
            sx={{
              backgroundColor: 'rgba(255, 255, 255, 0.05)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              borderRadius: 2,
              p: 2,
            }}
          >
            <Typography variant="subtitle2" sx={{ color: '#9ca3af', mb: 2 }}>
              Historical Performance vs Opponent
            </Typography>
            <Box sx={{ mb: 2 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="body2" sx={{ color: '#fafafa' }}>
                  Win Rate
                </Typography>
                <Typography variant="body2" sx={{ color: '#10b981', fontWeight: 600 }}>
                  {(playerData.historical_performance.vs_opponent * 100).toFixed(0)}%
                </Typography>
              </Box>
              <LinearProgress
                variant="determinate"
                value={playerData.historical_performance.vs_opponent * 100}
                sx={{
                  height: 6,
                  borderRadius: 3,
                  backgroundColor: 'rgba(255, 255, 255, 0.1)',
                  '& .MuiLinearProgress-bar': {
                    backgroundColor: '#10b981',
                  },
                }}
              />
            </Box>
            <Divider sx={{ my: 2, borderColor: 'rgba(255, 255, 255, 0.1)' }} />
            <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
              <Typography variant="caption" sx={{ color: '#6b7280' }}>
                Avg Score
              </Typography>
              <Typography variant="caption" sx={{ color: '#fafafa', fontWeight: 600 }}>
                {playerData.historical_performance.avg_score}
              </Typography>
            </Box>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 1 }}>
              <Typography variant="caption" sx={{ color: '#6b7280' }}>
                Matches Played
              </Typography>
              <Typography variant="caption" sx={{ color: '#fafafa', fontWeight: 600 }}>
                {playerData.historical_performance.matches_played}
              </Typography>
            </Box>
          </Card>
        </Grid>

        {/* Impact Metrics */}
        <Grid item xs={12}>
          <Card
            sx={{
              backgroundColor: 'rgba(255, 255, 255, 0.05)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              borderRadius: 2,
              p: 2,
            }}
          >
            <Typography variant="subtitle2" sx={{ color: '#9ca3af', mb: 2 }}>
              Impact Metrics
            </Typography>
            <Grid container spacing={2}>
              <Grid item xs={12} sm={4}>
                <Box>
                  <Typography variant="caption" sx={{ color: '#6b7280', display: 'block', mb: 0.5 }}>
                    Attack Contribution
                  </Typography>
                  <LinearProgress
                    variant="determinate"
                    value={playerData.impact_metrics.attack_contribution * 100}
                    sx={{
                      height: 6,
                      borderRadius: 3,
                      backgroundColor: 'rgba(255, 255, 255, 0.1)',
                      '& .MuiLinearProgress-bar': {
                        backgroundColor: '#3b82f6',
                      },
                    }}
                  />
                  <Typography variant="caption" sx={{ color: '#fafafa', mt: 0.5, display: 'block' }}>
                    {(playerData.impact_metrics.attack_contribution * 100).toFixed(0)}%
                  </Typography>
                </Box>
              </Grid>
              <Grid item xs={12} sm={4}>
                <Box>
                  <Typography variant="caption" sx={{ color: '#6b7280', display: 'block', mb: 0.5 }}>
                    Defense Contribution
                  </Typography>
                  <LinearProgress
                    variant="determinate"
                    value={playerData.impact_metrics.defense_contribution * 100}
                    sx={{
                      height: 6,
                      borderRadius: 3,
                      backgroundColor: 'rgba(255, 255, 255, 0.1)',
                      '& .MuiLinearProgress-bar': {
                        backgroundColor: '#ef4444',
                      },
                    }}
                  />
                  <Typography variant="caption" sx={{ color: '#fafafa', mt: 0.5, display: 'block' }}>
                    {(playerData.impact_metrics.defense_contribution * 100).toFixed(0)}%
                  </Typography>
                </Box>
              </Grid>
              <Grid item xs={12} sm={4}>
                <Box>
                  <Typography variant="caption" sx={{ color: '#6b7280', display: 'block', mb: 0.5 }}>
                    Set Piece Importance
                  </Typography>
                  <LinearProgress
                    variant="determinate"
                    value={playerData.impact_metrics.set_piece_importance * 100}
                    sx={{
                      height: 6,
                      borderRadius: 3,
                      backgroundColor: 'rgba(255, 255, 255, 0.1)',
                      '& .MuiLinearProgress-bar': {
                        backgroundColor: '#f59e0b',
                      },
                    }}
                  />
                  <Typography variant="caption" sx={{ color: '#fafafa', mt: 0.5, display: 'block' }}>
                    {(playerData.impact_metrics.set_piece_importance * 100).toFixed(0)}%
                  </Typography>
                </Box>
              </Grid>
            </Grid>
          </Card>
        </Grid>
      </Grid>

      {/* Selected Metric Explanation */}
      {selectedMetric && (
        <Box sx={{ mt: 3, p: 2, backgroundColor: 'rgba(16, 185, 129, 0.1)', borderRadius: 2 }}>
          <Typography variant="body2" sx={{ color: '#10b981' }}>
            {selectedMetric === 'selection' &&
              'Selection importance measures how much this player affects the team\'s overall win probability. High importance players are critical to team success.'}
            {selectedMetric === 'injury' &&
              'Injury risk is calculated based on recent injury history, age, position demands, and match frequency. Higher risk may affect availability.'}
          </Typography>
        </Box>
      )}
    </Card>
  );
};

export default PlayerImpactExplorer;

