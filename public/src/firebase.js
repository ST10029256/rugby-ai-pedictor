// Firebase configuration
import { initializeApp } from 'firebase/app';
import { getFirestore, doc, onSnapshot } from 'firebase/firestore';
import { getStorage } from 'firebase/storage';
import { getFunctions, httpsCallable } from 'firebase/functions';

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

export const getUpcomingMatches = (data) => {
  const callable = httpsCallable(functionsRegion, 'get_upcoming_matches');
  return callable(data);
};

export const getLiveMatches = async (data) => {
  // Use explicit HTTP endpoint with CORS headers to avoid browser CORS issues
  const url = 'https://us-central1-rugby-ai-61fd0.cloudfunctions.net/get_live_matches_http';

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data || {}),
  });

  // Normalize shape to match httpsCallable: { data: ... }
  const json = await response.json().catch(() => ({}));
  return { data: json };
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
  // Try callable function first (handles CORS automatically)
  try {
    const callable = httpsCallable(functionsRegion, 'verify_license_key');
    return await callable(data);
  } catch (error) {
    // If callable fails, try HTTP endpoint as fallback
    console.warn('Callable function failed, trying HTTP endpoint:', error);
    try {
      const url = 'https://us-central1-rugby-ai-61fd0.cloudfunctions.net/verify_license_key_http';
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

      const json = await response.json().catch(() => ({}));
      return { data: json };
    } catch (httpError) {
      // If both fail, throw the original callable error
      throw error;
    }
  }
};

export const getNewsFeed = async (data) => {
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

export const getLeagueStandings = async ({ highlightlyLeagueId, sportsdbLeagueId, leagueName }) => {
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
      license_key: licenseKey,
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

/**
 * Subscribe to Firestore standings cache for real-time updates.
 * When the API updates the server-side cache, this listener fires and the app can update.
 * @param {number} highlightlyLeagueId - Highlightly league ID
 * @param {number[]} seasons - Seasons to listen to (e.g. [2025, 2024])
 * @param {(standings: object, season: number) => void} onUpdate - Callback when cache updates
 * @returns {() => void} Unsubscribe function
 */
export const subscribeToStandingsCache = (highlightlyLeagueId, seasons, onUpdate) => {
  const unsubs = [];
  for (const year of seasons) {
    const docId = `hl::${Number(highlightlyLeagueId)}::season::${Number(year)}`;
    const ref = doc(db, 'standings_cache_v1', docId);
    const unsub = onSnapshot(ref, (snap) => {
      if (!snap.exists()) return;
      const data = snap.data();
      const standings = data?.standings;
      if (standings && typeof standings === 'object') {
        onUpdate(standings, year);
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

export const getHistoricalPredictions = async (data) => {
  // Use explicit HTTP endpoint with CORS headers to avoid browser CORS issues
  const url = 'https://us-central1-rugby-ai-61fd0.cloudfunctions.net/get_historical_predictions_http';

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

export const getHistoricalBacktest = async (data) => {
  // True walk-forward backtest (unseen) - server trains only on past games per week
  const url = 'https://us-central1-rugby-ai-61fd0.cloudfunctions.net/get_historical_backtest_http';

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

  const json = await response.json().catch(() => ({}));
  return { data: json };
};

export default app;

