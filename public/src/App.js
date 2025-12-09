import React, { useState, useEffect } from 'react';
import { Box, Drawer, Typography, CssBaseline, ThemeProvider, createTheme, CircularProgress, IconButton, useMediaQuery } from '@mui/material';
import MenuIcon from '@mui/icons-material/Menu';
import CloseIcon from '@mui/icons-material/Close';
import LeagueSelector from './components/LeagueSelector';
import LeagueMetrics from './components/LeagueMetrics';
import LiveMatches from './components/LiveMatches';
import ManualOddsInput from './components/ManualOddsInput';
import PredictionsDisplay from './components/PredictionsDisplay';
import { getLeagues, getUpcomingMatches } from './firebase';
import './App.css';

const darkTheme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: '#10b981',
    },
    secondary: {
      main: '#3b82f6',
    },
    background: {
      default: '#0e1117',
      paper: '#1f2937',
    },
  },
});

const LEAGUE_CONFIGS = {
  4986: { name: "Rugby Championship", neutral_mode: false },
  4446: { name: "United Rugby Championship", neutral_mode: false },
  5069: { name: "Currie Cup", neutral_mode: false },
  4574: { name: "Rugby World Cup", neutral_mode: true },
  4551: { name: "Super Rugby", neutral_mode: false },
  4430: { name: "French Top 14", neutral_mode: false },
  4414: { name: "English Premiership Rugby", neutral_mode: false },
  5479: { name: "Rugby Union International Friendlies", neutral_mode: true },
};

function App() {
  const [leagues, setLeagues] = useState([]);
  const [selectedLeague, setSelectedLeague] = useState(null);
  const [upcomingMatches, setUpcomingMatches] = useState([]);
  const [predictions, setPredictions] = useState([]);
  const [manualOdds, setManualOdds] = useState({});
  const [loading, setLoading] = useState(true);
  const [loadingMatches, setLoadingMatches] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  
  const isMobile = useMediaQuery('(max-width:768px)');

  useEffect(() => {
    // Load leagues - try API first, fallback to LEAGUE_CONFIGS
    getLeagues()
      .then((result) => {
        console.log('Leagues API response:', result);
        console.log('Result data:', result?.data);
        let availableLeagues = [];
        
        if (result && result.data) {
          if (result.data.leagues && Array.isArray(result.data.leagues)) {
            availableLeagues = result.data.leagues;
            console.log('Found leagues in result.data.leagues:', availableLeagues);
          } else if (result.data.error) {
            console.warn('API returned error, using fallback:', result.data.error);
            // Fallback to LEAGUE_CONFIGS
            availableLeagues = Object.entries(LEAGUE_CONFIGS).map(([id, config]) => ({
              id: parseInt(id),
              name: config.name,
            }));
          } else {
            // Check if data is directly the leagues array
            if (Array.isArray(result.data)) {
              availableLeagues = result.data;
            } else {
              // Try to find leagues in nested structure
              const possibleLeagues = result.data.leagues || result.data.data?.leagues || [];
              if (Array.isArray(possibleLeagues) && possibleLeagues.length > 0) {
                availableLeagues = possibleLeagues;
              }
            }
          }
        }
        
        // If still empty, use LEAGUE_CONFIGS as fallback
        if (availableLeagues.length === 0) {
          console.log('Using LEAGUE_CONFIGS fallback');
          availableLeagues = Object.entries(LEAGUE_CONFIGS).map(([id, config]) => ({
            id: parseInt(id),
            name: config.name,
          }));
        }
        
        console.log('Final available leagues:', availableLeagues);
        setLeagues(availableLeagues);
        if (availableLeagues.length > 0) {
          setSelectedLeague(availableLeagues[0].id);
          console.log('Set selected league to:', availableLeagues[0].id);
        }
        setLoading(false);
      })
      .catch((error) => {
        console.error('Error loading leagues from API, using fallback:', error);
        // Fallback to LEAGUE_CONFIGS
        const fallbackLeagues = Object.entries(LEAGUE_CONFIGS).map(([id, config]) => ({
          id: parseInt(id),
          name: config.name,
        }));
        setLeagues(fallbackLeagues);
        if (fallbackLeagues.length > 0) {
          setSelectedLeague(fallbackLeagues[0].id);
        }
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (!selectedLeague) {
      setUpcomingMatches([]);
      return;
    }

    // Clear old matches immediately to prevent showing wrong games
    setUpcomingMatches([]);
    setPredictions([]);
    setLoadingMatches(true);

    const fetchUpcoming = async () => {
      console.log('\n=== fetchUpcoming called ===');
      console.log('Selected league:', selectedLeague);
      
      try {
        console.log('📡 Calling getUpcomingMatches API...');
        const startTime = Date.now();
        const result = await getUpcomingMatches({ league_id: selectedLeague, limit: 50 });
        const duration = Date.now() - startTime;
        console.log(`⏱️ API call took ${duration}ms`);
        
        console.log('📦 Full result object:', result);
        console.log('📦 Result.data:', result?.data);
        console.log('📦 Result.data.matches:', result?.data?.matches);
        
        if (result && result.data) {
          const matches = result.data.matches || [];
          console.log(`✅ Found ${matches.length} upcoming matches`);
          
          if (result.data.debug) {
            console.log('🔍 Debug info:', result.data.debug);
            console.log(`   Total checked: ${result.data.debug.total_checked}`);
            console.log(`   With scores: ${result.data.debug.with_scores}`);
            console.log(`   Past dates: ${result.data.debug.past_dates}`);
            console.log(`   No date: ${result.data.debug.no_date}`);
            console.log(`   Date parse failures: ${result.data.debug.date_parse_failures}`);
            console.log(`   Team lookup count: ${result.data.debug.team_lookup_count}`);
            console.log(`   Team names found: ${result.data.debug.team_names_found}`);
            console.log(`   Women filtered: ${result.data.debug.women_filtered}`);
            
            if (result.data.debug.sample_dates && result.data.debug.sample_dates.length > 0) {
              console.log('   Sample failed dates:', result.data.debug.sample_dates);
            }
          }
          
          if (result.data.warning) {
            console.warn('⚠️ API warning:', result.data.warning);
          }
          
          if (result.data.error) {
            console.error('❌ API error:', result.data.error);
          }
          
          console.log('📋 Matches array:', matches);
          setUpcomingMatches(matches);
          console.log('✅ State updated with matches');
        } else {
          console.warn('⚠️ No matches data in result');
          console.warn('Result structure:', {
            hasResult: !!result,
            hasData: !!(result?.data),
            dataKeys: result?.data ? Object.keys(result.data) : []
          });
          setUpcomingMatches([]);
        }
      } catch (err) {
        console.error('❌ Exception loading upcoming matches:', err);
        console.error('Error name:', err.name);
        console.error('Error message:', err.message);
        console.error('Error stack:', err.stack);
        setUpcomingMatches([]);
      } finally {
        setLoadingMatches(false);
      }
      
      console.log('=== fetchUpcoming completed ===\n');
    };

    fetchUpcoming();
  }, [selectedLeague]);

  const handleGeneratePredictions = async () => {
    console.log('=== handleGeneratePredictions called ===');
    console.log('selectedLeague:', selectedLeague);
    console.log('upcomingMatches.length:', upcomingMatches.length);
    console.log('upcomingMatches:', upcomingMatches);
    
    if (!selectedLeague || upcomingMatches.length === 0) {
      console.warn('Cannot generate predictions: no league selected or no matches');
      console.warn('selectedLeague:', selectedLeague, 'upcomingMatches.length:', upcomingMatches.length);
      return;
    }

    console.log('✅ Starting prediction generation for', upcomingMatches.length, 'matches');
    console.log('League ID:', selectedLeague);
    setGenerating(true);
    const newPredictions = [];
    const seenMatchups = new Set(); // Track unique matchups (matching Streamlit)
    console.log('Initialized prediction arrays');

    // Import predictMatch dynamically
    console.log('Importing predictMatch from firebase...');
    const { predictMatch } = await import('./firebase');
    console.log('✅ predictMatch imported:', typeof predictMatch);

    // Precompute unique match tasks (so we don't waste time on duplicates)
    const tasks = [];
    for (const match of upcomingMatches) {
      const matchDate = match.date_event ? match.date_event.split('T')[0] : new Date().toISOString().split('T')[0];
      const matchupKey = `${match.home_team_id || match.home_team}::${match.away_team_id || match.away_team}::${matchDate}`;
      if (seenMatchups.has(matchupKey)) {
        console.log('⏭️ Skipping duplicate matchup (precompute):', matchupKey);
        continue;
      }
      seenMatchups.add(matchupKey);

      const idKey = `manual_odds_by_ids::${match.home_team_id || ''}::${match.away_team_id || ''}::${matchDate}`;
      const nameKey = `${match.home_team}::${match.away_team}::${matchDate}`;
      const odds = manualOdds[idKey] || manualOdds[nameKey];

      tasks.push({ match, matchDate, matchupKey, odds });
    }

    console.log(`Prepared ${tasks.length} unique match tasks (from ${upcomingMatches.length} upcoming matches)`);

    // Helper function to retry API calls with exponential backoff
    const retryWithBackoff = async (fn, maxRetries = 3, initialDelay = 1000) => {
      for (let attempt = 0; attempt < maxRetries; attempt++) {
        try {
          return await fn();
        } catch (error) {
          const isLastAttempt = attempt === maxRetries - 1;
          const isCorsError = error.message?.includes('CORS') || error.code === 'functions/internal';
          const is503Error = error.message?.includes('503') || error.code === 'functions/unavailable';
          
          if (isLastAttempt) {
            throw error;
          }
          
          // Only retry on CORS/503 errors
          if (isCorsError || is503Error) {
            const delay = initialDelay * Math.pow(2, attempt);
            console.log(`⚠️ Retry attempt ${attempt + 1}/${maxRetries} after ${delay}ms`);
            await new Promise(resolve => setTimeout(resolve, delay));
          } else {
            throw error;
          }
        }
      }
    };

    // Worker to process tasks with limited parallelism
    const concurrency = Math.min(2, tasks.length || 1); // Reduced to 2 to avoid overwhelming backend
    let taskIndex = 0;

    const runTask = async () => {
      while (taskIndex < tasks.length) {
        const currentIndex = taskIndex++;
        const { match, matchDate, odds } = tasks[currentIndex];

        console.log(`\n--- Processing match ${currentIndex + 1}/${tasks.length} ---`);
        console.log('Match data:', match);
        console.log('Match date:', matchDate);
        console.log('Manual odds found:', odds);

        try {
          console.log(`📊 Calling predictMatch: ${match.home_team} vs ${match.away_team} (${matchDate})`);
          console.log('Request params:', {
            home_team: match.home_team,
            away_team: match.away_team,
            league_id: selectedLeague,
            match_date: matchDate,
            enhanced: false,
          });

          const startTime = Date.now();
          const result = await retryWithBackoff(async () => {
            return await predictMatch({
              home_team: match.home_team,
              away_team: match.away_team,
              league_id: selectedLeague,
              match_date: matchDate,
              enhanced: false,
            });
          });
          const duration = Date.now() - startTime;
          console.log(`⏱️ Prediction took ${duration}ms`);
          console.log('Result:', result);
          console.log('Result.data:', result?.data);

          if (result && result.data && !result.data.error) {
            console.log('✅ Prediction successful');
            const pred = result.data;

            // Extract AI prediction values (matching Streamlit make_expert_prediction)
            const aiHomeWinProb = pred.home_win_prob || 0.5;
            const predictedHomeScore = parseFloat(pred.predicted_home_score || 0);
            const predictedAwayScore = parseFloat(pred.predicted_away_score || 0);
            
            console.log(`📊 Scores for ${match.home_team} vs ${match.away_team}:`, {
              predicted_home_score: pred.predicted_home_score,
              predicted_away_score: pred.predicted_away_score,
              parsed_home: predictedHomeScore,
              parsed_away: predictedAwayScore,
              rounded_home: Math.round(predictedHomeScore),
              rounded_away: Math.round(predictedAwayScore)
            });

            // Combine AI prediction with manual odds (matching Streamlit logic EXACTLY)
            let homeWinProb = aiHomeWinProb;
            let predictionType = 'AI Only (No Odds)';

            if (odds && odds.home > 0 && odds.away > 0) {
              try {
                const homeDecimal = parseFloat(odds.home);
                const awayDecimal = parseFloat(odds.away);

                if (homeDecimal > 0 && awayDecimal > 0) {
                  const homeProbRaw = 1.0 / homeDecimal;
                  const awayProbRaw = 1.0 / awayDecimal;
                  const totalProb = homeProbRaw + awayProbRaw;
                  const oddsHomeWinProb = homeProbRaw / totalProb;

                  const aiWeight = 0.4;
                  const oddsWeight = 0.6;
                  homeWinProb = aiWeight * aiHomeWinProb + oddsWeight * oddsHomeWinProb;

                  predictionType = 'Hybrid AI + Manual Odds';
                }
              } catch (e) {
                predictionType = 'AI Only (Invalid Manual Odds)';
              }
            }

            let winner;
            let finalConfidence;
            if (homeWinProb > 0.5) {
              winner = match.home_team;
              finalConfidence = homeWinProb;
            } else if (homeWinProb < 0.5) {
              winner = match.away_team;
              finalConfidence = 1 - homeWinProb;
            } else {
              winner = 'Draw';
              finalConfidence = 0.5;
            }

            const scoreDiff = Math.abs(predictedHomeScore - predictedAwayScore);
            let intensity = 'Competitive Game';
            if (scoreDiff <= 2) {
              intensity = 'Close Thrilling Match';
            } else if (scoreDiff <= 5) {
              intensity = 'Competitive Game';
            } else if (scoreDiff <= 10) {
              intensity = 'Moderate Advantage';
            } else {
              intensity = 'Decisive Victory';
            }

            let confidenceLevel = 'Close Match Expected';
            if (finalConfidence >= 0.8) {
              confidenceLevel = 'High Confidence';
            } else if (finalConfidence >= 0.65) {
              confidenceLevel = 'Moderate Confidence';
            }

            const finalPrediction = {
              home_team: match.home_team,
              away_team: match.away_team,
              date: matchDate,
              winner: winner,
              confidence: `${(finalConfidence * 100).toFixed(1)}%`,
              home_score: Math.round(predictedHomeScore).toString(),
              away_score: Math.round(predictedAwayScore).toString(),
              home_win_prob: homeWinProb,
              league_id: selectedLeague,
              intensity: intensity,
              confidence_level: confidenceLevel,
              score_diff: Math.round(predictedHomeScore - predictedAwayScore),
              prediction_type: predictionType,
              ai_probability: aiHomeWinProb,
              hybrid_probability: homeWinProb,
              confidence_boost: finalConfidence - Math.max(aiHomeWinProb, 1 - aiHomeWinProb),
              home_team_id: match.home_team_id,
              away_team_id: match.away_team_id,
              live_odds_available: !!(odds && odds.home > 0 && odds.away > 0),
              manual_odds: odds,
            };

            newPredictions.push(finalPrediction);
            console.log('✅ Added prediction to array:', finalPrediction);
          } else {
            console.warn('❌ Prediction failed or returned error');
            console.warn('Result:', result);
            if (result?.data?.error) {
              console.error('Error from API:', result.data.error);
              if (result.data.traceback) {
                console.error('Traceback:', result.data.traceback);
              }
            }
          }
        } catch (err) {
          console.error(`❌ Exception predicting match ${match.home_team} vs ${match.away_team}:`, err);
          console.error('Error name:', err.name);
          console.error('Error message:', err.message);
          console.error('Error stack:', err.stack);
          console.error('Full error object:', JSON.stringify(err, Object.getOwnPropertyNames(err)));
        }
      }
    };

    await Promise.all(Array.from({ length: concurrency }, () => runTask()));

    console.log(`\n=== Prediction generation complete ===`);
    console.log(`Generated ${newPredictions.length} predictions out of ${upcomingMatches.length} matches`);
    console.log('Predictions:', newPredictions);
    setPredictions(newPredictions);
    setGenerating(false);
    console.log('✅ State updated, generating set to false');
  };

  const handleManualOddsChange = (matchKey, odds) => {
    setManualOdds(prev => ({
      ...prev,
      [matchKey]: odds,
    }));
  };

  if (loading) {
    return (
      <ThemeProvider theme={darkTheme}>
        <CssBaseline />
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="100vh">
          <Typography>Loading...</Typography>
        </Box>
      </ThemeProvider>
    );
  }

  const leagueName = selectedLeague ? LEAGUE_CONFIGS[selectedLeague]?.name || 'Unknown' : '';

  const handleDrawerToggle = () => {
    setMobileOpen(!mobileOpen);
  };

  const drawerContent = (
    <Box sx={{ p: 3, height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h6" sx={{ color: '#fafafa', fontWeight: 700 }}>
          🎯 Control Panel
        </Typography>
        {isMobile && (
          <IconButton
            onClick={handleDrawerToggle}
            sx={{ 
              color: '#fafafa',
              transition: 'all 0.2s ease',
              '&:hover': {
                transform: 'rotate(90deg)',
                backgroundColor: 'rgba(255, 255, 255, 0.1)',
              },
              '&:active': {
                transform: 'rotate(90deg) scale(0.9)',
              },
            }}
            aria-label="close drawer"
          >
            <CloseIcon />
          </IconButton>
        )}
      </Box>
      <LeagueSelector
        leagues={leagues}
        selectedLeague={selectedLeague}
        onLeagueChange={(league) => {
          setSelectedLeague(league);
          if (isMobile) {
            setMobileOpen(false);
          }
        }}
      />
    </Box>
  );

  return (
    <ThemeProvider theme={darkTheme}>
      <CssBaseline />
      <Box sx={{ display: 'flex', minHeight: '100vh', backgroundColor: '#0e1117' }}>
        {/* Mobile Hamburger Button */}
        {isMobile && !mobileOpen && (
          <IconButton
            color="inherit"
            aria-label="open drawer"
            edge="start"
            onClick={handleDrawerToggle}
            sx={{
              position: 'fixed',
              top: 16,
              left: 16,
              zIndex: 1300,
              backgroundColor: 'rgba(38, 39, 48, 0.95)',
              color: '#fafafa',
              padding: '14px',
              borderRadius: '14px',
              boxShadow: '0 4px 20px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.1)',
              backdropFilter: 'blur(10px)',
              transition: 'all 0.3s ease',
              opacity: mobileOpen ? 0 : 1,
              transform: mobileOpen ? 'scale(0.8)' : 'scale(1)',
              pointerEvents: mobileOpen ? 'none' : 'auto',
              '&:hover': {
                backgroundColor: 'rgba(38, 39, 48, 1)',
                transform: 'scale(1.05)',
              },
              '&:active': {
                transform: 'scale(0.95)',
              },
            }}
          >
            <MenuIcon sx={{ fontSize: '28px' }} />
          </IconButton>
        )}

        {/* Sidebar Drawer */}
        <Drawer
          variant={isMobile ? 'temporary' : 'permanent'}
          open={isMobile ? mobileOpen : true}
          onClose={handleDrawerToggle}
          ModalProps={{
            keepMounted: true, // Better open performance on mobile.
            closeAfterTransition: true,
          }}
          transitionDuration={{ enter: 300, exit: 250 }}
          sx={{
            width: isMobile ? 280 : 280,
            flexShrink: 0,
            '& .MuiDrawer-paper': {
              width: 280,
              boxSizing: 'border-box',
              backgroundColor: '#262730',
              borderRight: '1px solid #4b5563',
              boxShadow: isMobile ? '4px 0 20px rgba(0,0,0,0.5)' : 'none',
              transition: 'transform 300ms cubic-bezier(0.4, 0, 0.2, 1) 0ms',
            },
            '& .MuiBackdrop-root': {
              transition: 'opacity 250ms cubic-bezier(0.4, 0, 0.2, 1) 0ms',
            },
          }}
        >
          {drawerContent}
        </Drawer>

        {/* Main Content */}
        <Box
          component="main"
          sx={{
            flexGrow: 1,
            p: { xs: '1rem', sm: 2, md: 3 },
            backgroundColor: '#0e1117',
            color: '#fafafa',
            width: { xs: '100%', sm: 'auto' },
            overflowX: 'hidden',
            boxSizing: 'border-box',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            paddingLeft: { xs: '1rem', sm: 2, md: 3 },
            paddingRight: { xs: '1rem', sm: 2, md: 3 },
          }}
        >
          <Box className="main-content-wrapper" sx={{ width: '100%', maxWidth: '100%' }}>
            {/* Header */}
            <Box className="main-header" sx={{ mt: { xs: 6, sm: 0 }, width: '100%' }}>
              <Box className="rugby-ball-emoji" sx={{ display: { xs: 'block', sm: 'none' }, textAlign: 'center', fontSize: '3rem', mb: 1 }}>
                🏉
              </Box>
              <Typography variant="h1" className="main-header-title">
                <Box component="span" sx={{ display: { xs: 'none', sm: 'inline' } }}>🏉 </Box>
                Rugby AI Predictions
              </Typography>
              <Typography variant="body1" className="main-header-subtitle">
                Advanced AI-powered match predictions
              </Typography>
            </Box>

            {selectedLeague && (
              <Box sx={{ width: '100%', maxWidth: '100%', boxSizing: 'border-box' }}>
              {/* League Metrics */}
              <LeagueMetrics leagueId={selectedLeague} leagueName={leagueName} />

              <Typography variant="caption" sx={{ display: 'block', mb: 2, color: '#a0aec0', textAlign: 'center', width: '100%' }}>
                AI-Powered Match Predictions
              </Typography>

              {/* Live Matches */}
              <LiveMatches leagueId={selectedLeague} />

              {/* Manual Odds Input */}
              {loadingMatches ? (
                <Box sx={{ mb: 4, p: 4, backgroundColor: '#1f2937', borderRadius: 2, textAlign: 'center' }}>
                  <Typography variant="h6" sx={{ mb: 2, color: '#fafafa' }}>
                    📅 Loading Upcoming Matches...
                  </Typography>
                  <Box sx={{ display: 'flex', justifyContent: 'center' }}>
                    <CircularProgress size={40} sx={{ color: '#10b981' }} />
                  </Box>
                </Box>
              ) : upcomingMatches.length > 0 ? (
                <ManualOddsInput
                  matches={upcomingMatches}
                  manualOdds={manualOdds}
                  onOddsChange={handleManualOddsChange}
                />
              ) : (
                <Box sx={{ mb: 4, p: 2, backgroundColor: '#1f2937', borderRadius: 2 }}>
                  <Typography variant="h6" sx={{ mb: 1, color: '#fafafa' }}>
                    📅 Upcoming Matches
                  </Typography>
                  <Typography color="text.secondary">
                    {selectedLeague ? 'No upcoming matches found for this league' : 'Select a league to see upcoming matches'}
                  </Typography>
                </Box>
              )}

                {/* Generate Predictions Button */}
                <Box sx={{ my: 4, display: 'flex', justifyContent: 'center', flexDirection: 'column', alignItems: 'center', gap: 2, width: '100%' }}>
                  {generating && (
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                      <CircularProgress size={20} sx={{ color: '#10b981' }} />
                      <Typography sx={{ color: '#fafafa', fontSize: '1rem' }}>Analyzing matches...</Typography>
                    </Box>
                  )}
                  <button
                    className="generate-button"
                    onClick={handleGeneratePredictions}
                    disabled={generating || upcomingMatches.length === 0}
                  >
                    🎯 Generate Expert Predictions
                  </button>
                </Box>

                {/* Predictions Display */}
                {predictions.length > 0 && (
                  <PredictionsDisplay
                    predictions={predictions}
                    leagueName={leagueName}
                  />
                )}
              </Box>
            )}

            {!selectedLeague && (
              <Box sx={{ textAlign: 'center', mt: 8 }}>
                <Typography variant="h2" sx={{ color: '#2c3e50', mb: 2 }}>
                  🏉 Select a League to Begin
                </Typography>
                <Typography variant="body1" sx={{ color: '#7f8c8d' }}>
                  Choose from our AI-powered rugby prediction leagues
                </Typography>
              </Box>
            )}
          </Box>
        </Box>
      </Box>
    </ThemeProvider>
  );
}

export default App;
