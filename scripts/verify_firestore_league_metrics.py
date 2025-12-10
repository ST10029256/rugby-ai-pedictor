#!/usr/bin/env python3
"""
Verify and force-update league_metrics documents in Firestore
"""
import json
import sys
import platform
from pathlib import Path

# Fix Windows encoding
if platform.system() == 'Windows':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.append(str(Path(__file__).parent.parent))

try:
    from firebase_admin import initialize_app, firestore
except ImportError:
    print("Error: firebase-admin not installed. Install with: pip install firebase-admin")
    sys.exit(1)

def verify_and_fix_league_metrics():
    """Verify and fix league_metrics documents"""
    try:
        initialize_app()
        db = firestore.client()
        
        # Load XGBoost registry
        registry_path = Path(__file__).parent.parent / "artifacts" / "model_registry.json"
        with open(registry_path, 'r') as f:
            registry_data = json.load(f)
        
        leagues_ref = db.collection('league_metrics')
        leagues = registry_data.get('leagues', {})
        
        print("Verifying league_metrics documents...")
        print("=" * 60)
        
        for league_id, league_data in leagues.items():
            doc_ref = leagues_ref.document(league_id)
            doc = doc_ref.get()
            
            performance = league_data.get('performance', {})
            accuracy = performance.get('winner_accuracy', 0.0) * 100
            model_type = league_data.get('model_type', 'unknown')
            
            if doc.exists:
                current_data = doc.to_dict()
                current_type = current_data.get('model_type', 'unknown')
                current_acc = current_data.get('accuracy', 0)
                
                print(f"\nLeague {league_id} ({league_data.get('name')}):")
                print(f"  Current: model_type={current_type}, accuracy={current_acc}%")
                print(f"  Expected: model_type={model_type}, accuracy={round(accuracy, 1)}%")
                
                if current_type != model_type or abs(current_acc - round(accuracy, 1)) > 0.1:
                    print(f"  ❌ MISMATCH - Updating...")
                    # Calculate AI rating
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
                        'league_id': int(league_id),
                        'league_name': league_data.get('name'),
                        'accuracy': round(accuracy, 1),
                        'training_games': league_data.get('training_games', 0),
                        'ai_rating': ai_rating,
                        'trained_at': league_data.get('trained_at'),
                        'model_type': model_type,
                        'performance': performance,
                        'last_updated': registry_data.get('last_updated')
                    }
                    
                    doc_ref.set(league_metric)
                    print(f"  [OK] Updated!")
                else:
                    print(f"  [OK] Correct")
            else:
                print(f"\nLeague {league_id}: ❌ Document does not exist - Creating...")
                # Calculate AI rating
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
                    'league_id': int(league_id),
                    'league_name': league_data.get('name'),
                    'accuracy': round(accuracy, 1),
                    'training_games': league_data.get('training_games', 0),
                    'ai_rating': ai_rating,
                    'trained_at': league_data.get('trained_at'),
                    'model_type': model_type,
                    'performance': performance,
                    'last_updated': registry_data.get('last_updated')
                }
                
                doc_ref.set(league_metric)
                print(f"  [OK] Created!")
        
        print("\n" + "=" * 60)
        print("Verification complete!")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    verify_and_fix_league_metrics()

