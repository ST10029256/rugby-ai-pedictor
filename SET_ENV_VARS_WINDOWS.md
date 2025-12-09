# Setting Environment Variables (Windows PowerShell)

## Quick Method: Use Firebase CLI

Since you're using **2nd Gen Functions (v2)**, you need to use **Secrets** instead of regular environment variables.

### Step 1: Set Secrets

Open PowerShell in the `rugby-ai-predictor` directory:

```powershell
cd rugby-ai-predictor

# Set MODEL_STORAGE_BUCKET
echo "rugby-ai-61fd0.firebasestorage.app" | firebase functions:secrets:set MODEL_STORAGE_BUCKET

# Set SPORTDEVS_API_KEY (replace YOUR_KEY with your actual key)
echo "YOUR_SPORTDEVS_KEY" | firebase functions:secrets:set SPORTDEVS_API_KEY

# Set HIGHLIGHTLY_API_KEY (optional, replace YOUR_KEY)
echo "YOUR_HIGHLIGHTLY_KEY" | firebase functions:secrets:set HIGHLIGHTLY_API_KEY
```

### Step 2: Update main.py to Use Secrets

For 2nd Gen functions, secrets are accessed differently. Update `main.py`:

```python
# Instead of os.getenv(), use:
from firebase_functions import secrets

# Access secrets like this:
storage_bucket = secrets.get("MODEL_STORAGE_BUCKET").value or 'rugby-ai-61fd0.firebasestorage.app'
sportdevs_key = secrets.get("SPORTDEVS_API_KEY").value or ''
highlightly_key = secrets.get("HIGHLIGHTLY_API_KEY").value or ''
```

### Step 3: Redeploy

```powershell
firebase deploy --only functions
```

## Alternative: Use Console

1. Go to: https://console.firebase.google.com/project/rugby-ai-61fd0/functions/secrets
2. Click "Add secret"
3. Add each variable:
   - `MODEL_STORAGE_BUCKET`
   - `SPORTDEVS_API_KEY`
   - `HIGHLIGHTLY_API_KEY`

## Note

If you can't find the Secrets section in Console, the CLI method above will work. The secrets will be automatically available to your functions after redeployment.

