#!/usr/bin/env python3
"""
Upload model registry to Firestore for faster access by Cloud Functions
"""
import json
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

try:
    from firebase_admin import initialize_app, firestore
    from firebase_admin.credentials import Certificate
except ImportError:
    print("Error: firebase-admin not installed. Install with: pip install firebase-admin")
    sys.exit(1)

def upload_registry_to_firestore(registry_path: str, project_id: str = "rugby-ai-61fd0"):
    """
    Upload model registry JSON to Firestore
    
    Args:
        registry_path: Path to model_registry.json (XGBoost models)
        project_id: Firebase project ID
    """
    try:
        # Initialize Firebase Admin with explicit project ID
        try:
            # Try to initialize with explicit project
            from firebase_admin import get_app
            try:
                app = get_app(project_id)
                print(f"[OK] Using existing Firebase Admin connection for project: {project_id}")
            except ValueError:
                # App doesn't exist, initialize with project
                initialize_app(options={'projectId': project_id})
                print(f"[OK] Initialized Firebase Admin for project: {project_id}")
        except ValueError:
            # Already initialized, continue
            print(f"[OK] Firebase Admin already initialized (using project: {project_id})")
            pass
        except Exception as e:
            print(f"[WARNING] Could not initialize with project {project_id}: {e}")
            print("   Make sure you have:")
            print("   1. Set GOOGLE_APPLICATION_CREDENTIALS environment variable, OR")
            print("   2. Run 'gcloud auth application-default login', OR")
            print("   3. Have a service account key file")
            return False
        
        # Read the registry file
        if not os.path.exists(registry_path):
            print(f"[ERROR] Registry file not found: {registry_path}")
            return False
        
        print(f"Reading registry from: {registry_path}")
        with open(registry_path, 'r') as f:
            registry_data = json.load(f)
        
        # Initialize Firestore (uses the app we initialized above)
        db = firestore.client()
        
        # Determine document name based on model type in registry
        # Check first league's model_type to determine if it's XGBoost or optimized
        first_league = list(registry_data.get('leagues', {}).values())
        if first_league:
            model_type = first_league[0].get('model_type', 'unknown')
            if 'xgboost' in model_type.lower() or 'xgb' in model_type.lower():
                doc_name = 'xgboost'
            elif 'stacking' in model_type.lower() or 'optimized' in model_type.lower():
                doc_name = 'optimized'
            else:
                # Default based on path
                if 'optimized' in registry_path.lower():
                    doc_name = 'optimized'
                else:
                    doc_name = 'xgboost'
        else:
            # Default based on path
            if 'optimized' in registry_path.lower():
                doc_name = 'optimized'
            else:
                doc_name = 'xgboost'
        
        # Upload to Firestore as a single document
        doc_ref = db.collection('model_registry').document(doc_name)
        
        print("Uploading to Firestore...")
        doc_ref.set(registry_data)
        
        print("[OK] Successfully uploaded model registry to Firestore!")
        print(f"   Collection: model_registry")
        print(f"   Document: {doc_name}")
        
        # Also store individual league metrics for easier querying
        print("\nStoring individual league metrics...")
        leagues_ref = db.collection('league_metrics')
        
        leagues = registry_data.get('leagues', {})
        for league_id, league_data in leagues.items():
            performance = league_data.get('performance', {})
            accuracy = performance.get('winner_accuracy', 0.0) * 100
            
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
            
            # Determine default model_type based on which registry this is
            default_model_type = 'xgboost' if doc_name == 'xgboost' else 'stacking'
            
            league_metric = {
                'league_id': int(league_id),
                'league_name': league_data.get('name'),
                'accuracy': round(accuracy, 1),
                'training_games': league_data.get('training_games', 0),
                'ai_rating': ai_rating,
                'trained_at': league_data.get('trained_at'),
                'model_type': league_data.get('model_type', default_model_type),
                'performance': performance,
                'last_updated': registry_data.get('last_updated')
            }
            
            leagues_ref.document(league_id).set(league_metric)
            print(f"   [OK] League {league_id} ({league_data.get('name')}): {accuracy:.1f}% accuracy")
        
        print(f"\n[OK] Successfully stored {len(leagues)} league metrics!")
        return True
        
    except Exception as e:
        print(f"[ERROR] Error uploading to Firestore: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Upload model registry to Firestore')
    parser.add_argument(
        '--registry',
        default='artifacts/model_registry.json',
        help='Path to model registry JSON file'
    )
    parser.add_argument(
        '--project-id',
        default='rugby-ai-61fd0',
        help='Firebase project ID'
    )
    
    args = parser.parse_args()
    
    print("Uploading Model Registry to Firestore")
    print("=" * 50)
    
    success = upload_registry_to_firestore(args.registry, args.project_id)
    
    if success:
        print("\n" + "=" * 50)
        print("[OK] Upload complete!")
        print("\nThe model registry is now available in Firestore:")
        print("  - Collection: model_registry")
        print(f"  - Document: (determined by model_type)")
        print("  - Individual metrics: league_metrics/{league_id}")
        sys.exit(0)
    else:
        print("\n" + "=" * 50)
        print("[ERROR] Upload failed!")
        sys.exit(1)


if __name__ == '__main__':
    main()

