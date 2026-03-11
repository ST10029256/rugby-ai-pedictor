#!/usr/bin/env python3
"""Delete all league_metrics documents from Firestore"""
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
print("Deleting ALL league_metrics documents from Firestore...")
print("=" * 70)

leagues_ref = db.collection('league_metrics')
all_docs = list(leagues_ref.stream())

if not all_docs:
    print("\nNo documents found in league_metrics collection.")
    sys.exit(0)

print(f"\nFound {len(all_docs)} documents to delete:")
for doc in all_docs:
    data = doc.to_dict()
    league_id = doc.id
    league_name = data.get('league_name', 'Unknown')
    print(f"  - {league_id} ({league_name})")

print("\nDeleting...")
deleted_count = 0
for doc in all_docs:
    doc.reference.delete()
    deleted_count += 1
    print(f"  [OK] Deleted {doc.id}")

print("\n" + "=" * 70)
print(f"[SUCCESS] Deleted {deleted_count} documents from league_metrics")
print("=" * 70)
print("\nNext step: Run the upload script to recreate them:")
print("  python scripts/upload_model_registry_to_firestore.py")
print("=" * 70)

