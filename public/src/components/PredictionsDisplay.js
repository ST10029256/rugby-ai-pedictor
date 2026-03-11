import React, { memo, useEffect, useMemo } from 'react';
import { Box, Typography, Grid } from '@mui/material';
import { MEDIA_URLS } from '../utils/storageUrls';
import { hasMeaningfulTime, formatSASTTimePM, formatSASTDateYMD } from '../utils/date';

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

  const getPredictionKickoffMs = (prediction) => {
    const kickoff = prediction?.kickoff_at;
    if (!kickoff) return Number.MAX_SAFE_INTEGER;
    const t = new Date(kickoff).getTime();
    return Number.isNaN(t) ? Number.MAX_SAFE_INTEGER : t;
  };

  // Group and sort predictions by date + kickoff time.
  const predictionsByDate = useMemo(() => {
    const grouped = {};
    (predictions || []).forEach((pred) => {
      const date = pred.date || (pred.kickoff_at && formatSASTDateYMD(pred.kickoff_at)) || 'TBD';
      if (!grouped[date]) grouped[date] = [];
      grouped[date].push(pred);
    });
    Object.keys(grouped).forEach((date) => {
      grouped[date].sort((a, b) => {
        const ta = getPredictionKickoffMs(a);
        const tb = getPredictionKickoffMs(b);
        if (ta !== tb) return ta - tb;
        const ah = String(a?.home_team || '');
        const bh = String(b?.home_team || '');
        if (ah !== bh) return ah.localeCompare(bh);
        return String(a?.away_team || '').localeCompare(String(b?.away_team || ''));
      });
    });
    return grouped;
  }, [predictions]);

  const getDisplayScores = (prediction) => {
    let homeScore = prediction.home_score;
    let awayScore = prediction.away_score;

    if (!homeScore && prediction.predicted_home_score !== undefined) {
      homeScore = Math.round(parseFloat(prediction.predicted_home_score)).toString();
    }
    if (!awayScore && prediction.predicted_away_score !== undefined) {
      awayScore = Math.round(parseFloat(prediction.predicted_away_score)).toString();
    }

    const homeNum = Number.parseInt(homeScore || '0', 10);
    const awayNum = Number.parseInt(awayScore || '0', 10);
    return {
      homeScore: homeScore || '0',
      awayScore: awayScore || '0',
      homeNum: Number.isNaN(homeNum) ? 0 : homeNum,
      awayNum: Number.isNaN(awayNum) ? 0 : awayNum,
    };
  };

  const getDisplayWinner = (prediction) => {
    const { homeNum, awayNum } = getDisplayScores(prediction);
    if (homeNum === awayNum) return 'Draw';
    return prediction.winner || prediction.predicted_winner || prediction.home_team;
  };

  // Calculate summary metrics
  const confidenceValues = predictions.map((p) => {
    const conf = typeof p.confidence === 'string' 
      ? parseFloat(p.confidence.replace('%', '')) 
      : (p.confidence * 100);
    return conf;
  });
  const highConf = confidenceValues.filter((c) => c >= 70).length;
  const homeWins = predictions.filter((p) => {
    const winner = getDisplayWinner(p);
    return winner === 'Home' || winner === p.home_team;
  }).length;
  const awayWins = predictions.filter((p) => {
    const winner = getDisplayWinner(p);
    return winner === 'Away' || winner === p.away_team;
  }).length;
  const draws = predictions.filter((p) => {
    const winner = getDisplayWinner(p);
    return winner === 'Draw';
  }).length;
  const avgScoreDiff = predictions.reduce((sum, p) => {
    const { homeNum, awayNum } = getDisplayScores(p);
    return sum + Math.abs(homeNum - awayNum);
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

  const summaryMetrics = [
    { value: `${highConf}/${predictions.length}`, label: 'High Confidence' },
    { value: avgScoreDiff.toFixed(1), label: 'Avg Margin (pts)' },
    { value: homeWins, label: 'Home Wins' },
    { value: awayWins, label: 'Away Wins' },
    { value: draws, label: 'Draws' },
    { value: `${hybridCount}/${predictions.length}`, label: 'Hybrid Predictions' },
    { value: `${(avgConfidenceBoost * 100).toFixed(1)}%`, label: 'Avg Confidence Boost' },
  ];

  return (
    <Box sx={{ 
      width: '100%', 
      maxWidth: { xs: 420, sm: '100%', md: 900, lg: '1600px' }, 
      boxSizing: 'border-box',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      mx: 'auto',
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
          <Box key={date} sx={{ width: '100%', maxWidth: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
            <Box className="date-header" sx={{ textAlign: 'center', width: '100%' }}>
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
              if (intensity.includes('Narrow')) intensityClass = 'intensity-close';
              else if (intensity.includes('Solid')) intensityClass = 'intensity-moderate';
              else if (intensity.includes('Wide')) intensityClass = 'intensity-decisive';
              const kickoffTimeDisplay =
                prediction.kickoff_at && hasMeaningfulTime(prediction.kickoff_at)
                  ? formatSASTTimePM(prediction.kickoff_at)
                  : '';

              // Display guard: if shown scores are equal, force Draw in UI.
              const winner = getDisplayWinner(prediction);
              const homeTeam = prediction.home_team;
              const awayTeam = prediction.away_team;
              
              let winnerClass = 'winner-home';
              if (winner === awayTeam) winnerClass = 'winner-away';
              else if (winner === 'Draw') winnerClass = 'winner-draw';

              const { homeScore, awayScore } = getDisplayScores(prediction);
              
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
                  {kickoffTimeDisplay && (
                    <Box sx={{ position: 'relative', height: { xs: 'auto', md: 86, lg: 94 }, mb: { xs: 1.5, sm: 1.85, md: 1.25 } }}>
                      <Box
                        sx={{
                          display: 'flex',
                          flexDirection: 'column',
                          alignItems: 'center',
                          justifyContent: 'center',
                          gap: { xs: 0.4, sm: 0.55 },
                          position: { xs: 'static', md: 'absolute' },
                          top: { md: '30%' },
                          left: { md: 0 },
                          right: { md: 0 },
                          transform: { md: 'translateY(-50%)' },
                        }}
                      >
                        <Typography
                          variant="overline"
                          sx={{
                            fontWeight: 700,
                            letterSpacing: { xs: 2.8, sm: 3.4, md: 3.8, lg: 4.2 },
                            fontSize: { xs: '0.54rem', sm: '0.62rem', md: '0.72rem', lg: '0.8rem' },
                            lineHeight: 1,
                            textTransform: 'uppercase',
                            color: 'rgba(226, 232, 240, 0.9)',
                            mb: { xs: 0.15, sm: 0.2 },
                            textShadow: '0 1px 3px rgba(0, 0, 0, 0.4)',
                          }}
                        >
                          Kickoff
                        </Typography>
                        <Typography
                          variant="body2"
                          sx={{
                            fontWeight: 900,
                            letterSpacing: { xs: 1.15, sm: 1.4, md: 1.6, lg: 1.8 },
                            textTransform: 'uppercase',
                            fontSize: { xs: '1.34rem', sm: '1.6rem', md: '1.95rem', lg: '2.15rem' },
                            lineHeight: 1,
                            textAlign: 'center',
                            background:
                              'linear-gradient(180deg, #ffffff 0%, #f8fafc 30%, #bae6fd 62%, #93c5fd 100%)',
                            WebkitBackgroundClip: 'text',
                            WebkitTextFillColor: 'transparent',
                            backgroundClip: 'text',
                            filter:
                              'drop-shadow(0 3px 10px rgba(59,130,246,0.4)) drop-shadow(0 2px 3px rgba(0,0,0,0.6))',
                          }}
                        >
                          {kickoffTimeDisplay}
                        </Typography>
                      </Box>
                    </Box>
                  )}
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

                  {(!prediction.manual_odds || !(prediction.manual_odds.home > 0 && prediction.manual_odds.away > 0)) &&
                    prediction.bookmaker_count > 0 && (
                      <Box className="odds-container">
                        <Box className="odds-header">
                          <Typography className="odds-title">📊 Live Bookmaker Consensus</Typography>
                        </Box>
                        <Box className="odds-row">
                          <Box className="odds-team">
                            <Typography className="team-name">{homeTeam}</Typography>
                            <Typography className="odds-value home-odds">
                              {((prediction.bookmaker_probability || 0) * 100).toFixed(1)}%
                            </Typography>
                          </Box>
                          <Typography className="odds-vs">VS</Typography>
                          <Box className="odds-team">
                            <Typography className="team-name">{awayTeam}</Typography>
                            <Typography className="odds-value away-odds">
                              {((1 - (prediction.bookmaker_probability || 0)) * 100).toFixed(1)}%
                            </Typography>
                          </Box>
                        </Box>
                        <Typography sx={{ textAlign: 'center', color: '#9ca3af', fontSize: '0.82rem', mt: 1 }}>
                          {prediction.bookmaker_count} bookmakers
                        </Typography>
                      </Box>
                    )}

                  <Box sx={{ borderTop: '1px solid #4b5563', borderBottom: '1px solid #4b5563', py: 2, my: 2 }}>
                    <Box className="winner-display">
                      <Typography
                        className={`winner-text ${winnerClass}`}
                        sx={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          gap: '0.38em',
                          width: '100%',
                          textAlign: 'center',
                        }}
                      >
                        {winner === 'Draw' ? (
                          <>
                            <Box component="span" sx={{ width: '1.1em', textAlign: 'center', lineHeight: 1 }}>
                              🤝
                            </Box>
                            <Box component="span">Draw</Box>
                          </>
                        ) : (
                          `🏆 ${winner} Wins`
                        )}
                      </Typography>
                    </Box>

                    <Box className="confidence-bar">
                      <Box className={`confidence-fill ${confClass}`} style={{ width: `${confidence}%` }}>
                        <Box className="confidence-text">{confidence.toFixed(1)}% Confidence</Box>
                      </Box>
                    </Box>

                    <Box
                      className={`intensity-badge ${intensityClass}`}
                      sx={{
                        mt: { xs: 1.5, sm: 1.8, md: 2.1 },
                        mx: 'auto',
                        width: 'fit-content',
                        minWidth: { xs: '78%', sm: '66%', md: '58%', lg: '52%' },
                        px: { xs: 1.25, sm: 1.8, md: 2.2, lg: 2.5 },
                        py: { xs: 0.78, sm: 0.92, md: 1.05 },
                        borderRadius: { xs: 999, md: 999 },
                        fontSize: { xs: '0.88rem', sm: '0.95rem', md: '1.02rem', lg: '1.08rem' },
                        lineHeight: 1.15,
                        fontWeight: 800,
                        letterSpacing: 0.15,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        textAlign: 'center',
                        boxShadow: '0 8px 24px rgba(2,6,23,0.28)',
                      }}
                    >
                      📊 {intensity}
                    </Box>
                    {/* Method label */}
                    <Typography
                      variant="body2"
                      className="method-label"
                      sx={{
                        textAlign: 'center',
                        mt: { xs: 1.4, sm: 1.7, md: 2 },
                        mx: 'auto',
                        width: 'fit-content',
                        maxWidth: { xs: '94%', sm: '86%', md: '78%', lg: '72%' },
                        px: { xs: 1.05, sm: 1.4, md: 1.7 },
                        py: { xs: 0.55, sm: 0.62, md: 0.72 },
                        borderRadius: 999,
                        border: '1px solid rgba(148,163,184,0.32)',
                        background: 'linear-gradient(145deg, rgba(30,41,59,0.8), rgba(15,23,42,0.8))',
                        fontSize: { xs: '0.74rem', sm: '0.8rem', md: '0.86rem', lg: '0.9rem' },
                        fontWeight: 700,
                        letterSpacing: 0.12,
                        lineHeight: 1.12,
                      }}
                    >
                      🔬 Method: {prediction.prediction_type || 'AI Only (No Odds)'}
                    </Typography>

                    {/* Hybrid analysis - Clean display */}
                    {(prediction.prediction_type === 'Hybrid AI + Manual Odds' || prediction.prediction_type === 'Hybrid AI + Live Odds') && (
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
          {summaryMetrics.map((metric) => (
            <Grid key={metric.label} item xs={6} md={3} sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
              <Box className="summary-metric" sx={{ width: '100%', textAlign: 'center' }}>
                <Typography className="summary-metric-value" sx={{ textAlign: 'center', width: '100%' }}>
                  {metric.value}
                </Typography>
                <Typography className="summary-metric-label" sx={{ textAlign: 'center', width: '100%' }}>
                  {metric.label}
                </Typography>
              </Box>
            </Grid>
          ))}
        </Grid>
      </Box>
    </Box>
  );
});

export default PredictionsDisplay;

