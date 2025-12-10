import React, { useState, useEffect, memo } from 'react';
import { Box, CircularProgress } from '@mui/material';
import { getLeagueMetrics } from '../firebase';

const LeagueMetrics = memo(function LeagueMetrics({ leagueId, leagueName }) {
  const [metrics, setMetrics] = useState({
    accuracy: 0,
    trainingGames: 0,
    aiRating: 'N/A',
    last10Accuracy: 0,
    loading: true
  });

  useEffect(() => {
        if (!leagueId) {
      setMetrics({ accuracy: 0, trainingGames: 0, aiRating: 'N/A', last10Accuracy: 0, loading: false });
      return;
    }

    const fetchMetrics = async () => {
      try {
        console.log(`📊 Fetching league metrics for league_id: ${leagueId}`);
        setMetrics(prev => ({ ...prev, loading: true }));
        const result = await getLeagueMetrics({ league_id: leagueId });
        
        console.log('📊 League metrics API response:', result);
        console.log('📊 Result.data:', result?.data);
        
        if (result && result.data) {
          if (result.data.error) {
            console.error('❌ League metrics error:', result.data.error);
            setMetrics({
              accuracy: 0,
              trainingGames: 0,
              aiRating: 'N/A',
              last10Accuracy: 0,
              loading: false
            });
          } else {
            const accuracy = result.data.accuracy || 0;
            const trainingGames = result.data.training_games || 0;
            const aiRating = result.data.ai_rating || 'N/A';
            const last10Accuracy = result.data.last_10_accuracy || 0;
            
            console.log('✅ League metrics received:', {
              accuracy: accuracy,
              training_games: trainingGames,
              ai_rating: aiRating,
              last_10_accuracy: last10Accuracy,
              full_data: result.data
            });
            
            // Log the actual values clearly
            console.log(`📊 Metrics for league ${leagueId}:`);
            console.log(`   Accuracy: ${accuracy}%`);
            console.log(`   Games Trained: ${trainingGames}`);
            console.log(`   AI last 10 games: ${last10Accuracy}/10`);
            
            // Also log the full data object for debugging
            console.log('   Full response data:', JSON.stringify(result.data, null, 2));
            
            setMetrics({
              accuracy: accuracy,
              trainingGames: trainingGames,
              aiRating: aiRating,
              last10Accuracy: last10Accuracy,
              loading: false
            });
          }
        } else {
          console.warn('⚠️ No data in league metrics response');
          setMetrics({
            accuracy: 0,
            trainingGames: 0,
            aiRating: 'N/A',
            last10Accuracy: 0,
            loading: false
          });
        }
      } catch (error) {
        console.error('❌ Exception fetching league metrics:', error);
        console.error('Error details:', {
          name: error.name,
          message: error.message,
          stack: error.stack
        });
        setMetrics({
          accuracy: 0,
          trainingGames: 0,
          aiRating: 'N/A',
          last10Accuracy: 0,
          loading: false
        });
      }
    };

    fetchMetrics();
  }, [leagueId]);

  if (metrics.loading) {
    return (
      <Box className="custom-metrics-container" sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '150px' }}>
        <CircularProgress size={40} sx={{ color: '#10b981' }} />
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
        <Box className="metric-label">AI last 10 games</Box>
        <Box className="metric-value">
          {metrics.last10Accuracy > 0 
            ? `${metrics.last10Accuracy}/10`
            : 'N/A'}
        </Box>
        <Box className="metric-delta">Based on Accuracy</Box>
      </Box>
    </Box>
  );
});

export default LeagueMetrics;

