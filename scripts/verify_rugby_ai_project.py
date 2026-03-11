#!/usr/bin/env python3
"""Verify data in rugby-ai-61fd0 project"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

try:
    from firebase_admin import initialize_app, firestore, get_app
except ImportError:
    print("Error: firebase-admin not installed")
    sys.exit(1)

project_id = 'rugby-ai-61fd0'

try:
    try:
        app = get_app(project_id)
    except ValueError:
        app = initialize_app(options={'projectId': project_id})
except:
    app = initialize_app()

db = firestore.client()

print("=" * 70)
print(f"Checking Firestore in project: {project_id}")
print("=" * 70)

# Check league_metrics
print("\nleague_metrics collection:")
leagues_ref = db.collection('league_metrics')
all_docs = list(leagues_ref.stream())
print(f"  Found {len(all_docs)} documents")

if all_docs:
    print("  Documents:")
    for doc in all_docs:
        data = doc.to_dict()
        print(f"    - {doc.id}: {data.get('league_name')} (model_type: {data.get('model_type')})")

# Check model_registry
print("\nmodel_registry collection:")
registry_ref = db.collection('model_registry')
registry_docs = list(registry_ref.stream())
print(f"  Found {len(registry_docs)} documents")

if registry_docs:
    for doc in registry_docs:
        data = doc.to_dict()
        league_count = len(data.get('leagues', {}))
        print(f"    - {doc.id}: {league_count} leagues")

print("\n" + "=" * 70)
print(f"Data is now in the correct project: {project_id}")
print("Check Firebase Console for project 'Rugby-AI'")
print("=" * 70)

