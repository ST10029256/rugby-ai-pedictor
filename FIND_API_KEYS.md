# Where Your API Keys Are Stored

## Current API Keys Found

### 1. **SportDevs API Key**
- **Location**: `expert_ai_app.py` (line 83)
- **Value**: `qwh9orOkZESulf4QBhf0IQ` (hardcoded as default)
- **How it's used**: 
  ```python
  SPORTDEVS_API_KEY = os.getenv("SPORTDEVS_API_KEY", "qwh9orOkZESulf4QBhf0IQ")
  ```
  - First tries environment variable `SPORTDEVS_API_KEY`
  - Falls back to hardcoded key if not found

### 2. **TheSportsDB API Key**
- **Location**: `expert_ai_app.py` (line 84)
- **Value**: `"123"` (free/public key)
- **How it's used**:
  ```python
  THESPORTSDB_API_KEY = os.getenv("THESPORTSDB_API_KEY", "123")
  ```

### 3. **Highlightly API Key**
- **Status**: Not found in code
- **Where it should be**: Environment variable `HIGHLIGHTLY_API_KEY`
- **Used in**: `prediction/enhanced_predictor.py` and `rugby-ai-predictor/main.py`

## Where Keys Are Loaded From

The app checks for API keys in this order:

1. **Environment Variables** (highest priority)
   - `SPORTDEVS_API_KEY`
   - `THESPORTSDB_API_KEY`
   - `HIGHLIGHTLY_API_KEY`
   - `APISPORTS_API_KEY`

2. **Streamlit Secrets** (for local Streamlit apps)
   - File: `.streamlit/secrets.toml` (doesn't exist yet)
   - Template: `secrets.toml.example`

3. **Hardcoded Defaults** (fallback)
   - SportDevs: `qwh9orOkZESulf4QBhf0IQ`
   - TheSportsDB: `"123"`

## For Firebase Cloud Functions

Your Cloud Functions need these environment variables set:
- `SPORTDEVS_API_KEY` = `qwh9orOkZESulf4QBhf0IQ` (from your code)
- `HIGHLIGHTLY_API_KEY` = (you need to find this or get a new one)
- `MODEL_STORAGE_BUCKET` = `rugby-ai-61fd0.firebasestorage.app`

## How to Set for Firebase

### Option 1: Google Cloud Console (Recommended)
1. Go to: https://console.cloud.google.com/run?project=rugby-ai-61fd0
2. Click on a function service (e.g., `predict-match-2jbomp443a`)
3. Click "Edit & Deploy New Revision"
4. Go to "Variables & Secrets" tab
5. Add:
   - `SPORTDEVS_API_KEY` = `qwh9orOkZESulf4QBhf0IQ`
   - `HIGHLIGHTLY_API_KEY` = (your key)
   - `MODEL_STORAGE_BUCKET` = `rugby-ai-61fd0.firebasestorage.app`

### Option 2: Check if you have Highlightly key
Search your files or check where you got it from. If you don't have one, the enhanced predictor features won't work, but basic predictions will still work.

