# Enable Firebase Storage - Step by Step Guide

## Problem: Storage Not Visible in Firebase Console

If you don't see "Storage" in the Firebase Console, it needs to be initialized first.

## Solution: Enable Firebase Storage

### Method 1: Via Firebase Console (Recommended)

1. **Go to Firebase Console:**
   - Visit: https://console.firebase.google.com/project/rugby-ai-61fd0/overview

2. **Enable Storage:**
   - In the left sidebar, look for **"Build"** section
   - Click on **"Storage"** (if you see it)
   - OR click **"Get Started"** if Storage isn't visible yet
   - OR go directly to: https://console.firebase.google.com/project/rugby-ai-61fd0/storage

3. **If you see "Get Started" button:**
   - Click **"Get Started"**
   - Choose **"Start in production mode"** (we'll set rules separately)
   - Select a **Cloud Storage location** (choose closest to your users, e.g., `us-central1` or `us-east1`)
   - Click **"Done"**

4. **Storage should now be visible!**

### Method 2: Via Firebase CLI

If Console method doesn't work, try CLI:

```powershell
# Make sure you're in the project root
cd "C:\Users\dylan\OneDrive\Desktop\Knights\Knights Code\rugby-ai-pedictor-main"

# Initialize Storage (if not already done)
firebase init storage
```

### Method 3: Direct URL Access

Try accessing Storage directly:
- https://console.firebase.google.com/project/rugby-ai-61fd0/storage

If it says "Storage not initialized", click the "Get Started" button.

---

## After Storage is Enabled

1. **Create Media Folder:**
   - In Storage, click **"Add folder"**
   - Name it: `media`
   - Click **"Create"**

2. **Upload Files:**
   - Navigate into the `media` folder
   - Click **"Upload file"**
   - Upload these 4 files:
     - `public/public/video_rugby.mov`
     - `public/public/video_rugby_ball.mov`
     - `public/public/login_video.mov`
     - `public/public/image_rugby.jpeg`

3. **Make Files Public:**
   - Click on each uploaded file
   - Go to **"Permissions"** tab
   - Click **"Add member"**
   - In "New members", type: `allUsers`
   - Select role: **"Cloud Storage Object Viewer"** (or "Reader")
   - Click **"Save"**

4. **Verify URLs:**
   - After uploading, click on a file
   - Copy the "Download URL" or check the URL format
   - Should look like: `https://firebasestorage.googleapis.com/v0/b/rugby-ai-61fd0.firebasestorage.app/o/media%2Fvideo_rugby.mov?alt=media`

---

## Troubleshooting

### Still can't see Storage?

1. **Check Project Permissions:**
   - Make sure you're logged in with an account that has Owner/Editor permissions
   - Go to: https://console.firebase.google.com/project/rugby-ai-61fd0/settings/iam

2. **Try Different Browser:**
   - Sometimes browser extensions can block Firebase Console features
   - Try Chrome or Edge in incognito mode

3. **Check Firebase Plan:**
   - Storage should be available on all plans (including Spark free tier)
   - Go to: https://console.firebase.google.com/project/rugby-ai-61fd0/usage

4. **Wait a Few Minutes:**
   - Sometimes it takes a few minutes for Storage to appear after enabling

---

## Quick Test

Once Storage is enabled, you can test by running:
```powershell
firebase storage:rules:get
```

This should show your storage rules if Storage is properly set up.

---

## Next Steps After Uploading

1. **Deploy Storage Rules:**
   ```powershell
   firebase deploy --only storage
   ```

2. **Build and Deploy App:**
   ```powershell
   cd public
   npm run build
   cd ..
   firebase deploy --only hosting
   ```

3. **Test:**
   - Open your app
   - Check browser DevTools → Network tab
   - Media files should load from `firebasestorage.googleapis.com`

