# Database Migration Guide: SQLite → Firestore

## Overview

This guide explains how to migrate your SQLite database to Firestore for the Firebase app.

## What Will Be Migrated

- **6 leagues** → `leagues` collection
- **177 teams** → `teams` collection  
- **1,943 matches** → `matches` collection
- **77 seasons** → `seasons` collection

**Total: 2,203 records**

## Prerequisites

1. **Install Google Cloud Firestore client:**
   ```bash
   pip install google-cloud-firestore
   ```

2. **Authenticate with Google Cloud:**
   ```bash
   gcloud auth application-default login
   ```
   Or set the `GOOGLE_APPLICATION_CREDENTIALS` environment variable.

## Migration Steps

### Step 1: Dry Run (Recommended First)

Test the migration without writing data:

```bash
python scripts/migrate_to_firestore.py --dry-run
```

This will show you:
- How many records will be migrated
- Any potential issues
- No data will be written to Firestore

### Step 2: Run Actual Migration

Once you're satisfied with the dry run:

```bash
python scripts/migrate_to_firestore.py
```

This will:
- Read all data from `data.sqlite`
- Write to Firestore collections
- Use batch writes (500 records at a time) for efficiency
- Show progress as it migrates

### Step 3: Verify Migration

Check your Firestore console:
https://console.firebase.google.com/project/rugby-ai-61fd0/firestore

You should see:
- `leagues` collection with 6 documents
- `teams` collection with 177 documents
- `matches` collection with 1,943 documents
- `seasons` collection with 77 documents

## Migration Options

```bash
# Skip specific collections
python scripts/migrate_to_firestore.py --skip-leagues
python scripts/migrate_to_firestore.py --skip-teams
python scripts/migrate_to_firestore.py --skip-events
python scripts/migrate_to_firestore.py --skip-seasons

# Use different database file
python scripts/migrate_to_firestore.py --db path/to/database.sqlite

# Use different Firebase project
python scripts/migrate_to_firestore.py --project-id your-project-id
```

## Firestore Collections Structure

### `leagues` Collection
```
leagues/{league_id}
  - id: int
  - name: string
  - sport: string
  - alternate_name: string
  - country: string
  - migrated_at: timestamp
```

### `teams` Collection
```
teams/{team_id}
  - id: int
  - league_id: int
  - name: string
  - short_name: string
  - alternate_name: string
  - stadium: string
  - formed_year: int
  - country: string
  - migrated_at: timestamp
```

### `matches` Collection
```
matches/{event_id}
  - id: int
  - league_id: int
  - season: string
  - date_event: datetime (or string)
  - timestamp: string
  - round: int
  - home_team_id: int
  - away_team_id: int
  - home_score: int (or null for upcoming)
  - away_score: int (or null for upcoming)
  - venue: string
  - status: string
  - migrated_at: timestamp
```

### `seasons` Collection
```
seasons/{league_id}_{season}
  - league_id: int
  - season: string
  - migrated_at: timestamp
```

## After Migration

1. **Update Cloud Functions** to use Firestore instead of SQLite
2. **Test the functions** to ensure they can read from Firestore
3. **Update prediction modules** to query Firestore

## Cost Estimate

- **Writes**: 2,203 writes = ~$0.00 (within free tier)
- **Storage**: ~1-2 MB = **FREE** (within 5 GB free tier)
- **Reads**: Will be charged per read, but very minimal

**Total cost: $0/month** for your current data size.

## Troubleshooting

### Error: "Could not find default credentials"
```bash
gcloud auth application-default login
```

### Error: "Permission denied"
Make sure your Google account has Firestore permissions in the Firebase project.

### Error: "Project not found"
Check your project ID in `.firebaserc` or use `--project-id` flag.

## Next Steps

After migration:
1. Update `prediction/db.py` to use Firestore
2. Update `prediction/features.py` to query Firestore
3. Test predictions to ensure they work with Firestore data

