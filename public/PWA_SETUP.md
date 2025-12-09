# PWA Setup Instructions

Your app is now configured as a Progressive Web App (PWA)! Follow these steps to complete the setup:

## Step 1: Generate Icons

You need to create two icon files: `icon-192.png` and `icon-512.png`

### Option A: Using the HTML Generator (Recommended)
1. Open `public/public/generate-icons.html` in your web browser
2. Click "Generate & Download 192x192" button
3. Click "Generate & Download 512x512" button
4. Save both files as `icon-192.png` and `icon-512.png` in the `public/public/` folder

### Option B: Create Icons Manually
Create two PNG images:
- `icon-192.png` - 192x192 pixels
- `icon-512.png` - 512x512 pixels

Place them in the `public/public/` folder.

## Step 2: Build and Deploy

1. Build your app:
   ```bash
   npm run build
   ```

2. Deploy to Firebase (or your hosting service):
   ```bash
   firebase deploy
   ```

## Step 3: Test PWA Installation

After deployment:
1. Visit https://rugby-ai-61fd0.web.app/
2. On mobile devices: Look for "Add to Home Screen" prompt
3. On desktop (Chrome/Edge): Look for the install icon in the address bar
4. On desktop (Firefox): Menu → Install

## What's Included

✅ **manifest.json** - PWA configuration with app name, icons, theme colors
✅ **service-worker.js** - Offline functionality and caching
✅ **Updated index.html** - PWA meta tags and manifest link
✅ **Service worker registration** - Automatic registration in index.js

## Features Enabled

- 📱 Installable on mobile and desktop
- 🔄 Offline functionality (cached resources)
- 🎨 Custom theme colors matching your app
- 🏠 Standalone display mode (no browser UI)

## Troubleshooting

### Icons not showing
- Make sure `icon-192.png` and `icon-512.png` are in `public/public/` folder
- Rebuild the app after adding icons: `npm run build`

### Install prompt not appearing
- Make sure you're using HTTPS (Firebase Hosting provides this)
- Check browser console for service worker errors
- Clear browser cache and reload

### Service worker not registering
- Check browser console for errors
- Make sure `service-worker.js` is in `public/public/` folder
- Verify the service worker is accessible at `/service-worker.js` after build

