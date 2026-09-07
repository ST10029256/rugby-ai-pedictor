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
import { VIEW_CONTENT_WRAPPER_SX, clearViewLoadingScrollLock } from './utils/viewLoader';
import { getLeagues, getUpcomingMatches, verifyLicenseKey } from './firebase';
import { MEDIA_URLS } from './utils/storageUrls';
import './App.css';
import { getLocalYYYYMMDD, getKickoffAtFromMatch } from './utils/date';
import { getBiometricRegistration, handleDeviceAuthFailure, saveDeviceSession } from './utils/biometricAuth';
import { getDeviceId } from './utils/deviceId';
import { ensureProfileFromAuth } from './utils/userProfile';
import { predictionsWidgetSx } from './utils/predictionsLayout';
import { applyLeagueDisplayNames, modelTeamNameForPrediction } from './utils/teamDisplayNames';
import { hasUsableOdds, impliedHomeProbability, oddsAdjustedView } from './utils/oddsAdjustment';

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

function addDaysIso(isoDate, days) {
  const d = toUTCDateFromIso(isoDate);
  if (!d) return '';
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function parseScoreValue(raw) {
  if (raw === null || raw === undefined || raw === '') return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

function matchActualScores(match) {
  const actualHome = parseScoreValue(match?.home_score);
  const actualAway = parseScoreValue(match?.away_score);
  if (actualHome === null || actualAway === null) {
    return { actual_home_score: null, actual_away_score: null };
  }
  return { actual_home_score: actualHome, actual_away_score: actualAway };
}

function withMatchActuals(prediction, match) {
  const actuals = matchActualScores(match);
  const predictedHome = parseScoreValue(
    prediction?.predicted_home_score ?? prediction?.home_score
  );
  const predictedAway = parseScoreValue(
    prediction?.predicted_away_score ?? prediction?.away_score
  );
  let predictionCorrect = prediction?.prediction_correct;
  if (
    predictionCorrect == null &&
    actuals.actual_home_score !== null &&
    predictedHome !== null &&
    predictedAway !== null
  ) {
    const actualWinner =
      actuals.actual_home_score > actuals.actual_away_score
        ? 'home'
        : actuals.actual_away_score > actuals.actual_home_score
          ? 'away'
          : 'draw';
    const predictedWinner =
      predictedHome > predictedAway ? 'home' : predictedAway > predictedHome ? 'away' : 'draw';
    predictionCorrect = actualWinner === predictedWinner;
  }
  return {
    ...prediction,
    ...actuals,
    prediction_correct: predictionCorrect ?? null,
  };
}

function cardFromFrozenMatch(match, leagueId, odds) {
  const matchDate = extractMatchDateIso(match) || getLocalYYYYMMDD();
  const kickoffAt = getKickoffAtFromMatch(match, leagueId);
  const predictedHome = parseScoreValue(match?.predicted_home_score);
  const predictedAway = parseScoreValue(match?.predicted_away_score);
  const hasAi = predictedHome !== null && predictedAway !== null;
  const apiWinner = match?.predicted_winner;
  const homeWinProb = parseScoreValue(match?.home_win_prob);
  const yourOddsView = oddsAdjustedView(
    homeWinProb ?? 0.5,
    odds,
    match.home_team,
    match.away_team
  );

  if (!hasAi) {
    return withMatchActuals({
      home_team: match.home_team,
      away_team: match.away_team,
      date: matchDate,
      kickoff_at: kickoffAt,
      league_id: leagueId,
      home_team_id: match.home_team_id,
      away_team_id: match.away_team_id,
      prediction_unavailable: true,
      unavailable_reason: 'No AI forecast was locked at midnight before kickoff',
      winner: null,
      predicted_winner: null,
      confidence: null,
      home_score: null,
      away_score: null,
      show_scores: false,
      model_available: false,
      manual_odds: odds,
    }, match);
  }

  let winner = null;
  if (apiWinner === 'Draw' || apiWinner === 'draw') {
    winner = 'Draw';
  } else if (apiWinner === 'Home' || apiWinnerMatchesSide(apiWinner, match, 'home')) {
    winner = match.home_team;
  } else if (apiWinner === 'Away' || apiWinnerMatchesSide(apiWinner, match, 'away')) {
    winner = match.away_team;
  } else if (predictedHome === predictedAway) {
    winner = 'Draw';
  } else {
    winner = predictedHome > predictedAway ? match.home_team : match.away_team;
  }

  let confidence = match?.predicted_confidence ?? match?.confidence ?? homeWinProb;
  if (typeof confidence === 'string') {
    const parsed = parseFloat(String(confidence).replace('%', ''));
    confidence = parsed > 1 ? parsed / 100 : parsed;
  }
  if (typeof confidence === 'number' && confidence > 1) {
    confidence = confidence / 100;
  }
  if (!Number.isFinite(confidence)) {
    confidence = homeWinProb != null
      ? (homeWinProb > 0.5 ? homeWinProb : 1 - homeWinProb)
      : 0.5;
  }

  const displayHome = Math.round(predictedHome);
  const displayAway = Math.round(predictedAway);
  const scoreDiff = Math.abs(displayHome - displayAway);
  let intensity = 'Tight Margin (3-5 pts)';
  if (scoreDiff <= 2) intensity = 'Narrow Margin (0-2 pts)';
  else if (scoreDiff <= 5) intensity = 'Tight Margin (3-5 pts)';
  else if (scoreDiff <= 10) intensity = 'Solid Margin (6-10 pts)';
  else intensity = 'Wide Margin (11+ pts)';

  let confidenceLevel = 'Close Match Expected';
  if (confidence >= 0.8) confidenceLevel = 'High Confidence';
  else if (confidence >= 0.65) confidenceLevel = 'Moderate Confidence';

  return withMatchActuals({
    home_team: match.home_team,
    away_team: match.away_team,
    date: matchDate,
    kickoff_at: kickoffAt,
    winner,
    predicted_winner: winner,
    confidence: `${(confidence * 100).toFixed(1)}%`,
    home_score: String(displayHome),
    away_score: String(displayAway),
    predicted_home_score: displayHome,
    predicted_away_score: displayAway,
    home_win_prob: homeWinProb,
    league_id: leagueId,
    intensity,
    confidence_level: confidenceLevel,
    score_diff: displayHome - displayAway,
    prediction_type: 'AI Snapshot (midnight lock)',
    ai_probability: homeWinProb,
    hybrid_probability: homeWinProb,
    bookmaker_count: match?.odds_bookmaker_count || 0,
    confidence_boost: 0,
    home_team_id: match.home_team_id,
    away_team_id: match.away_team_id,
    live_odds_available: hasUsableOdds(odds),
    manual_odds: odds,
    show_scores: true,
    model_available: true,
    your_odds_home_win_prob: yourOddsView ? yourOddsView.home_win_prob : null,
    your_odds_winner: yourOddsView ? yourOddsView.winner : null,
    your_odds_confidence: yourOddsView ? yourOddsView.confidence : null,
    your_odds_implied_home_win_prob: yourOddsView ? yourOddsView.odds_implied_home_win_prob : null,
  }, match);
}

function getNextMatchWeek(matches) {
  const dated = (matches || [])
    .map((match) => ({ match, dateIso: extractMatchDateIso(match) }))
    .filter((x) => x.dateIso)
    .sort((a, b) => a.dateIso.localeCompare(b.dateIso));

  if (dated.length === 0) {
    return { matches: [], startDateIso: '', endDateIso: '' };
  }

  const todayIso = getLocalYYYYMMDD();
  const yesterdayIso = addDaysIso(todayIso, -1);
  const yesterday = dated.filter((x) => x.dateIso === yesterdayIso);
  const upcoming = dated.filter((x) => x.dateIso >= todayIso);

  // Keep yesterday after midnight so those cards can flip to AI vs actual,
  // and still show the next live round instead of hiding it behind yesterday.
  let cluster = [];
  if (upcoming.length > 0) {
    cluster = [upcoming[0]];
    let lastIso = upcoming[0].dateIso;
    const MAX_GAP_DAYS = 2;
    for (let i = 1; i < upcoming.length; i += 1) {
      const currIso = upcoming[i].dateIso;
      const prevDate = toUTCDateFromIso(lastIso);
      const currDate = toUTCDateFromIso(currIso);
      if (!prevDate || !currDate) break;
      const gapDays = Math.round((currDate.getTime() - prevDate.getTime()) / (24 * 60 * 60 * 1000));
      if (gapDays > MAX_GAP_DAYS) break;
      cluster.push(upcoming[i]);
      lastIso = currIso;
    }
  }

  const combined = [...yesterday, ...cluster];
  const source = combined.length > 0 ? combined : dated.slice(0, 1);
  return {
    matches: source.map((x) => x.match),
    startDateIso: source[0].dateIso,
    endDateIso: source[source.length - 1].dateIso,
  };
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
    // Currie Cup standings labels ↔ Highlightly short names
    'goldenlions': 'lions',
    'bluebulls': 'bulls',
    'sharksxv': 'sharks',
    'sharkscurriecup': 'sharks',
    'stormersxxiii': 'stormers',
    'stormersxiii': 'stormers',
    'bolandcavaliers': 'boland',
    'freestatecheetahs': 'cheetahs',
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

function predictionTeamName(match, side = 'home') {
  return canonicalTeamNameForPrediction(modelTeamNameForPrediction(match, side));
}

function apiWinnerMatchesSide(apiWinner, match, side = 'home') {
  const label = String(apiWinner || '').trim().toLowerCase();
  if (!label) return false;
  const display = String(side === 'away' ? match?.away_team : match?.home_team || '').trim().toLowerCase();
  const raw = String(
    side === 'away'
      ? (match?.away_team_raw || match?.away_team || '')
      : (match?.home_team_raw || match?.home_team || '')
  )
    .trim()
    .toLowerCase();
  return label === display || label === raw;
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
  const dateIso = extractMatchDateIso(match);
  const todayIso = getLocalYYYYMMDD();
  const oldestKeepIso = addDaysIso(todayIso, -1);
  // Yesterday stays on Predictions after midnight so AI vs actual can show.
  // Today and future stay as the live/upcoming card.
  if (dateIso && oldestKeepIso && dateIso >= oldestKeepIso) {
    return null;
  }
  if (isFinishedMatch(match)) return 'finished_status';
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
          // Unscored weekend games must stay on Predictions after midnight.
          const oldestKeepIso = addDaysIso(todayIso, -2);
          if (!hasRecordedResult(match) && dateIso && oldestKeepIso && dateIso >= oldestKeepIso) {
            return null;
          }
          return 'kickoff_in_past';
        }
        return null;
      }
      // Corrupted/stale rows where stored kickoff day disagrees with fixture day.
      // These are usually duplicate sqlite-id clones and should not appear in odds.
      return 'kickoff_date_mismatch';
    }
  }

  // Date-only fallback for feeds that omit a trustworthy kickoff timestamp.
  // Keep same-day/future fixtures visible even if a partial score was synced.
  if (!dateIso) return 'missing_date';
  if (dateIso < todayIso) {
    const oldestKeepIso = addDaysIso(todayIso, -2);
    if (!hasRecordedResult(match) && oldestKeepIso && dateIso >= oldestKeepIso) {
      return null;
    }
    return 'fixture_date_in_past';
  }
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
    const hlId = match?.highlightly_match_id || match?.highlightlyMatchId;
    const docId = match?.id || match?.event_id;
    const isCanonicalHlDoc =
      hlId !== undefined &&
      hlId !== null &&
      String(hlId).trim() !== '' &&
      String(docId) === String(hlId);
    // Prefer Highlightly-canonical docs so sqlite-id clones lose dedupe ties.
    return (
      (isCanonicalHlDoc ? 8 : 0) +
      (hasKickoff ? 4 : 0) +
      (hasIds ? 2 : 0) +
      (hasEventId ? 1 : 0)
    );
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
  const [generatedPredictions, setGeneratedPredictions] = useState([]);
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

  const oddsInputMatches = useMemo(() => {
    const todayIso = getLocalYYYYMMDD();
    return upcomingWindowMatches.filter((match) => {
      const dateIso = extractMatchDateIso(match);
      return !dateIso || dateIso >= todayIso;
    });
  }, [upcomingWindowMatches]);

  const postGameCards = useMemo(() => {
    if (!selectedLeague) return [];
    const todayIso = getLocalYYYYMMDD();
    const yesterdayIso = addDaysIso(todayIso, -1);
    return upcomingWindowMatches
      .filter((match) => extractMatchDateIso(match) === yesterdayIso)
      .map((match) => {
        const matchDate = extractMatchDateIso(match) || yesterdayIso;
        const idKey = `manual_odds_by_ids::${match.home_team_id || ''}::${match.away_team_id || ''}::${matchDate}`;
        const nameKey = `${match.home_team}::${match.away_team}::${matchDate}`;
        return cardFromFrozenMatch(match, selectedLeague, manualOdds[idKey] || manualOdds[nameKey]);
      })
      .filter((card) => card.predicted_home_score != null || card.home_score != null);
  }, [selectedLeague, upcomingWindowMatches, manualOdds]);

  const predictions = useMemo(() => {
    const generatedKeys = new Set(
      generatedPredictions.map((p) => `${p.home_team}::${p.away_team}::${p.date}`)
    );
    const extras = postGameCards.filter(
      (card) => !generatedKeys.has(`${card.home_team}::${card.away_team}::${card.date}`)
    );
    return [...extras, ...generatedPredictions];
  }, [postGameCards, generatedPredictions]);

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
    setGeneratedPredictions([]);
    setMobileOpen(false);
    setActiveView('predictions');

    // Clear mobile scroll locks so the login screen stays interactive.
    const html = document.documentElement;
    const body = document.body;
    const root = document.getElementById('root');
    html.classList.remove('news-reels-immersive', 'news-page-scroll', 'drawer-open', 'menu-open');
    body.classList.remove('news-reels-immersive', 'news-page-scroll', 'drawer-open', 'menu-open');
    if (root) root.classList.remove('news-reels-immersive', 'news-page-scroll', 'drawer-open', 'menu-open');
    html.style.overflow = '';
    html.style.height = '';
    body.style.overflow = '';
    body.style.position = '';
    body.style.top = '';
    body.style.width = '';
    body.style.touchAction = '';
    body.style.overscrollBehavior = '';
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


  // Prevent page scrolling when mobile drawer is open (only while authenticated).
  useEffect(() => {
    if (!authenticated || !isMobile || !mobileOpen) return;

    const html = document.documentElement;
    const body = document.body;
    const root = document.getElementById('root');
    const scrollY = window.scrollY;

    html.classList.add('drawer-open');
    body.classList.add('drawer-open');
    if (root) root.classList.add('drawer-open');

    const hadPageScroll =
      html.classList.contains('news-page-scroll') ||
      body.classList.contains('news-page-scroll');
    html.classList.remove('news-page-scroll');
    body.classList.remove('news-page-scroll');
    if (root) root.classList.remove('news-page-scroll');

    // Lock page without position:fixed (that jumps/glitches the panel on iOS).
    html.style.overflow = 'hidden';
    body.style.overflow = 'hidden';
    body.style.overscrollBehavior = 'none';

    return () => {
      html.classList.remove('drawer-open');
      body.classList.remove('drawer-open');
      if (root) root.classList.remove('drawer-open');

      if (hadPageScroll) {
        html.classList.add('news-page-scroll');
        body.classList.add('news-page-scroll');
        if (root) root.classList.add('news-page-scroll');
      }

      html.style.overflow = '';
      body.style.overflow = '';
      body.style.overscrollBehavior = '';
      window.scrollTo(0, scrollY);
    };
  }, [authenticated, mobileOpen, isMobile]);

  // News + Standings + Predictions + History should use normal page scrolling (no inner scroll panel).
  // Mobile news uses fixed full-screen reels below nav — lock document scroll instead.
  useEffect(() => {
    const html = document.documentElement;
    const body = document.body;
    const root = document.getElementById('root');
    const shouldUseReelsImmersive =
      authenticated && isMobileReelsViewport && activeView === 'news';
    const shouldUsePageScroll =
      authenticated &&
      ((activeView === 'news' && !shouldUseReelsImmersive) ||
        activeView === 'standings' ||
        activeView === 'teams' ||
        activeView === 'lineups' ||
        activeView === 'predictions' ||
        activeView === 'history' ||
        activeView === 'profile');

    html.classList.toggle('news-page-scroll', shouldUsePageScroll);
    body.classList.toggle('news-page-scroll', shouldUsePageScroll);
    html.classList.toggle('news-reels-immersive', shouldUseReelsImmersive);
    body.classList.toggle('news-reels-immersive', shouldUseReelsImmersive);
    if (root) {
      root.classList.toggle('news-page-scroll', shouldUsePageScroll);
      root.classList.toggle('news-reels-immersive', shouldUseReelsImmersive);
    }

    // Drop any stuck mobile loading lock when switching views.
    clearViewLoadingScrollLock();

    // Desktop/tablet: only html may be a scroll container, and only when content overflows.
    if (shouldUsePageScroll && !isMobileReelsViewport) {
      html.style.setProperty('overflow-y', 'auto', 'important');
      html.style.setProperty('overflow-x', 'hidden', 'important');
      html.style.height = 'auto';
      html.style.maxHeight = '';
      body.style.setProperty('overflow', 'visible', 'important');
      body.style.height = 'auto';
      body.style.position = '';
      body.style.top = '';
      body.style.width = '';
      body.style.overscrollBehavior = 'none';
      if (root) {
        root.style.setProperty('overflow', 'visible', 'important');
        root.style.height = 'auto';
        root.style.minHeight = '100%';
      }
    }

    return () => {
      html.classList.remove('news-page-scroll');
      body.classList.remove('news-page-scroll');
      html.classList.remove('news-reels-immersive');
      body.classList.remove('news-reels-immersive');
      if (root) {
        root.classList.remove('news-page-scroll');
        root.classList.remove('news-reels-immersive');
        root.style.overflow = '';
        root.style.height = '';
        root.style.minHeight = '';
      }
      html.style.overflow = '';
      html.style.overflowY = '';
      html.style.overflowX = '';
      html.style.height = '';
      body.style.overflow = '';
      body.style.overflowY = '';
      body.style.overflowX = '';
      body.style.height = '';
      clearViewLoadingScrollLock();
    };
  }, [authenticated, activeView, isMobileReelsViewport]);

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
    setGeneratedPredictions([]);
    setLoadingMatches(true);

    const fetchUpcoming = async () => {
      try {
        const result = await getUpcomingMatches({ league_id: selectedLeague, limit: 50 });
        
        if (result && result.data) {
          const matches = (result.data.matches || []).map((m) =>
            applyLeagueDisplayNames(m, selectedLeague)
          );
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

    // Odds arrive on the fixture itself, refreshed hourly for everyone by
    // scripts/refresh_match_odds.py. This used to fire one request per fixture
    // per viewer, so the same round was priced thousands of times over and two
    // people could be shown different odds depending on when they loaded.
    const hydrateSharedBookmakerOdds = () => {
      const fills = {};

      for (const match of upcomingWindowMatches) {
        const homeOdds = Number(match.odds_home);
        const awayOdds = Number(match.odds_away);
        if (!(homeOdds > 0) || !(awayOdds > 0)) continue;

        const matchDate = extractMatchDateIso(match) || getLocalYYYYMMDD();
        const idKey = `manual_odds_by_ids::${match.home_team_id || ''}::${match.away_team_id || ''}::${matchDate}`;
        const nameKey = `${match.home_team}::${match.away_team}::${matchDate}`;
        const dedupeKey = `${idKey}::${String(match.id || match.event_id || '')}`;
        if (autoOddsFetchedKeysRef.current.has(dedupeKey)) continue;
        autoOddsFetchedKeysRef.current.add(dedupeKey);

        const auto = {
          home: Number(homeOdds.toFixed(2)),
          away: Number(awayOdds.toFixed(2)),
        };
        fills[idKey] = auto;
        fills[nameKey] = auto;
      }

      if (cancelled || runId !== autoOddsRunRef.current || !Object.keys(fills).length) {
        return;
      }

      setManualOdds((prev) => {
        const next = { ...prev };
        let changed = false;
        for (const [key, auto] of Object.entries(fills)) {
          const existing = prev[key];
          // Anything the user typed wins over the shared market price.
          if (existing && Number(existing.home) > 0 && Number(existing.away) > 0) continue;
          next[key] = auto;
          changed = true;
        }
        return changed ? next : prev;
      });
    };

    hydrateSharedBookmakerOdds();
    return () => {
      cancelled = true;
    };
  }, [selectedLeague, upcomingWindowMatches]);


  const handleGeneratePredictions = async () => {
    if (!selectedLeague || oddsInputMatches.length === 0) {
      return;
    }

    setGenerating(true);
    const newPredictions = [];
    const seenMatchups = new Set();
    const seenEventIds = new Set();
    const { predictMatch, predictMatchesBatch } = await import('./firebase');

    const tasks = [];
    for (const match of oddsInputMatches) {
      const matchDate = extractMatchDateIso(match) || getLocalYYYYMMDD();
      const eventIdKey = String(match.event_id || match.id || '').trim();
      if (eventIdKey) {
        if (seenEventIds.has(eventIdKey)) continue;
        seenEventIds.add(eventIdKey);
      }
      const homeKey = match.home_team_id || normalizeTeamNameForDedupe(match.home_team);
      const awayKey = match.away_team_id || normalizeTeamNameForDedupe(match.away_team);
      const matchupKey = `${homeKey}::${awayKey}::${matchDate}`;
      if (seenMatchups.has(matchupKey)) continue;
      seenMatchups.add(matchupKey);
      const idKey = `manual_odds_by_ids::${match.home_team_id || ''}::${match.away_team_id || ''}::${matchDate}`;
      const nameKey = `${match.home_team}::${match.away_team}::${matchDate}`;
      tasks.push({ match, matchDate, odds: manualOdds[idKey] || manualOdds[nameKey] });
    }

    const batchByEventId = new Map();
    const batchByNameKey = new Map();
    try {
      const batchResult = await predictMatchesBatch({
        league_id: selectedLeague,
        matches: tasks.map(({ match, matchDate }) => ({
          event_id: match.id || match.event_id || null,
          home_team: predictionTeamName(match, 'home'),
          away_team: predictionTeamName(match, 'away'),
          match_date: matchDate,
        })),
      });
      for (const p of batchResult?.data?.predictions || []) {
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

    const retryWithBackoff = async (fn, maxRetries = 3, initialDelay = 1000) => {
      for (let attempt = 0; attempt < maxRetries; attempt++) {
        try {
          return await fn();
        } catch (error) {
          const isLastAttempt = attempt === maxRetries - 1;
          const isCorsError = error.message?.includes('CORS') || error.code === 'functions/internal';
          const is503Error = error.message?.includes('503') || error.code === 'functions/unavailable';
          if (isLastAttempt || !(isCorsError || is503Error)) throw error;
          await new Promise((resolve) => setTimeout(resolve, initialDelay * Math.pow(2, attempt)));
        }
      }
    };

    let taskIndex = 0;
    const concurrency = Math.min(2, tasks.length || 1);
    const runTask = async () => {
      while (taskIndex < tasks.length) {
        const currentIndex = taskIndex++;
        const { match, matchDate, odds } = tasks[currentIndex];
        const kickoffAt = getKickoffAtFromMatch(match, selectedLeague);
        try {
          const result = await retryWithBackoff(async () => {
            const eid = String(match.id || match.event_id || '');
            const nameKey = `${predictionTeamName(match, 'home')}::${predictionTeamName(match, 'away')}::${matchDate}`;
            const fromBatch = (eid && batchByEventId.get(eid)) || batchByNameKey.get(nameKey);
            if (fromBatch) return { data: fromBatch };
            return await predictMatch({
              home_team: predictionTeamName(match, 'home'),
              away_team: predictionTeamName(match, 'away'),
              league_id: selectedLeague,
              match_date: matchDate,
              event_id: match.id || match.event_id || null,
              enhanced: false,
            });
          });

          if (!result?.data || result.data.error) {
            if (result?.data?.error) console.error('Prediction error:', result.data.error);
            continue;
          }
          const pred = result.data;
          if (pred.prediction_unavailable) {
            newPredictions.push(withMatchActuals({
              home_team: match.home_team,
              away_team: match.away_team,
              date: matchDate,
              kickoff_at: kickoffAt,
              league_id: selectedLeague,
              home_team_id: match.home_team_id,
              away_team_id: match.away_team_id,
              prediction_unavailable: true,
              unavailable_reason: pred.unavailable_reason || 'No pre-kickoff forecast was recorded',
              winner: null,
              predicted_winner: null,
              confidence: null,
              home_score: null,
              away_score: null,
              show_scores: false,
              model_available: false,
              manual_odds: odds,
            }, match));
            continue;
          }

          const modelAvailable = pred.model_available !== false && pred.show_scores !== false;
          const bookmakerHomeWinProb = pred.bookmaker_home_win_prob ?? null;
          const bookmakerCount = pred.bookmaker_count ?? 0;

          if (!modelAvailable) {
            const userImplied = hasUsableOdds(odds) ? impliedHomeProbability(odds.home, odds.away) : null;
            const homeWinProb = userImplied ?? pred.home_win_prob ?? bookmakerHomeWinProb ?? 0.5;
            const apiWinner = pred.predicted_winner || pred.winner;
            let winner;
            let finalConfidence;
            if (apiWinner === 'Draw' || apiWinner === 'draw') {
              winner = 'Draw';
              finalConfidence = 0.5;
            } else if (apiWinner === 'Home' || apiWinnerMatchesSide(apiWinner, match, 'home')) {
              winner = match.home_team;
              finalConfidence = homeWinProb > 0.5 ? homeWinProb : 1 - homeWinProb;
            } else if (apiWinner === 'Away' || apiWinnerMatchesSide(apiWinner, match, 'away')) {
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
            newPredictions.push(withMatchActuals({
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
              confidence_level: finalConfidence >= 0.8 ? 'High Confidence' : finalConfidence >= 0.65 ? 'Moderate Confidence' : 'Close Match Expected',
              score_diff: null,
              prediction_type: userImplied !== null ? 'Your Odds Only' : (pred.prediction_type || 'Bookmaker Odds Only'),
              ai_probability: null,
              hybrid_probability: homeWinProb,
              bookmaker_probability: bookmakerHomeWinProb ?? homeWinProb,
              bookmaker_count: bookmakerCount,
              confidence_boost: 0,
              home_team_id: match.home_team_id,
              away_team_id: match.away_team_id,
              live_odds_available: bookmakerCount > 0 || hasUsableOdds(odds),
              manual_odds: odds,
            }, match));
            continue;
          }

          const aiHomeWinProb = pred.ai_home_win_prob ?? pred.home_win_prob ?? 0.5;
          const homeWinProb = pred.hybrid_home_win_prob ?? pred.home_win_prob ?? aiHomeWinProb;
          const predictedHomeScore = parseFloat(pred.predicted_home_score ?? 0);
          const predictedAwayScore = parseFloat(pred.predicted_away_score ?? 0);
          const displayHomeScore = Math.round(predictedHomeScore);
          const displayAwayScore = Math.round(predictedAwayScore);
          const yourOddsView = oddsAdjustedView(aiHomeWinProb, odds, match.home_team, match.away_team);
          const apiWinner = pred.predicted_winner || pred.winner;
          let winner;
          let finalConfidence;
          if (apiWinner === 'Draw' || apiWinner === 'draw') {
            winner = 'Draw';
            finalConfidence = 0.5;
          } else if (apiWinner === 'Home' || apiWinnerMatchesSide(apiWinner, match, 'home')) {
            winner = match.home_team;
            finalConfidence = homeWinProb > 0.5 ? homeWinProb : 1 - homeWinProb;
          } else if (apiWinner === 'Away' || apiWinnerMatchesSide(apiWinner, match, 'away')) {
            winner = match.away_team;
            finalConfidence = homeWinProb < 0.5 ? 1 - homeWinProb : homeWinProb;
          } else if (displayHomeScore === displayAwayScore) {
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
          const scoreDiff = Math.abs(displayHomeScore - displayAwayScore);
          let intensity = 'Tight Margin (3-5 pts)';
          if (scoreDiff <= 2) intensity = 'Narrow Margin (0-2 pts)';
          else if (scoreDiff <= 5) intensity = 'Tight Margin (3-5 pts)';
          else if (scoreDiff <= 10) intensity = 'Solid Margin (6-10 pts)';
          else intensity = 'Wide Margin (11+ pts)';

          newPredictions.push(withMatchActuals({
            home_team: match.home_team,
            away_team: match.away_team,
            date: matchDate,
            kickoff_at: kickoffAt,
            winner,
            predicted_winner: winner,
            confidence: `${(finalConfidence * 100).toFixed(1)}%`,
            home_score: displayHomeScore.toString(),
            away_score: displayAwayScore.toString(),
            predicted_home_score: displayHomeScore,
            predicted_away_score: displayAwayScore,
            home_win_prob: homeWinProb,
            league_id: selectedLeague,
            intensity,
            confidence_level: finalConfidence >= 0.8 ? 'High Confidence' : finalConfidence >= 0.65 ? 'Moderate Confidence' : 'Close Match Expected',
            score_diff: displayHomeScore - displayAwayScore,
            prediction_type: pred.prediction_type || (bookmakerCount > 0 ? 'Hybrid AI + Live Odds' : 'AI Only (No Odds)'),
            ai_probability: aiHomeWinProb,
            hybrid_probability: homeWinProb,
            bookmaker_probability: bookmakerHomeWinProb,
            bookmaker_count: bookmakerCount,
            confidence_boost: finalConfidence - Math.max(aiHomeWinProb, 1 - aiHomeWinProb),
            home_team_id: match.home_team_id,
            away_team_id: match.away_team_id,
            live_odds_available: bookmakerCount > 0 || hasUsableOdds(odds),
            manual_odds: odds,
            show_scores: true,
            model_available: true,
            your_odds_home_win_prob: yourOddsView ? yourOddsView.home_win_prob : null,
            your_odds_winner: yourOddsView ? yourOddsView.winner : null,
            your_odds_confidence: yourOddsView ? yourOddsView.confidence : null,
            your_odds_implied_home_win_prob: yourOddsView ? yourOddsView.odds_implied_home_win_prob : null,
          }, match));
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
    setGeneratedPredictions(dedupedPredictions);
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
    // Keep the control panel open so the league dropdown can close cleanly.
    // Panel closes via nav change / explicit close only.
  }, []);

  // Show login widget if not authenticated
  if (checkingAuth) {
    return (
      <ThemeProvider theme={darkTheme}>
        <CssBaseline />
        <Box
          display="flex"
          flexDirection="column"
          justifyContent="center"
          alignItems="center"
          sx={{
            position: 'fixed',
            inset: 0,
            width: '100%',
            height: '100dvh',
            minHeight: '100dvh',
            display: 'flex',
            placeContent: 'center',
            placeItems: 'center',
            backgroundColor: '#020617',
            zIndex: 40,
          }}
        >
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
        <Box
          display="flex"
          flexDirection="column"
          justifyContent="center"
          alignItems="center"
          sx={{
            position: 'fixed',
            inset: 0,
            width: '100%',
            height: '100dvh',
            minHeight: '100dvh',
            display: 'flex',
            placeContent: 'center',
            placeItems: 'center',
            backgroundColor: '#020617',
            zIndex: 40,
          }}
        >
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
      // Outer panel scrolls on mobile — avoid nested scroll glitches.
      overflowY: isMobile ? 'visible' : 'auto',
      overflowX: 'hidden',
      WebkitOverflowScrolling: isMobile ? 'auto' : 'touch',
      overscrollBehavior: 'contain',
      minHeight: isMobile ? '100%' : 'auto',
      ...(!isMobile ? {
        contain: 'layout style',
      } : {}),
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
          <Typography
            variant="h5"
            sx={{
              color: '#fafafa',
              fontWeight: 800,
              fontSize: '1.1rem',
              textAlign: 'center',
              letterSpacing: '-0.02em',
              width: '100%',
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
                      display: 'grid',
                      gridTemplateColumns: '28px 1fr 28px',
                      alignItems: 'center',
                      justifyContent: 'stretch',
                      gap: 0,
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
                      transition: 'background-color 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease',
                      WebkitUserSelect: 'none',
                      userSelect: 'none',
                      WebkitTouchCallout: 'none',
                      touchAction: 'manipulation',
                      '&:hover': {
                        backgroundColor: isActive
                          ? 'linear-gradient(135deg, rgba(16,185,129,0.24), rgba(16,185,129,0.12))'
                          : 'rgba(255,255,255,0.06)',
                        borderColor: isActive ? 'rgba(16, 185, 129, 0.55)' : 'rgba(255,255,255,0.12)',
                      },
                      '&:active': {
                        transform: 'none',
                      },
                    }}
                  >
                    <Box
                      component="span"
                      sx={{
                        justifySelf: 'start',
                        fontSize: '1.1rem',
                        lineHeight: 1,
                        width: 28,
                        textAlign: 'left',
                      }}
                    >
                      {item.icon}
                    </Box>
                    <Box
                      component="span"
                      sx={{
                        textAlign: 'center',
                        width: '100%',
                        lineHeight: 1.2,
                      }}
                    >
                      {item.label}
                    </Box>
                    <Box aria-hidden component="span" sx={{ width: 28 }} />
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
                transition: 'background-color 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease',
                WebkitUserSelect: 'none',
                userSelect: 'none',
                touchAction: 'manipulation',
                '&:hover': {
                  color: '#fafafa',
                  backgroundColor: 'rgba(239, 68, 68, 0.15)',
                  borderColor: 'rgba(239, 68, 68, 0.3)',
                  boxShadow: '0 4px 12px rgba(239, 68, 68, 0.2)',
                },
                '&:active': {
                  transform: 'none',
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
                transition: 'background-color 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease',
                WebkitUserSelect: 'none',
                userSelect: 'none',
                touchAction: 'manipulation',
                '&:hover': {
                  color: '#fafafa',
                  backgroundColor: 'rgba(239, 68, 68, 0.15)',
                  borderColor: 'rgba(239, 68, 68, 0.3)',
                  boxShadow: '0 4px 12px rgba(239, 68, 68, 0.2)',
                },
                '&:active': {
                  transform: 'none',
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
      <Box
        className="app-shell"
        sx={{ 
        display: 'flex', 
        minHeight: '100%',
        backgroundColor: '#0e1117',
        position: 'relative',
        // Desktop + non-reels mobile: shell grows so the document can scroll
        ...(isMobileNewsReels
          ? {
              overflow: 'hidden',
              height: '100dvh',
              maxHeight: '100dvh',
              minHeight: '100dvh',
            }
          : {
              overflow: 'visible',
              height: 'auto',
              maxHeight: 'none',
              minHeight: '100dvh',
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
                overflowY: 'auto',
                overflowX: 'hidden',
                position: 'fixed',
                top: 0,
                left: 0,
                height: '100dvh',
                maxHeight: '100dvh',
                WebkitOverflowScrolling: 'touch',
                overscrollBehavior: 'contain',
                // layout/style only — paint containment clips Select menus
                contain: 'layout style',
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
            {/* Backdrop — below nav so hamburger/close stays tappable */}
            {mobileOpen && (
              <Box
                onClick={handleDrawerToggle}
                sx={{
                  position: 'fixed',
                  top: 'var(--app-mobile-nav-offset)',
                  left: 0,
                  right: 0,
                  bottom: 0,
                  backgroundColor: 'rgba(0, 0, 0, 0.7)',
                  zIndex: 2099,
                  animation: 'fadeIn 0.25s ease-out',
                  '@keyframes fadeIn': {
                    from: { opacity: 0 },
                    to: { opacity: 1 },
                  },
                }}
              />
            )}
            
            {/* Mobile Control Panel — single scroll owner; no nested scroll / will-change thrash */}
            <Box
              className="mobile-control-panel"
              sx={{
                position: 'fixed',
                top: 'var(--app-mobile-nav-offset)',
                left: 0,
                width: '280px',
                height: 'calc(100dvh - var(--app-mobile-nav-offset))',
                maxHeight: 'calc(100dvh - var(--app-mobile-nav-offset))',
                background: 'linear-gradient(180deg, #262730 0%, #1f2937 100%)',
                borderRight: '1px solid rgba(16, 185, 129, 0.2)',
                boxShadow: '4px 0 24px rgba(0, 0, 0, 0.5), inset -1px 0 0 rgba(16, 185, 129, 0.1)',
                zIndex: 2100,
                transform: mobileOpen ? 'translate3d(0,0,0)' : 'translate3d(-100%,0,0)',
                transition: 'transform 0.28s cubic-bezier(0.4, 0, 0.2, 1)',
                overflowY: 'auto',
                overflowX: 'hidden',
                WebkitOverflowScrolling: 'touch',
                overscrollBehavior: 'contain',
                // manipulation > pan-y: allows taps on Select without scroll hijack
                touchAction: 'manipulation',
                display: 'flex',
                flexDirection: 'column',
                pointerEvents: mobileOpen ? 'auto' : 'none',
                // Solid fill — blur on a sliding panel causes iOS tap/scroll flicker
                WebkitBackdropFilter: 'none',
                backdropFilter: 'none',
                '@supports not (height: 100dvh)': {
                  height: 'calc(100svh - var(--app-mobile-nav-offset))',
                  maxHeight: 'calc(100svh - var(--app-mobile-nav-offset))',
                },
              }}
            >
              {drawerContent}
            </Box>
          </>
        )}

        {/* Navigation Tabs - Fixed header on all screen sizes */}
        <Box
          className="app-top-nav"
          sx={{ 
            // Full viewport width so the scrollbar sits under the header (no right gap)
            position: 'fixed',
            top: 0,
            left: { xs: 0, md: '280px' },
            right: 'auto',
            width: { xs: '100vw', md: 'calc(100vw - 280px)' },
            maxWidth: { xs: '100vw', md: 'calc(100vw - 280px)' },
            display: 'flex',
            gap: { xs: 0, md: 2 },
            justifyContent: { xs: 'center', md: 'center' },
            alignItems: 'center',
            paddingLeft: { xs: '12px', sm: '16px', md: '32px' },
            paddingRight: { xs: '12px', sm: '16px', md: '32px' },
            paddingTop: { xs: 'calc(env(safe-area-inset-top, 0px) + 14px)', md: '12px' },
            paddingBottom: { xs: '14px', md: '12px' },
            backgroundColor: '#0e1117',
            backdropFilter: { xs: 'none', md: 'blur(10px)' },
            WebkitBackdropFilter: { xs: 'none', md: 'blur(10px)' },
            borderBottom: '1px solid rgba(16, 185, 129, 0.2)',
            boxShadow: '0 2px 8px rgba(0, 0, 0, 0.3)',
            zIndex: isMobile && mobileOpen ? 2200 : 2000,
            minHeight: { xs: 'calc(68px + env(safe-area-inset-top, 0px))', md: '56px' },
            boxSizing: 'border-box',
            margin: 0,
            overflow: 'hidden',
            WebkitFontSmoothing: 'antialiased',
            MozOsxFontSmoothing: 'grayscale',
          }}>
            {isMobile ? (
              <Box
                sx={{
                  display: 'grid',
                  gridTemplateColumns: '40px 1fr 40px',
                  alignItems: 'center',
                  width: '100%',
                  height: 40,
                  minHeight: 40,
                }}
              >
                <IconButton
                  color="inherit"
                  aria-label={mobileOpen ? 'close menu' : 'open menu'}
                  onClick={handleDrawerToggle}
                  sx={{
                    justifySelf: 'start',
                    width: 40,
                    height: 40,
                    minWidth: 40,
                    minHeight: 40,
                    p: 0,
                    m: 0,
                    backgroundColor: '#262730',
                    backdropFilter: 'none',
                    WebkitBackdropFilter: 'none',
                    color: '#fafafa',
                    borderRadius: '10px',
                    boxShadow: '0 4px 16px rgba(0,0,0,0.35), 0 0 0 1px rgba(255,255,255,0.08)',
                    transition: 'background-color 0.2s ease',
                    WebkitTapHighlightColor: 'transparent',
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    '& .MuiSvgIcon-root': {
                      fontSize: 22,
                      filter: 'none',
                      opacity: 1,
                    },
                    '&:hover': {
                      backgroundColor: 'rgba(16, 185, 129, 0.18)',
                    },
                  }}
                >
                  {mobileOpen ? <CloseIcon /> : <MenuIcon />}
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
                      // drop-shadow filters can bleed blur into nearby text on mobile WebKit
                      filter: 'none',
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
                      // Solid color on mobile — gradient + background-clip text looks soft/blurry
                      color: '#f8fafc',
                      background: 'none',
                      WebkitBackgroundClip: 'unset',
                      WebkitTextFillColor: 'unset',
                      backgroundClip: 'unset',
                    }}
                  >
                    {APP_DISPLAY_NAME}
                  </Typography>
                </Box>

                <Box aria-hidden sx={{ width: 40, height: 40 }} />
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
              : {
                  xs: 'var(--app-mobile-nav-offset)',
                  sm: 'var(--app-tablet-nav-offset, 64px)',
                  md: 'var(--app-desktop-nav-offset, 56px)',
                },
            backgroundColor: 'transparent',
            color: '#fafafa',
            width: '100%',
            boxSizing: 'border-box',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'stretch',
            paddingLeft: 0,
            paddingRight: 0,
            position: 'relative',
            zIndex: 1,
            ...(isMobileNewsReels ? {
              overflow: 'hidden',
              height: '100dvh',
              maxHeight: '100dvh',
              contain: 'layout style',
              '@supports not (height: 100dvh)': {
                height: '100svh',
                maxHeight: '100svh',
              },
            } : ((activeView === 'news' || activeView === 'standings' || activeView === 'teams' || activeView === 'lineups' || activeView === 'predictions' || activeView === 'history' || activeView === 'profile') ? {
              // Grow with content only — forced minHeight was creating empty scroll
              overflow: 'visible',
              height: 'auto',
              maxHeight: 'none',
              minHeight: 0,
              contain: 'none',
            } : {
              overflowY: 'auto',
              overflowX: 'hidden',
              height: '100vh',
              maxHeight: '100vh',
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
            paddingTop: isMobileNewsReels
              ? 0
              : CONTENT_TAB_VIEWS.has(activeView)
                ? 0
                : 'var(--app-content-top-gap, 20px)',
            overflow: 'visible',
            boxSizing: 'border-box',
            alignItems: 'stretch',
          }}>
            {CONTENT_TAB_VIEWS.has(activeView) ? (
              <Box
                sx={
                  activeView === 'news'
                    ? {
                        ...VIEW_CONTENT_WRAPPER_SX,
                        ...(isMobileNewsReels
                          ? { p: 0, px: 0, pt: 0, pb: 0 }
                          : null),
                        minHeight: isMobileNewsReels ? '100%' : VIEW_CONTENT_WRAPPER_SX.minHeight,
                        height: isMobileNewsReels ? '100%' : 'auto',
                        overflow: isMobileNewsReels ? 'hidden' : VIEW_CONTENT_WRAPPER_SX.overflowY,
                      }
                    : activeView === 'lineups'
                    ? { ...VIEW_CONTENT_WRAPPER_SX, bgcolor: 'transparent' }
                    : VIEW_CONTENT_WRAPPER_SX
                }
              >
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
                mt: { xs: 0, sm: 0 },
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
                  minHeight: 220,
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  py: 4,
                  mb: 4,
                }}>
                  <RugbyBallLoader size={100} color="#10b981" compact label="Loading matches..." />
                </Box>
              ) : oddsInputMatches.length > 0 ? (
                <ManualOddsInput
                  matches={oddsInputMatches}
                  selectedLeague={selectedLeague}
                  manualOdds={manualOdds}
                  onOddsChange={handleManualOddsChange}
                  showHeader={false}
                />
              ) : upcomingWindowMatches.length === 0 ? (
                <Box sx={{ ...predictionsWidgetSx, mb: 4, p: 2, backgroundColor: '#1f2937', borderRadius: 2 }}>
                  <Typography variant="h6" sx={{ mb: 1, color: '#fafafa' }}>
                    📅 Upcoming Matches
                  </Typography>
                  <Typography color="text.secondary">
                    {selectedLeague ? 'No upcoming matches found for this league' : 'Select a league to see upcoming matches'}
                  </Typography>
                </Box>
              ) : null}

                <Box sx={{ ...predictionsWidgetSx, my: 4, display: 'flex', flexDirection: 'column', alignItems: 'stretch', gap: 2 }}>
                  {generating && (
                    <Box sx={{
                      width: '100%',
                      minHeight: 220,
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
                    disabled={generating || oddsInputMatches.length === 0}
                  >
                    🎯 Generate Expert Predictions
                  </button>
                </Box>

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
