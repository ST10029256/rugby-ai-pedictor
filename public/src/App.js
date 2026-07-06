import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Box, Drawer, Typography, CssBaseline, ThemeProvider, createTheme, IconButton, useMediaQuery, Button } from '@mui/material';
import MenuIcon from '@mui/icons-material/Menu';
import CloseIcon from '@mui/icons-material/Close';
import LogoutIcon from '@mui/icons-material/Logout';
import LeagueSelector from './components/LeagueSelector';
import LeagueMetrics from './components/LeagueMetrics';
import LiveMatches from './components/LiveMatches';
import ManualOddsInput from './components/ManualOddsInput';
import PredictionsDisplay from './components/PredictionsDisplay';
import LoginWidget from './components/LoginWidget';
import { ProfileDrawerSummary, UserProfilePage } from './components/UserProfilePanel';
import SubscriptionPage from './components/SubscriptionPage';
import NewsFeed from './components/NewsFeed';
import LeagueStandings from './components/LeagueStandings';
import MatchLineups from './components/MatchLineups';
import LeagueTeams from './components/LeagueTeams';
import RugbyBallLoader from './components/RugbyBallLoader';
import HistoricalPredictions from './components/HistoricalPredictions';
import { VIEW_CONTENT_WRAPPER_SX } from './utils/viewLoader';
import { getLeagues, getUpcomingMatches, verifyLicenseKey } from './firebase';
import { MEDIA_URLS } from './utils/storageUrls';
import './App.css';
import { getLocalYYYYMMDD, getKickoffAtFromMatch } from './utils/date';
import { getBiometricRegistration, handleDeviceAuthFailure, saveDeviceSession } from './utils/biometricAuth';
import { getDeviceId } from './utils/deviceId';
import { ensureProfileFromAuth } from './utils/userProfile';
import { predictionsWidgetSx } from './utils/predictionsLayout';

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
  5480: { name: "Nations Championship", neutral_mode: true },
};
const DEBUG_UPCOMING_LEAGUES = new Set([4714]);
const APP_DISPLAY_NAME = 'Rugby AI Predictor';
const APP_NAV_VIEWS = [
  { id: 'predictions', label: 'Predictions', icon: '🎯' },
  { id: 'news', label: 'News', icon: '📰' },
  { id: 'standings', label: 'Standings', icon: '🏆' },
  { id: 'teams', label: 'Teams', icon: '🏉' },
  { id: 'lineups', label: 'Lineups', icon: '👥' },
  { id: 'history', label: 'History', icon: '📜' },
];
const CONTENT_TAB_VIEWS = new Set(['news', 'standings', 'teams', 'lineups', 'history']);

function extractMatchDateIso(match) {
  const raw = String(
    match?.date_event ||
    match?.dateEvent ||
    match?.kickoff_at ||
    match?.kickoffAt ||
    match?.timestamp ||
    ''
  ).trim();
  const m = raw.match(/^\d{4}-\d{2}-\d{2}/);
  return m ? m[0] : '';
}

function toUTCDateFromIso(isoDate) {
  const [y, m, d] = String(isoDate).split('-').map((v) => parseInt(v, 10));
  if (!y || !m || !d) return null;
  return new Date(Date.UTC(y, m - 1, d));
}

function getNextMatchWeek(matches) {
  const todayIso = getLocalYYYYMMDD();
  const dated = (matches || [])
    .map((match) => ({ match, dateIso: extractMatchDateIso(match) }))
    .filter((x) => x.dateIso && x.dateIso >= todayIso)
    .sort((a, b) => a.dateIso.localeCompare(b.dateIso));

  if (dated.length === 0) {
    return { matches: [], startDateIso: '', endDateIso: '' };
  }

  // Keep only the first contiguous fixture block (current round/weekend).
  // Example: dates [2026-03-06, 2026-03-07, 2026-03-14] => keep 06+07, exclude 14.
  const cluster = [dated[0]];
  let lastIso = dated[0].dateIso;
  const MAX_GAP_DAYS = 2;
  for (let i = 1; i < dated.length; i += 1) {
    const currIso = dated[i].dateIso;
    const prevDate = toUTCDateFromIso(lastIso);
    const currDate = toUTCDateFromIso(currIso);
    if (!prevDate || !currDate) break;
    const gapDays = Math.round((currDate.getTime() - prevDate.getTime()) / (24 * 60 * 60 * 1000));
    if (gapDays > MAX_GAP_DAYS) break;
    cluster.push(dated[i]);
    lastIso = currIso;
  }

  const startDateIso = cluster[0].dateIso;
  const endDateIso = cluster[cluster.length - 1].dateIso;
  const windowMatches = cluster.map((x) => x.match);
  return { matches: windowMatches, startDateIso, endDateIso };
}

function getMatchKickoffSortMs(match, leagueId) {
  const kickoffAt = getKickoffAtFromMatch(match, leagueId);
  if (kickoffAt) {
    const t = new Date(kickoffAt).getTime();
    if (!Number.isNaN(t)) return t;
  }
  const dateIso = extractMatchDateIso(match);
  if (dateIso) {
    const t = new Date(`${dateIso}T00:00:00`).getTime();
    if (!Number.isNaN(t)) return t;
  }
  return Number.MAX_SAFE_INTEGER;
}

function normalizeTeamNameForDedupe(name) {
  const cleaned = String(name || '')
    .toLowerCase()
    .replace(/\bsuper rugby\b/g, '')
    .replace(/\brugby\b/g, '')
    .replace(/\bnew south wales\b/g, '')
    .replace(/\bwellington\b/g, '')
    .replace(/\botago\b/g, '')
    .replace(/\bqueensland\b/g, '')
    .replace(/\bact\b/g, '')
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  const aliases = {
    'newsouthwaleswaratahs': 'waratahs',
    'wellingtonhurricanes': 'hurricanes',
    'hurricanessuperrugby': 'hurricanes',
    'otagohighlanders': 'highlanders',
    'highlanderssuperrugby': 'highlanders',
    'actbrumbies': 'brumbies',
    'queenslandreds': 'reds',
    'bluessuperrugby': 'blues',
    'crusaderssuperrugby': 'crusaders',
    'chiefssuperrugby': 'chiefs',
  };
  const key = cleaned.replace(/\s+/g, '');
  return aliases[key] || cleaned;
}

function canonicalTeamNameForPrediction(name) {
  const raw = String(name || '')
    .replace(/\bsuper rugby\b/gi, '')
    .replace(/\brugby\b/gi, '')
    .replace(/\s+/g, ' ')
    .trim();
  const norm = normalizeTeamNameForDedupe(raw);
  const toTitle = {
    waratahs: 'Waratahs',
    hurricanes: 'Hurricanes',
    highlanders: 'Highlanders',
    brumbies: 'Brumbies',
    reds: 'Reds',
    blues: 'Blues',
    crusaders: 'Crusaders',
    chiefs: 'Chiefs',
  };
  return toTitle[norm] || raw;
}

function hasMeaningfulKickoffForMatch(match, leagueId) {
  const kickoff = getKickoffAtFromMatch(match, leagueId);
  if (!kickoff) return false;
  const m = String(kickoff).match(/(\d{1,2}):(\d{2})/);
  if (!m) return false;
  const hh = Number(m[1]);
  const mm = Number(m[2]);
  return !(hh === 0 && mm === 0);
}

function isFinishedMatch(match) {
  const statusText = String(
    match?.status ||
    match?.match_status ||
    match?.fixture?.status?.short ||
    match?.fixture?.status?.long ||
    ''
  ).toUpperCase();
  if (!statusText) return false;
  return ['FT', 'AET', 'PEN', 'FINISHED', 'FULL TIME', 'COMPLETED'].some((token) =>
    statusText.includes(token)
  );
}

function hasRecordedResult(match) {
  const homeRaw = match?.home_score;
  const awayRaw = match?.away_score;
  if (homeRaw === null || homeRaw === undefined || awayRaw === null || awayRaw === undefined) {
    return false;
  }
  const home = Number(homeRaw);
  const away = Number(awayRaw);
  if (!Number.isFinite(home) || !Number.isFinite(away)) {
    return false;
  }
  // A non-zero scoreline strongly indicates the match has started/finished.
  return home > 0 || away > 0;
}

function extractIsoDateFromRaw(rawValue) {
  const raw = String(rawValue || '').trim();
  const m = raw.match(/^\d{4}-\d{2}-\d{2}/);
  return m ? m[0] : '';
}

function isLikelyStaleScoredFixture(match) {
  if (!hasRecordedResult(match)) return false;
  const fixtureDateIso = extractMatchDateIso(match);
  const timestampDateIso = extractIsoDateFromRaw(match?.timestamp || match?.strTimestamp);
  if (!fixtureDateIso || !timestampDateIso) return false;
  const fixtureDate = toUTCDateFromIso(fixtureDateIso);
  const timestampDate = toUTCDateFromIso(timestampDateIso);
  if (!fixtureDate || !timestampDate) return false;
  const diffDays = Math.abs(
    Math.round((fixtureDate.getTime() - timestampDate.getTime()) / (24 * 60 * 60 * 1000))
  );
  return diffDays > 2;
}

function isUpcomingMatch(match, leagueId) {
  return getUpcomingExclusionReason(match, leagueId) === null;
}

function getUpcomingExclusionReason(match, leagueId) {
  if (!match) return 'missing_match';
  if (isFinishedMatch(match)) return 'finished_status';
  const dateIso = extractMatchDateIso(match);
  const todayIso = getLocalYYYYMMDD();
  const isTodayFixture = Boolean(dateIso) && dateIso === todayIso;
  const staleScoredFutureFixture =
    isLikelyStaleScoredFixture(match) && Boolean(dateIso) && dateIso > todayIso;
  if (hasRecordedResult(match) && !staleScoredFutureFixture && !isTodayFixture) {
    return 'has_recorded_result';
  }

  const nowMs = Date.now();
  const kickoffAt = getKickoffAtFromMatch(match, leagueId);
  if (kickoffAt) {
    const kickoffMs = new Date(kickoffAt).getTime();
    if (Number.isFinite(kickoffMs)) {
      const kickoffDateIso = String(kickoffAt).match(/^\d{4}-\d{2}-\d{2}/)?.[0] || '';
      const kickoffAlignedWithFixtureDate = !dateIso || !kickoffDateIso || kickoffDateIso === dateIso;
      if (kickoffAlignedWithFixtureDate) {
        // Keep all same-day fixtures visible until local midnight.
        if (dateIso && dateIso === todayIso) {
          return null;
        }
        // Keep only genuinely upcoming kickoffs (small grace for clock skew).
        if (kickoffMs < nowMs - 5 * 60 * 1000) {
          return 'kickoff_in_past';
        }
        return null;
      }
      // If kickoff timestamp date disagrees with fixture date, keep using date-only fallback.
    }
  }

  // Date-only fallback for feeds that omit a trustworthy kickoff timestamp.
  // Keep same-day/future fixtures visible even if a partial score was synced.
  if (!dateIso) return 'missing_date';
  if (dateIso < todayIso) return 'fixture_date_in_past';
  return null;
}

function dedupeUpcomingMatches(matches, leagueId) {
  const sideIdentity = (match, side) => {
    const id = side === 'home' ? match?.home_team_id : match?.away_team_id;
    const name = side === 'home' ? match?.home_team : match?.away_team;
    if (id !== undefined && id !== null && String(id).trim() !== '') {
      return `id:${String(id).trim()}`;
    }
    return `name:${normalizeTeamNameForDedupe(name)}`;
  };

  const buildPairKey = (match) => {
    const home = normalizeTeamNameForDedupe(match?.home_team);
    const away = normalizeTeamNameForDedupe(match?.away_team);
    if (home <= away) return `${home}|${away}`;
    return `${away}|${home}`;
  };

  const getMatchQualityScore = (match) => {
    const hasKickoff = hasMeaningfulKickoffForMatch(match, leagueId);
    const hasIds = Boolean(match?.home_team_id && match?.away_team_id);
    const hasEventId = Boolean(match?.event_id || match?.id);
    return (hasKickoff ? 4 : 0) + (hasIds ? 2 : 0) + (hasEventId ? 1 : 0);
  };

  const byKey = new Map();
  for (const match of matches || []) {
    const dateIso = extractMatchDateIso(match) || getLocalYYYYMMDD();
    const home = sideIdentity(match, 'home');
    const away = sideIdentity(match, 'away');
    const key = `${dateIso}|${home}|${away}`;
    const existing = byKey.get(key);
    if (!existing) {
      byKey.set(key, match);
      continue;
    }

    const existingScore = getMatchQualityScore(existing);
    const currentScore = getMatchQualityScore(match);

    if (currentScore > existingScore) {
      byKey.set(key, match);
      continue;
    }
    if (currentScore === existingScore) {
      const tExisting = getMatchKickoffSortMs(existing, leagueId);
      const tCurrent = getMatchKickoffSortMs(match, leagueId);
      if (tCurrent < tExisting) {
        byKey.set(key, match);
      }
    }
  }
  const exactDeduped = Array.from(byKey.values());

  // Second pass: collapse near-duplicate fixtures for the same matchup when dates drift by ~1 day.
  // This handles API inconsistencies like same teams appearing on Fri and Sat for the same round.
  const byMatchup = new Map();
  const MAX_NEAR_DUP_MS = 72 * 60 * 60 * 1000; // 72 hours (handles stale date-only API duplicates)
  for (const match of exactDeduped) {
    const matchupKey = buildPairKey(match);
    const kickoffMs = getMatchKickoffSortMs(match, leagueId);
    const existing = byMatchup.get(matchupKey);
    if (!existing) {
      byMatchup.set(matchupKey, match);
      continue;
    }

    const existingMs = getMatchKickoffSortMs(existing, leagueId);
    const nearDuplicate =
      Number.isFinite(existingMs) &&
      Number.isFinite(kickoffMs) &&
      Math.abs(existingMs - kickoffMs) <= MAX_NEAR_DUP_MS;

    if (!nearDuplicate) {
      // Keep both when they are clearly separate fixtures.
      byMatchup.set(`${matchupKey}|${kickoffMs}`, match);
      continue;
    }

    const existingScore = getMatchQualityScore(existing);
    const currentScore = getMatchQualityScore(match);
    if (currentScore > existingScore) {
      byMatchup.set(matchupKey, match);
      continue;
    }
    if (currentScore === existingScore && kickoffMs < existingMs) {
      byMatchup.set(matchupKey, match);
    }
  }

  return Array.from(byMatchup.values());
}

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
  const [activeView, setActiveView] = useState('predictions'); // 'predictions', 'news', 'standings', 'history', or 'profile'
  const [profileRevision, setProfileRevision] = useState(0);
  const [userPreferences] = useState({
    followed_teams: [],
    followed_leagues: [],
  });
  const videoRef = useRef(null);
  const headerVideoRef = useRef(null);
  const autoOddsFetchedKeysRef = useRef(new Set());
  const autoOddsRunRef = useRef(0);
  const autoOddsLastSignatureRef = useRef('');
  
  const isMobile = useMediaQuery('(max-width:899.95px)');
  const isMobileReelsViewport = useMediaQuery('(max-width:768px)');
  const isMobileNewsReels = isMobileReelsViewport && activeView === 'news';
  const isTallMobileViewport = useMediaQuery('(min-height:860px)');

  const upcomingWindow = useMemo(() => getNextMatchWeek(upcomingMatches), [upcomingMatches]);
  const upcomingWindowMatches = useMemo(() => {
    return [...(upcomingWindow.matches || [])].sort((a, b) => {
      const ta = getMatchKickoffSortMs(a, selectedLeague);
      const tb = getMatchKickoffSortMs(b, selectedLeague);
      if (ta !== tb) return ta - tb;
      const ah = String(a?.home_team || '');
      const bh = String(b?.home_team || '');
      if (ah !== bh) return ah.localeCompare(bh);
      return String(a?.away_team || '').localeCompare(String(b?.away_team || ''));
    });
  }, [upcomingWindow.matches, selectedLeague]);

  // Check authentication on mount — skip silent auto-login when biometric is enabled.
  useEffect(() => {
    const checkAuthentication = async () => {
      try {
        const biometricEnabled = Boolean(getBiometricRegistration());

        const storedAuth = localStorage.getItem('rugby_ai_auth');
        if (storedAuth) {
          const auth = JSON.parse(storedAuth);
          
            // Validate stored auth structure
          if (!auth.licenseKey) {
            localStorage.removeItem('rugby_ai_auth');
            setCheckingAuth(false);
            return;
          }

          // Biometric users must unlock on the login screen each visit.
          if (biometricEnabled) {
            setAuthenticated(false);
            setCheckingAuth(false);
            return;
          }
          
          // Check if expired (with 1 hour buffer to account for timezone differences)
          if (auth.expiresAt && auth.expiresAt * 1000 < Date.now() - 3600000) {
            localStorage.removeItem('rugby_ai_auth');
            localStorage.setItem('rugby_ai_license_key', auth.licenseKey);
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
                deviceId: getDeviceId(),
              };
              
              // Save updated auth data
              localStorage.setItem('rugby_ai_auth', JSON.stringify(updatedAuth));
              saveDeviceSession(updatedAuth);
              setAuthData(updatedAuth);
            setAuthenticated(true);
          } else {
              const failure = handleDeviceAuthFailure(result.data);
              if (failure === 'blocked' || failure === 'pending') {
                setAuthenticated(false);
                setCheckingAuth(false);
                return;
              }
              // Key is no longer valid — keep key pre-filled for renewal entry.
            localStorage.removeItem('rugby_ai_auth');
            localStorage.setItem('rugby_ai_license_key', auth.licenseKey);
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
    ensureProfileFromAuth(auth);
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
    // Keep device session for biometric login on this device.
    if (authData?.licenseKey && getBiometricRegistration()) {
      saveDeviceSession(authData);
    } else if (authData?.licenseKey) {
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

    const html = document.documentElement;
    const body = document.body;
    const root = document.getElementById('root');
    const mainContent = document.querySelector('main') || document.querySelector('.main-content-wrapper');
    
    // Store original scroll position
    const scrollY = window.scrollY;
    const mainScrollTop = mainContent ? mainContent.scrollTop : 0;
    
    // Disable scrolling
    html.classList.add('drawer-open');
    body.classList.add('drawer-open');
    if (root) root.classList.add('drawer-open');
    html.style.overflow = 'hidden';
    html.style.height = '100%';
    body.style.overflow = 'hidden';
    body.style.position = 'fixed';
    body.style.top = `-${scrollY}px`;
    body.style.width = '100%';
    body.style.touchAction = 'none';
    body.style.overscrollBehavior = 'none';
    
    if (mainContent) {
      mainContent.style.overflow = 'hidden';
      mainContent.style.touchAction = 'none';
      mainContent.style.overscrollBehavior = 'none';
    }

    return () => {
      // Restore scrolling when drawer closes
      html.classList.remove('drawer-open');
      body.classList.remove('drawer-open');
      if (root) root.classList.remove('drawer-open');
      html.style.overflow = '';
      html.style.height = '';
      body.style.overflow = '';
      body.style.position = '';
      body.style.top = '';
      body.style.width = '';
      body.style.touchAction = '';
      body.style.overscrollBehavior = '';
      
      // Restore scroll position
      window.scrollTo(0, scrollY);
      
      if (mainContent) {
        mainContent.style.overflow = '';
        mainContent.style.touchAction = '';
        mainContent.style.overscrollBehavior = '';
        mainContent.scrollTop = mainScrollTop;
      }
    };
  }, [mobileOpen, isMobile]);

  // News + Standings + Predictions + History should use normal page scrolling (no inner scroll panel).
  // Mobile news uses fixed full-screen reels below nav — lock document scroll instead.
  useEffect(() => {
    const html = document.documentElement;
    const body = document.body;
    const root = document.getElementById('root');
    const shouldUseReelsImmersive = isMobileReelsViewport && activeView === 'news';
    const shouldUsePageScroll =
      (activeView === 'news' && !shouldUseReelsImmersive) ||
      activeView === 'standings' ||
      activeView === 'teams' ||
      activeView === 'lineups' ||
      activeView === 'predictions' ||
      activeView === 'history' ||
      activeView === 'profile';

    html.classList.toggle('news-page-scroll', shouldUsePageScroll);
    body.classList.toggle('news-page-scroll', shouldUsePageScroll);
    html.classList.toggle('news-reels-immersive', shouldUseReelsImmersive);
    body.classList.toggle('news-reels-immersive', shouldUseReelsImmersive);
    if (root) {
      root.classList.toggle('news-page-scroll', shouldUsePageScroll);
      root.classList.toggle('news-reels-immersive', shouldUseReelsImmersive);
    }

    return () => {
      html.classList.remove('news-page-scroll');
      body.classList.remove('news-page-scroll');
      html.classList.remove('news-reels-immersive');
      body.classList.remove('news-reels-immersive');
      if (root) {
        root.classList.remove('news-page-scroll');
        root.classList.remove('news-reels-immersive');
      }
    };
  }, [activeView, isMobileReelsViewport]);

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
    // eslint-disable-next-line react-hooks/exhaustive-deps -- load leagues once on auth; avoid re-running when selectedLeague changes
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
          const dedupedMatches = dedupeUpcomingMatches(matches, selectedLeague);
          const diagnostics = dedupedMatches.map((m) => {
            const reason = getUpcomingExclusionReason(m, selectedLeague);
            return {
              id: m?.id || m?.event_id || '',
              home: m?.home_team || '',
              away: m?.away_team || '',
              date_event: String(m?.date_event || ''),
              timestamp: String(m?.timestamp || ''),
              kickoff_at: String(getKickoffAtFromMatch(m, selectedLeague) || ''),
              score: `${m?.home_score ?? '-'}-${m?.away_score ?? '-'}`,
              exclusion_reason: reason || 'included',
            };
          });
          const upcomingOnlyMatches = dedupedMatches.filter((m) => isUpcomingMatch(m, selectedLeague));

          if (DEBUG_UPCOMING_LEAGUES.has(Number(selectedLeague))) {
            const reasonCounts = diagnostics.reduce((acc, row) => {
              const key = row.exclusion_reason;
              acc[key] = (acc[key] || 0) + 1;
              return acc;
            }, {});
            console.groupCollapsed(
              `[Upcoming Debug] league=${selectedLeague} raw=${matches.length} deduped=${dedupedMatches.length} kept=${upcomingOnlyMatches.length}`
            );
            console.log('Reason counts:', reasonCounts);
            console.table(diagnostics);
            console.groupEnd();
          }

          setUpcomingMatches(upcomingOnlyMatches);
          
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

  useEffect(() => {
    autoOddsFetchedKeysRef.current.clear();
  }, [selectedLeague]);

  useEffect(() => {
    let cancelled = false;
    const runId = ++autoOddsRunRef.current;
    if (!selectedLeague || upcomingWindowMatches.length === 0) {
      return undefined;
    }
    const signature = `${selectedLeague}::${upcomingWindowMatches
      .map((m) => `${m.id || m.event_id || ''}:${extractMatchDateIso(m) || ''}`)
      .join('|')}`;
    if (autoOddsLastSignatureRef.current === signature) {
      return undefined;
    }
    autoOddsLastSignatureRef.current = signature;

    const toDecimalOdds = (winProb) => {
      const p = Number(winProb);
      if (!Number.isFinite(p) || p <= 0 || p >= 1) return null;
      return Number((1 / p).toFixed(2));
    };

    const hydrateLiveBookmakerOdds = async () => {
      try {
        const { predictMatch } = await import('./firebase');
        const tasks = [];

        for (const match of upcomingWindowMatches) {
          const matchDate = extractMatchDateIso(match) || getLocalYYYYMMDD();
          const idKey = `manual_odds_by_ids::${match.home_team_id || ''}::${match.away_team_id || ''}::${matchDate}`;
          const nameKey = `${match.home_team}::${match.away_team}::${matchDate}`;
          const dedupeKey = `${idKey}::${String(match.id || match.event_id || '')}`;
          if (autoOddsFetchedKeysRef.current.has(dedupeKey)) continue;
          autoOddsFetchedKeysRef.current.add(dedupeKey);
          tasks.push({ match, matchDate, idKey, nameKey });
        }

        const concurrency = Math.min(2, tasks.length || 1);
        let taskIndex = 0;
        const oddsFillStats = {
          filled: 0,
          noBookmaker: 0,
          invalid: 0,
          preserved: 0,
        };

        const worker = async () => {
          while (!cancelled && taskIndex < tasks.length) {
            const currentIndex = taskIndex++;
            const { match, matchDate, idKey, nameKey } = tasks[currentIndex];
            try {
              const result = await predictMatch({
                home_team: canonicalTeamNameForPrediction(match.home_team),
                away_team: canonicalTeamNameForPrediction(match.away_team),
                league_id: selectedLeague,
                match_date: matchDate,
                event_id: match.id || match.event_id || null,
                enhanced: false,
                odds_only: true,
              });
              if (cancelled || runId !== autoOddsRunRef.current) {
                continue;
              }
              const pred = result?.data || {};
              const bookmakerCount = Number(pred.bookmaker_count || 0);
              const homeProb = Number(pred.bookmaker_home_win_prob);
              if (bookmakerCount <= 0) {
                oddsFillStats.noBookmaker += 1;
                continue;
              }

              const avgHome = Number(pred.avg_home_odds);
              const avgAway = Number(pred.avg_away_odds);
              const homeOdds = avgHome > 0
                ? Number(avgHome.toFixed(2))
                : toDecimalOdds(homeProb);
              const awayOdds = avgAway > 0
                ? Number(avgAway.toFixed(2))
                : toDecimalOdds(1 - homeProb);
              if (!homeOdds || !awayOdds) {
                oddsFillStats.invalid += 1;
                continue;
              }

              const wasCancelled = cancelled;
              const activeRunId = runId;
              const auto = { home: homeOdds, away: awayOdds };
              setManualOdds((prev) => {
                if (wasCancelled || activeRunId !== autoOddsRunRef.current) {
                  return prev;
                }
                const existing = prev[idKey] || prev[nameKey];
                if (existing && Number(existing.home) > 0 && Number(existing.away) > 0) {
                  oddsFillStats.preserved += 1;
                  return prev;
                }
                oddsFillStats.filled += 1;
                return {
                  ...prev,
                  [idKey]: auto,
                  [nameKey]: auto,
                };
              });
            } catch (_) {
              // Best-effort autofill only.
            }
          }
        };

        await Promise.all(Array.from({ length: concurrency }, () => worker()));
        if (cancelled || runId !== autoOddsRunRef.current) {
          return;
        }
        // Keep variables to make troubleshooting easy if logs are re-enabled.
        void oddsFillStats.filled;
        void oddsFillStats.noBookmaker;
        void oddsFillStats.invalid;
        void oddsFillStats.preserved;
      } catch (_) {
        // Keep manual input usable even if autofill fails.
      }
    };

    hydrateLiveBookmakerOdds();
    return () => {
      cancelled = true;
    };
  }, [selectedLeague, upcomingWindowMatches]);

  const handleGeneratePredictions = async () => {
    if (!selectedLeague || upcomingWindowMatches.length === 0) {
      return;
    }

    setGenerating(true);
    const newPredictions = [];
    const seenMatchups = new Set();
    const seenEventIds = new Set();

    // Import predict helpers dynamically
    const { predictMatch, predictMatchesBatch } = await import('./firebase');

    // Precompute unique match tasks (so we don't waste time on duplicates)
    const tasks = [];
    for (const match of upcomingWindowMatches) {
      const matchDate = extractMatchDateIso(match) || getLocalYYYYMMDD();
      const eventIdKey = String(match.event_id || match.id || '').trim();
      if (eventIdKey) {
        if (seenEventIds.has(eventIdKey)) {
          continue;
        }
        seenEventIds.add(eventIdKey);
      }

      const homeKey = match.home_team_id || normalizeTeamNameForDedupe(match.home_team);
      const awayKey = match.away_team_id || normalizeTeamNameForDedupe(match.away_team);
      const matchupKey = `${homeKey}::${awayKey}::${matchDate}`;
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

    // Fast path: ask the backend for the whole round in a single request.
    // It serves cached / snapshot predictions and computes only the misses,
    // so we avoid firing one Cloud Function call per match. We still fall back
    // to per-match calls below for anything the batch didn't return.
    const batchByEventId = new Map();
    const batchByNameKey = new Map();
    try {
      const batchMatches = tasks.map(({ match, matchDate }) => ({
        event_id: match.id || match.event_id || null,
        home_team: canonicalTeamNameForPrediction(match.home_team),
        away_team: canonicalTeamNameForPrediction(match.away_team),
        match_date: matchDate,
      }));
      const batchResult = await predictMatchesBatch({
        league_id: selectedLeague,
        matches: batchMatches,
      });
      const preds = batchResult?.data?.predictions || [];
      for (const p of preds) {
        if (p && !p.error) {
          if (p.event_id !== null && p.event_id !== undefined) {
            batchByEventId.set(String(p.event_id), p);
          }
          batchByNameKey.set(`${p.home_team}::${p.away_team}::${p.match_date}`, p);
        }
      }
    } catch (batchErr) {
      console.warn('Batch prediction unavailable, using per-match fallback:', batchErr?.message);
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
        const kickoffAt = getKickoffAtFromMatch(match, selectedLeague);

        try {
          const result = await retryWithBackoff(async () => {
            // Prefer the batched result when present; only hit the network for misses.
            const eid = String(match.id || match.event_id || '');
            const nameKey = `${canonicalTeamNameForPrediction(match.home_team)}::${canonicalTeamNameForPrediction(match.away_team)}::${matchDate}`;
            const fromBatch =
              (eid && batchByEventId.get(eid)) || batchByNameKey.get(nameKey);
            if (fromBatch) {
              return { data: fromBatch };
            }
            return await predictMatch({
              home_team: canonicalTeamNameForPrediction(match.home_team),
              away_team: canonicalTeamNameForPrediction(match.away_team),
              league_id: selectedLeague,
              match_date: matchDate,
              event_id: match.id || match.event_id || null,
              enhanced: false,
            });
          });

          if (result && result.data && !result.data.error) {
            const pred = result.data;
            const modelAvailable = pred.model_available !== false && pred.show_scores !== false;
            const bookmakerHomeWinProb = pred.bookmaker_home_win_prob ?? null;
            const bookmakerCount = pred.bookmaker_count ?? 0;

            if (!modelAvailable) {
              let homeWinProb = pred.home_win_prob ?? bookmakerHomeWinProb ?? 0.5;
              let predictionType = pred.prediction_type || 'Bookmaker Odds Only';

              if (odds && odds.home > 0 && odds.away > 0) {
                const homeDecimal = parseFloat(odds.home);
                const awayDecimal = parseFloat(odds.away);
                if (homeDecimal > 0 && awayDecimal > 0) {
                  const homeProbRaw = 1.0 / homeDecimal;
                  const awayProbRaw = 1.0 / awayDecimal;
                  const totalProb = homeProbRaw + awayProbRaw;
                  homeWinProb = homeProbRaw / totalProb;
                  predictionType = 'Bookmaker Odds Only';
                }
              }

              let winner;
              let finalConfidence;
              const apiWinner = pred.predicted_winner || pred.winner;
              if (apiWinner === 'Draw' || apiWinner === 'draw') {
                winner = 'Draw';
                finalConfidence = 0.5;
              } else if (apiWinner === 'Home' || apiWinner === match.home_team) {
                winner = match.home_team;
                finalConfidence = homeWinProb > 0.5 ? homeWinProb : 1 - homeWinProb;
              } else if (apiWinner === 'Away' || apiWinner === match.away_team) {
                winner = match.away_team;
                finalConfidence = homeWinProb < 0.5 ? 1 - homeWinProb : homeWinProb;
              } else if (homeWinProb > 0.5) {
                winner = match.home_team;
                finalConfidence = homeWinProb;
              } else if (homeWinProb < 0.5) {
                winner = match.away_team;
                finalConfidence = 1 - homeWinProb;
              } else {
                winner = 'Draw';
                finalConfidence = 0.5;
              }

              let confidenceLevel = 'Close Match Expected';
              if (finalConfidence >= 0.8) {
                confidenceLevel = 'High Confidence';
              } else if (finalConfidence >= 0.65) {
                confidenceLevel = 'Moderate Confidence';
              }

              newPredictions.push({
                home_team: match.home_team,
                away_team: match.away_team,
                date: matchDate,
                kickoff_at: kickoffAt,
                winner,
                predicted_winner: winner,
                confidence: `${(finalConfidence * 100).toFixed(1)}%`,
                home_score: null,
                away_score: null,
                show_scores: false,
                model_available: false,
                home_win_prob: homeWinProb,
                league_id: selectedLeague,
                intensity: 'Odds-based pick (no AI score yet)',
                confidence_level: confidenceLevel,
                score_diff: null,
                prediction_type: predictionType,
                ai_probability: null,
                hybrid_probability: homeWinProb,
                bookmaker_probability: bookmakerHomeWinProb ?? homeWinProb,
                bookmaker_count: bookmakerCount,
                confidence_boost: 0,
                home_team_id: match.home_team_id,
                away_team_id: match.away_team_id,
                live_odds_available: bookmakerCount > 0 || !!(odds && odds.home > 0 && odds.away > 0),
                manual_odds: odds,
              });
              continue;
            }

            // Extract AI prediction values (matching Streamlit make_expert_prediction)
            const aiHomeWinProb = pred.ai_home_win_prob ?? pred.home_win_prob ?? 0.5;
            const backendHybridProb = pred.hybrid_home_win_prob ?? pred.home_win_prob ?? aiHomeWinProb;
            const predictedHomeScore = parseFloat(pred.predicted_home_score || 0);
            const predictedAwayScore = parseFloat(pred.predicted_away_score || 0);
            const displayHomeScore = Math.round(predictedHomeScore);
            const displayAwayScore = Math.round(predictedAwayScore);
            const isDisplayedDraw = displayHomeScore === displayAwayScore;

            // Start from backend output (can already be Hybrid AI + Live Odds).
            let homeWinProb = backendHybridProb;
            let predictionType = pred.prediction_type || (bookmakerCount > 0 ? 'Hybrid AI + Live Odds' : 'AI Only (No Odds)');

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
            // Use predicted_winner from API when available; otherwise derive from scores (allow Draw)
            const apiWinner = pred.predicted_winner || pred.winner;
            if (apiWinner === 'Draw' || apiWinner === 'draw') {
              winner = 'Draw';
              finalConfidence = 0.5;
            } else if (apiWinner === 'Home' || apiWinner === match.home_team) {
              winner = match.home_team;
              finalConfidence = homeWinProb > 0.5 ? homeWinProb : 1 - homeWinProb;
            } else if (apiWinner === 'Away' || apiWinner === match.away_team) {
              winner = match.away_team;
              finalConfidence = homeWinProb < 0.5 ? 1 - homeWinProb : homeWinProb;
            } else if (isDisplayedDraw || predictedHomeScore === predictedAwayScore) {
              winner = 'Draw';
              finalConfidence = 0.5;
            } else if (homeWinProb > 0.5) {
              winner = match.home_team;
              finalConfidence = homeWinProb;
            } else if (homeWinProb < 0.5) {
              winner = match.away_team;
              finalConfidence = 1 - homeWinProb;
            } else {
              winner = 'Draw';
              finalConfidence = 0.5;
            }

            // Keep displayed scores consistent with final winner after odds blending.
            let alignedHomeScore = displayHomeScore;
            let alignedAwayScore = displayAwayScore;
            if (winner === match.away_team && alignedHomeScore >= alignedAwayScore) {
              [alignedHomeScore, alignedAwayScore] = [alignedAwayScore, alignedHomeScore];
            } else if (winner === match.home_team && alignedAwayScore >= alignedHomeScore) {
              [alignedHomeScore, alignedAwayScore] = [alignedAwayScore, alignedHomeScore];
            } else if (winner === 'Draw' && alignedHomeScore !== alignedAwayScore) {
              const avg = Math.round((alignedHomeScore + alignedAwayScore) / 2);
              alignedHomeScore = avg;
              alignedAwayScore = avg;
            }

            const scoreDiff = Math.abs(alignedHomeScore - alignedAwayScore);
            let intensity = 'Tight Margin (3-5 pts)';
            if (scoreDiff <= 2) {
              intensity = 'Narrow Margin (0-2 pts)';
            } else if (scoreDiff <= 5) {
              intensity = 'Tight Margin (3-5 pts)';
            } else if (scoreDiff <= 10) {
              intensity = 'Solid Margin (6-10 pts)';
            } else {
              intensity = 'Wide Margin (11+ pts)';
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
              kickoff_at: kickoffAt,
              winner: winner,
              predicted_winner: winner,
              confidence: `${(finalConfidence * 100).toFixed(1)}%`,
              home_score: alignedHomeScore.toString(),
              away_score: alignedAwayScore.toString(),
              home_win_prob: homeWinProb,
              league_id: selectedLeague,
              intensity: intensity,
              confidence_level: confidenceLevel,
              score_diff: alignedHomeScore - alignedAwayScore,
              prediction_type: predictionType,
              ai_probability: aiHomeWinProb,
              hybrid_probability: homeWinProb,
              bookmaker_probability: bookmakerHomeWinProb,
              bookmaker_count: bookmakerCount,
              confidence_boost: finalConfidence - Math.max(aiHomeWinProb, 1 - aiHomeWinProb),
              home_team_id: match.home_team_id,
              away_team_id: match.away_team_id,
              live_odds_available: bookmakerCount > 0 || !!(odds && odds.home > 0 && odds.away > 0),
              manual_odds: odds,
              show_scores: true,
              model_available: true,
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

    const dedupedPredictions = dedupeUpcomingMatches(
      newPredictions.map((p) => ({
        ...p,
        date_event: p.date,
        home_team: p.home_team,
        away_team: p.away_team,
        kickoff_at: p.kickoff_at,
      })),
      selectedLeague
    ).map((p) => ({
      ...p,
      date: p.date_event || p.date,
    }));
    setPredictions(dedupedPredictions);
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

  const handleViewChange = useCallback((view) => {
    setActiveView(view);
    if (isMobile) {
      setMobileOpen(false);
    }
  }, [isMobile]);

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
        <Box display="flex" flexDirection="column" justifyContent="center" alignItems="center" minHeight="100vh">
          <RugbyBallLoader size={120} color="#10b981" label="Loading..." />
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
        <Box display="flex" flexDirection="column" justifyContent="center" alignItems="center" minHeight="100vh">
          <RugbyBallLoader size={120} color="#10b981" label="Loading..." />
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
      overflowY: isMobile && isTallMobileViewport ? 'hidden' : 'auto',
      overflowX: 'hidden',
      minHeight: isMobile ? '100%' : 'auto',
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
        justifyContent: isMobile ? 'center' : 'center', 
        alignItems: 'center', 
        mb: isMobile ? 2 : 4,
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
        {isMobile ? (
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: '40px 1fr 40px',
              alignItems: 'center',
              width: '100%',
            }}
          >
            <Box aria-hidden sx={{ width: 40 }} />
            <Typography
              variant="h5"
              sx={{
                color: '#fafafa',
                fontWeight: 800,
                fontSize: '1.1rem',
                textAlign: 'center',
                letterSpacing: '-0.02em',
                justifySelf: 'center',
                '& .text': {
                  background: 'linear-gradient(135deg, #fafafa 0%, #10b981 100%)',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                  backgroundClip: 'text',
                },
              }}
            >
              <span className="text">Menu</span>
            </Typography>
            <IconButton
              onClick={handleDrawerToggle}
              sx={{
                justifySelf: 'end',
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
          </Box>
        ) : (
          <>
        <Typography variant="h5" sx={{ 
          color: '#fafafa', 
          fontWeight: 800,
          fontSize: '1.5rem',
          textAlign: 'center',
          letterSpacing: '-0.02em',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 1,
          '& .text': {
            background: 'linear-gradient(135deg, #fafafa 0%, #10b981 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
          },
        }}>
              <img src="/rugby_emoji.png" alt="Rugby Ball" style={{ width: '24px', height: '24px', marginRight: '8px', verticalAlign: 'middle' }} />
              <span className="text">Control Panel</span>
        </Typography>
          </>
        )}
      </Box>

      {isMobile ? (
        <>
          <Box sx={{ flexShrink: 0, width: '100%', mb: 2.5 }}>
            <Typography
              sx={{
                color: '#64748b',
                fontSize: '0.68rem',
                fontWeight: 700,
                letterSpacing: '0.12em',
                textTransform: 'uppercase',
                mb: 1.25,
                px: 0.5,
              }}
            >
              League
            </Typography>
            <LeagueSelector
              leagues={leagues}
              selectedLeague={selectedLeague}
              onLeagueChange={handleLeagueChange}
            />
            <Box
              sx={{
                width: '72%',
                maxWidth: 220,
                height: '2px',
                mx: 'auto',
                mt: 2.5,
                borderRadius: '2px',
                background: 'linear-gradient(90deg, transparent 0%, #10b981 50%, transparent 100%)',
                opacity: 0.6,
              }}
            />
          </Box>

          <Box sx={{ flex: '1 1 auto', minHeight: 0, width: '100%', mb: 2, overflowY: 'auto' }}>
            <Typography
              sx={{
                color: '#64748b',
                fontSize: '0.68rem',
                fontWeight: 700,
                letterSpacing: '0.12em',
                textTransform: 'uppercase',
                mb: 1.25,
                px: 0.5,
              }}
            >
              Navigate
            </Typography>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.65 }}>
              {APP_NAV_VIEWS.map((item) => {
                const isActive = activeView === item.id;
                return (
                  <Button
                    key={item.id}
                    fullWidth
                    onClick={() => handleViewChange(item.id)}
                    sx={{
                      justifyContent: 'flex-start',
                      gap: 1.25,
                      py: 1.15,
                      px: 1.5,
                      borderRadius: '12px',
                      textTransform: 'none',
                      fontWeight: 700,
                      fontSize: '0.95rem',
                      color: isActive ? '#d1fae5' : '#e2e8f0',
                      backgroundColor: isActive
                        ? 'linear-gradient(135deg, rgba(16,185,129,0.18), rgba(16,185,129,0.08))'
                        : 'rgba(255,255,255,0.03)',
                      border: isActive
                        ? '1px solid rgba(16, 185, 129, 0.45)'
                        : '1px solid rgba(255,255,255,0.06)',
                      boxShadow: isActive ? '0 4px 14px rgba(16, 185, 129, 0.15)' : 'none',
                      transition: 'all 0.2s ease',
                      '&:hover': {
                        backgroundColor: isActive
                          ? 'linear-gradient(135deg, rgba(16,185,129,0.24), rgba(16,185,129,0.12))'
                          : 'rgba(255,255,255,0.06)',
                        borderColor: isActive ? 'rgba(16, 185, 129, 0.55)' : 'rgba(255,255,255,0.12)',
                        transform: 'translateX(2px)',
                      },
                    }}
                  >
                    <Box component="span" sx={{ fontSize: '1.1rem', lineHeight: 1, width: 24, textAlign: 'center' }}>
                      {item.icon}
                    </Box>
                    {item.label}
                  </Button>
                );
              })}
            </Box>

            <Box
              sx={{
                width: '72%',
                maxWidth: 220,
                height: '2px',
                mx: 'auto',
                mt: 2.5,
                mb: 2,
                borderRadius: '2px',
                background: 'linear-gradient(90deg, transparent 0%, #10b981 50%, transparent 100%)',
                opacity: 0.6,
              }}
            />
            <ProfileDrawerSummary
              authData={authData}
              onOpenProfile={() => handleViewChange('profile')}
              isActive={activeView === 'profile'}
              profileRevision={profileRevision}
            />
          </Box>

          <Box
            sx={{
              flexShrink: 0,
              mt: 'auto',
              width: '100%',
              pt: 1.5,
              borderTop: '1px solid rgba(255,255,255,0.08)',
            }}
          >
            <Button
              fullWidth
              onClick={handleLogout}
              startIcon={<LogoutIcon />}
              sx={{
                color: '#d1d5db',
                fontSize: '0.875rem',
                textTransform: 'none',
                fontWeight: 600,
                px: 2.5,
                py: 1.1,
                borderRadius: '12px',
                backgroundColor: 'rgba(255, 255, 255, 0.03)',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                transition: 'all 0.3s ease',
                '&:hover': {
                  color: '#fafafa',
                  backgroundColor: 'rgba(239, 68, 68, 0.15)',
                  borderColor: 'rgba(239, 68, 68, 0.3)',
                  transform: 'translateY(-1px)',
                  boxShadow: '0 4px 12px rgba(239, 68, 68, 0.2)',
                },
              }}
            >
              Logout
            </Button>
          </Box>
        </>
      ) : (
        <>
          <Box sx={{ flexShrink: 0, width: '100%', mb: 2.5 }}>
            <Typography
              sx={{
                color: '#64748b',
                fontSize: '0.68rem',
                fontWeight: 700,
                letterSpacing: '0.12em',
                textTransform: 'uppercase',
                mb: 1.25,
                px: 0.5,
              }}
            >
              League
            </Typography>
            <LeagueSelector
              leagues={leagues}
              selectedLeague={selectedLeague}
              onLeagueChange={handleLeagueChange}
            />
            <Box
              sx={{
                width: '72%',
                maxWidth: 220,
                height: '2px',
                mx: 'auto',
                mt: 2.5,
                borderRadius: '2px',
                background: 'linear-gradient(90deg, transparent 0%, #10b981 50%, transparent 100%)',
                opacity: 0.6,
              }}
            />
            <Box sx={{ mt: 2.5 }}>
              <ProfileDrawerSummary
                authData={authData}
                onOpenProfile={() => handleViewChange('profile')}
                isActive={activeView === 'profile'}
                profileRevision={profileRevision}
              />
            </Box>
          </Box>

          <Box sx={{ flex: '1 1 auto', minHeight: 0 }} />

          <Box
            sx={{
              flexShrink: 0,
              mt: 'auto',
              width: '100%',
              pt: 1.5,
              borderTop: '1px solid rgba(255,255,255,0.08)',
            }}
          >
            <Button
              fullWidth
              onClick={handleLogout}
              startIcon={<LogoutIcon />}
              sx={{
                color: '#d1d5db',
                fontSize: '0.875rem',
                textTransform: 'none',
                fontWeight: 600,
                px: 2.5,
                py: 1.1,
                borderRadius: '12px',
                backgroundColor: 'rgba(255, 255, 255, 0.03)',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                transition: 'all 0.3s ease',
                '&:hover': {
                  color: '#fafafa',
                  backgroundColor: 'rgba(239, 68, 68, 0.15)',
                  borderColor: 'rgba(239, 68, 68, 0.3)',
                  transform: 'translateY(-1px)',
                  boxShadow: '0 4px 12px rgba(239, 68, 68, 0.2)',
                },
              }}
            >
              Logout
            </Button>
          </Box>
        </>
      )}
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
        overflow:
          !isMobile &&
          (activeView === 'news' ||
            activeView === 'standings' ||
            activeView === 'teams' ||
            activeView === 'predictions' ||
            activeView === 'lineups' ||
            activeView === 'history' ||
            activeView === 'profile')
            ? 'visible'
            : 'hidden',
        // Desktop only: Ensure container allows sticky positioning
        ...(isMobile ? {} : (activeView === 'news' || activeView === 'standings' || activeView === 'teams' || activeView === 'lineups' || activeView === 'predictions' || activeView === 'history' || activeView === 'profile' ? {
          height: 'auto',
          overflow: 'visible',
        } : {
          height: '100vh',
          overflow: 'hidden',
        })),
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
          onError={() => {
            const v = videoRef.current;
            if (!v) return;
            // Hard fallback for dev / CORS issues.
            try {
              v.src = '/video_rugby.mp4';
              v.load();
              v.play().catch(() => {});
            } catch {}
          }}
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
                position: 'fixed',
                top: 0,
                left: 0,
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
            {/* Keep iOS notch/safe-area fully painted while scrolling */}
            <Box
              sx={{
                position: 'fixed',
                top: 0,
                left: 0,
                right: 0,
                height: 'env(safe-area-inset-top, 0px)',
                backgroundColor: '#0e1117',
                zIndex: 2001,
                pointerEvents: 'none',
              }}
            />
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
                  zIndex: 2099,
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
                top: 'var(--app-mobile-nav-offset)',
                left: 0,
                width: '280px',
                height: 'calc(100svh - var(--app-mobile-nav-offset))',
                background: 'linear-gradient(180deg, rgba(38, 39, 48, 0.98) 0%, rgba(31, 41, 55, 0.95) 100%)',
                backdropFilter: 'blur(20px) saturate(180%)',
                borderRight: '1px solid rgba(16, 185, 129, 0.2)',
                boxShadow: '4px 0 24px rgba(0, 0, 0, 0.5), inset -1px 0 0 rgba(16, 185, 129, 0.1)',
                zIndex: 2100,
                transform: mobileOpen ? 'translateX(0)' : 'translateX(-100%)',
                transition: 'transform 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                overflowY: isTallMobileViewport ? 'hidden' : 'auto',
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
            left: { xs: 0, md: '280px' },
            right: 0,
            width: { xs: '100%', md: 'auto' },
            maxWidth: 'none',
            display: 'flex',
            gap: { xs: 0, md: 2 },
            justifyContent: { xs: 'center', md: 'center' },
            alignItems: 'center',
            paddingLeft: { xs: '12px', sm: '16px', md: '32px' },
            paddingRight: { xs: '12px', sm: '16px', md: '32px' },
            paddingTop: { xs: 'calc(env(safe-area-inset-top, 0px) + 10px)', md: '12px' },
            paddingBottom: { xs: '10px', md: '12px' },
            backgroundColor: '#0e1117',
            backdropFilter: 'blur(10px)',
            borderBottom: '1px solid rgba(16, 185, 129, 0.2)',
            boxShadow: '0 2px 8px rgba(0, 0, 0, 0.3)',
            zIndex: 2000,
            minHeight: { xs: 'calc(56px + env(safe-area-inset-top, 0px))', md: '56px' },
            boxSizing: 'border-box',
            margin: 0,
            overflow: 'hidden',
          }}>
            {isMobile ? (
              <Box
                sx={{
                  display: 'grid',
                  gridTemplateColumns: '40px 1fr 40px',
                  alignItems: 'center',
                  width: '100%',
                  minHeight: 36,
                }}
              >
                <IconButton
                  color="inherit"
                  aria-label={mobileOpen ? 'close menu' : 'open menu'}
                  onClick={handleDrawerToggle}
                  sx={{
                    justifySelf: 'start',
                    backgroundColor: 'rgba(38, 39, 48, 0.95)',
                    backdropFilter: 'blur(10px)',
                    color: '#fafafa',
                    padding: '7px',
                    borderRadius: '10px',
                    boxShadow: '0 4px 16px rgba(0,0,0,0.35), 0 0 0 1px rgba(255,255,255,0.08)',
                    transition: 'all 0.25s ease',
                    '&:hover': {
                      backgroundColor: 'rgba(16, 185, 129, 0.18)',
                      transform: 'scale(1.04)',
                    },
                    '&:active': {
                      transform: 'scale(0.96)',
                    },
                  }}
                >
                  {mobileOpen ? (
                    <CloseIcon sx={{ fontSize: '20px' }} />
                  ) : (
                    <MenuIcon sx={{ fontSize: '20px' }} />
                  )}
                </IconButton>

                <Box
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 0.75,
                    minWidth: 0,
                    px: 0.5,
                  }}
                >
                  <Box
                    component="img"
                    src="/rugby_emoji.png"
                    alt=""
                    aria-hidden
                    sx={{
                      width: 22,
                      height: 22,
                      flexShrink: 0,
                      filter: 'drop-shadow(0 2px 6px rgba(0,0,0,0.35))',
                    }}
                  />
                  <Typography
                    sx={{
                      fontWeight: 800,
                      fontSize: { xs: '0.9rem', sm: '0.98rem' },
                      letterSpacing: '-0.02em',
                      lineHeight: 1.2,
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      background: 'linear-gradient(135deg, #f8fafc 0%, #10b981 100%)',
                      WebkitBackgroundClip: 'text',
                      WebkitTextFillColor: 'transparent',
                      backgroundClip: 'text',
                    }}
                  >
                    {APP_DISPLAY_NAME}
                  </Typography>
                </Box>

                <Box aria-hidden sx={{ width: 40 }} />
              </Box>
            ) : (
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 2,
                justifyContent: 'center',
                flex: 1,
                minWidth: 0,
              }}
            >
            {APP_NAV_VIEWS.map((item) => (
            <Button
              key={item.id}
              onClick={() => handleViewChange(item.id)}
              sx={{
                color: activeView === item.id ? '#10b981' : '#9ca3af',
                borderBottom: activeView === item.id ? '2px solid #10b981' : '2px solid transparent',
                borderRadius: 0,
                textTransform: 'none',
                fontWeight: 600,
                px: 3,
                py: 1,
                fontSize: '14px',
                whiteSpace: 'nowrap',
                minWidth: 'fit-content',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                '&:hover': {
                  backgroundColor: 'rgba(16, 185, 129, 0.1)',
                },
              }}
            >
              {item.icon} {item.label}
            </Button>
            ))}
            </Box>
            )}
          </Box>

        {/* Main Content */}
        <Box
          component="main"
          className={
            isMobileNewsReels
              ? 'main-news-reels-immersive'
              : ((activeView === 'news' ||
                  activeView === 'standings' ||
                  activeView === 'teams' ||
                  activeView === 'predictions' ||
                  activeView === 'lineups' ||
            activeView === 'history' ||
                  activeView === 'profile')
                  ? 'main-news-page-scroll'
                  : undefined)
          }
          sx={{
            flexGrow: 1,
            // Use full available width across all main views.
            p: 0,
            pt: isMobileNewsReels
              ? 0
              : { xs: 'var(--app-mobile-nav-offset)', sm: '84px', md: '84px' },
            backgroundColor: 'transparent',
            color: '#fafafa',
            width: '100%',
            overflowX: 'hidden',
            boxSizing: 'border-box',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'stretch',
            paddingLeft: 0,
            paddingRight: 0,
            position: 'relative',
            zIndex: 1,
            ...(isMobileNewsReels ? {
              overflowY: 'hidden',
              height: '100svh',
              maxHeight: '100svh',
              contain: 'layout style',
            } : ((activeView === 'news' || activeView === 'standings' || activeView === 'teams' || activeView === 'lineups' || activeView === 'predictions' || activeView === 'history' || activeView === 'profile') ? {
              overflowY: 'visible',
              height: 'auto',
              maxHeight: 'none',
              // News uses full page scroll to avoid nested scroll containers.
              contain: 'layout style',
            } : {
              overflowY: 'auto',
              height: '100vh',
              maxHeight: '100vh',
              // Prevent layout shifts when dropdown opens
              contain: 'layout style',
            })),
          }}
        >
          <Box className="main-content-wrapper" sx={{ 
            width: '100%', 
            maxWidth: activeView === 'predictions' ? { xs: '100%', sm: '900px', md: '100%' } : '100%',
            mx: activeView === 'predictions' ? { xs: 0, sm: 'auto', md: 0 } : 0,
            px: {
              xs: activeView === 'predictions' ? 1 : 0,
              sm: activeView === 'predictions' ? 2 : 0,
              md: activeView === 'predictions' ? 2 : 0,
              lg: activeView === 'predictions' ? 3 : 0,
            },
            paddingTop: 0,
            overflowX: activeView === 'predictions' ? 'visible' : 'hidden',
            boxSizing: 'border-box',
          }}>
            {CONTENT_TAB_VIEWS.has(activeView) ? (
              <Box sx={VIEW_CONTENT_WRAPPER_SX}>
                {activeView === 'news' ? (
                  <NewsFeed
                    userPreferences={userPreferences}
                    leagueId={selectedLeague}
                    leagueName={leagueName}
                  />
                ) : activeView === 'standings' ? (
                  <LeagueStandings leagueId={selectedLeague} leagueName={leagueName} />
                ) : activeView === 'teams' ? (
                  <LeagueTeams leagueId={selectedLeague} leagueName={leagueName} />
                ) : activeView === 'lineups' ? (
                  <MatchLineups leagueId={selectedLeague} leagueName={leagueName} />
                ) : (
                  <HistoricalPredictions leagueId={selectedLeague} leagueName={leagueName} />
                )}
              </Box>
            ) : activeView === 'profile' ? (
              <UserProfilePage
                authData={authData}
                onProfileChange={() => setProfileRevision((r) => r + 1)}
              />
            ) : (
              <>
            {/* Header Video - same width as odds */}
            <Box 
              sx={{ 
                mt: { xs: 2, sm: 0 },
                width: '100%',
                maxWidth: { xs: '100%', sm: '900px', md: '100%' },
                height: { xs: '280px', sm: '380px', md: '550px', lg: '600px' },
                mx: 'auto',
                overflow: 'hidden',
                borderRadius: { xs: '12px', sm: '8px' },
                position: 'relative',
                display: 'block',
                padding: 0,
                marginBottom: 0,
                background: 'transparent',
                boxShadow: 'none',
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
                    display: 'block',
                    width: '100%',
                    height: '100%',
                    objectFit: 'cover',
                    objectPosition: 'center 65%',
                    willChange: 'transform',
                    transform: 'translateZ(0)',
                  }}
                  onError={(e) => {
                    console.error('Header video failed to load:', e);
                    const v = headerVideoRef.current;
                    if (!v) return;
                    // Hard fallback for dev / CORS issues.
                    try {
                      v.src = '/video_rugby_ball.mp4';
                      v.load();
                      v.play().catch(() => {});
                    } catch {}
                  }}
                >
                  <source src={MEDIA_URLS.videoRugbyBall} type="video/mp4" />
                </video>
            </Box>

            {selectedLeague && (
              <Box sx={{ width: '100%', boxSizing: 'border-box' }}>
              {/* League Metrics */}
              <LeagueMetrics leagueId={selectedLeague} leagueName={leagueName} />

              <Box
                sx={{
                  ...predictionsWidgetSx,
                  mb: 2.8,
                  px: { xs: 1.7, sm: 2.4 },
                  py: { xs: 1.5, sm: 1.85 },
                  borderRadius: 3,
                  border: '1px solid rgba(16,185,129,0.25)',
                  background:
                    'linear-gradient(135deg, rgba(15,23,42,0.9) 0%, rgba(30,41,59,0.8) 55%, rgba(16,185,129,0.12) 100%)',
                  textAlign: 'center',
                  boxShadow: '0 14px 34px rgba(2,6,23,0.28)',
                }}
              >
                <Typography
                  variant="h6"
                  sx={{ color: '#f8fafc', fontWeight: 800, letterSpacing: 0.25, mb: 0.55 }}
                >
                  AI-Powered Match Predictions
                </Typography>
                <Typography
                  variant="caption"
                  sx={{ display: 'block', mt: 0.45, color: '#cbd5e1', fontSize: '0.77rem' }}
                >
                  Odds are grouped by match date below and auto-filled from Highlightly bookmakers when available (typically 1–7 days before kickoff). Edit or clear fields to use your own odds.
                </Typography>
              </Box>

              {/* Live Matches */}
              <LiveMatches leagueId={selectedLeague} />

              {/* Manual Odds Input */}
              {loadingMatches ? (
                <Box sx={{ 
                  ...predictionsWidgetSx,
                  minHeight: { xs: 'calc(100svh - 400px)', sm: 'calc(100vh - 450px)' },
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  py: 4,
                  mb: 4,
                }}>
                  <RugbyBallLoader size={100} color="#10b981" compact label="Loading matches..." />
                </Box>
              ) : upcomingWindowMatches.length > 0 ? (
                <ManualOddsInput
                  matches={upcomingWindowMatches}
                  selectedLeague={selectedLeague}
                  manualOdds={manualOdds}
                  onOddsChange={handleManualOddsChange}
                  showHeader={false}
                />
              ) : (
                <Box sx={{ ...predictionsWidgetSx, mb: 4, p: 2, backgroundColor: '#1f2937', borderRadius: 2 }}>
                  <Typography variant="h6" sx={{ mb: 1, color: '#fafafa' }}>
                    📅 Upcoming Matches
                  </Typography>
                  <Typography color="text.secondary">
                    {selectedLeague ? 'No upcoming matches found for this league' : 'Select a league to see upcoming matches'}
                  </Typography>
                </Box>
              )}

                {/* Generate Predictions Button */}
                <Box sx={{ ...predictionsWidgetSx, my: 4, display: 'flex', flexDirection: 'column', alignItems: 'stretch', gap: 2 }}>
                  {generating && (
                    <Box sx={{ 
                      width: '100%', 
                      minHeight: { xs: 'calc(100svh - 400px)', sm: 'calc(100vh - 450px)' },
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      justifyContent: 'center',
                      py: 4,
                      mb: 2,
                    }}>
                      <RugbyBallLoader size={100} color="#10b981" compact label="Generating predictions..." />
                    </Box>
                  )}
                  <button
                    className="generate-button"
                    onClick={handleGeneratePredictions}
                    disabled={generating || upcomingWindowMatches.length === 0}
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
