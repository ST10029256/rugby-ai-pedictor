# Simple Way to Set Environment Variables

## Using Firebase CLI (Easiest Method)

Open PowerShell in your project root:

```powershell
cd rugby-ai-predictor

# Set environment variables (these will be available to all functions)
firebase functions:config:set \
  model_storage_bucket="rugby-ai-61fd0.firebasestorage.app" \
  sportdevs_api_key="qwh9orOkZESulf4QBhf0IQ" \
  highlightly_api_key="9c27c5f8-9437-4d42-8cc9-5179d3290a5b"

# Redeploy functions to apply changes
firebase deploy --only functions
```

**Note:** Replace `YOUR_SPORTDEVS_KEY_HERE` and `YOUR_HIGHLIGHTLY_KEY_HERE` with your actual API keys.

## Access in Code

The code already uses `os.getenv()`, but for Firebase config, you need to access them as:
- `MODEL_STORAGE_BUCKET` (automatically converted from `model_storage_bucket`)
- `SPORTDEVS_API_KEY` (automatically converted from `sportdevs_api_key`)
- `HIGHLIGHTLY_API_KEY` (automatically converted from `highlightly_api_key`)

Actually, wait - for 2nd Gen functions, the config system is different. Let me check...

## For 2nd Gen Functions (What You're Using)

2nd Gen functions use a different system. You can either:

1. **Set in function definition** (recommended)
2. **Use Secrets** (for sensitive data like API keys)
3. **Set as environment variables in Cloud Run** (since 2nd Gen uses Cloud Run)

The easiest is to update the function definition to include environment variables directly.

