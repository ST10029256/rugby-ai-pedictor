# 📤 Upload Model Registry to Firestore

This guide shows you how to store the model registry in Firestore for faster access by Cloud Functions.

## 🎯 Why Firestore?

- **Faster**: Direct database queries are faster than file downloads
- **More Reliable**: No need to manage file storage
- **Easier Updates**: Update metrics without redeploying functions
- **Better Performance**: Cloud Functions can cache Firestore reads

## 📋 Prerequisites

1. **Firebase Admin SDK** installed:
   ```bash
   pip install firebase-admin
   ```

2. **Firebase Authentication** set up:
   - Option A: Use Application Default Credentials (recommended)
     ```bash
     gcloud auth application-default login
     ```
   - Option B: Set service account key
     ```bash
     export GOOGLE_APPLICATION_CREDENTIALS="path/to/service-account-key.json"
     ```

## 🚀 Quick Start

### Step 1: Run the Upload Script

```bash
python scripts/upload_model_registry_to_firestore.py
```

This will:
- Read `artifacts_optimized/model_registry_optimized.json`
- Upload to Firestore collection `model_registry` as document `optimized`
- Create individual league metrics in `league_metrics` collection

### Step 2: Verify Upload

Check Firebase Console:
1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Select your project: `rugby-ai-61fd0`
3. Navigate to **Firestore Database**
4. Check collections:
   - `model_registry` → document `optimized`
   - `league_metrics` → documents for each league (4414, 4446, etc.)

## 📝 Manual Upload (Alternative)

If you prefer to upload manually:

### Using Firebase Console

1. Go to Firestore Database in Firebase Console
2. Create collection: `model_registry`
3. Create document: `optimized`
4. Copy contents of `artifacts_optimized/model_registry_optimized.json`
5. Paste as JSON in the document

### Using Firebase CLI

```bash
# Install Firebase CLI if not already installed
npm install -g firebase-tools

# Login
firebase login

# Use Firestore emulator or direct import
# (Note: Direct JSON import requires Firestore Admin SDK)
```

## 🔄 Updating the Registry

### After Retraining Models

When you retrain models and update the registry:

1. **Retrain models** (updates `model_registry_optimized.json`):
   ```bash
   python scripts/train_models_optimized.py
   ```

2. **Upload to Firestore**:
   ```bash
   python scripts/upload_model_registry_to_firestore.py
   ```

### Automated Updates

You can add this to your training script to auto-upload:

```python
# At the end of train_models_optimized.py
if __name__ == '__main__':
    # ... training code ...
    
    # Auto-upload to Firestore
    try:
        from scripts.upload_model_registry_to_firestore import upload_registry_to_firestore
        upload_registry_to_firestore('artifacts_optimized/model_registry_optimized.json')
    except Exception as e:
        print(f"Warning: Could not upload to Firestore: {e}")
```

## 🔍 How It Works

### Firestore Structure

```
model_registry/
  └── optimized/
      ├── last_updated: "2025-11-18T14:36:27"
      ├── optimization_enabled: true
      └── leagues/
          ├── "4414": { ... }
          ├── "4446": { ... }
          └── ...

league_metrics/
  ├── "4414": {
  │     league_id: 4414,
  │     league_name: "English Premiership Rugby",
  │     accuracy: 63.0,
  │     training_games: 203,
  │     ai_rating: "6/10",
  │     ...
  │   }
  ├── "4446": { ... }
  └── ...
```

### Cloud Function Access

The `get_league_metrics` function now:
1. **First** tries `league_metrics/{league_id}` (fastest - single document read)
2. **Then** tries `model_registry/optimized` (full registry)
3. **Falls back** to Cloud Storage file
4. **Finally** falls back to local file (development)

## ✅ Verification

### Test the Function

After uploading, test locally or via deployed function:

```python
# Test locally
from firebase_admin import initialize_app, firestore
initialize_app()
db = firestore.client()

# Check if data exists
doc = db.collection('league_metrics').document('4414').get()
if doc.exists:
    print("✅ League metrics found:", doc.to_dict())
else:
    print("❌ League metrics not found")
```

### Test via API

```bash
# Using curl (after deployment)
curl -X POST https://us-central1-rugby-ai-61fd0.cloudfunctions.net/get_league_metrics \
  -H "Content-Type: application/json" \
  -d '{"data": {"league_id": 4414}}'
```

## 🐛 Troubleshooting

### Error: "Could not initialize Firebase Admin"

**Solution**: Set up authentication:
```bash
# Option 1: Application Default Credentials
gcloud auth application-default login

# Option 2: Service Account Key
export GOOGLE_APPLICATION_CREDENTIALS="path/to/key.json"
```

### Error: "Permission denied"

**Solution**: Make sure your account has Firestore write permissions:
1. Go to [IAM & Admin](https://console.cloud.google.com/iam-admin/iam)
2. Find your account
3. Ensure it has "Cloud Datastore User" or "Firebase Admin" role

### Data Not Showing in Cloud Function

**Solution**: 
1. Verify data exists in Firestore Console
2. Check Cloud Function logs for errors
3. Ensure function is reading from correct collection/document

## 📊 Performance Comparison

| Method | Read Time | Update Time | Reliability |
|--------|-----------|-------------|-------------|
| Firestore | ~50-100ms | ~100ms | ⭐⭐⭐⭐⭐ |
| Cloud Storage | ~200-500ms | ~500ms | ⭐⭐⭐⭐ |
| Local File | ~10ms | N/A | ⭐⭐⭐ |

## 🎉 Benefits

✅ **Faster API responses** - Direct database queries  
✅ **Easier updates** - No redeployment needed  
✅ **Better caching** - Firestore client caching  
✅ **Scalable** - Handles concurrent requests well  
✅ **Reliable** - Built-in redundancy and backups  

Your model registry is now optimized for production! 🚀

