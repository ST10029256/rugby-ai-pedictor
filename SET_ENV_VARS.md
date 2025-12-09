# Setting Environment Variables for Cloud Functions

## Method 1: Firebase Console (Recommended)

1. **Go to Functions Configuration:**
   - Navigate to: https://console.firebase.google.com/project/rugby-ai-61fd0/functions
   - Click on **"Configuration"** tab (or look for "Environment Variables" / "Secrets")
   - If you don't see it, try: https://console.firebase.google.com/project/rugby-ai-61fd0/functions/config

2. **Add Environment Variables:**
   Click "Add variable" or "Edit" and add these 3 variables:

   | Variable Name | Value |
   |--------------|-------|
   | `MODEL_STORAGE_BUCKET` | `rugby-ai-61fd0.firebasestorage.app` |
   | `SPORTDEVS_API_KEY` | (your SportDevs API key) |
   | `HIGHLIGHTLY_API_KEY` | (your Highlightly API key - optional) |

3. **Save and Redeploy:**
   After adding variables, you may need to redeploy functions:
   ```bash
   cd rugby-ai-predictor
   firebase deploy --only functions
   ```

## Method 2: Firebase CLI (Alternative)

If the Console doesn't show the Configuration option, use CLI:

```bash
cd rugby-ai-predictor

# Set environment variables
firebase functions:config:set \
  model_storage_bucket="rugby-ai-61fd0.firebasestorage.app" \
  sportdevs_api_key="YOUR_SPORTDEVS_KEY" \
  highlightly_api_key="YOUR_HIGHLIGHTLY_KEY"

# Redeploy functions
firebase deploy --only functions
```

**Note:** For 2nd Gen functions, you might need to use secrets instead:
```bash
# Create secrets (more secure for API keys)
echo -n "rugby-ai-61fd0.firebasestorage.app" | firebase functions:secrets:set MODEL_STORAGE_BUCKET
echo -n "YOUR_KEY" | firebase functions:secrets:set SPORTDEVS_API_KEY
echo -n "YOUR_KEY" | firebase functions:secrets:set HIGHLIGHTLY_API_KEY

# Then update main.py to use secrets
```

## Method 3: Direct URL

Try these direct links:
- **Configuration**: https://console.firebase.google.com/project/rugby-ai-61fd0/functions/config
- **Secrets**: https://console.firebase.google.com/project/rugby-ai-61fd0/functions/secrets

## Verification

After setting variables, check they're loaded:
1. View function logs: https://console.firebase.google.com/project/rugby-ai-61fd0/functions/logs
2. Test a function call
3. Check logs for any "environment variable not found" errors

## Important Notes

- **2nd Gen Functions** (which you're using) may require **Secrets** instead of regular environment variables
- Secrets are more secure for API keys
- After setting secrets, you need to update `main.py` to access them differently

If you can't find the Configuration tab, let me know and I'll help you set up secrets instead!

