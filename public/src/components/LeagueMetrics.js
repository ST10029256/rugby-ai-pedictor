import React, { useState, useEffect, memo } from 'react';
import { Box } from '@mui/material';
import RugbyBallLoader from './RugbyBallLoader';
import { getLeagueMetrics } from '../firebase';

const LeagueMetrics = memo(function LeagueMetrics({ leagueId, leagueName }) {
  const [metrics, setMetrics] = useState({
    accuracy: 0,
    trainingGames: 0,
    aiRating: 'N/A',
    margin: 0,
    loading: true
  });

  useEffect(() => {
        if (!leagueId) {
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
        debugLog(`📊 Fetching league metrics for league_id: ${leagueId}`);
        setMetrics(prev => ({ ...prev, loading: true }));
        const result = await getLeagueMetrics({ league_id: leagueId });
        
        debugLog('📊 League metrics API response:', result);
        debugLog('📊 Result.data:', result?.data);
        
        if (result && result.data) {
          if (result.data.error) {
            console.error('❌ League metrics error:', result.data.error);
            setMetrics({
              accuracy: 0,
              trainingGames: 0,
              aiRating: 'N/A',
              margin: 0,
              loading: false
            });
          } else {
            const accuracy = result.data.accuracy || 0;
            const trainingGames = result.data.training_games || 0;
            const aiRating = result.data.ai_rating || 'N/A';
            const margin = result.data.overall_mae || result.data.margin || 0;
            
            debugLog('✅ League metrics received:', {
              accuracy: accuracy,
              training_games: trainingGames,
              ai_rating: aiRating,
              margin: margin,
              full_data: result.data
            });
            
            // Log the actual values clearly
            debugLog(`📊 Metrics for league ${leagueId}:`);
            debugLog(`   Accuracy: ${accuracy}%`);
            debugLog(`   Games Trained: ${trainingGames}`);
            debugLog(`   Margin Error: ${margin.toFixed(2)} points`);
            
            // Also log the full data object for debugging
            debugLog('   Full response data:', JSON.stringify(result.data, null, 2));
            
            setMetrics({
              accuracy: accuracy,
              trainingGames: trainingGames,
              aiRating: aiRating,
              margin: margin,
              loading: false
            });
          }
        } else {
          debugLog('⚠️ No data in league metrics response');
          setMetrics({
            accuracy: 0,
            trainingGames: 0,
            aiRating: 'N/A',
            margin: 0,
            loading: false
          });
        }
      } catch (error) {
        console.error('❌ Exception fetching league metrics:', error);
        // Keep details only when debugging.
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
  }, [leagueId]);

  if (metrics.loading) {
    return (
      <Box sx={{ 
        width: '100%',
        minHeight: { xs: '200px', sm: '240px' },
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        py: 3,
        boxSizing: 'border-box',
      }}>
        <RugbyBallLoader size={100} color="#10b981" compact label="Loading metrics..." />
      </Box>
    );
  }

  return (
    <Box className="custom-metrics-container">
      <Box className="custom-metric">
        <Box className="metric-label">Accuracy</Box>
        <Box className="metric-value">{metrics.accuracy.toFixed(1)}%</Box>
        <Box className="metric-delta">League Specific</Box>
      </Box>
      <Box className="custom-metric">
        <Box className="metric-label">League</Box>
        <Box className="metric-value" sx={{ fontSize: '1.2rem' }}>{leagueName}</Box>
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
  );
});

export default LeagueMetrics;

