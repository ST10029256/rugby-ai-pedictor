import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Box, Drawer, Typography, CssBaseline, ThemeProvider, createTheme, CircularProgress, IconButton, useMediaQuery, Button } from '@mui/material';
import MenuIcon from '@mui/icons-material/Menu';
import CloseIcon from '@mui/icons-material/Close';
import LogoutIcon from '@mui/icons-material/Logout';
import LeagueSelector from './components/LeagueSelector';
import LeagueMetrics from './components/LeagueMetrics';
import LiveMatches from './components/LiveMatches';
import ManualOddsInput from './components/ManualOddsInput';
import PredictionsDisplay from './components/PredictionsDisplay';
import LoginWidget from './components/LoginWidget';
import SubscriptionPage from './components/SubscriptionPage';
import NewsFeed from './components/NewsFeed';
import LeagueStandings from './components/LeagueStandings';
import RugbyBallLoader from './components/RugbyBallLoader';
import HistoricalPredictions from './components/HistoricalPredictions';
import { getLeagues, getUpcomingMatches, verifyLicenseKey } from './firebase';
import { MEDIA_URLS } from './utils/storageUrls';
import './App.css';
import { getLocalYYYYMMDD } from './utils/date';

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
  4714: { name: "Six Nations Championship", neutral_mode: true },
  5479: { name: "Rugby Union International Friendlies", neutral_mode: true },
};

function App() {
  const [authenticated, setAuthenticated] = useState(false);
  const [authData, setAuthData] = useState(null);
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [showSubscription, setShowSubscription] = useState(false);
  const [leagues, setLeagues] = useState([]);
  const [selectedLeague, setSelectedLeague] = useState(null);
  const [upcomingMatches, setUpcomingMatches] = useState([]);
  const [predictions, setPredictions] = useState([]);
  const [manualOdds, setManualOdds] = useState({});
  const [loading, setLoading] = useState(true);
  const [loadingMatches, setLoadingMatches] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [activeView, setActiveView] = useState('predictions'); // 'predictions', 'news', 'standings', or 'history'
  const [userPreferences] = useState({
    followed_teams: [],
    followed_leagues: [],
  });
  const videoRef = useRef(null);
  const headerVideoRef = useRef(null);
  
  const isMobile = useMediaQuery('(max-width:768px)');

  // Check authentication on mount - auto-login if valid key is stored
  useEffect(() => {
    const checkAuthentication = async () => {
      try {
        const storedAuth = localStorage.getItem('rugby_ai_auth');
        if (storedAuth) {
          const auth = JSON.parse(storedAuth);
          
            // Validate stored auth structure
          if (!auth.licenseKey) {
            localStorage.removeItem('rugby_ai_auth');
            setCheckingAuth(false);
            return;
          }
          
          // Check if expired (with 1 hour buffer to account for timezone differences)
          if (auth.expiresAt && auth.expiresAt * 1000 < Date.now() - 3600000) {
            localStorage.removeItem('rugby_ai_auth');
            setAuthenticated(false);
            setCheckingAuth(false);
            return;
          }
          
          // Verify with server to ensure key is still valid
          try {
          const result = await verifyLicenseKey({ license_key: auth.licenseKey });
            if (result.data && result.data.valid) {
              // Update auth data with latest info from server
              const updatedAuth = {
                licenseKey: auth.licenseKey,
                expiresAt: result.data.expires_at || auth.expiresAt,
                subscriptionType: result.data.subscription_type || auth.subscriptionType,
                email: result.data.email || auth.email,
                authenticatedAt: Date.now(),
              };
              
              // Save updated auth data
              localStorage.setItem('rugby_ai_auth', JSON.stringify(updatedAuth));
              setAuthData(updatedAuth);
            setAuthenticated(true);
          } else {
              // Key is no longer valid
            localStorage.removeItem('rugby_ai_auth');
            setAuthenticated(false);
          }
          } catch (verifyError) {
            // If verification fails (network error, etc.), still allow login with stored data
            setAuthData(auth);
            setAuthenticated(true);
          }
        } else {
          // No stored auth
          setAuthenticated(false);
        }
      } catch (error) {
        console.error('Auth check error:', error);
        localStorage.removeItem('rugby_ai_auth');
        setAuthenticated(false);
      } finally {
        setCheckingAuth(false);
      }
    };
    
    checkAuthentication();
  }, []);

  const handleLoginSuccess = (auth) => {
    setAuthData(auth);
    setAuthenticated(true);
    
    // Restore selected league from localStorage after login
    const savedLeague = localStorage.getItem('rugby_ai_selected_league');
    if (savedLeague) {
      const leagueId = parseInt(savedLeague);
      if (!isNaN(leagueId)) {
        setSelectedLeague(leagueId);
      }
    }
  };

  const handleLogout = () => {
    // Save license key before removing auth so it can be pre-filled on next login
    if (authData && authData.licenseKey) {
      localStorage.setItem('rugby_ai_license_key', authData.licenseKey);
    }
    
    localStorage.removeItem('rugby_ai_auth');
    // Keep selected league in localStorage so it's restored on next login
    setAuthenticated(false);
    setAuthData(null);
    setLeagues([]);
    setSelectedLeague(null);
    setUpcomingMatches([]);
    setPredictions([]);
  };

  // Restore selected league from localStorage after authentication check
  useEffect(() => {
    if (authenticated && !selectedLeague) {
      const savedLeague = localStorage.getItem('rugby_ai_selected_league');
      if (savedLeague) {
        const leagueId = parseInt(savedLeague);
        if (!isNaN(leagueId)) {
          setSelectedLeague(leagueId);
        }
      }
    }
  }, [authenticated, selectedLeague]);

  // Save selected league to localStorage whenever it changes
  useEffect(() => {
    if (selectedLeague) {
      localStorage.setItem('rugby_ai_selected_league', selectedLeague.toString());
    }
  }, [selectedLeague]);


  // Prevent scrolling when mobile drawer is open
  useEffect(() => {
    if (!isMobile || !mobileOpen) return;

    const body = document.body;
    const mainContent = document.querySelector('main') || document.querySelector('.main-content-wrapper');
    
    // Store original scroll position
    const scrollY = window.scrollY;
    const mainScrollTop = mainContent ? mainContent.scrollTop : 0;
    
    // Disable scrolling
    body.classList.add('drawer-open');
    body.style.overflow = 'hidden';
    body.style.position = 'fixed';
    body.style.top = `-${scrollY}px`;
    body.style.width = '100%';
    
    if (mainContent) {
      mainContent.style.overflow = 'hidden';
    }

    return () => {
      // Restore scrolling when drawer closes
      body.classList.remove('drawer-open');
      body.style.overflow = '';
      body.style.position = '';
      body.style.top = '';
      body.style.width = '';
      
      // Restore scroll position
      window.scrollTo(0, scrollY);
      
      if (mainContent) {
        mainContent.style.overflow = '';
        mainContent.scrollTop = mainScrollTop;
      }
    };
  }, [mobileOpen, isMobile]);

  useEffect(() => {
    // Only load leagues when authenticated
    if (!authenticated) {
      setLeagues([]);
      return;
    }

    // Load leagues - try API first, fallback to LEAGUE_CONFIGS
    getLeagues()
      .then((result) => {
        let availableLeagues = [];
        
        if (result && result.data) {
          if (result.data.leagues && Array.isArray(result.data.leagues)) {
            availableLeagues = result.data.leagues;
          } else if (result.data.error) {
            // Fallback to LEAGUE_CONFIGS
            availableLeagues = Object.entries(LEAGUE_CONFIGS).map(([id, config]) => ({
              id: parseInt(id),
              name: config.name,
              upcoming_matches: 0,
              recent_matches: 0,
              has_news: false,
              total_news: 0,
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
          availableLeagues = Object.entries(LEAGUE_CONFIGS).map(([id, config]) => ({
            id: parseInt(id),
            name: config.name,
          }));
        } else {
          // Merge API leagues with LEAGUE_CONFIGS to ensure all configured leagues are available
          // This ensures Six Nations and other leagues are always available even if API doesn't return them
          const configLeagues = Object.entries(LEAGUE_CONFIGS).map(([id, config]) => ({
            id: parseInt(id),
            name: config.name,
            upcoming_matches: 0,
            recent_matches: 0,
            has_news: false,
            total_news: 0,
          }));
          
          // Create a map of existing leagues by ID
          const leagueMap = new Map(availableLeagues.map(l => [l.id, l]));
          
          // Add any leagues from LEAGUE_CONFIGS that aren't in the API response
          configLeagues.forEach(configLeague => {
            if (!leagueMap.has(configLeague.id)) {
              availableLeagues.push(configLeague);
            }
          });
          
          // Sort by ID to keep consistent order
          availableLeagues.sort((a, b) => a.id - b.id);
        }
        
        setLeagues(availableLeagues);
        if (availableLeagues.length > 0) {
          // Only auto-select if no league is currently selected and no saved league exists
          const savedLeague = localStorage.getItem('rugby_ai_selected_league');
          if (!selectedLeague && !savedLeague) {
          setSelectedLeague(availableLeagues[0].id);
          } else if (savedLeague) {
            const leagueId = parseInt(savedLeague);
            // Verify the saved league is still in available leagues
            if (!isNaN(leagueId) && availableLeagues.some(l => l.id === leagueId)) {
              setSelectedLeague(leagueId);
            } else if (!selectedLeague) {
              // Saved league not available, use first available
              setSelectedLeague(availableLeagues[0].id);
            }
          }
        }
        setLoading(false);
      })
      .catch((error) => {
        console.error('Error loading leagues from API, using fallback:', error);
        // Fallback to LEAGUE_CONFIGS
        const fallbackLeagues = Object.entries(LEAGUE_CONFIGS).map(([id, config]) => ({
          id: parseInt(id),
          name: config.name,
          upcoming_matches: 0,
          recent_matches: 0,
          has_news: false,
          total_news: 0,
        }));
        setLeagues(fallbackLeagues);
        if (fallbackLeagues.length > 0) {
          const savedLeague = localStorage.getItem('rugby_ai_selected_league');
          if (savedLeague) {
            const leagueId = parseInt(savedLeague);
            if (!isNaN(leagueId) && fallbackLeagues.some(l => l.id === leagueId)) {
              setSelectedLeague(leagueId);
            } else {
          setSelectedLeague(fallbackLeagues[0].id);
            }
          } else {
            setSelectedLeague(fallbackLeagues[0].id);
          }
        }
        setLoading(false);
      });
  }, [authenticated]);

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
      try {
        const result = await getUpcomingMatches({ league_id: selectedLeague, limit: 50 });
        
        if (result && result.data) {
          const matches = result.data.matches || [];
          setUpcomingMatches(matches);
          
          if (result.data.error) {
            console.error('API error:', result.data.error);
          }
        } else {
          setUpcomingMatches([]);
        }
      } catch (err) {
        console.error('Exception loading upcoming matches:', err);
        setUpcomingMatches([]);
      } finally {
        setLoadingMatches(false);
      }
    };

    fetchUpcoming();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedLeague]);

  const handleGeneratePredictions = async () => {
    if (!selectedLeague || upcomingMatches.length === 0) {
      return;
    }

    setGenerating(true);
    const newPredictions = [];
    const seenMatchups = new Set(); // Track unique matchups (matching Streamlit)

    // Import predictMatch dynamically
    const { predictMatch } = await import('./firebase');

    // Precompute unique match tasks (so we don't waste time on duplicates)
    const tasks = [];
    for (const match of upcomingMatches) {
      const matchDate = match.date_event ? match.date_event.split('T')[0] : getLocalYYYYMMDD();
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

        try {
          const result = await retryWithBackoff(async () => {
            return await predictMatch({
              home_team: match.home_team,
              away_team: match.away_team,
              league_id: selectedLeague,
              match_date: matchDate,
              enhanced: false,
            });
          });

          if (result && result.data && !result.data.error) {
            const pred = result.data;

            // Extract AI prediction values (matching Streamlit make_expert_prediction)
            const aiHomeWinProb = pred.home_win_prob || 0.5;
            const predictedHomeScore = parseFloat(pred.predicted_home_score || 0);
            const predictedAwayScore = parseFloat(pred.predicted_away_score || 0);

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
          } else {
            if (result?.data?.error) {
              console.error('Prediction error:', result.data.error);
            }
          }
        } catch (err) {
          console.error('Exception predicting match:', err);
        }
      }
    };

    await Promise.all(Array.from({ length: concurrency }, () => runTask()));

    setPredictions(newPredictions);
    setGenerating(false);
  };

  const handleManualOddsChange = useCallback((matchKey, odds) => {
    setManualOdds(prev => ({
      ...prev,
      [matchKey]: odds,
    }));
  }, []);

  const leagueName = useMemo(() => {
    return selectedLeague ? LEAGUE_CONFIGS[selectedLeague]?.name || 'Unknown' : '';
  }, [selectedLeague]);

  // Setup video background loop
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const handleLoadedMetadata = () => {
      video.play().catch(() => {
        // Autoplay might be blocked, that's fine
      });
    };

    const handleCanPlay = () => {
      // Video ready to play
    };

    const handleError = (e) => {
      console.error('Background video failed to load:', e);
    };

    video.addEventListener('loadedmetadata', handleLoadedMetadata);
    video.addEventListener('canplay', handleCanPlay);
    video.addEventListener('error', handleError);
    video.loop = true;
    video.muted = true;
    video.playsInline = true;

    return () => {
      video.removeEventListener('loadedmetadata', handleLoadedMetadata);
      video.removeEventListener('canplay', handleCanPlay);
      video.removeEventListener('error', handleError);
    };
  }, []);

  const handleDrawerToggle = useCallback(() => {
    setMobileOpen(prev => !prev);
  }, []);

  const handleLeagueChange = useCallback((league) => {
    setSelectedLeague(league);
    if (isMobile) {
      setMobileOpen(false);
    }
  }, [isMobile]);

  // Show login widget if not authenticated
  if (checkingAuth) {
    return (
      <ThemeProvider theme={darkTheme}>
        <CssBaseline />
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="100vh">
          <RugbyBallLoader size={120} color="#10b981" />
        </Box>
      </ThemeProvider>
    );
  }

  if (!authenticated) {
    if (showSubscription) {
    return (
      <ThemeProvider theme={darkTheme}>
        <CssBaseline />
          <SubscriptionPage onBack={() => setShowSubscription(false)} />
        </ThemeProvider>
      );
    }
    return (
      <ThemeProvider theme={darkTheme}>
        <CssBaseline />
        <LoginWidget onLoginSuccess={handleLoginSuccess} onShowSubscription={() => setShowSubscription(true)} />
      </ThemeProvider>
    );
  }

  if (loading) {
    return (
      <ThemeProvider theme={darkTheme}>
        <CssBaseline />
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="100vh">
          <RugbyBallLoader size={120} color="#10b981" />
        </Box>
      </ThemeProvider>
    );
  }

  const drawerContent = (
    <Box sx={{ 
      p: 3, 
      height: '100%',
      width: '100%',
      display: 'flex', 
      flexDirection: 'column',
      boxSizing: 'border-box',
      background: 'linear-gradient(180deg, rgba(38, 39, 48, 0.95) 0%, rgba(31, 41, 55, 0.98) 100%)',
      position: 'relative',
      overflowY: 'auto',
      overflowX: 'hidden',
      minHeight: isMobile ? '100vh' : 'auto',
      // Prevent content from affecting layout when dropdown opens
      ...(!isMobile ? {
        contain: 'layout style',
      } : {}),
      // Premium styling
      '&::before': {
        content: '""',
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        height: '2px',
        background: 'linear-gradient(90deg, transparent 0%, #10b981 50%, transparent 100%)',
        opacity: 0.6,
      },
    }}>
      {/* Premium Header */}
      <Box sx={{ 
        display: 'flex', 
        justifyContent: isMobile ? 'space-between' : 'center', 
        alignItems: 'center', 
        mb: 4,
        flexShrink: 0,
        width: '100%',
        position: 'relative',
        pb: 2,
        '&::after': {
          content: '""',
          position: 'absolute',
          bottom: 0,
          left: '50%',
          transform: 'translateX(-50%)',
          width: '60px',
          height: '2px',
          background: 'linear-gradient(90deg, transparent 0%, #10b981 50%, transparent 100%)',
          borderRadius: '2px',
        },
      }}>
        <Typography variant="h5" sx={{ 
          color: '#fafafa', 
          fontWeight: 800,
          fontSize: isMobile ? '1.25rem' : '1.5rem',
          textAlign: isMobile ? 'left' : 'center',
          letterSpacing: '-0.02em',
          display: 'flex',
          alignItems: 'center',
          justifyContent: isMobile ? 'flex-start' : 'center',
          gap: 1,
          '& .emoji': {
            fontSize: isMobile ? '1.5rem' : '1.75rem',
            filter: 'drop-shadow(0 2px 4px rgba(0, 0, 0, 0.3))',
          },
          '& .text': {
            background: 'linear-gradient(135deg, #fafafa 0%, #10b981 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
            textShadow: '0 2px 8px rgba(16, 185, 129, 0.3)',
          },
        }}>
          <img src="/rugby_emoji.png" alt="Rugby Ball" style={{ width: '24px', height: '24px', marginRight: '8px', verticalAlign: 'middle' }} />
          <span className="text">Control Panel</span>
        </Typography>
        {isMobile && (
          <IconButton
            onClick={handleDrawerToggle}
            sx={{ 
              color: '#fafafa',
              backgroundColor: 'rgba(255, 255, 255, 0.05)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
              '&:hover': {
                transform: 'rotate(90deg) scale(1.1)',
                backgroundColor: 'rgba(16, 185, 129, 0.2)',
                borderColor: 'rgba(16, 185, 129, 0.4)',
                boxShadow: '0 4px 12px rgba(16, 185, 129, 0.3)',
              },
              '&:active': {
                transform: 'rotate(90deg) scale(0.95)',
              },
            }}
            aria-label="close drawer"
          >
            <CloseIcon />
          </IconButton>
        )}
      </Box>
      
      {/* Premium Logout Button */}
      <Box sx={{ 
        mb: 3, 
        display: 'flex', 
        justifyContent: 'center',
        flexShrink: 0,
        width: '100%',
      }}>
        <Button
          onClick={handleLogout}
          startIcon={<LogoutIcon />}
          sx={{
            color: '#d1d5db',
            fontSize: '0.875rem',
            textTransform: 'none',
            fontWeight: 500,
            px: 2.5,
            py: 1,
            borderRadius: '10px',
            backgroundColor: 'rgba(255, 255, 255, 0.03)',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            transition: 'all 0.3s ease',
            '&:hover': {
              color: '#fafafa',
              backgroundColor: 'rgba(239, 68, 68, 0.15)',
              borderColor: 'rgba(239, 68, 68, 0.3)',
              transform: 'translateY(-2px)',
              boxShadow: '0 4px 12px rgba(239, 68, 68, 0.2)',
            },
          }}
        >
          Logout
        </Button>
      </Box>
      <Box sx={{ 
        flex: '1 1 auto',
        display: 'flex',
        flexDirection: 'column',
        width: '100%',
        minHeight: 0,
        mt: 2,
      }}>
        <LeagueSelector
          leagues={leagues}
          selectedLeague={selectedLeague}
          onLeagueChange={handleLeagueChange}
        />
      </Box>
    </Box>
  );

  return (
    <ThemeProvider theme={darkTheme}>
      <CssBaseline />
      <Box sx={{ 
        display: 'flex', 
        minHeight: '100vh', 
        backgroundColor: '#0e1117',
        position: 'relative',
        overflow: 'hidden',
        // Desktop only: Ensure container allows sticky positioning
        ...(isMobile ? {} : {
          height: '100vh',
          overflow: 'hidden',
        }),
      }}>
        {/* Video Background */}
        <Box
          component="video"
          ref={videoRef}
          autoPlay
          muted
          loop
          playsInline
          preload="auto"
          sx={{
            position: 'fixed',
            top: 0,
            left: 0,
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            zIndex: 0,
            pointerEvents: 'none',
          }}
        >
          <source src={MEDIA_URLS.videoRugby} type="video/mp4" />
        </Box>

        {/* Dark overlay for better readability */}
        <Box
          sx={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(14, 17, 23, 0.75)',
            zIndex: 1,
            pointerEvents: 'none',
            // Ensure overlay doesn't cover drawer on mobile
            ...(isMobile && mobileOpen ? {
              zIndex: 1100, // Below drawer
            } : {}),
          }}
        />
        {/* Mobile Hamburger Button */}
        {isMobile && !mobileOpen && (
          <IconButton
            color="inherit"
            aria-label="open drawer"
            edge="start"
            onClick={handleDrawerToggle}
            sx={{
              position: 'fixed',
              top: { xs: 12, sm: 16 },
              left: { xs: 20, sm: 20 },
              zIndex: 1300,
              backgroundColor: 'rgba(38, 39, 48, 0.95)',
              backdropFilter: 'blur(10px)',
              color: '#fafafa',
              padding: { xs: '8px', sm: '14px' },
              borderRadius: '12px',
              boxShadow: '0 4px 20px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.1)',
              transition: 'all 0.3s ease',
              opacity: mobileOpen ? 0 : 1,
              transform: mobileOpen ? 'scale(0.8)' : 'scale(1)',
              pointerEvents: mobileOpen ? 'none' : 'auto',
              willChange: 'transform',
              '&:hover': {
                backgroundColor: 'rgba(38, 39, 48, 1)',
                transform: 'scale(1.05)',
              },
              '&:active': {
                transform: 'scale(0.95)',
              },
            }}
          >
            <MenuIcon sx={{ fontSize: { xs: '22px', sm: '28px' } }} />
          </IconButton>
        )}

        {/* Desktop Sidebar Drawer */}
        {!isMobile && (
          <Drawer
            variant="permanent"
            open={true}
            sx={{
              width: 280,
              flexShrink: 0,
              position: 'relative',
              zIndex: 2,
              '& .MuiDrawer-paper': {
                width: 280,
                boxSizing: 'border-box',
                background: 'linear-gradient(180deg, rgba(38, 39, 48, 0.98) 0%, rgba(31, 41, 55, 0.95) 100%)',
                backdropFilter: 'blur(20px) saturate(180%)',
                borderRight: '1px solid rgba(16, 185, 129, 0.2)',
                boxShadow: '4px 0 24px rgba(0, 0, 0, 0.4), inset -1px 0 0 rgba(16, 185, 129, 0.1)',
                overflow: 'visible',
                position: 'sticky',
                top: 0,
                height: '100vh',
                maxHeight: '100vh',
                // Prevent drawer from affecting main content layout
                contain: 'layout style paint',
              },
            }}
          >
            {drawerContent}
          </Drawer>
        )}

        {/* Mobile Control Panel - Fixed Position Overlay */}
        {isMobile && (
          <>
            {/* Backdrop */}
            {mobileOpen && (
              <Box
                onClick={handleDrawerToggle}
                sx={{
                  position: 'fixed',
                  top: 0,
                  left: 0,
                  right: 0,
                  bottom: 0,
                  backgroundColor: 'rgba(0, 0, 0, 0.7)',
                  zIndex: 1299,
                  animation: 'fadeIn 0.3s ease-in-out',
                  willChange: 'opacity',
                  '@keyframes fadeIn': {
                    from: { opacity: 0 },
                    to: { opacity: 1 },
                  },
                }}
              />
            )}
            
            {/* Mobile Control Panel */}
            <Box
              sx={{
                position: 'fixed',
                top: 0,
                left: 0,
                width: '280px',
                height: '100vh',
                background: 'linear-gradient(180deg, rgba(38, 39, 48, 0.98) 0%, rgba(31, 41, 55, 0.95) 100%)',
                backdropFilter: 'blur(20px) saturate(180%)',
                borderRight: '1px solid rgba(16, 185, 129, 0.2)',
                boxShadow: '4px 0 24px rgba(0, 0, 0, 0.5), inset -1px 0 0 rgba(16, 185, 129, 0.1)',
                zIndex: 1300,
                transform: mobileOpen ? 'translateX(0)' : 'translateX(-100%)',
                transition: 'transform 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                overflowY: 'auto',
                overflowX: 'hidden',
                display: 'flex',
                flexDirection: 'column',
                willChange: 'transform', // GPU acceleration
                backfaceVisibility: 'hidden', // Smooth rendering
              }}
            >
              {drawerContent}
            </Box>
          </>
        )}

        {/* Navigation Tabs - Fixed header on all screen sizes */}
        <Box sx={{ 
            position: 'fixed',
            top: 0,
            left: { xs: 0, sm: '280px' },
            right: 0,
            width: { xs: '100vw', sm: 'auto' },
            maxWidth: 'none',
            display: 'flex',
            gap: { xs: 0.25, sm: 2 },
            justifyContent: { xs: 'flex-start', sm: 'center' },
            alignItems: 'center',
            paddingLeft: { xs: '60px', sm: '24px', md: '32px' },
            paddingRight: { xs: '20px', sm: '24px', md: '32px' },
            paddingTop: { xs: '12px', sm: '12px' },
            paddingBottom: { xs: '12px', sm: '12px' },
            backgroundColor: 'rgba(14, 17, 23, 0.95)',
            backdropFilter: 'blur(10px)',
            borderBottom: '1px solid rgba(16, 185, 129, 0.2)',
            boxShadow: '0 2px 8px rgba(0, 0, 0, 0.3)',
            zIndex: 1200,
            minHeight: { xs: '56px', sm: '56px' },
            boxSizing: 'border-box',
            margin: 0,
            overflowX: { xs: 'auto', sm: 'visible' },
            WebkitOverflowScrolling: 'touch',
            scrollbarWidth: 'none',
            '&::-webkit-scrollbar': { display: 'none' },
          }}>
            <Button
              onClick={() => setActiveView('predictions')}
              sx={{
                color: activeView === 'predictions' ? '#10b981' : '#9ca3af',
                borderBottom: activeView === 'predictions' ? '2px solid #10b981' : '2px solid transparent',
                borderRadius: 0,
                textTransform: 'none',
                fontWeight: 600,
                px: { xs: 1, sm: 3 },
                py: { xs: 0.75, sm: 1 },
                fontSize: '14px',
                '& .MuiButton-label, & .MuiButton-root': {
                  fontSize: '14px',
                },
                whiteSpace: 'nowrap',
                minWidth: 'fit-content',
                height: { xs: '36px', sm: 'auto' }, // Fixed height on mobile
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flex: { xs: 1, sm: 'none' }, // Equal width on mobile
                '&:hover': {
                  backgroundColor: 'rgba(16, 185, 129, 0.1)',
                },
              }}
            >
              🎯 Predictions
            </Button>
            <Button
              onClick={() => setActiveView('news')}
              sx={{
                color: activeView === 'news' ? '#10b981' : '#9ca3af',
                borderBottom: activeView === 'news' ? '2px solid #10b981' : '2px solid transparent',
                borderRadius: 0,
                textTransform: 'none',
                fontWeight: 600,
                px: { xs: 1, sm: 3 },
                py: { xs: 0.75, sm: 1 },
                fontSize: '14px',
                '& .MuiButton-label, & .MuiButton-root': {
                  fontSize: '14px',
                },
                whiteSpace: 'nowrap',
                minWidth: 'fit-content',
                height: { xs: '36px', sm: 'auto' }, // Fixed height on mobile
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flex: { xs: 1, sm: 'none' }, // Equal width on mobile
                '&:hover': {
                  backgroundColor: 'rgba(16, 185, 129, 0.1)',
                },
              }}
            >
              📰 News
            </Button>
            <Button
              onClick={() => setActiveView('standings')}
              sx={{
                color: activeView === 'standings' ? '#10b981' : '#9ca3af',
                borderBottom: activeView === 'standings' ? '2px solid #10b981' : '2px solid transparent',
                borderRadius: 0,
                textTransform: 'none',
                fontWeight: 600,
                px: { xs: 1, sm: 3 },
                py: { xs: 0.75, sm: 1 },
                fontSize: '14px',
                '& .MuiButton-label, & .MuiButton-root': {
                  fontSize: '14px',
                },
                whiteSpace: 'nowrap',
                minWidth: 'fit-content',
                height: { xs: '36px', sm: 'auto' }, // Fixed height on mobile
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flex: { xs: 1, sm: 'none' }, // Equal width on mobile
                '&:hover': {
                  backgroundColor: 'rgba(16, 185, 129, 0.1)',
                },
              }}
            >
              🏆 Standings
            </Button>
            <Button
              onClick={() => setActiveView('history')}
              sx={{
                color: activeView === 'history' ? '#10b981' : '#9ca3af',
                borderBottom: activeView === 'history' ? '2px solid #10b981' : '2px solid transparent',
                borderRadius: 0,
                textTransform: 'none',
                fontWeight: 600,
                px: { xs: 1, sm: 3 },
                py: { xs: 0.75, sm: 1 },
                fontSize: '14px',
                '& .MuiButton-label, & .MuiButton-root': {
                  fontSize: '14px',
                },
                whiteSpace: 'nowrap',
                minWidth: 'fit-content',
                height: { xs: '36px', sm: 'auto' }, // Fixed height on mobile
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flex: { xs: 1, sm: 'none' }, // Equal width on mobile
                '&:hover': {
                  backgroundColor: 'rgba(16, 185, 129, 0.1)',
                },
              }}
            >
              📜 History
            </Button>
          </Box>

        {/* Main Content */}
        <Box
          component="main"
          sx={{
            flexGrow: 1,
            // On mobile, let the header video go edge-to-edge in Predictions view (no extra gap).
            // Other views keep comfortable padding.
            p: { xs: activeView === 'predictions' ? 0 : '1rem', sm: 2, md: 3 },
            backgroundColor: 'transparent',
            color: '#fafafa',
            width: { xs: '100%', sm: 'auto' },
            overflowX: 'hidden',
            boxSizing: 'border-box',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            paddingLeft: { xs: activeView === 'predictions' ? 0 : '1rem', sm: 2, md: 3 },
            paddingRight: { xs: activeView === 'predictions' ? 0 : '1rem', sm: 2, md: 3 },
            position: 'relative',
            zIndex: 2,
            // Desktop only: Allow main content to scroll independently
            ...(isMobile ? {} : {
              overflowY: 'auto',
              height: '100vh',
              maxHeight: '100vh',
              // Prevent layout shifts when dropdown opens
              contain: 'layout style',
            }),
          }}
        >
          <Box className="main-content-wrapper" sx={{ 
            width: '100%', 
            maxWidth: '100%',
            paddingTop: { xs: '80px', sm: '90px' }, // Space for fixed header at same level as burger (mobile) or just header (desktop)
            overflowX: activeView === 'predictions' ? 'visible' : 'hidden',
            boxSizing: 'border-box',
          }}>
            {activeView === 'news' ? (
              <NewsFeed 
                userPreferences={userPreferences} 
                leagueId={selectedLeague} 
                leagueName={leagueName}
              />
            ) : activeView === 'standings' ? (
              <Box sx={{ 
                width: '100%', 
                maxWidth: '1400px', 
                mx: 'auto', 
                p: { xs: 2, sm: 3, md: 4 },
                position: 'relative',
                minHeight: 'calc(100vh - 300px)',
                overflowX: 'visible',
                overflowY: 'visible',
                boxSizing: 'border-box',
              }}>
                <LeagueStandings leagueId={selectedLeague} leagueName={leagueName} />
              </Box>
            ) : activeView === 'history' ? (
              <HistoricalPredictions leagueId={selectedLeague} leagueName={leagueName} />
            ) : (
              <>
            {/* Header Video */}
            <Box 
              className="main-header" 
              sx={{ 
                // Remove the extra top gap on mobile; keep desktop spacing.
                mt: { xs: 0, sm: 0 }, 
                width: { xs: '100%', sm: 'calc(100% + 32px)', md: 'calc(100% + 48px)' },
                height: { xs: '300px', sm: '450px', md: '600px' },
                marginLeft: { xs: 0, sm: -2, md: -3 },
                marginRight: { xs: 0, sm: -2, md: -3 },
                // Edge-to-edge on mobile looks better and avoids visible gaps.
                borderRadius: { xs: 0, sm: '8px' },
                overflow: 'hidden',
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
                padding: 0,
              }}
            >
              <Box
                sx={{
                  width: '100%',
                  height: '100%',
                  '& video': {
                    width: '100%',
                    height: '100%',
                    objectFit: 'cover',
                    objectPosition: { xs: 'center center', sm: 'center 70%', md: 'center 80%' },
                  },
                }}
              >
                <video
                  ref={headerVideoRef}
                  autoPlay
                  muted
                  loop
                  playsInline
                  preload="auto"
                  style={{
                    willChange: 'transform',
                    transform: 'translateZ(0)', // GPU acceleration
                  }}
                  onError={(e) => {
                    console.error('Header video failed to load:', e);
                  }}
                >
                  <source src={MEDIA_URLS.videoRugbyBall} type="video/mp4" />
                </video>
              </Box>
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
                <Box sx={{ mb: 4, p: 4, backgroundColor: '#1f2937', borderRadius: 2, textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '200px' }}>
                  <Typography variant="h6" sx={{ mb: 2, color: '#fafafa' }}>
                    📅 Loading Upcoming Matches...
                  </Typography>
                  <RugbyBallLoader size={100} color="#10b981" />
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
                    <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 2, mb: 2, width: '100%' }}>
                      <RugbyBallLoader size={100} color="#10b981" />
                      <Typography sx={{ color: '#fafafa', fontSize: '1rem', textAlign: 'center' }}>Analyzing matches...</Typography>
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
                  <img src="/rugby_emoji.png" alt="Rugby Ball" style={{ width: '32px', height: '32px', verticalAlign: 'middle', marginRight: '8px' }} /> Select a League to Begin
                </Typography>
                <Typography variant="body1" sx={{ color: '#7f8c8d' }}>
                  Choose from our AI-powered rugby prediction leagues
                </Typography>
              </Box>
            )}
              </>
            )}
          </Box>
        </Box>
      </Box>
    </ThemeProvider>
  );
}

export default App;
