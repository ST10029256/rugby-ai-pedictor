# Quick Start: React Frontend

## ✅ Everything is Ready!

Your React frontend is already configured to work with your Firebase functions.

## 🚀 Run the App (3 Steps)

### Step 1: Install Dependencies
```powershell
cd public
npm install
```

### Step 2: Start Development Server
```powershell
npm start
```

The app will open at `http://localhost:3000`

### Step 3: Test It!

1. **Select a League** from the dropdown
2. **Enter Team Names** (e.g., "Leinster" and "Munster")
3. **Select a Date**
4. **Click "Get Prediction"**

The app will call your deployed Cloud Functions and show the prediction!

## 📋 What You'll See

- **League Selector** - Choose from 8 leagues
- **Match Predictor** - Enter teams and get AI predictions
- **Upcoming Matches** - See upcoming fixtures
- **Live Matches** - See live/ongoing matches

## 🔧 Configuration

The app uses default Firebase config with your project ID (`rugby-ai-61fd0`). 

**Optional:** To get full Firebase features, register a web app:
1. Go to: https://console.firebase.google.com/project/rugby-ai-61fd0/settings/general
2. Click "Add app" → Web icon
3. Copy config to `public/.env`

But it will work without this for basic function calls!

## 🚢 Deploy to Firebase Hosting

Once tested locally:

```powershell
cd public
npm run build
cd ..
firebase deploy --only hosting
```

Your app will be live at: `https://rugby-ai-61fd0.web.app`

## 🐛 Troubleshooting

**Functions not working?**
- Check browser console (F12)
- Verify functions are deployed: https://console.firebase.google.com/project/rugby-ai-61fd0/functions
- Check function logs for errors

**CORS errors?**
- Callable functions handle CORS automatically
- If errors persist, check Firebase project settings

**"Module not found" errors?**
- Run `npm install` in the `public` directory
- Make sure you're in the `public` folder when running commands

