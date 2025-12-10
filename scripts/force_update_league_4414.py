#!/usr/bin/env python3
"""Force update league 4414 document to ensure it's XGBoost"""
import json
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

# Load XGBoost registry
registry_path = Path(__file__).parent.parent / "artifacts" / "model_registry.json"
with open(registry_path, 'r') as f:
    registry_data = json.load(f)

league_4414_data = registry_data['leagues']['4414']
performance = league_4414_data.get('performance', {})
accuracy = performance.get('winner_accuracy', 0.0) * 100

if accuracy >= 80:
    ai_rating = '9/10'
elif accuracy >= 75:
    ai_rating = '8/10'
elif accuracy >= 70:
    ai_rating = '7/10'
elif accuracy >= 65:
    ai_rating = '6/10'
elif accuracy >= 60:
    ai_rating = '5/10'
else:
    ai_rating = '4/10'

league_metric = {
    'league_id': 4414,
    'league_name': league_4414_data.get('name'),
    'accuracy': round(accuracy, 1),
    'training_games': league_4414_data.get('training_games', 0),
    'ai_rating': ai_rating,
    'trained_at': league_4414_data.get('trained_at'),
    'model_type': 'xgboost',  # Force this
    'performance': performance,
    'last_updated': registry_data.get('last_updated')
}

print(f"Force updating league_metrics/4414...")
print(f"  model_type: xgboost")
print(f"  accuracy: {round(accuracy, 1)}%")
print(f"  trained_at: {league_4414_data.get('trained_at')}")

# Force update
leagues_ref = db.collection('league_metrics')
doc_ref = leagues_ref.document('4414')
doc_ref.set(league_metric)

# Verify it was written
doc = doc_ref.get()
if doc.exists:
    data = doc.to_dict()
    print(f"\nVerification:")
    print(f"  model_type: {data.get('model_type')} (expected: xgboost)")
    print(f"  accuracy: {data.get('accuracy')}% (expected: {round(accuracy, 1)}%)")
    
    if data.get('model_type') == 'xgboost' and abs(data.get('accuracy', 0) - round(accuracy, 1)) < 0.1:
        print(f"\n[OK] Document successfully updated!")
    else:
        print(f"\n[ERROR] Document still incorrect!")
else:
    print("[ERROR] Document doesn't exist after update!")

