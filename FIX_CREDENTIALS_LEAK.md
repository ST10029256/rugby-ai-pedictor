# ⚠️ Security Fix: Credentials File Leaked

## What Happened

The GitHub Actions workflow accidentally committed a Google Cloud service account credentials file (`gha-creds-91811cdcc7cd6890.json`) to the repository. GitHub's push protection blocked this, which is good!

## ✅ What I Fixed

1. **Updated `.gitignore`** - Added patterns to exclude all credential files
2. **Updated workflows** - Modified both workflows to explicitly exclude credential files when committing
3. **Added safety checks** - Workflows now remove credential files before committing

## 🔒 What You Need to Do

### 1. Rotate/Regenerate the Service Account Key (IMPORTANT!)

Since the key was exposed (even though the push was blocked), you should regenerate it:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Navigate to **IAM & Admin** → **Service Accounts**
3. Click on `firebase-adminsdk-fbsvc@rugby-ai-61fd0.iam.gserviceaccount.com`
4. Go to **KEYS** tab
5. **Delete the old key** (the one that was exposed)
6. **Create a new key** (JSON format)
7. **Update GitHub Secret**:
   - Go to GitHub → Settings → Secrets → Actions
   - Edit `GCP_SA_KEY`
   - Paste the new JSON key
   - Save

### 2. Remove the File from Git History (If Already Committed)

If the file was committed in a previous push, remove it:

```bash
# Remove from git history
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch gha-creds-*.json *-creds-*.json" \
  --prune-empty --tag-name-filter cat -- --all

# Force push (be careful!)
git push origin --force --all
```

**OR** if you're not comfortable with that, just regenerate the key (step 1) - that's the most important part.

### 3. Verify the Fix

After pushing the updated workflows:
- The workflows will no longer commit credential files
- `.gitignore` will prevent them from being tracked
- Future runs will be safe

## ✅ Status

- ✅ `.gitignore` updated
- ✅ Workflows updated to exclude credentials
- ⚠️ **You need to regenerate the service account key**

The workflows are now safe and won't commit credential files in the future!

