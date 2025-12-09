# 🚀 Firebase Deployment Guide

Complete guide to deploy your Rugby AI Predictor app to Firebase.

## 📋 Prerequisites

1. **Firebase CLI** - Install if you haven't already:
   ```bash
   npm install -g firebase-tools
   ```

2. **Firebase Account** - Make sure you're logged in:
   ```bash
   firebase login
   ```

3. **Project Setup** - Your project is already configured:
   - Project ID: `rugby-ai-61fd0`
   - Firebase config files are in place

## 🔑 Environment Variables Setup

Before deploying, you need to set environment variables for Cloud Functions.

### Option 1: Set via Firebase Console (Recommended)

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Select your project: `rugby-ai-61fd0`
3. Navigate to **Functions** → **Configuration**
4. Add the following environment variables:

```
SPORTDEVS_API_KEY=your_sportdevs_api_key
THESPORTSDB_API_KEY=your_thesportsdb_api_key
HIGHLIGHTLY_API_KEY=your_highlightly_api_key (optional)
APISPORTS_API_KEY=your_apisports_api_key (optional)
DB_PATH=/tmp/data.sqlite
```

### Option 2: Set via Firebase CLI

```bash
firebase functions:config:set \
  sportdevs.api_key="your_sportdevs_api_key" \
  thesportsdb.api_key="your_thesportsdb_api_key" \
  highlightly.api_key="your_highlightly_api_key" \
  apisports.api_key="your_apisports_api_key"
```

## 📦 Pre-Deployment Checklist

### 1. Build the React App
```bash
cd public
npm run build
cd ..
```

✅ You've already done this! The build folder exists at `public/build`

### 2. Verify Build Output
Make sure `public/build` contains:
- `index.html`
- `static/` folder with JS and CSS files

### 3. Check Firebase Configuration
Verify these files exist:
- ✅ `firebase.json` - Hosting and Functions config
- ✅ `.firebaserc` - Project ID configuration
- ✅ `firestore.rules` - Firestore security rules
- ✅ `firestore.indexes.json` - Firestore indexes
- ✅ `storage.rules` - Storage security rules

## 🚀 Deployment Steps

### Step 1: Initialize Firebase (if not already done)

```bash
# Make sure you're in the project root
cd "C:\Users\dylan\OneDrive\Desktop\Knights\Knights Code\rugby-ai-pedictor-main"

# Verify Firebase project
firebase use --add
# Select: rugby-ai-61fd0 (default)
```

### Step 2: Deploy Everything

**Option A: Deploy All Services (Recommended)**
```bash
firebase deploy
```

This will deploy:
- ✅ Hosting (React frontend)
- ✅ Cloud Functions (backend API)
- ✅ Firestore Rules
- ✅ Storage Rules

**Option B: Deploy Individual Services**

```bash
# Deploy only hosting (frontend)
firebase deploy --only hosting

# Deploy only functions (backend)
firebase deploy --only functions

# Deploy only Firestore rules
firebase deploy --only firestore:rules

# Deploy only Storage rules
firebase deploy --only storage
```

### Step 3: Monitor Deployment

Watch the deployment progress. You'll see:
- Building functions
- Uploading hosting files
- Deploying to Firebase

## 🌐 Post-Deployment

### Access Your App

After successful deployment, your app will be available at:
```
https://rugby-ai-61fd0.web.app
```
or
```
https://rugby-ai-61fd0.firebaseapp.com
```

### Verify Deployment

1. **Check Hosting**
   - Visit the URL above
   - Verify the React app loads correctly
   - Test league selection and predictions

2. **Check Cloud Functions**
   - Go to Firebase Console → Functions
   - Verify all functions are deployed:
     - `predict_match`
     - `get_upcoming_matches`
     - `get_live_matches`
     - `get_leagues`

3. **Test API Endpoints**
   - Open browser console on your deployed app
   - Check for any API errors
   - Verify predictions are working

## 🔧 Troubleshooting

### Common Issues

#### 1. Build Errors
```bash
# Clean and rebuild
cd public
rm -rf build node_modules
npm install
npm run build
cd ..
```

#### 2. Function Deployment Fails
- Check `functions/requirements.txt` for dependencies
- Verify Python version (should be 3.11)
- Check function logs in Firebase Console

#### 3. Environment Variables Not Set
- Go to Firebase Console → Functions → Configuration
- Add missing environment variables
- Redeploy functions: `firebase deploy --only functions`

#### 4. Hosting Not Updating
- Clear browser cache
- Check `firebase.json` hosting configuration
- Verify `public/build` folder exists

#### 5. CORS Errors
- Check Firestore rules are deployed
- Verify Cloud Functions are accessible
- Check browser console for specific errors

### View Logs

```bash
# View function logs
firebase functions:log

# View specific function logs
firebase functions:log --only predict_match
```

## 🔄 Updating the Deployment

### For Frontend Changes

1. Make changes to React app in `public/src/`
2. Rebuild:
   ```bash
   cd public
   npm run build
   cd ..
   ```
3. Deploy hosting:
   ```bash
   firebase deploy --only hosting
   ```

### For Backend Changes

1. Make changes to `functions/main.py` or prediction modules
2. Deploy functions:
   ```bash
   firebase deploy --only functions
   ```

### For Both

```bash
# Rebuild frontend
cd public && npm run build && cd ..

# Deploy everything
firebase deploy
```

## 📊 Monitoring

### Firebase Console

1. **Hosting Dashboard**
   - View traffic and usage
   - Check deployment history
   - Monitor performance

2. **Functions Dashboard**
   - View execution metrics
   - Check error rates
   - Monitor cold start times

3. **Firestore Dashboard**
   - View database usage
   - Monitor read/write operations
   - Check data size

## 🔐 Security Checklist

- ✅ Firestore rules are deployed
- ✅ Storage rules are deployed
- ✅ API keys are in environment variables (not in code)
- ✅ CORS is properly configured
- ✅ Authentication is set up (if needed)

## 📝 Quick Reference

```bash
# Login to Firebase
firebase login

# Check current project
firebase use

# Deploy everything
firebase deploy

# Deploy only hosting
firebase deploy --only hosting

# Deploy only functions
firebase deploy --only functions

# View logs
firebase functions:log

# Open hosting URL
firebase open hosting:site
```

## ✅ Deployment Complete!

Your Rugby AI Predictor app is now live on Firebase! 🎉

**Next Steps:**
1. Test all features on the deployed app
2. Monitor Firebase Console for any issues
3. Set up custom domain (optional)
4. Configure CDN caching (optional)
5. Set up monitoring alerts (optional)

## 🆘 Need Help?

- Check Firebase Console for detailed error messages
- Review function logs: `firebase functions:log`
- Check browser console for frontend errors
- Verify all environment variables are set correctly

