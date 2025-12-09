# Firebase Migration Guide

This guide explains how to migrate the Rugby AI Predictor from Streamlit to Firebase.

## Architecture Overview

### Current (Streamlit)
- **Frontend**: Streamlit Python app
- **Backend**: Python scripts running on server
- **Database**: SQLite (data.sqlite)
- **Deployment**: Streamlit Cloud

### New (Firebase)
- **Frontend**: React web app (hosted on Firebase Hosting)
- **Backend**: Firebase Cloud Functions (Python)
- **Database**: Firestore (NoSQL)
- **Storage**: Cloud Storage (for ML models)
- **Deployment**: Firebase Hosting + Cloud Functions

## Project Structure

```
.
├── firebase.json              # Firebase configuration
├── .firebaserc                # Firebase project settings
├── firestore.rules            # Firestore security rules
├── firestore.indexes.json    # Firestore indexes
├── storage.rules              # Cloud Storage rules
├── functions/                 # Cloud Functions (Python backend)
│   ├── main.py               # HTTP endpoints
│   ├── requirements.txt      # Python dependencies
│   └── prediction/           # Prediction modules (copy from root)
├── public/                    # React frontend (to be created)
│   ├── index.html
│   ├── src/
│   └── package.json
└── [existing files...]
```

## Migration Steps

### 1. Set Up Firebase Project

```bash
# Install Firebase CLI
npm install -g firebase-tools

# Login to Firebase
firebase login

# Initialize Firebase project
firebase init

# Select:
# - Firestore
# - Functions
# - Hosting
# - Storage
```

### 2. Set Up Cloud Functions

```bash
cd functions
pip install -r requirements.txt

# Copy prediction modules
cp -r ../prediction .
```

### 3. Migrate Database to Firestore

Create a migration script to convert SQLite to Firestore:

```python
# scripts/migrate_to_firestore.py
import sqlite3
from google.cloud import firestore

# Connect to SQLite
conn = sqlite3.connect('data.sqlite')
cursor = conn.cursor()

# Connect to Firestore
db = firestore.Client()

# Migrate teams
cursor.execute("SELECT * FROM team")
teams = cursor.fetchall()
for team in teams:
    db.collection('teams').document(str(team[0])).set({
        'id': team[0],
        'name': team[2],
        'league_id': team[1],
        # ... other fields
    })

# Migrate matches
cursor.execute("SELECT * FROM event")
events = cursor.fetchall()
for event in events:
    db.collection('matches').document(str(event[0])).set({
        'id': event[0],
        'league_id': event[1],
        'home_team_id': event[2],
        'away_team_id': event[3],
        'date_event': event[4],
        'home_score': event[5],
        'away_score': event[6],
        # ... other fields
    })
```

### 4. Upload ML Models to Cloud Storage

```python
# scripts/upload_models.py
from google.cloud import storage

client = storage.Client()
bucket = client.bucket('your-project-id.appspot.com')

# Upload all model files
import os
for root, dirs, files in os.walk('artifacts_optimized'):
    for file in files:
        if file.endswith('.pkl'):
            blob = bucket.blob(f'models/{file}')
            blob.upload_from_filename(os.path.join(root, file))
```

### 5. Create React Frontend

```bash
cd public
npx create-react-app . --template typescript
npm install firebase @mui/material @emotion/react @emotion/styled
```

### 6. Update Prediction Modules

Modify prediction modules to work with Firestore instead of SQLite:

- Update `prediction/db.py` to use Firestore client
- Update model loading to fetch from Cloud Storage
- Update feature building to query Firestore

### 7. Deploy

```bash
# Deploy functions
firebase deploy --only functions

# Deploy hosting
firebase deploy --only hosting

# Deploy Firestore rules
firebase deploy --only firestore:rules

# Deploy storage rules
firebase deploy --only storage
```

## API Endpoints

### Cloud Functions HTTP Endpoints

- `POST /predict_match` - Get match prediction
- `GET /get_upcoming_matches?league_id=4986` - Get upcoming matches
- `GET /get_live_matches?league_id=4986` - Get live matches
- `GET /get_leagues` - Get available leagues
- `GET /health_check` - Health check

## Environment Variables

Set in Firebase Console > Functions > Configuration:

- `HIGHLIGHTLY_API_KEY`
- `SPORTDEVS_API_KEY`
- `THESPORTSDB_API_KEY`
- `DB_PATH` (if using local SQLite, otherwise use Firestore)

## Benefits of Firebase

1. **Scalability**: Auto-scales with traffic
2. **Performance**: CDN for static assets, edge functions
3. **Real-time**: Firestore real-time listeners
4. **Security**: Built-in authentication and security rules
5. **Cost**: Pay-as-you-go pricing
6. **Mobile**: Easy to add mobile apps later

## Next Steps

1. Create React frontend components
2. Implement Firestore queries in prediction modules
3. Set up Cloud Storage for models
4. Migrate database
5. Test and deploy

