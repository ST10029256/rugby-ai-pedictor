# Setting Up Firestore Database

## Error Message
```
404 The database (default) does not exist for project rugby-ai-61fd0
```

## Solution: Create Firestore Database

You need to create the Firestore database first. Here are two ways:

### Option 1: Via Firebase Console (Recommended)

1. **Visit the Firestore setup page:**
   https://console.cloud.google.com/datastore/setup?project=rugby-ai-61fd0

2. **Or go to Firebase Console:**
   https://console.firebase.google.com/project/rugby-ai-61fd0/firestore

3. **Click "Create database"**

4. **Choose mode:**
   - **Native mode** (recommended) - Full Firestore features
   - **Datastore mode** - Legacy mode

5. **Select location:**
   - Choose `africa-south1` (South Africa) - matches your earlier selection
   - Or `us-central1` (Iowa) - default, good for most use cases

6. **Security rules:**
   - Start in **test mode** (for development)
   - Or use the rules from `firestore.rules` file

7. **Click "Create"**

### Option 2: Via gcloud CLI

```bash
gcloud firestore databases create --location=africa-south1 --project=rugby-ai-61fd0
```

Or for us-central1:
```bash
gcloud firestore databases create --location=us-central1 --project=rugby-ai-61fd0
```

## After Creating the Database

Once the database is created, you can run the migration:

```bash
python scripts/migrate_to_firestore.py
```

## Important Notes

- **Location matters**: Choose the same location you selected during `firebase init` (africa-south1)
- **Native mode**: Use Native mode (not Datastore mode) for full Firestore features
- **First database is free**: The first database in a project is free

## Quick Setup Link

Click here to create the database:
https://console.firebase.google.com/project/rugby-ai-61fd0/firestore

