#!/usr/bin/env python3
"""Check ALL possible Firestore documents for a league"""
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

league_id = 4414
league_id_str = str(league_id)

print("=" * 60)
print(f"Checking ALL possible documents for league {league_id}:")
print("=" * 60)

# Check league_metrics collection with string ID
print(f"\n1. league_metrics/{league_id_str} (string):")
doc_ref = db.collection('league_metrics').document(league_id_str)
doc = doc_ref.get()
if doc.exists:
    data = doc.to_dict()
    print(f"   EXISTS: model_type={data.get('model_type')}, accuracy={data.get('accuracy')}, training_games={data.get('training_games')}, trained_at={data.get('trained_at')}")
else:
    print("   NOT FOUND")

# Check with integer ID (as string)
print(f"\n2. league_metrics/{int(league_id_str)} (int as string):")
doc_ref = db.collection('league_metrics').document(str(int(league_id_str)))
doc = doc_ref.get()
if doc.exists:
    data = doc.to_dict()
    print(f"   EXISTS: model_type={data.get('model_type')}, accuracy={data.get('accuracy')}, training_games={data.get('training_games')}, trained_at={data.get('trained_at')}")
else:
    print("   NOT FOUND")

# List all documents in league_metrics collection
print(f"\n3. All documents in league_metrics collection:")
all_docs = db.collection('league_metrics').stream()
found_4414 = False
for doc in all_docs:
    doc_data = doc.to_dict()
    if doc.id == league_id_str or doc_data.get('league_id') == league_id:
        found_4414 = True
        print(f"   Document ID: {doc.id}")
        print(f"   Data: model_type={doc_data.get('model_type')}, accuracy={doc_data.get('accuracy')}, training_games={doc_data.get('training_games')}, trained_at={doc_data.get('trained_at')}")

if not found_4414:
    print(f"   No document found with league_id={league_id}")

# Check model_registry/xgboost
print(f"\n4. model_registry/xgboost:")
registry_ref = db.collection('model_registry').document('xgboost')
registry_doc = registry_ref.get()
if registry_doc.exists:
    registry = registry_doc.to_dict()
    league_data = registry.get('leagues', {}).get(league_id_str)
    if league_data:
        print(f"   EXISTS: model_type={league_data.get('model_type')}, accuracy={league_data.get('performance', {}).get('winner_accuracy', 0) * 100}%, training_games={league_data.get('training_games')}")
    else:
        print(f"   Document exists but no data for league {league_id_str}")
else:
    print("   NOT FOUND")

# Check model_registry/optimized
print(f"\n5. model_registry/optimized:")
registry_ref = db.collection('model_registry').document('optimized')
registry_doc = registry_ref.get()
if registry_doc.exists:
    registry = registry_doc.to_dict()
    league_data = registry.get('leagues', {}).get(league_id_str)
    if league_data:
        print(f"   EXISTS: model_type={league_data.get('model_type')}, accuracy={league_data.get('performance', {}).get('winner_accuracy', 0) * 100}%, training_games={league_data.get('training_games')}")
    else:
        print(f"   Document exists but no data for league {league_id_str}")
else:
    print("   NOT FOUND")

print("\n" + "=" * 60)

