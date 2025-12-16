# Fix Secret Manager Permissions

The error "No email service configured" means the function can't access the secrets. This is usually a permissions issue.

## Quick Fix: Grant Secret Manager Access

The Cloud Functions service account needs permission to read secrets.

### Option 1: Via Firebase Console (Easiest)

1. Go to: https://console.firebase.google.com/project/rugby-ai-61fd0/settings/serviceaccounts
2. Find your Cloud Functions service account (usually: `rugby-ai-61fd0@appspot.gserviceaccount.com`)
3. Click "Manage in Google Cloud Console"
4. Go to "Permissions" tab
5. Click "Grant Access"
6. Add role: **Secret Manager Secret Accessor**
7. Save

### Option 2: Via Command Line

```bash
# Get the service account email
gcloud iam service-accounts list --project=rugby-ai-61fd0

# Grant Secret Manager access (replace SERVICE_ACCOUNT_EMAIL)
gcloud projects add-iam-policy-binding rugby-ai-61fd0 \
  --member="serviceAccount:SERVICE_ACCOUNT_EMAIL" \
  --role="roles/secretmanager.secretAccessor"
```

### Option 3: Verify Secrets Exist

Make sure the secrets were created correctly:

```bash
# List all secrets
gcloud secrets list --project=rugby-ai-61fd0

# Verify GMAIL_USER exists
gcloud secrets versions access latest --secret="GMAIL_USER" --project=rugby-ai-61fd0

# Verify GMAIL_APP_PASSWORD exists  
gcloud secrets versions access latest --secret="GMAIL_APP_PASSWORD" --project=rugby-ai-61fd0
```

## After Granting Permissions

1. Redeploy the function:
   ```bash
   cd rugby-ai-predictor
   firebase deploy --only functions:generate_license_key_with_email
   ```

2. Test again - the function should now be able to access secrets

## Alternative: Use Environment Variables (If Secrets Don't Work)

If Secret Manager still doesn't work, we can use Firebase Functions config (legacy method):

```bash
firebase functions:config:set gmail.user="your-email@gmail.com"
firebase functions:config:set gmail.app_password="your-app-password"
firebase deploy --only functions:generate_license_key_with_email
```

Then update the code to read from `functions.config()` instead of Secret Manager.

