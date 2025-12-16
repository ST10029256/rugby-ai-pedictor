# Quick Firebase Storage Setup

## The Issue
Firebase Storage needs to be **initialized** before you can see it in the console.

## Quick Fix (2 minutes)

### Step 1: Enable Storage via Console

1. **Open this URL directly:**
   ```
   https://console.firebase.google.com/project/rugby-ai-61fd0/storage
   ```

2. **If you see "Get Started":**
   - Click **"Get Started"**
   - Select **"Start in production mode"**
   - Choose location: **`us-central1`** (or closest to you)
   - Click **"Done"**

3. **If Storage is already enabled:**
   - You'll see the Storage interface
   - Skip to Step 2

### Step 2: Create Media Folder

1. Click **"Add folder"** (or the folder icon)
2. Name it: `media`
3. Click **"Create"** or press Enter

### Step 3: Upload Files

1. Click into the `media` folder
2. Click **"Upload file"**
3. Upload these 4 files (one at a time or all at once):
   - Navigate to: `public/public/video_rugby.mov`
   - Navigate to: `public/public/video_rugby_ball.mov`
   - Navigate to: `public/public/login_video.mov`
   - Navigate to: `public/public/image_rugby.jpeg`

### Step 4: Make Files Public

**For each file you uploaded:**

1. Click on the file name
2. Click the **"Permissions"** tab (or the lock icon)
3. Click **"Add member"**
4. In the text box, type: `allUsers`
5. Select role: **"Cloud Storage Object Viewer"**
6. Click **"Save"**

**Repeat for all 4 files.**

### Step 5: Verify

1. Click on any file
2. You should see a **"Download URL"** or **"gs://"** URL
3. The URL should contain: `firebasestorage.googleapis.com`

---

## Alternative: If Console Doesn't Work

### Try Firebase CLI Init

```powershell
# Make sure you're in project root
cd "C:\Users\dylan\OneDrive\Desktop\Knights\Knights Code\rugby-ai-pedictor-main"

# Initialize Storage
firebase init storage
```

When prompted:
- Select your project: `rugby-ai-61fd0`
- Choose location: `us-central1`
- Use default rules file: `storage.rules` (already exists)

Then manually upload files via Console.

---

## After Uploading - Deploy

```powershell
# Deploy storage rules (already done, but good to verify)
firebase deploy --only storage

# Build app
cd public
npm run build
cd ..

# Deploy hosting
firebase deploy --only hosting
```

---

## Still Can't See Storage?

1. **Check you're logged in:**
   - Visit: https://console.firebase.google.com/
   - Make sure you see your project

2. **Check permissions:**
   - Go to: https://console.firebase.google.com/project/rugby-ai-61fd0/settings/iam
   - Make sure your account has "Owner" or "Editor" role

3. **Try direct link:**
   - https://console.firebase.google.com/project/rugby-ai-61fd0/storage
   - If it says "Storage not initialized", click "Get Started"

4. **Wait 2-3 minutes:**
   - Sometimes it takes a moment to appear

---

## File Locations Reference

**Files to upload are located at:**
- `C:\Users\dylan\OneDrive\Desktop\Knights\Knights Code\rugby-ai-pedictor-main\public\public\video_rugby.mov`
- `C:\Users\dylan\OneDrive\Desktop\Knights\Knights Code\rugby-ai-pedictor-main\public\public\video_rugby_ball.mov`
- `C:\Users\dylan\OneDrive\Desktop\Knights\Knights Code\rugby-ai-pedictor-main\public\public\login_video.mov`
- `C:\Users\dylan\OneDrive\Desktop\Knights\Knights Code\rugby-ai-pedictor-main\public\public\image_rugby.jpeg`

**Upload destination in Storage:**
- `media/video_rugby.mov`
- `media/video_rugby_ball.mov`
- `media/login_video.mov`
- `media/image_rugby.jpeg`

