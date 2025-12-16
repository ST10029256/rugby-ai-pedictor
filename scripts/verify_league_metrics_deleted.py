#!/usr/bin/env python3
"""Verify if league_metrics documents are deleted"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

try:
    from firebase_admin import initialize_app, firestore
except ImportError:
    print("Error: firebase-admin not installed")
    sys.exit(1)

initialize_app()
db = firestore.client()

print("=" * 70)
print("Checking if league_metrics documents exist in Firestore:")
print("=" * 70)

leagues_ref = db.collection('league_metrics')
all_docs = list(leagues_ref.stream())

if not all_docs:
    print("\n[CONFIRMED] No documents found - all league_metrics are deleted!")
    print("The collection is empty.")
else:
    print(f"\n[FOUND] {len(all_docs)} documents still exist:")
    for doc in all_docs:
        data = doc.to_dict()
        league_id = doc.id
        league_name = data.get('league_name', 'Unknown')
        model_type = data.get('model_type', 'unknown')
        print(f"  - {league_id} ({league_name}): model_type={model_type}")

print("\n" + "=" * 70)

