#!/usr/bin/env python3
"""Force update ALL league_metrics documents to ensure they're XGBoost"""
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

leagues_ref = db.collection('league_metrics')
leagues = registry_data.get('leagues', {})

print(f"Force updating ALL {len(leagues)} league_metrics documents...")
print("=" * 60)

for league_id_str, league_data in leagues.items():
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
    
    league_metric = {
        'league_id': int(league_id_str),
        'league_name': league_data.get('name'),
        'accuracy': round(accuracy, 1),
        'training_games': league_data.get('training_games', 0),
        'ai_rating': ai_rating,
        'trained_at': league_data.get('trained_at'),
        'model_type': 'xgboost',  # FORCE XGBoost
        'performance': performance,
        'last_updated': registry_data.get('last_updated')
    }
    
    # Try both string and integer document IDs
    doc_ref_str = leagues_ref.document(league_id_str)
    doc_ref_int = leagues_ref.document(str(int(league_id_str)))
    
    # Update both to be safe
    doc_ref_str.set(league_metric)
    doc_ref_int.set(league_metric)
    
    # Verify
    doc_str = doc_ref_str.get()
    doc_int = doc_ref_int.get()
    
    if doc_str.exists:
        data = doc_str.to_dict()
        status = "OK" if data.get('model_type') == 'xgboost' else "FAILED"
    elif doc_int.exists:
        data = doc_int.to_dict()
        status = "OK" if data.get('model_type') == 'xgboost' else "FAILED"
    else:
        status = "NOT FOUND"
    
    print(f"League {league_id_str}: {league_data.get('name')}")
    print(f"  model_type: xgboost (forced)")
    print(f"  accuracy: {round(accuracy, 1)}%")
    print(f"  Status: {status}")
    print()

print("=" * 60)
print("Force update complete!")

# Now verify by reading back
print("\nVerifying all documents...")
print("=" * 60)

for league_id_str in leagues.keys():
    doc_ref = leagues_ref.document(league_id_str)
    doc = doc_ref.get()
    
    if doc.exists:
        data = doc.to_dict()
        model_type = data.get('model_type', 'unknown')
        accuracy = data.get('accuracy', 0)
        league_name = data.get('league_name', 'Unknown')
        
        status = "OK" if model_type == 'xgboost' else f"FAILED ({model_type})"
        print(f"League {league_id_str} ({league_name}): model_type={model_type}, accuracy={accuracy}% - {status}")
    else:
        print(f"League {league_id_str}: NOT FOUND")

