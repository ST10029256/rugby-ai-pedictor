// Firebase configuration
import { initializeApp } from 'firebase/app';
import { getFirestore, doc, onSnapshot } from 'firebase/firestore';
import { getStorage } from 'firebase/storage';
import { getFunctions, httpsCallable } from 'firebase/functions';
import { getDeviceAuthPayload } from './utils/deviceId';
import {
  expandLeagueIds,
  LEAGUE_ID_MAPPING,
  getLeagueConfig,
  leagueDisplayName,
} from './utils/leagues';

// Firebase config for rugby-ai-61fd0
// For callable functions, we mainly need projectId
// Other fields can be minimal for serverless functions
const firebaseConfig = {
  apiKey: "AIzaSyAMZ0md0_DADjaI7Z4QujftjMp6e2P6gaw",
  authDomain: "rugby-ai-61fd0.firebaseapp.com",
  projectId: "rugby-ai-61fd0",
  storageBucket: "rugby-ai-61fd0.firebasestorage.app",
  messagingSenderId: "645506509698",
  appId: "1:645506509698:web:4882017949752488443d9b",
  measurementId: "G-Q26B5ZNKRQ"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);

// Initialize services
export const db = getFirestore(app);
export const storage = getStorage(app);

// Cloud Functions - specify region for 2nd Gen functions
const functionsRegion = getFunctions(app, 'us-central1');

export const predictMatch = async (data) => {
  // Use explicit HTTP endpoint with CORS headers for local dev reliability.
  const url = 'https://us-central1-rugby-ai-61fd0.cloudfunctions.net/predict_match_http';

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data || {}),
  });

  const json = await response.json().catch(() => ({}));
  if (!response.ok) {
    const backendMessage = json?.error || `HTTP error! status: ${response.status}`;
    throw new Error(backendMessage);
  }

  // Normalize shape to match httpsCallable response contract.
  return { data: json };
};

export const getUpcomingMatches = async (data) => {
  const callable = httpsCallable(functionsRegion, 'get_upcoming_matches');
  const ids = expandLeagueIds(data?.league_id);
  if (ids.length <= 1) return callable(data);
  const results = await Promise.all(ids.map((id) => callable({ ...data, league_id: id })));
  const matches = [];
  for (let i = 0; i < results.length; i += 1) {
    for (const match of results[i]?.data?.matches || []) {
      matches.push({ ...match, league_id: match.league_id ?? ids[i] });
    }
  }
  return { data: { matches } };
};

// Predict an entire round of fixtures in a single request. The backend serves
// cached / snapshot predictions where possible and computes only the misses,
// replacing N per-match calls with one.
export const predictMatchesBatch = async (data) => {
  const url = 'https://us-central1-rugby-ai-61fd0.cloudfunctions.net/predict_matches_batch_http';

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data || {}),
  });

  const json = await response.json().catch(() => ({}));
  if (!response.ok) {
    const backendMessage = json?.error || `HTTP error! status: ${response.status}`;
    throw new Error(backendMessage);
  }

  return { data: json };
};

const fetchLiveMatchesOnce = async (data) => {
  const url = 'https://us-central1-rugby-ai-61fd0.cloudfunctions.net/get_live_matches_http';
  const response = await fetch(url, {
    method: 'POST',
    cache: 'no-store',
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': 'no-cache',
    },
    body: JSON.stringify({ ...(data || {}), _ts: Date.now() }),
  });
  const json = await response.json().catch(() => ({}));
  return { data: json };
};

export const getLiveMatches = async (data) => {
  const ids = expandLeagueIds(data?.league_id);
  if (ids.length <= 1) return fetchLiveMatchesOnce(data);
  const results = await Promise.all(ids.map((id) => fetchLiveMatchesOnce({ ...data, league_id: id })));
  const matches = [];
  let signature = '';
  let detection = false;
  for (let i = 0; i < results.length; i += 1) {
    const payload = results[i]?.data || {};
    detection = detection || payload.detection === true;
    signature = `${signature}|${payload.signature || ''}`;
    for (const match of payload.matches || []) {
      matches.push({ ...match, league_id: match.league_id ?? ids[i] });
    }
  }
  return { data: { matches, signature, detection } };
};

export const getLeagues = () => {
  const callable = httpsCallable(functionsRegion, 'get_leagues');
  return callable({});
};

export const getLeagueMetrics = (data) => {
  const callable = httpsCallable(functionsRegion, 'get_league_metrics');
  return callable(data);
};

export const verifyLicenseKey = async (data) => {
  const payload = { ...data, ...(await getDeviceAuthPayload()) };
  const url = 'https://us-central1-rugby-ai-61fd0.cloudfunctions.net/verify_license_key_http';
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload || {}),
    });
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    const json = await response.json().catch(() => ({}));
    return { data: json };
  } catch (httpError) {
    console.warn('HTTP verify failed, trying callable:', httpError);
    try {
      const callable = httpsCallable(functionsRegion, 'verify_license_key');
      return await callable(payload);
    } catch (error) {
      throw httpError;
    }
  }
};

export const requestEmailLoginCode = async (data) => {
  const payload = { email: data?.email || '' };
  const url = 'https://us-central1-rugby-ai-61fd0.cloudfunctions.net/request_email_login_code_http';
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const json = await response.json().catch(() => ({}));
    if (json && (json.status || typeof json.success === 'boolean')) {
      return { data: json };
    }
    if (!response.ok) {
      throw new Error(json?.error || `HTTP error! status: ${response.status}`);
    }
    return { data: json };
  } catch (httpError) {
    try {
      const callable = httpsCallable(functionsRegion, 'request_email_login_code');
      return await callable(payload);
    } catch (error) {
      throw httpError;
    }
  }
};

export const verifyEmailLoginCode = async (data) => {
  const payload = { ...data, ...(await getDeviceAuthPayload()) };
  const url = 'https://us-central1-rugby-ai-61fd0.cloudfunctions.net/verify_email_login_code_http';
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload || {}),
    });
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    const json = await response.json().catch(() => ({}));
    return { data: json };
  } catch (httpError) {
    console.warn('HTTP email verify failed, trying callable:', httpError);
    const callable = httpsCallable(functionsRegion, 'verify_email_login_code');
    return callable(payload);
  }
};

const fetchNewsFeedOnce = async (data) => {
  // Use explicit HTTP endpoint with CORS headers to avoid browser CORS issues
  const url = 'https://us-central1-rugby-ai-61fd0.cloudfunctions.net/get_news_feed_http';

  console.log('🌐 [firebase.js] getNewsFeed called with data:', data);
  console.log('🌐 [firebase.js] Request URL:', url);
  console.log('🌐 [firebase.js] Request body:', JSON.stringify(data || {}, null, 2));
  console.log('🌐 [firebase.js] League ID in request:', data?.league_id, typeof data?.league_id);

  try {
    console.log('🌐 [firebase.js] Making fetch request...');
    const requestStartedAt = performance.now();
    
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data || {}),
    });

    const fetchDurationMs = performance.now() - requestStartedAt;
    console.log(`⏱️ [firebase.js] Fetch duration: ${fetchDurationMs.toFixed(1)} ms`);
    console.log('🌐 [firebase.js] Response status:', response.status);
    console.log('🌐 [firebase.js] Response ok:', response.ok);
    console.log('🌐 [firebase.js] Response statusText:', response.statusText);

    if (!response.ok) {
      const errorText = await response.text().catch(() => 'Could not read error response');
      console.error('🌐 [firebase.js] HTTP error response:', errorText);
      console.error('🌐 [firebase.js] Error status:', response.status);
      throw new Error(`HTTP error! status: ${response.status}, body: ${errorText}`);
    }

    console.log('🌐 [firebase.js] Parsing JSON response...');
    const json = await response.json().catch(async (parseError) => {
      console.error('🌐 [firebase.js] JSON parse error:', parseError);
      try {
        const responseText = await response.text();
        console.error('🌐 [firebase.js] Response text (first 500 chars):', responseText.substring(0, 500));
      } catch (textError) {
        console.error('🌐 [firebase.js] Could not read response text:', textError);
      }
      return {};
    });
    
    console.log('🌐 [firebase.js] Response JSON:', json);
    console.log('🌐 [firebase.js] Response news count:', json?.news?.length || 0);
    console.log('🌐 [firebase.js] Response success:', json?.success);
    console.log('🌐 [firebase.js] Response count:', json?.count);
    console.log('🌐 [firebase.js] Response debug:', json?.debug);
    console.log('🌐 [firebase.js] Response error:', json?.error);
    
    if (json?.news && json.news.length > 0) {
      console.log('🌐 [firebase.js] First news item:', json.news[0]);
      console.log('🌐 [firebase.js] First news item league_id:', json.news[0]?.league_id);
    }
    
    return { data: json };
  } catch (error) {
    console.error('🌐 [firebase.js] Error fetching news feed via HTTP:', error);
    console.error('🌐 [firebase.js] Error name:', error.name);
    console.error('🌐 [firebase.js] Error message:', error.message);
    console.error('🌐 [firebase.js] Error stack:', error.stack);
    throw error; // Re-throw the error for the calling component to handle
  }
};

export const getNewsFeed = async (data) => {
  const ids = expandLeagueIds(data?.league_id);
  if (ids.length <= 1) return fetchNewsFeedOnce(data);
  const results = await Promise.all(ids.map((id) => fetchNewsFeedOnce({ ...data, league_id: id })));
  const news = [];
  let success = false;
  for (let i = 0; i < results.length; i += 1) {
    const result = results[i];
    if (result?.data?.success) success = true;
    for (const item of result?.data?.news || []) {
      news.push({ ...item, league_id: item.league_id ?? ids[i] });
    }
  }
  return { data: { ...(results[0]?.data || {}), success, news, count: news.length } };
};

export const getTrendingTopics = async (data) => {
  // Use explicit HTTP endpoint with CORS headers to avoid browser CORS issues
  const url = 'https://us-central1-rugby-ai-61fd0.cloudfunctions.net/get_trending_topics_http';

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data || {}),
  });

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  // Normalize shape to match httpsCallable: { data: ... }
  const json = await response.json().catch(() => ({}));
  return { data: json };
};

const fetchLeagueStandingsOnce = async ({
  highlightlyLeagueId,
  sportsdbLeagueId,
  leagueName,
  season,
  forceRefresh = false,
}) => {
  // Use explicit HTTP endpoint with CORS headers to avoid browser CORS issues
  const url = 'https://us-central1-rugby-ai-61fd0.cloudfunctions.net/get_league_standings_http';

  let licenseKey = null;
  try {
    const raw = localStorage.getItem('rugby_ai_auth');
    if (raw) {
      const auth = JSON.parse(raw);
      licenseKey = auth?.licenseKey || null;
    }
  } catch (e) {
    // ignore
  }

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      league_id: highlightlyLeagueId,
      sportsdb_league_id: sportsdbLeagueId,
      league_name: leagueName,
      season,
      license_key: licenseKey,
      force_refresh: Boolean(forceRefresh),
      // Server-side cache TTL hint (seconds). The function clamps this.
      cache_ttl_seconds: 21600, // 6 hours
    }),
  });

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  // Normalize shape to match httpsCallable: { data: ... }
  const json = await response.json().catch(() => ({}));
  return json;
};

export const getLeagueStandings = async (args) => {
  const ids = expandLeagueIds(args?.sportsdbLeagueId);
  if (ids.length <= 1) return fetchLeagueStandingsOnce(args);
  const parts = await Promise.all(
    ids.map((id) =>
      fetchLeagueStandingsOnce({
        ...args,
        sportsdbLeagueId: id,
        highlightlyLeagueId: LEAGUE_ID_MAPPING[id] || args?.highlightlyLeagueId,
        leagueName: getLeagueConfig(id)?.matchLabel || getLeagueConfig(id)?.name || args?.leagueName,
      })
    )
  );
  const groups = [];
  let first = null;
  for (let i = 0; i < parts.length; i += 1) {
    const part = parts[i];
    if (!part?.success || !part.standings) continue;
    if (!first) first = part;
    const label = getLeagueConfig(ids[i])?.matchLabel || getLeagueConfig(ids[i])?.name;
    for (const group of part.standings.groups || []) {
      const groupName = group?.name || group?.group_name;
      groups.push({
        ...group,
        name: groupName && label && groupName !== label ? `${label} · ${groupName}` : (label || groupName),
      });
    }
  }
  if (!first) return parts.find(Boolean) || { success: false };
  return {
    ...first,
    standings: {
      ...first.standings,
      groups,
      league: {
        ...(first.standings.league || {}),
        name: leagueDisplayName(args.sportsdbLeagueId),
      },
    },
  };
};

const fetchLeagueLineupMatchesOnce = async ({
  sportsdbLeagueId,
  season,
  matchScope = 'historic',
} = {}) => {
  const url = 'https://us-central1-rugby-ai-61fd0.cloudfunctions.net/get_match_lineups_http';
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      sportsdb_league_id: sportsdbLeagueId,
      list_matches: true,
      season,
      match_scope: matchScope,
    }),
  });

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  return response.json().catch(() => ({}));
};

export const getLeagueLineupMatches = async (args = {}) => {
  const ids = expandLeagueIds(args.sportsdbLeagueId);
  if (ids.length <= 1) return fetchLeagueLineupMatchesOnce(args);
  const parts = await Promise.all(ids.map((id) => fetchLeagueLineupMatchesOnce({ ...args, sportsdbLeagueId: id })));
  const matches = [];
  for (const part of parts) {
    matches.push(...(part?.matches || part?.data?.matches || []));
  }
  return { ...(parts[0] || {}), matches };
};

export const getMatchLineups = async ({
  sportsdbLeagueId,
  sportEventId,
} = {}) => {
  const url = 'https://us-central1-rugby-ai-61fd0.cloudfunctions.net/get_match_lineups_http';
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      sportsdb_league_id: sportsdbLeagueId,
      sport_event_id: sportEventId,
    }),
  });

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  return response.json().catch(() => ({}));
};

/**
 * Subscribe to Firestore standings cache for real-time updates.
 * @param {number} sportsdbLeagueId - Local/SportsDB league ID
 * @param {number[]} seasons - Seasons to listen to (e.g. [2025, 2024])
 * @param {(standings: object, season: number, meta: object) => void} onUpdate - Callback when cache updates
 * @returns {() => void} Unsubscribe function
 */
export const subscribeToStandingsCache = (sportsdbLeagueId, seasons, onUpdate) => {
  const unsubs = [];
  for (const year of seasons) {
    const docId = `ldb::${Number(sportsdbLeagueId)}::season::${Number(year)}`;
    const ref = doc(db, 'standings_cache_v1', docId);
    const unsub = onSnapshot(ref, (snap) => {
      if (!snap.exists()) return;
      const data = snap.data();
      const standings = data?.standings;
      if (standings && typeof standings === 'object') {
        onUpdate(standings, year, {
          source: data?.source || null,
        });
      }
    }, (err) => {
      console.warn('Standings cache listener error:', err);
    });
    unsubs.push(unsub);
  }
  return () => unsubs.forEach((u) => u());
};

export const parseSocialEmbed = (data) => {
  const callable = httpsCallable(functionsRegion, 'parse_social_embed');
  return callable(data);
};

const createHistoryRequestId = (prefix) => {
  const suffix = Math.random().toString(36).slice(2, 10);
  return `${prefix}-${Date.now()}-${suffix}`;
};

const previewResponseBody = (text, limit = 1200) => {
  if (!text) return '';
  return text.length > limit ? `${text.slice(0, limit)}...[truncated]` : text;
};

const headersToObject = (headers) => {
  try {
    return Object.fromEntries(headers.entries());
  } catch (error) {
    return { error: `Could not serialize headers: ${error?.message || error}` };
  }
};

const parseJsonSafely = (text) => {
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch (error) {
    return null;
  }
};

const postHistoryEndpoint = async ({ url, data, label, requestPrefix }) => {
  const requestId = data?.client_request_id || createHistoryRequestId(requestPrefix);
  const payload = { ...(data || {}), client_request_id: requestId };
  const startedAt = performance.now();

  console.log(`[${label}] HTTP request start`, {
    requestId,
    url,
    payload,
  });

  let response;
  try {
    response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Client-Request-Id': requestId,
      },
      body: JSON.stringify(payload),
    });
  } catch (error) {
    console.error(`[${label}] Network failure`, {
      requestId,
      url,
      durationMs: Number((performance.now() - startedAt).toFixed(1)),
      message: error?.message || String(error),
      stack: error?.stack || null,
      payload,
    });
    throw error;
  }

  const durationMs = Number((performance.now() - startedAt).toFixed(1));
  const responseHeaders = headersToObject(response.headers);
  const rawText = await response.text().catch(() => '');
  const parsedJson = parseJsonSafely(rawText);
  const bodyPreview = previewResponseBody(rawText);

  console.log(`[${label}] HTTP response received`, {
    requestId,
    url,
    status: response.status,
    statusText: response.statusText,
    ok: response.ok,
    redirected: response.redirected,
    type: response.type,
    durationMs,
    headers: responseHeaders,
    bodyLength: rawText.length,
    bodyPreview,
  });

  if (!response.ok) {
    const error = new Error(`HTTP error ${response.status} ${response.statusText} [requestId=${requestId}]`);
    error.status = response.status;
    error.statusText = response.statusText;
    error.requestId = requestId;
    error.responseBody = rawText;
    error.responseJson = parsedJson;
    error.responseHeaders = responseHeaders;
    console.error(`[${label}] HTTP failure`, {
      requestId,
      status: response.status,
      statusText: response.statusText,
      durationMs,
      responseHeaders,
      bodyPreview,
    });
    throw error;
  }

  return {
    data: parsedJson ?? {},
    requestId,
    responseHeaders,
    status: response.status,
  };
};

export const getHistoricalPredictions = async (data) => {
  const url = 'https://us-central1-rugby-ai-61fd0.cloudfunctions.net/get_historical_predictions_http';
  const ids = expandLeagueIds(data?.league_id);
  if (ids.length <= 1) {
    return postHistoryEndpoint({
      url,
      data,
      label: 'HistoryReplay',
      requestPrefix: 'hist-replay',
    });
  }
  const allMatches = [];
  let matchesByYearWeek = {};
  let firstPage = null;
  for (const id of ids) {
    let offset = 0;
    for (let pageNum = 0; pageNum < 20; pageNum += 1) {
      const page = await postHistoryEndpoint({
        url,
        data: { ...data, league_id: id, offset, limit: data?.limit || 250 },
        label: 'HistoryReplay',
        requestPrefix: 'hist-replay',
      });
      if (!firstPage) firstPage = page;
      const pageData = page?.data || {};
      allMatches.push(...(pageData.all_matches || []));
      matchesByYearWeek = { ...matchesByYearWeek, ...(pageData.matches_by_year_week || {}) };
      if (!pageData.pagination?.has_more) break;
      const nextOffset = Number(pageData.pagination?.next_offset);
      if (!Number.isFinite(nextOffset) || nextOffset <= offset) break;
      offset = nextOffset;
    }
  }
  return {
    ...(firstPage || {}),
    data: {
      ...(firstPage?.data || {}),
      all_matches: allMatches,
      matches_by_year_week: matchesByYearWeek,
      pagination: { has_more: false, returned_rows: allMatches.length, total_rows: allMatches.length },
    },
  };
};

export const getHistoricalBacktest = async (data) => {
  const url = 'https://us-central1-rugby-ai-61fd0.cloudfunctions.net/get_historical_backtest_http';
  const ids = expandLeagueIds(data?.league_id);
  if (ids.length <= 1) {
    return postHistoryEndpoint({
      url,
      data,
      label: 'HistoryBacktest',
      requestPrefix: 'hist-backtest',
    });
  }
  const pages = await Promise.all(
    ids.map((id) =>
      postHistoryEndpoint({
        url,
        data: { ...data, league_id: id },
        label: 'HistoryBacktest',
        requestPrefix: 'hist-backtest',
      })
    )
  );
  const allMatches = [];
  let matchesByYearWeek = {};
  for (const page of pages) {
    const pageData = page?.data || {};
    allMatches.push(...(pageData.all_matches || []));
    matchesByYearWeek = {
      ...matchesByYearWeek,
      ...(pageData.matches_by_year_week || {}),
    };
  }
  return {
    ...(pages[0] || {}),
    data: {
      ...(pages[0]?.data || {}),
      all_matches: allMatches,
      matches_by_year_week: matchesByYearWeek,
      statistics: pages[0]?.data?.statistics,
    },
  };
};

export const scanFirestoreMatches = async (data) => {
  const url = 'https://us-central1-rugby-ai-61fd0.cloudfunctions.net/scan_firestore_matches_http';

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data || {}),
  });

  const json = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(json?.error || `HTTP error! status: ${response.status}`);
  }

  return { data: json };
};

export default app;

