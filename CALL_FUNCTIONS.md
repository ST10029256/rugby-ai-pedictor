# How to Call Your Cloud Functions

## Important: These are Callable Functions

Your functions use `@https_fn.on_call()` which means they're **callable functions**, not direct HTTP endpoints. They require:
1. Firebase authentication (or public access if configured)
2. Special request format

## Option 1: Use Firebase SDK (Recommended)

### From JavaScript/React:
```javascript
import { getFunctions, httpsCallable } from 'firebase/functions';

const functions = getFunctions();
const predictMatch = httpsCallable(functions, 'predict_match');

const result = await predictMatch({
  home_team: "Leinster",
  away_team: "Munster",
  league_id: 4446,
  match_date: "2025-11-25"
});

console.log(result.data);
```

### From Python:
```python
from firebase_functions import https_fn
import requests

# For callable functions, you need to use the Firebase SDK
# Or convert them to HTTP functions
```

## Option 2: Convert to HTTP Functions

We can change `@https_fn.on_call()` to `@https_fn.on_request()` to make them direct HTTP endpoints.

## Option 3: Check Function Logs

The "Bad Request" error might be due to:
- Missing authentication
- Wrong request format
- Function initialization error

Check logs at: https://console.firebase.google.com/project/rugby-ai-61fd0/functions/logs

## Quick Fix: Convert to HTTP Functions

Would you like me to convert them to HTTP functions so you can call them directly with curl/HTTP?

