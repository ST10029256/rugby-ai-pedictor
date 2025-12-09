# Setup Google Cloud Authentication for PWA Automation

This guide shows you how to set up the Google Cloud Service Account needed for automated Firestore sync and Cloud Storage uploads.

## Step 1: Use Existing Firebase Admin SDK Service Account ✅

**Use this service account:**
- **Email**: `firebase-adminsdk-fbsvc@rugby-ai-61fd0.iam.gserviceaccount.com`
- **Name**: `firebase-adminsdk`
- **Status**: ✅ Enabled

This service account is already configured for Firebase operations and should have the necessary permissions.

### Create Key for This Service Account:

1. **Click on** `firebase-adminsdk-fbsvc@rugby-ai-61fd0.iam.gserviceaccount.com` in your list
2. Go to the **KEYS** tab
3. Click **ADD KEY** → **Create new key**
4. Select **JSON** format
5. Click **CREATE**
6. The JSON key file will download automatically

**That's it!** You can skip to Step 5 (Add to GitHub Secrets).

---

**Alternative: Create New Service Account (Only if the above doesn't work)**

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select your project: `rugby-ai-61fd0`
3. Navigate to **IAM & Admin** → **Service Accounts**
4. Click **+ CREATE SERVICE ACCOUNT**

## Step 2: Verify Permissions (Optional Check)

Before proceeding, you can verify the Firebase Admin SDK service account has the right permissions:

1. Click on `firebase-adminsdk-fbsvc@rugby-ai-61fd0.iam.gserviceaccount.com`
2. Go to **PERMISSIONS** tab
3. It should have roles like:
   - **Firebase Admin SDK Administrator Service Agent**
   - **Cloud Datastore User** (for Firestore)
   - **Storage Object Admin** (for Cloud Storage)

If these permissions are missing, you may need to create a new service account (see Alternative below).

---

**Alternative: Create New Service Account**

## Step 2: Configure Service Account

1. **Service account name**: `github-actions-automation`
2. **Description**: `Service account for GitHub Actions automation`
3. Click **CREATE AND CONTINUE**

## Step 3: Grant Permissions

Add these roles:
- **Cloud Datastore User** (for Firestore)
- **Storage Object Admin** (for Cloud Storage uploads)

Click **CONTINUE** → **DONE**

## Step 4: Create and Download Key

1. Click on the service account you just created
2. Go to **KEYS** tab
3. Click **ADD KEY** → **Create new key**
4. Select **JSON** format
5. Click **CREATE**
6. The JSON key file will download automatically

## Step 5: Add to GitHub Secrets

1. Go to your GitHub repository
2. Navigate to **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. **Name**: `GCP_SA_KEY`
5. **Value**: Paste the entire contents of the downloaded JSON file
6. Click **Add secret**

## Step 6: Verify Setup

The next time the GitHub Actions workflow runs, it will:
- ✅ Authenticate using the service account
- ✅ Sync data to Firestore
- ✅ Upload models to Cloud Storage

## Security Notes

- ⚠️ **Never commit the JSON key file to your repository**
- ✅ The key is stored securely in GitHub Secrets
- ✅ Only GitHub Actions can access it
- ✅ You can revoke access anytime by deleting the service account

## Testing Locally

If you want to test the sync script locally:

```bash
# Set the environment variable
export GOOGLE_APPLICATION_CREDENTIALS="path/to/your/service-account-key.json"

# Or use gcloud auth
gcloud auth application-default login

# Test the sync
python scripts/sync_to_firestore.py --dry-run
```

## Troubleshooting

### Error: "Permission denied"
- Check that the service account has the correct roles
- Verify the JSON key is correct in GitHub Secrets

### Error: "Project not found"
- Ensure project ID is `rugby-ai-61fd0`
- Check that the service account has access to the project

### Error: "Authentication failed"
- Verify the JSON key is valid
- Check that the secret name is exactly `GCP_SA_KEY`

## Next Steps

Once set up, your automation will:
1. Run daily at 22:00 UTC
2. Sync new games to Firestore
3. Retrain AI when games complete
4. Upload models to Cloud Storage
5. Keep your PWA always up-to-date!

No manual work required! 🎉

