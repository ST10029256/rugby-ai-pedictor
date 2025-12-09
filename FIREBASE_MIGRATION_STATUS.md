# Firebase Migration Status

## ✅ Completed

### 1. Firestore Database Migration
- **Status**: ✅ Complete
- **Records Migrated**: 2,205 total
  - 8 leagues (fixed duplicate issue, added missing leagues)
  - 177 teams
  - 1,943 matches
  - 77 seasons
- **Script**: `scripts/migrate_to_firestore.py`
- **Verification**: `scripts/verify_firestore.py`

### 2. Cloud Storage Integration
- **Status**: ✅ Complete
- **Script**: `scripts/upload_models_to_storage.py`
- **Storage Loader**: `prediction/storage_loader.py` (supports Cloud Storage + local fallback)
- **Model Paths**: Updated `MultiLeaguePredictor` to support Cloud Storage
- **Models Uploaded**: 9 files (8 league models + registry JSON)
  - Total size: ~39 MB
  - Location: `gs://rugby-ai-61fd0.firebasestorage.app/models/`

### 3. Cloud Functions Updates
- **Status**: ✅ Updated
- **File**: `rugby-ai-predictor/main.py`
- **Changes**:
  - Updated to use Firestore instead of SQLite
  - Configured to load models from Cloud Storage
  - Set default bucket: `rugby-ai-61fd0.firebasestorage.app`

## 🔄 Next Steps

### 1. ✅ Upload ML Models to Cloud Storage
**COMPLETED** - All 8 league models + registry uploaded to `gs://rugby-ai-61fd0.firebasestorage.app/models/`

### 2. ✅ Update Team Lookup Logic
**COMPLETED** - `HybridPredictor.predict_match()` now supports Firestore
- Added `get_team_id_from_firestore()` helper function
- Updated `predict_match()` to use Firestore when `db_path == 'firestore'`
- Maintains backward compatibility with SQLite

**Note**: `get_ai_prediction()` still needs Firestore support for feature building
- Currently returns simplified prediction for Firestore
- TODO: Implement Firestore adapter for `build_feature_table()`

### 3. ✅ Deploy Cloud Functions
**COMPLETED** - All 4 Cloud Functions deployed successfully:
- `get_leagues(us-central1)` ✅
- `get_live_matches(us-central1)` ✅
- `get_upcoming_matches(us-central1)` ✅
- `predict_match(us-central1)` ✅

**Deployment Details:**
- Location: `us-central1`
- Runtime: Python 3.11 (2nd Gen)
- Container cleanup: 1 day retention

### 4. Set Environment Variables
In Firebase Console → Functions → Configuration:
- `MODEL_STORAGE_BUCKET`: `rugby-ai-61fd0.firebasestorage.app`
- `SPORTDEVS_API_KEY`: (your API key)
- `HIGHLIGHTLY_API_KEY`: (your API key, optional)

## 📊 Current Architecture

```
┌─────────────────┐
│  React Frontend │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Cloud Functions │
│  (Python 3.11)  │
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌─────────┐ ┌──────────────┐
│Firestore│ │Cloud Storage  │
│Database │ │  (ML Models)  │
└─────────┘ └──────────────┘
```

## 🐛 Known Issues / TODOs

1. **Feature Building**: `get_ai_prediction()` uses simplified prediction for Firestore
   - **Solution**: Implement Firestore adapter for `build_feature_table()`
   - **Location**: `prediction/hybrid_predictor.py` → `get_ai_prediction()` method
   - **Impact**: Predictions work but use simplified features (not full AI model features)

2. **Environment Variables**: Need to set in Firebase Console
   - `MODEL_STORAGE_BUCKET`: `rugby-ai-61fd0.firebasestorage.app`
   - `SPORTDEVS_API_KEY`: (your API key)
   - `HIGHLIGHTLY_API_KEY`: (optional)

## 📝 Files Modified

- `scripts/migrate_to_firestore.py` - Database migration script
- `scripts/upload_models_to_storage.py` - Model upload script (NEW)
- `scripts/verify_firestore.py` - Verification script (NEW)
- `prediction/storage_loader.py` - Cloud Storage loader (NEW)
- `prediction/hybrid_predictor.py` - Added Cloud Storage support
- `rugby-ai-predictor/main.py` - Updated for Firestore + Cloud Storage
- `rugby-ai-predictor/requirements.txt` - Updated dependencies

