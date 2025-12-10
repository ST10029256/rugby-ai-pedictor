#!/usr/bin/env python3
"""Directly verify what's in Firestore right now"""
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

# Check league_metrics/4414
doc_ref = db.collection('league_metrics').document('4414')
doc = doc_ref.get()

print("=" * 60)
print("Direct Firestore read for league_metrics/4414:")
print("=" * 60)

if doc.exists:
    data = doc.to_dict()
    print(f"Document exists: YES")
    print(f"model_type: {data.get('model_type')}")
    print(f"accuracy: {data.get('accuracy')}")
    print(f"training_games: {data.get('training_games')}")
    print(f"trained_at: {data.get('trained_at')}")
    print(f"last_updated: {data.get('last_updated')}")
    print(f"\nFull document:")
    import json
    print(json.dumps(data, indent=2, default=str))
else:
    print("Document does NOT exist!")

print("\n" + "=" * 60)
print("Checking league_metrics/4430:")
print("=" * 60)

doc_ref2 = db.collection('league_metrics').document('4430')
doc2 = doc_ref2.get()

if doc2.exists:
    data2 = doc2.to_dict()
    print(f"Document exists: YES")
    print(f"model_type: {data2.get('model_type')}")
    print(f"accuracy: {data2.get('accuracy')}")
    print(f"training_games: {data2.get('training_games')}")
    print(f"trained_at: {data2.get('trained_at')}")
else:
    print("Document does NOT exist!")

