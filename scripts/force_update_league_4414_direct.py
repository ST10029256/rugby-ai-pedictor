#!/usr/bin/env python3
"""Force update league_metrics/4414 with EXPLICIT XGBoost data"""
import json
import sys
from pathlib import Path
from datetime import datetime

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

league_id_str = "4414"
league_data = registry_data.get('leagues', {}).get(league_id_str)

if not league_data:
    print(f"ERROR: League {league_id_str} not found in registry!")
    sys.exit(1)

performance = league_data.get('performance', {})
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

# Create the document with EXPLICIT XGBoost values
league_metric = {
    'league_id': int(league_id_str),
    'league_name': league_data.get('name'),
    'accuracy': round(accuracy, 1),
    'training_games': league_data.get('training_games', 0),
    'ai_rating': ai_rating,
    'trained_at': league_data.get('trained_at'),
    'model_type': 'xgboost',  # EXPLICITLY FORCE XGBoost
    'performance': {
        'home_mae': performance.get('home_mae'),
        'away_mae': performance.get('away_mae'),
        'overall_mae': performance.get('overall_mae'),
        'winner_accuracy': performance.get('winner_accuracy')
    },
    'last_updated': datetime.now().isoformat()  # Current timestamp
}

print("=" * 60)
print("FORCE UPDATING league_metrics/4414")
print("=" * 60)
print(f"\nData to write:")
print(f"  model_type: {league_metric['model_type']}")
print(f"  accuracy: {league_metric['accuracy']}%")
print(f"  training_games: {league_metric['training_games']}")
print(f"  trained_at: {league_metric['trained_at']}")
print(f"  last_updated: {league_metric['last_updated']}")

# Read BEFORE update
leagues_ref = db.collection('league_metrics')
doc_ref = leagues_ref.document(league_id_str)
before_doc = doc_ref.get()

if before_doc.exists:
    before_data = before_doc.to_dict()
    print(f"\nBEFORE update:")
    print(f"  model_type: {before_data.get('model_type')}")
    print(f"  accuracy: {before_data.get('accuracy')}")
    print(f"  training_games: {before_data.get('training_games')}")
else:
    print("\nBEFORE update: Document does not exist")

# Write the document
print(f"\nWriting to league_metrics/{league_id_str}...")
doc_ref.set(league_metric)
print("[OK] Write completed")

# Read AFTER update
after_doc = doc_ref.get()

if after_doc.exists:
    after_data = after_doc.to_dict()
    print(f"\nAFTER update (read back):")
    print(f"  model_type: {after_data.get('model_type')}")
    print(f"  accuracy: {after_data.get('accuracy')}")
    print(f"  training_games: {after_data.get('training_games')}")
    print(f"  trained_at: {after_data.get('trained_at')}")
    print(f"  last_updated: {after_data.get('last_updated')}")
    
    if after_data.get('model_type') == 'xgboost':
        print("\n[SUCCESS] Document now has model_type='xgboost'")
    else:
        print(f"\n[ERROR] Document still has model_type='{after_data.get('model_type')}'")
        print("Something is overwriting our update!")
else:
    print("\n[ERROR] Document does not exist after update!")

print("\n" + "=" * 60)
print("If the console still shows 'stacking', try:")
print("1. Refresh the Firebase Console")
print("2. Clear browser cache")
print("3. Wait 10 seconds and check again")
print("=" * 60)

