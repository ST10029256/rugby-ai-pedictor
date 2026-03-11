#!/usr/bin/env python3
"""Check Firebase connection and project details"""
import sys
from pathlib import Path
import os

sys.path.append(str(Path(__file__).parent.parent))

try:
    from firebase_admin import initialize_app, firestore
    from firebase_admin import get_app
except ImportError:
    print("Error: firebase-admin not installed")
    sys.exit(1)

try:
    app = initialize_app()
except ValueError:
    app = get_app()  # Already initialized

# Get project ID from environment or app
project_id = os.environ.get('GOOGLE_CLOUD_PROJECT') or os.environ.get('GCLOUD_PROJECT')
if not project_id:
    try:
        project_id = app.project_id
    except:
        pass

print("=" * 70)
print("Firebase Connection Details:")
print("=" * 70)
print(f"Project ID: {project_id or 'Unknown (check GOOGLE_CLOUD_PROJECT env var)'}")
print()

# Check Firestore
db = firestore.client()
print("Checking Firestore collections...")

# Count documents in each collection
collections_to_check = ['league_metrics', 'model_registry', 'leagues', 'matches', 'predictions', 'seasons', 'teams']

print("\nCollection Status:")
print("-" * 70)
for coll_name in collections_to_check:
    try:
        docs = list(db.collection(coll_name).limit(1).stream())
        # Count total documents
        all_docs = list(db.collection(coll_name).stream())
        count = len(all_docs)
        status = "EXISTS" if count > 0 else "EMPTY"
        print(f"  {coll_name:20s}: {status:8s} ({count} documents)")
    except Exception as e:
        print(f"  {coll_name:20s}: ERROR - {e}")

print("\n" + "=" * 70)
print("To see these in Firebase Console:")
print("  1. Go to https://console.firebase.google.com/")
print(f"  2. Select project: {project_id or 'your-project'}")
print("  3. Go to Firestore Database")
print("  4. Check the Data tab")
print("  5. Look for 'league_metrics' and 'model_registry' collections")
print("=" * 70)

