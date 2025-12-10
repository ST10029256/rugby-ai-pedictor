# Fix: Upload XGBoost Models to Firebase

Your Firebase app is currently showing `"model_type": "stacking"` (optimized models) instead of XGBoost models.

## Steps to Fix:

### 1. Upload XGBoost Model Registry to Firestore

Run this command to upload the XGBoost registry:

```bash
python scripts/upload_model_registry_to_firestore.py --registry artifacts/model_registry.json
```

This will:
- Upload to Firestore document `model_registry/xgboost` 
- Update individual league metrics in `league_metrics/{league_id}` with `model_type: "xgboost"`

### 2. Deploy Updated Cloud Functions

After uploading the registry, redeploy your Cloud Functions:

```bash
firebase deploy --only functions
```

### 3. Verify

After deployment, check your app logs. You should see:
- `"model_type": "xgboost"` (not "stacking")
- Accuracies matching the expected XGBoost values from `scripts/xgboost_expected_accuracy.md`

## Expected XGBoost Accuracies:

- **4414** (English Premiership): ~77.88%
- **4430** (French Top 14): ~81.23%
- **4446** (United Rugby Championship): ~79.94%
- **4551** (Super Rugby): ~76.06%
- **4574** (Rugby World Cup): ~92.76%
- **4986** (Rugby Championship): ~56.25%
- **5069** (Currie Cup): ~71.59%
- **5479** (International Friendlies): ~89.36%

## Current Issue:

Your app is currently showing optimized/stacking accuracies (which are slightly higher but worse at score prediction):
- Currently showing: 63%, 76.9%, 69.4%, 67.7%, 84.4%, 61.4%, 58.8%, 73.3%
- Should show: 77.88%, 81.23%, 79.94%, 76.06%, 92.76%, 56.25%, 71.59%, 89.36%

The XGBoost models are already uploaded to Cloud Storage from the workflow, but the registry needs to be uploaded to Firestore.

