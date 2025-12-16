#!/usr/bin/env python3
"""List all collections in Firestore"""
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
print("All Collections in Firestore:")
print("=" * 70)

# Note: Firestore Admin SDK doesn't have a direct way to list collections
# But we can check the ones we know about and count documents
known_collections = [
    'league_metrics',
    'model_registry',
    'leagues',
    'matches',
    'predictions',
    'seasons',
    'teams'
]

for collection_name in known_collections:
    try:
        docs = list(db.collection(collection_name).stream())
        doc_count = len(docs)
        print(f"\n{collection_name}:")
        print(f"  - {doc_count} documents found")
        
        if doc_count > 0 and collection_name == 'league_metrics':
            print(f"  - Sample documents:")
            for i, doc in enumerate(docs[:3]):  # Show first 3
                data = doc.to_dict()
                print(f"    * {doc.id}: {data.get('league_name', 'Unknown')} (model_type: {data.get('model_type', 'unknown')})")
            if doc_count > 3:
                print(f"    ... and {doc_count - 3} more")
        
        if doc_count > 0 and collection_name == 'model_registry':
            print(f"  - Documents:")
            for doc in docs:
                data = doc.to_dict()
                doc_type = data.get('model_type', 'unknown') if 'model_type' in data else 'registry'
                league_count = len(data.get('leagues', {})) if 'leagues' in data else 0
                print(f"    * {doc.id}: {league_count} leagues (type: {doc_type})")
    
    except Exception as e:
        print(f"\n{collection_name}: ERROR - {e}")

print("\n" + "=" * 70)
print("Note: If a collection doesn't appear in Firebase Console,")
print("try refreshing the page or checking if you're viewing the correct database.")
print("=" * 70)

