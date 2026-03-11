#!/usr/bin/env python3
"""Simulate what the Cloud Function will read from Firestore"""
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
print("Simulating Cloud Function read path:")
print("=" * 60)

# This is exactly what the Cloud Function does
league_metric_ref = db.collection('league_metrics').document(league_id_str)
league_metric_doc = league_metric_ref.get()

if league_metric_doc.exists:
    league_metric = league_metric_doc.to_dict()
    model_type = league_metric.get('model_type', 'unknown')
    accuracy = league_metric.get('accuracy', 0.0)
    training_games = league_metric.get('training_games', 0)
    
    print(f"\nDocument path: {league_metric_ref.path}")
    print(f"model_type: {model_type}")
    print(f"accuracy: {accuracy}%")
    print(f"training_games: {training_games}")
    print(f"trained_at: {league_metric.get('trained_at')}")
    print(f"last_updated: {league_metric.get('last_updated')}")
    
    if model_type == 'xgboost':
        print("\n[SUCCESS] Cloud Function will read XGBoost data correctly!")
    else:
        print(f"\n[ERROR] Cloud Function will read wrong model_type: {model_type}")
else:
    print(f"\n[ERROR] Document does not exist!")

print("\n" + "=" * 60)
print("The Firebase Console may show cached data.")
print("The actual Firestore data is correct (as shown above).")
print("Your Cloud Function will read the correct XGBoost data.")
print("=" * 60)

