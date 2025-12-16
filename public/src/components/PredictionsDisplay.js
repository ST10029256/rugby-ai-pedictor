import React, { memo, useEffect } from 'react';
import { Box, Typography, Grid } from '@mui/material';
import { MEDIA_URLS } from '../utils/storageUrls';

const PredictionsDisplay = memo(function PredictionsDisplay({ predictions, leagueName }) {
  // Log image loading status
  useEffect(() => {
    const img = new Image();
    img.onload = () => {
      const source = MEDIA_URLS.imageRugby;
      if (source.includes('firebasestorage.googleapis.com')) {
        console.log('✅ [Storage] Rugby image loaded successfully from Firebase Storage');
      } else {
        console.log('📁 [Local] Rugby image loaded from local file');
      }
    };
    img.onerror = (e) => {
      console.error('❌ [Storage] Rugby image failed to load from:', MEDIA_URLS.imageRugby);
      console.error('Error details:', e);
    };
    img.src = MEDIA_URLS.imageRugby;
  }, []);

  // Group predictions by date
  const predictionsByDate = {};
  predictions.forEach((pred) => {
    const date = pred.date || 'TBD';
    if (!predictionsByDate[date]) {
      predictionsByDate[date] = [];
    }
    predictionsByDate[date].push(pred);
  });

  // Calculate summary metrics
  const confidenceValues = predictions.map((p) => {
    const conf = typeof p.confidence === 'string' 
      ? parseFloat(p.confidence.replace('%', '')) 
      : (p.confidence * 100);
    return conf;
  });
  const highConf = confidenceValues.filter((c) => c >= 70).length;
  const homeWins = predictions.filter((p) => {
    const winner = p.predicted_winner || p.winner || 'Home';
    return winner === 'Home' || winner === p.home_team;
  }).length;
  const awayWins = predictions.filter((p) => {
    const winner = p.predicted_winner || p.winner || 'Home';
    return winner === 'Away' || winner === p.away_team;
  }).length;
  const draws = predictions.filter((p) => {
    const winner = p.predicted_winner || p.winner || 'Home';
    return winner === 'Draw';
  }).length;
  const avgScoreDiff = predictions.reduce((sum, p) => {
    const home = parseFloat(p.predicted_home_score || p.home_score || 0);
    const away = parseFloat(p.predicted_away_score || p.away_score || 0);
    return sum + Math.abs(home - away);
  }, 0) / predictions.length;

  const hybridCount = predictions.filter(
    (p) => p.prediction_type === 'Hybrid AI + Manual Odds' || p.prediction_type === 'Hybrid AI + Live Odds'
  ).length;
  const confidenceBoosts = predictions
    .map((p) => (typeof p.confidence_boost === 'number' ? p.confidence_boost : 0))
    .filter((v) => !Number.isNaN(v));
  const avgConfidenceBoost =
    confidenceBoosts.length > 0
      ? confidenceBoosts.reduce((sum, v) => sum + v, 0) / confidenceBoosts.length
      : 0;

  return (
    <Box sx={{ 
      width: '100%', 
      maxWidth: '100%', 
      boxSizing: 'border-box',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      '@media (min-width: 1024px)': {
        maxWidth: '1600px',
        margin: '0 auto',
      },
      '@media (min-width: 1440px)': {
        maxWidth: '1800px',
      },
      '@media (min-width: 1920px)': {
        maxWidth: '2000px',
      },
    }}>
      {/* Predictions grouped by date */}
      {Object.keys(predictionsByDate)
        .sort()
        .map((date) => (
          <Box key={date} sx={{ width: '100%', maxWidth: '100%' }}>
            <Box className="date-header">
              <Typography variant="h2" component="h2">
                📅 {date}
              </Typography>
            </Box>

            {predictionsByDate[date].map((prediction, idx) => {
              // Normalize confidence (handle both string "68.5%" and number 0.685)
              let confidence = 50;
              if (typeof prediction.confidence === 'string') {
                confidence = parseFloat(prediction.confidence.replace('%', '')) || 50;
              } else if (typeof prediction.confidence === 'number') {
                confidence = prediction.confidence * 100;
              }
              
              let confClass = 'confidence-medium';
              if (confidence >= 80) confClass = 'confidence-high';
              else if (confidence < 65) confClass = 'confidence-low';

              // Use intensity from prediction (matching Streamlit - already calculated)
              const intensity = prediction.intensity || 'Competitive Game';
              
              let intensityClass = 'intensity-competitive';
              if (intensity.includes('Close')) intensityClass = 'intensity-close';
              else if (intensity.includes('Moderate')) intensityClass = 'intensity-moderate';
              else if (intensity.includes('Decisive')) intensityClass = 'intensity-decisive';

              // Use winner field directly (matching Streamlit - it's already a team name or 'Draw')
              const winner = prediction.winner || prediction.predicted_winner || prediction.home_team;
              const homeTeam = prediction.home_team;
              const awayTeam = prediction.away_team;
              
              let winnerClass = 'winner-home';
              if (winner === awayTeam) winnerClass = 'winner-away';
              else if (winner === 'Draw') winnerClass = 'winner-draw';

              // Extract scores - prioritize home_score/away_score (set in App.js), fallback to predicted_*_score
              let homeScore = prediction.home_score;
              let awayScore = prediction.away_score;
              
              // If home_score/away_score are not set, try predicted_*_score
              if (!homeScore && prediction.predicted_home_score !== undefined) {
                homeScore = Math.round(parseFloat(prediction.predicted_home_score)).toString();
              }
              if (!awayScore && prediction.predicted_away_score !== undefined) {
                awayScore = Math.round(parseFloat(prediction.predicted_away_score)).toString();
              }
              
              // Final fallback
              homeScore = homeScore || '0';
              awayScore = awayScore || '0';
              
              // Score extraction complete

              return (
              <Box 
                key={idx} 
                className="prediction-card fade-in-up"
                sx={{
                  backgroundImage: `url(${MEDIA_URLS.imageRugby})`,
                  backgroundSize: 'cover',
                  backgroundPosition: 'center',
                  backgroundRepeat: 'no-repeat',
                  position: 'relative',
                  '&::after': {
                    content: '""',
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    right: 0,
                    bottom: 0,
                    background: 'linear-gradient(145deg, rgba(26, 32, 44, 0.85) 0%, rgba(45, 55, 72, 0.85) 100%)',
                    zIndex: 0,
                    pointerEvents: 'none',
                  },
                  '& > *': {
                    position: 'relative',
                    zIndex: 1,
                  },
                }}
              >
                  {/* Score Display - Matching Streamlit exactly */}
                  <Box sx={{ my: 2 }}>
                    <Box sx={{ borderTop: '1px solid #4b5563', mb: 3 }} />
                    <Grid container spacing={{ xs: 0.5, sm: 2, md: 3 }} alignItems="center" justifyContent="center" sx={{ mb: 2, width: '100%', margin: '0 auto', maxWidth: '100%' }}>
                      <Grid item xs={5} sm={4} md={4} lg={4} xl={4} sx={{ 
                        padding: { xs: '0.25rem', sm: '0.5rem', md: '1rem' }, 
                        boxSizing: 'border-box',
                        minWidth: 0,
                        overflow: 'hidden',
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        justifyContent: 'center'
                      }}>
                        <Typography className="team-name" sx={{ 
                          wordBreak: 'break-word',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          display: '-webkit-box',
                          WebkitLineClamp: { xs: 2, sm: 1 },
                          WebkitBoxOrient: 'vertical',
                          lineHeight: { xs: '1.2', sm: '1.5' },
                          minHeight: { xs: '2.4em', sm: 'auto' },
                          maxHeight: { xs: '2.4em', sm: 'none' },
                          textAlign: 'center',
                          width: '100%',
                          marginBottom: { xs: '0.5rem', sm: '1rem' }
                        }}>{homeTeam}</Typography>
                        <Box component="div" className="team-score" sx={{ textAlign: 'center', width: '100%', fontWeight: 900, fontSize: { xs: '3.5rem', sm: '5rem', md: '7rem' }, fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "Roboto", "Oxygen", "Ubuntu", "Cantarell", "Fira Sans", "Droid Sans", "Helvetica Neue", sans-serif' }}>{homeScore}</Box>
                      </Grid>
                      <Grid item xs={2} sm={4} md={4} lg={4} xl={4} sx={{ 
                        display: 'flex', 
                        flexDirection: 'column',
                        alignItems: 'center', 
                        justifyContent: 'center', 
                        padding: { xs: '0.25rem', sm: '0.5rem', md: '1rem' }, 
                        boxSizing: 'border-box',
                        flexShrink: 0,
                        minWidth: { xs: '40px', sm: 'auto' },
                        alignSelf: { xs: 'stretch', sm: 'flex-end', md: 'flex-end' }
                      }}>
                        <Box sx={{ 
                          display: 'flex', 
                          alignItems: 'center', 
                          justifyContent: 'center', 
                          width: '100%',
                          height: '100%',
                          marginTop: { xs: '2.4em', sm: '2.4em', md: '2.4em' },
                          marginBottom: { xs: '0', sm: '0', md: '0' }
                        }}>
                          <Typography className="vs-text" sx={{ textAlign: 'center', width: '100%', margin: 0 }}>VS</Typography>
                        </Box>
                      </Grid>
                      <Grid item xs={5} sm={4} md={4} lg={4} xl={4} sx={{ 
                        padding: { xs: '0.25rem', sm: '0.5rem', md: '1rem' }, 
                        boxSizing: 'border-box',
                        minWidth: 0,
                        overflow: 'hidden',
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        justifyContent: 'center'
                      }}>
                        <Typography className="team-name" sx={{ 
                          wordBreak: 'break-word',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          display: '-webkit-box',
                          WebkitLineClamp: { xs: 2, sm: 1 },
                          WebkitBoxOrient: 'vertical',
                          lineHeight: { xs: '1.2', sm: '1.5' },
                          minHeight: { xs: '2.4em', sm: 'auto' },
                          maxHeight: { xs: '2.4em', sm: 'none' },
                          textAlign: 'center',
                          width: '100%',
                          marginBottom: { xs: '0.5rem', sm: '1rem' }
                        }}>{awayTeam}</Typography>
                        <Box component="div" className="team-score" sx={{ textAlign: 'center', width: '100%', fontWeight: 900, fontSize: { xs: '3.5rem', sm: '5rem', md: '7rem' }, fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "Roboto", "Oxygen", "Ubuntu", "Cantarell", "Fira Sans", "Droid Sans", "Helvetica Neue", sans-serif' }}>{awayScore}</Box>
                      </Grid>
                    </Grid>
                  </Box>

                  {/* Manual Odds Display */}
                  {prediction.manual_odds && prediction.manual_odds.home > 0 && prediction.manual_odds.away > 0 && (
                    <Box className="odds-container">
                      <Box className="odds-header">
                        <Typography className="odds-title">💰 Manual Betting Odds</Typography>
                      </Box>
                      <Box className="odds-row">
                        <Box className="odds-team">
                          <Typography className="team-name">{homeTeam}</Typography>
                          <Typography className="odds-value home-odds">
                            {prediction.manual_odds.home.toFixed(2)}
                          </Typography>
                        </Box>
                        <Typography className="odds-vs">VS</Typography>
                        <Box className="odds-team">
                          <Typography className="team-name">{awayTeam}</Typography>
                          <Typography className="odds-value away-odds">
                            {prediction.manual_odds.away.toFixed(2)}
                          </Typography>
                        </Box>
                      </Box>
                    </Box>
                  )}

                  <Box sx={{ borderTop: '1px solid #4b5563', borderBottom: '1px solid #4b5563', py: 2, my: 2 }}>
                    <Box className="winner-display">
                      <Typography className={`winner-text ${winnerClass}`}>
                        🏆 {winner} Wins
                      </Typography>
                    </Box>

                    <Box className="confidence-bar">
                      <Box className={`confidence-fill ${confClass}`} style={{ width: `${confidence}%` }}>
                        <Box className="confidence-text">{confidence.toFixed(1)}% Confidence</Box>
                      </Box>
                    </Box>

                    <Box className={`intensity-badge ${intensityClass}`}>
                      📊 {intensity}
                    </Box>
                    {/* Method label */}
                    <Typography variant="body2" className="method-label" sx={{ textAlign: 'center', mt: 2 }}>
                      🔬 Method: {prediction.prediction_type || 'AI Only (No Odds)'}
                    </Typography>

                    {/* Hybrid analysis - Clean display */}
                    {prediction.prediction_type === 'Hybrid AI + Manual Odds' && (
                      <Box sx={{ mt: 3, pt: 2, borderTop: '1px solid #4b5563' }}>
                        <Typography
                          variant="body2"
                          sx={{ color: '#ffffff', fontWeight: 600, mb: 2, textAlign: 'center', fontSize: '1rem' }}
                        >
                          🎯 Hybrid Analysis
                        </Typography>
                        <Grid container spacing={2}>
                          <Grid item xs={4}>
                            <Box sx={{ textAlign: 'center' }}>
                              <Typography sx={{ fontSize: { xs: '1.5rem', sm: '1.8rem' }, fontWeight: 700, color: '#ffffff', mb: 0.5 }}>
                                {(prediction.ai_probability * 100).toFixed(1)}%
                              </Typography>
                              <Typography sx={{ fontSize: { xs: '0.75rem', sm: '0.85rem' }, color: '#9ca3af', fontWeight: 500 }}>
                                🤖 AI Only
                              </Typography>
                            </Box>
                          </Grid>
                          <Grid item xs={4}>
                            <Box sx={{ textAlign: 'center' }}>
                              <Typography sx={{ fontSize: { xs: '1.5rem', sm: '1.8rem' }, fontWeight: 700, color: '#10b981', mb: 0.5 }}>
                                {(prediction.hybrid_probability * 100).toFixed(1)}%
                              </Typography>
                              <Typography sx={{ fontSize: { xs: '0.75rem', sm: '0.85rem' }, color: '#9ca3af', fontWeight: 500 }}>
                                🎲 Hybrid
                              </Typography>
                            </Box>
                          </Grid>
                          <Grid item xs={4}>
                            <Box sx={{ textAlign: 'center' }}>
                              <Typography sx={{ fontSize: { xs: '1.5rem', sm: '1.8rem' }, fontWeight: 700, color: '#fbbf24', mb: 0.5 }}>
                                +{(prediction.confidence_boost * 100).toFixed(1)}%
                              </Typography>
                              <Typography sx={{ fontSize: { xs: '0.75rem', sm: '0.85rem' }, color: '#9ca3af', fontWeight: 500 }}>
                                📈 Boost
                              </Typography>
                            </Box>
                          </Grid>
                        </Grid>
                      </Box>
                    )}
                  </Box>
                </Box>
              );
            })}
          </Box>
        ))}

      {/* Summary Section */}
      <Box className="summary-card">
        <Typography className="summary-title">📊 Prediction Summary</Typography>
        <Grid container spacing={3} sx={{ mt: 2, justifyContent: 'center', width: '100%', maxWidth: '100%' }}>
          <Grid item xs={6} md={3} sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
            <Box className="summary-metric" sx={{ width: '100%', textAlign: 'center' }}>
              <Typography className="summary-metric-value" sx={{ textAlign: 'center', width: '100%' }}>{highConf}/{predictions.length}</Typography>
              <Typography className="summary-metric-label" sx={{ textAlign: 'center', width: '100%' }}>High Confidence</Typography>
            </Box>
          </Grid>
          <Grid item xs={6} md={3} sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
            <Box className="summary-metric" sx={{ width: '100%', textAlign: 'center' }}>
              <Typography className="summary-metric-value" sx={{ textAlign: 'center', width: '100%' }}>{homeWins}</Typography>
              <Typography className="summary-metric-label" sx={{ textAlign: 'center', width: '100%' }}>Home Wins</Typography>
            </Box>
          </Grid>
          <Grid item xs={6} md={3} sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
            <Box className="summary-metric" sx={{ width: '100%', textAlign: 'center' }}>
              <Typography className="summary-metric-value" sx={{ textAlign: 'center', width: '100%' }}>{hybridCount}/{predictions.length}</Typography>
              <Typography className="summary-metric-label" sx={{ textAlign: 'center', width: '100%' }}>Hybrid Predictions</Typography>
            </Box>
          </Grid>
          <Grid item xs={6} md={3} sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
            <Box className="summary-metric" sx={{ width: '100%', textAlign: 'center' }}>
              <Typography className="summary-metric-value" sx={{ textAlign: 'center', width: '100%' }}>
                {(avgConfidenceBoost * 100).toFixed(1)}%
              </Typography>
              <Typography className="summary-metric-label" sx={{ textAlign: 'center', width: '100%' }}>Avg Confidence Boost</Typography>
            </Box>
          </Grid>
          <Grid item xs={6} md={3} sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
            <Box className="summary-metric" sx={{ 
              width: '100%', 
              textAlign: 'center', 
              transform: { 
                md: 'translateX(8vw)'
              } 
            }}>
              <Typography className="summary-metric-value" sx={{ textAlign: 'center', width: '100%' }}>{awayWins}</Typography>
              <Typography className="summary-metric-label" sx={{ textAlign: 'center', width: '100%' }}>Away Wins</Typography>
            </Box>
          </Grid>
          <Grid item xs={6} md={3} sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
            <Box className="summary-metric" sx={{ 
              width: '100%', 
              textAlign: 'center', 
              transform: { 
                md: 'translateX(8vw)'
              } 
            }}>
              <Typography className="summary-metric-value" sx={{ textAlign: 'center', width: '100%' }}>{draws}</Typography>
              <Typography className="summary-metric-label" sx={{ textAlign: 'center', width: '100%' }}>Draws</Typography>
            </Box>
          </Grid>
          <Grid item xs={12} md={6} sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
            <Box className="summary-metric" sx={{ width: '100%', textAlign: 'center' }}>
              <Typography className="summary-metric-value" sx={{ textAlign: 'center', width: '100%' }}>{avgScoreDiff.toFixed(1)}</Typography>
              <Typography className="summary-metric-label" sx={{ textAlign: 'center', width: '100%' }}>Avg Margin (pts)</Typography>
            </Box>
          </Grid>
        </Grid>
      </Box>
    </Box>
  );
});

export default PredictionsDisplay;

