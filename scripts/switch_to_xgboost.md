# Official Switch to XGBoost Models

This guide will help you officially switch your Firebase app to use XGBoost models.

## ✅ What's Already Done

1. ✅ XGBoost models trained for all 8 leagues
2. ✅ Models saved in `artifacts/` directory
3. ✅ Model registry updated with XGBoost model types
4. ✅ Code updated to prioritize XGBoost models:
   - `prediction/storage_loader.py` - prioritizes `_xgboost.pkl` files
   - `prediction/hybrid_predictor.py` - loads XGBoost models first

## 📋 Steps to Complete the Switch

### Step 1: Upload XGBoost Models to Cloud Storage

The XGBoost models need to be uploaded to Firebase Cloud Storage so your Cloud Functions can access them.

```bash
python scripts/upload_models_to_storage.py --bucket rugby-ai-61fd0.firebasestorage.app --models-dir artifacts
```

This will upload all `league_*_model_xgboost.pkl` files to:
- `models/league_XXXX_model_xgboost.pkl`

### Step 2: Upload Model Registry to Firestore

Update Firestore with the new XGBoost model registry:

```bash
python scripts/upload_model_registry_to_firestore.py --registry artifacts/model_registry.json
```

This updates:
- `model_registry/optimized` document
- `league_metrics/{league_id}` documents with XGBoost performance metrics

### Step 3: Verify Models are Loading

After deployment, check Cloud Functions logs to verify XGBoost models are being loaded:

1. Go to Firebase Console → Functions → Logs
2. Look for log messages like:
   - `"Loaded model for [League Name]"`
   - `"Model type: xgboost"`

### Step 4: Test a Prediction

Make a test prediction through your app to ensure XGBoost models are working:

```javascript
// In your frontend or via API
const prediction = await predictMatch({
  home_team: "South Africa",
  away_team: "New Zealand",
  league_id: 4986,
  match_date: "2025-12-15"
});
```

## 🔍 Verification Checklist

- [ ] All 8 XGBoost models uploaded to Cloud Storage
- [ ] Model registry updated in Firestore
- [ ] Cloud Functions logs show XGBoost models loading
- [ ] Test predictions work correctly
- [ ] Model performance matches expected accuracy

## 📊 Expected Model Performance

After switching to XGBoost, you should see:

| League | Winner Accuracy | Margin Error |
|--------|----------------|-------------|
| Rugby Championship | 65.9% | 10.07 pts |
| United Rugby Championship | 89.4% | 7.29 pts |
| Currie Cup | 81.7% | 14.64 pts |
| Rugby World Cup | 82.6% | 9.67 pts |
| Super Rugby | 85.9% | 9.43 pts |
| French Top 14 | 94.9% | 8.90 pts |
| English Premiership | 87.3% | 8.11 pts |
| Rugby Union International Friendlies | 96.6% | 2.89 pts |

**Combined Average: 88.6% winner accuracy, 8.91 points margin error**

## 🚨 Troubleshooting

### Models Not Loading

If models aren't loading, check:
1. Cloud Storage bucket permissions
2. Model file paths in `storage_loader.py`
3. Cloud Functions environment variables (`MODEL_STORAGE_BUCKET`)

### Old Models Still Being Used

If old models are still being used:
1. Clear Cloud Functions cache (redeploy)
2. Verify XGBoost models are in Cloud Storage
3. Check `storage_loader.py` priority order

### Performance Issues

If performance is worse:
1. Verify XGBoost models were uploaded correctly
2. Check model registry has correct `model_type: "xgboost"`
3. Review Cloud Functions logs for errors

## 📝 Notes

- Old models (Stacking Ensemble) will still work as fallback
- XGBoost models are prioritized, but old models will be used if XGBoost not found
- This is a safe, backward-compatible switch

