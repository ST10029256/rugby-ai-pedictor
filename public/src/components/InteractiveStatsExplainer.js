import React, { useState } from 'react';
import {
  Box,
  Typography,
  Card,
  CardContent,
  Chip,
  IconButton,
  Collapse,
  Tooltip,
} from '@mui/material';
import InfoIcon from '@mui/icons-material/Info';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import TrendingDownIcon from '@mui/icons-material/TrendingDown';

const InteractiveStatsExplainer = ({ statLabel, statValue, explanation, context = {} }) => {
  const [expanded, setExpanded] = useState(false);
  const [showTooltip, setShowTooltip] = useState(false);

  const isPositive = statValue > 0;
  const isNegative = statValue < 0;
  const absValue = Math.abs(statValue);

  return (
    <Card
      sx={{
        backgroundColor: '#1f2937',
        border: '1px solid rgba(255, 255, 255, 0.1)',
        borderRadius: 2,
        p: 2,
        cursor: 'pointer',
        transition: 'all 0.3s ease',
        '&:hover': {
          borderColor: isPositive ? '#10b981' : isNegative ? '#ef4444' : '#6b7280',
          boxShadow: `0 4px 12px rgba(0, 0, 0, 0.3)`,
        },
      }}
      onClick={() => setExpanded(!expanded)}
    >
      <CardContent sx={{ p: '0 !important' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Box sx={{ flex: 1 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
              <Typography variant="subtitle1" sx={{ color: '#fafafa', fontWeight: 600 }}>
                {statLabel}
              </Typography>
              <Tooltip
                title="Click to see detailed explanation"
                open={showTooltip}
                onOpen={() => setShowTooltip(true)}
                onClose={() => setShowTooltip(false)}
              >
                <InfoIcon
                  sx={{
                    fontSize: 18,
                    color: '#9ca3af',
                    cursor: 'help',
                  }}
                  onMouseEnter={() => setShowTooltip(true)}
                  onMouseLeave={() => setShowTooltip(false)}
                />
              </Tooltip>
            </Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              {isPositive && <TrendingUpIcon sx={{ fontSize: 20, color: '#10b981' }} />}
              {isNegative && <TrendingDownIcon sx={{ fontSize: 20, color: '#ef4444' }} />}
              <Typography
                variant="h5"
                sx={{
                  color: isPositive ? '#10b981' : isNegative ? '#ef4444' : '#fafafa',
                  fontWeight: 700,
                }}
              >
                {isPositive ? '+' : isNegative ? '' : ''}
                {typeof statValue === 'number' ? statValue.toFixed(1) : statValue}
                {typeof statValue === 'number' && '%'}
              </Typography>
            </Box>
          </Box>
          <IconButton
            size="small"
            sx={{
              color: '#9ca3af',
              transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)',
              transition: 'transform 0.3s ease',
            }}
          >
            <InfoIcon />
          </IconButton>
        </Box>

        <Collapse in={expanded}>
          <Box
            sx={{
              mt: 2,
              pt: 2,
              borderTop: '1px solid rgba(255, 255, 255, 0.1)',
            }}
          >
            <Typography variant="body2" sx={{ color: '#d1d5db', mb: 2 }}>
              {explanation}
            </Typography>

            {/* Context-specific details */}
            {context.player_name && (
              <Box
                sx={{
                  p: 1.5,
                  mb: 1,
                  backgroundColor: 'rgba(16, 185, 129, 0.1)',
                  borderRadius: 1,
                }}
              >
                <Typography variant="caption" sx={{ color: '#10b981', fontWeight: 600, display: 'block', mb: 0.5 }}>
                  Player Impact
                </Typography>
                <Typography variant="body2" sx={{ color: '#d1d5db' }}>
                  {context.player_name} {context.impact_description || 'affects this statistic'}
                </Typography>
              </Box>
            )}

            {context.team_name && (
              <Box
                sx={{
                  p: 1.5,
                  mb: 1,
                  backgroundColor: 'rgba(59, 130, 246, 0.1)',
                  borderRadius: 1,
                }}
              >
                <Typography variant="caption" sx={{ color: '#3b82f6', fontWeight: 600, display: 'block', mb: 0.5 }}>
                  Team Context
                </Typography>
                <Typography variant="body2" sx={{ color: '#d1d5db' }}>
                  {context.team_name} {context.team_context || 'team performance'}
                </Typography>
              </Box>
            )}

            {context.matchup && (
              <Box
                sx={{
                  p: 1.5,
                  backgroundColor: 'rgba(139, 92, 246, 0.1)',
                  borderRadius: 1,
                }}
              >
                <Typography variant="caption" sx={{ color: '#8b5cf6', fontWeight: 600, display: 'block', mb: 0.5 }}>
                  Matchup Analysis
                </Typography>
                <Typography variant="body2" sx={{ color: '#d1d5db' }}>
                  {context.matchup}
                </Typography>
              </Box>
            )}

            {/* Example calculation if available */}
            {context.calculation && (
              <Box sx={{ mt: 2, p: 1.5, backgroundColor: 'rgba(255, 255, 255, 0.05)', borderRadius: 1 }}>
                <Typography variant="caption" sx={{ color: '#9ca3af', display: 'block', mb: 0.5 }}>
                  How it's calculated
                </Typography>
                <Typography variant="body2" sx={{ color: '#fafafa', fontFamily: 'monospace' }}>
                  {context.calculation}
                </Typography>
              </Box>
            )}
          </Box>
        </Collapse>
      </CardContent>
    </Card>
  );
};

// Example usage component
export const StatExplainerExample = () => {
  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h6" sx={{ color: '#fafafa', mb: 3 }}>
        Interactive Stats Explainer Examples
      </Typography>

      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <InteractiveStatsExplainer
          statLabel="Scrum Efficiency"
          statValue={-12}
          explanation="Without Kitshoff, Stormers lose 18% scrum stability. This directly impacts set-piece dominance and territory control. The replacement prop has a 15% lower scrum success rate based on historical data."
          context={{
            player_name: 'Kitshoff',
            impact_description: 'is a key scrum anchor. His absence reduces scrum stability by 18%',
            team_name: 'Stormers',
            team_context: 'typically relies on strong set-piece play',
            calculation: 'Scrum Efficiency = (Won Scrums / Total Scrums) × 100. Without Kitshoff: -18% base reduction',
          }}
        />

        <InteractiveStatsExplainer
          statLabel="Win Probability Change"
          statValue={-6.2}
          explanation="The lineup changes reduce win probability by 6.2 percentage points. This is calculated based on player impact ratings, historical performance, and matchup analysis."
          context={{
            team_name: 'Stormers',
            matchup: 'Against a strong scrummaging team, the loss of key forwards is particularly impactful',
          }}
        />

        <InteractiveStatsExplainer
          statLabel="Attack Rating"
          statValue={+8.5}
          explanation="The inclusion of a creative playmaker increases attacking threat significantly. This player averages 2.3 line breaks per game and creates 15% more try-scoring opportunities."
        />
      </Box>
    </Box>
  );
};

export default InteractiveStatsExplainer;

