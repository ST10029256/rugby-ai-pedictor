# React Frontend Setup Guide

## Quick Start

Your React frontend is already set up! You just need to:

### 1. Install Dependencies

```powershell
cd public
npm install
```

### 2. Get Firebase Web App Config (Optional but Recommended)

For full Firebase features, register a web app:

1. Go to: https://console.firebase.google.com/project/rugby-ai-61fd0/settings/general
2. Scroll down to "Your apps"
3. Click the Web icon (`</>`) to add a web app
4. Register app (name it "Rugby AI Web")
5. Copy the config values

### 3. Create Environment File (Optional)

Create `public/.env` with your Firebase config:

```env
REACT_APP_FIREBASE_API_KEY=your_api_key
REACT_APP_FIREBASE_AUTH_DOMAIN=rugby-ai-61fd0.firebaseapp.com
REACT_APP_FIREBASE_PROJECT_ID=rugby-ai-61fd0
REACT_APP_FIREBASE_STORAGE_BUCKET=rugby-ai-61fd0.firebasestorage.app
REACT_APP_FIREBASE_MESSAGING_SENDER_ID=your_sender_id
REACT_APP_FIREBASE_APP_ID=your_app_id
```

**Note:** The app will work with just the project ID (already set as default).

### 4. Run the App

```powershell
cd public
npm start
```

The app will open at `http://localhost:3000`

## What's Already Set Up

✅ **Firebase Functions Integration**
- `predictMatch` - Get match predictions
- `getUpcomingMatches` - Get upcoming matches
- `getLiveMatches` - Get live matches
- `getLeagues` - Get available leagues

✅ **React Components**
- `MatchPredictor` - Input form for predictions
- `UpcomingMatches` - Display upcoming matches
- `LiveMatches` - Display live matches
- `LeagueSelector` - Select league

✅ **Material-UI Theme**
- Dark theme with green/blue accents
- Responsive design

## Testing the Functions

The functions are already deployed and ready to use. The React app will automatically call them when you:

1. Select a league
2. Enter team names and date
3. Click "Get Prediction"

## Deploy to Firebase Hosting

Once everything works locally:

```powershell
cd public
npm run build
cd ..
firebase deploy --only hosting
```

Your app will be live at: `https://rugby-ai-61fd0.web.app`

## Troubleshooting

### Functions Not Working?
- Check browser console for errors
- Verify functions are deployed: https://console.firebase.google.com/project/rugby-ai-61fd0/functions
- Check function logs for errors

### CORS Errors?
- Callable functions handle CORS automatically
- If you see CORS errors, check Firebase project settings

### Authentication Errors?
- Callable functions work without authentication by default
- If you see auth errors, check Firestore security rules

