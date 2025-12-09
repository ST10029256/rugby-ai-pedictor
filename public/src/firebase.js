// Firebase configuration
import { initializeApp } from 'firebase/app';
import { getFirestore } from 'firebase/firestore';
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

export const predictMatch = (data) => {
  const callable = httpsCallable(functionsRegion, 'predict_match');
  return callable(data);
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

export default app;

