import React, { useState, useEffect, memo } from 'react';
import { Box } from '@mui/material';
import RugbyBallLoader from './RugbyBallLoader';
import { getLeagueMetrics } from '../firebase';
import { predictionsWidgetSx } from '../utils/predictionsLayout';

const ratingFromAccuracy = (accuracy) => {
  if (accuracy >= 80) return '9/10';
  if (accuracy >= 75) return '8/10';
  if (accuracy >= 70) return '7/10';
  if (accuracy >= 65) return '6/10';
  if (accuracy >= 60) return '5/10';
  if (accuracy > 0) return '4/10';
  return 'N/A';
};

const LeagueMetrics = memo(function LeagueMetrics({ leagueId, leagueIds, leagueName }) {
  const [metrics, setMetrics] = useState({
    accuracy: 0,
    trainingGames: 0,
    aiRating: 'N/A',
    margin: 0,
    loading: true
  });
  const leagueIdsKey = Array.isArray(leagueIds) && leagueIds.length
    ? leagueIds.join(',')
    : String(leagueId || '');

  useEffect(() => {
    const ids = [...new Set(leagueIdsKey.split(',').map((id) => String(id || '').trim()).filter(Boolean))];
    if (!ids.length) {
      setMetrics({ accuracy: 0, trainingGames: 0, aiRating: 'N/A', margin: 0, loading: false });
      return;
    }

    const isDebugEnabled = (key) => {
      try {
        return typeof window !== 'undefined' && window.localStorage && window.localStorage.getItem(key) === '1';
      } catch {
        return false;
      }
    };
    // Enable via localStorage.setItem('debug_metrics', '1')
    const DEBUG_METRICS = isDebugEnabled('debug_metrics');
    const debugLog = (...args) => DEBUG_METRICS && console.log(...args);

    const fetchMetrics = async () => {
      try {
        debugLog(`📊 Fetching league metrics for league_ids: ${ids.join(',')}`);
        setMetrics(prev => ({ ...prev, loading: true }));
        const results = await Promise.all(ids.map((id) => getLeagueMetrics({ league_id: id })));
        const rows = results
          .map((result) => result?.data)
          .filter((data) => data && !data.error);

        if (!rows.length) {
          debugLog('⚠️ No data in league metrics response');
          setMetrics({
            accuracy: 0,
            trainingGames: 0,
            aiRating: 'N/A',
            margin: 0,
            loading: false
          });
          return;
        }

        const trainingGames = rows.reduce((sum, data) => sum + (Number(data.training_games) || 0), 0);
        const accuracyWeight = rows.reduce(
          (sum, data) => sum + ((Number(data.accuracy) || 0) * (Number(data.training_games) || 0)),
          0
        );
        const marginWeight = rows.reduce(
          (sum, data) => sum + ((Number(data.overall_mae || data.margin) || 0) * (Number(data.training_games) || 0)),
          0
        );
        const accuracy = trainingGames > 0 ? accuracyWeight / trainingGames : (Number(rows[0].accuracy) || 0);
        const margin = trainingGames > 0 ? marginWeight / trainingGames : (Number(rows[0].overall_mae || rows[0].margin) || 0);
        const aiRating = rows.length === 1
          ? (rows[0].ai_rating || ratingFromAccuracy(accuracy))
          : ratingFromAccuracy(accuracy);

        debugLog('✅ League metrics received:', {
          ids,
          accuracy,
          training_games: trainingGames,
          ai_rating: aiRating,
          margin,
        });

        setMetrics({
          accuracy,
          trainingGames,
          aiRating,
          margin,
          loading: false
        });
      } catch (error) {
        console.error('❌ Exception fetching league metrics:', error);
        if (DEBUG_METRICS) {
          console.error('Error details:', {
            name: error.name,
            message: error.message,
            stack: error.stack
          });
        }
        setMetrics({
          accuracy: 0,
          trainingGames: 0,
          aiRating: 'N/A',
          margin: 0,
          loading: false
        });
      }
    };

    fetchMetrics();
  }, [leagueIdsKey]);

  if (metrics.loading) {
    return (
      <Box sx={{ 
        ...predictionsWidgetSx,
        minHeight: { xs: '200px', sm: '240px' },
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        py: 3,
      }}>
        <RugbyBallLoader size={100} color="#10b981" compact label="Loading metrics..." />
      </Box>
    );
  }

  return (
    <Box sx={predictionsWidgetSx}>
    <Box className="custom-metrics-container">
      <Box className="custom-metric">
        <Box className="metric-label">Accuracy</Box>
        <Box className="metric-value">{metrics.accuracy.toFixed(1)}%</Box>
        <Box className="metric-delta">League Specific</Box>
      </Box>
      <Box className="custom-metric">
        <Box className="metric-label">League</Box>
        <Box className="metric-value metric-value--league">{leagueName || '—'}</Box>
        <Box className="metric-delta">Selected</Box>
      </Box>
      <Box className="custom-metric">
        <Box className="metric-label">Games Trained</Box>
        <Box className="metric-value">{metrics.trainingGames}</Box>
        <Box className="metric-delta">Completed</Box>
      </Box>
      <Box className="custom-metric">
        <Box className="metric-label">Margin Error</Box>
        <Box className="metric-value">
          {metrics.margin > 0 
            ? `${metrics.margin.toFixed(1)} pts`
            : 'N/A'}
        </Box>
        <Box className="metric-delta">Avg per Team</Box>
      </Box>
    </Box>
    </Box>
  );
});

export default LeagueMetrics;

