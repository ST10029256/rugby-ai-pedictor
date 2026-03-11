# Upload Media Files to Firebase Storage

## Quick Start Guide

### Step 1: Upload Files via Firebase Console (Easiest Method)

1. **Go to Firebase Console:**
   - Visit: https://console.firebase.google.com/project/rugby-ai-61fd0/storage
   - Or: Firebase Console → Storage → Files

2. **Create Media Folder:**
   - Click "Get Started" if Storage isn't initialized
   - Click "Add folder" → Name it `media`

3. **Upload Files:**
   - Navigate to the `media` folder
   - Click "Upload file"
   - Upload these files:
     - `video_rugby.mov`
     - `video_rugby_ball.mov`
     - `login_video.mov`
     - `image_rugby.jpeg`

4. **Make Files Public:**
   - Click on each uploaded file
   - Go to "Permissions" tab
   - Click "Add member"
   - Add `allUsers` with role `Cloud Storage Object Viewer` (or `Reader`)
   - Click "Save"

### Step 2: Verify URLs

After uploading, the files will be accessible at:
- `https://firebasestorage.googleapis.com/v0/b/rugby-ai-61fd0.firebasestorage.app/o/media%2Fvideo_rugby.mov?alt=media`
- `https://firebasestorage.googleapis.com/v0/b/rugby-ai-61fd0.firebasestorage.app/o/media%2Fvideo_rugby_ball.mov?alt=media`
- `https://firebasestorage.googleapis.com/v0/b/rugby-ai-61fd0.firebasestorage.app/o/media%2Flogin_video.mov?alt=media`
- `https://firebasestorage.googleapis.com/v0/b/rugby-ai-61fd0.firebasestorage.app/o/media%2Fimage_rugby.jpeg?alt=media`

### Step 3: Test

1. Build the app: `cd public && npm run build`
2. Deploy: `firebase deploy --only hosting`
3. Test the app - videos and images should load from Storage CDN

---

## Alternative: Using Firebase CLI

### Prerequisites
```bash
npm install -g firebase-tools
firebase login
```

### Upload Commands
```bash
# Navigate to project root
cd "C:\Users\dylan\OneDrive\Desktop\Knights\Knights Code\rugby-ai-pedictor-main"

# Upload each file
firebase storage:upload "public/public/video_rugby.mov" "media/video_rugby.mov" --project rugby-ai-61fd0
firebase storage:upload "public/public/video_rugby_ball.mov" "media/video_rugby_ball.mov" --project rugby-ai-61fd0
firebase storage:upload "public/public/login_video.mov" "media/login_video.mov" --project rugby-ai-61fd0
firebase storage:upload "public/public/image_rugby.jpeg" "media/image_rugby.jpeg" --project rugby-ai-61fd0
```

**Note:** Firebase CLI might not have direct storage upload. Use Console method or gsutil instead.

---

## Alternative: Using gsutil (Google Cloud SDK)

### Prerequisites
1. Install Google Cloud SDK: https://cloud.google.com/sdk/docs/install
2. Authenticate: `gcloud auth login`
3. Set project: `gcloud config set project rugby-ai-61fd0`

### Upload Commands
```bash
# Upload files
gsutil cp "public/public/video_rugby.mov" gs://rugby-ai-61fd0.firebasestorage.app/media/video_rugby.mov
gsutil cp "public/public/video_rugby_ball.mov" gs://rugby-ai-61fd0.firebasestorage.app/media/video_rugby_ball.mov
gsutil cp "public/public/login_video.mov" gs://rugby-ai-61fd0.firebasestorage.app/media/login_video.mov
gsutil cp "public/public/image_rugby.jpeg" gs://rugby-ai-61fd0.firebasestorage.app/media/image_rugby.jpeg

# Make files publicly readable
gsutil acl ch -u AllUsers:R gs://rugby-ai-61fd0.firebasestorage.app/media/video_rugby.mov
gsutil acl ch -u AllUsers:R gs://rugby-ai-61fd0.firebasestorage.app/media/video_rugby_ball.mov
gsutil acl ch -u AllUsers:R gs://rugby-ai-61fd0.firebasestorage.app/media/login_video.mov
gsutil acl ch -u AllUsers:R gs://rugby-ai-61fd0.firebasestorage.app/media/image_rugby.jpeg
```

---

## After Uploading

1. **Deploy Storage Rules:**
   ```bash
   firebase deploy --only storage
   ```

2. **Build and Deploy App:**
   ```bash
   cd public
   npm run build
   cd ..
   firebase deploy --only hosting
   ```

3. **Verify:**
   - Open browser DevTools → Network tab
   - Reload the app
   - Check that media files are loading from `firebasestorage.googleapis.com`
   - Files should load much faster from CDN

---

## Troubleshooting

### Files not loading?
- Check file permissions in Firebase Console (must be public)
- Verify file names match exactly (case-sensitive)
- Check browser console for CORS errors
- Temporarily set `USE_STORAGE = false` in `storageUrls.js` to use local files

### Still slow?
- Files might be large - consider converting to optimized formats (see MEDIA_OPTIMIZATION_GUIDE.md)
- Check network tab to see actual load times
- Verify CDN is working (files should load from nearest location)

---

## File Locations

**Source files to upload:**
- `public/public/video_rugby.mov`
- `public/public/video_rugby_ball.mov`
- `public/public/login_video.mov`
- `public/public/image_rugby.jpeg`

**Destination in Storage:**
- `media/video_rugby.mov`
- `media/video_rugby_ball.mov`
- `media/login_video.mov`
- `media/image_rugby.jpeg`

