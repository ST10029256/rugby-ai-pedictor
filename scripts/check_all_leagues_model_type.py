#!/usr/bin/env python3
"""Check model_type for ALL leagues in Firestore"""
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
print("Checking model_type for ALL leagues in league_metrics:")
print("=" * 70)

leagues_ref = db.collection('league_metrics')
all_docs = leagues_ref.stream()

all_correct = True
for doc in all_docs:
    data = doc.to_dict()
    league_id = doc.id
    league_name = data.get('league_name', 'Unknown')
    model_type = data.get('model_type', 'unknown')
    accuracy = data.get('accuracy', 0)
    last_updated = data.get('last_updated', 'N/A')
    
    status = "OK" if model_type == 'xgboost' else "FAILED"
    if model_type != 'xgboost':
        all_correct = False
    
    print(f"[{status}] League {league_id} ({league_name}):")
    print(f"   model_type: {model_type}")
    print(f"   accuracy: {accuracy}%")
    print(f"   last_updated: {last_updated}")
    print()

print("=" * 70)
if all_correct:
    print("[SUCCESS] ALL leagues have model_type='xgboost' in Firestore!")
    print("\nIf Firebase Console shows different data, it's likely cached.")
    print("Try:")
    print("  1. Hard refresh (Ctrl+F5 or Cmd+Shift+R)")
    print("  2. Clear browser cache")
    print("  3. Wait a few minutes for Console to sync")
    print("  4. Your Cloud Functions will read the CORRECT data!")
else:
    print("[ERROR] Some leagues still have incorrect model_type!")
print("=" * 70)

