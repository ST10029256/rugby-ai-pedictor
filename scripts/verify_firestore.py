#!/usr/bin/env python3
"""Quick script to verify Firestore data"""

from google.cloud import firestore

db = firestore.Client(project='rugby-ai-61fd0')

print("=" * 60)
print("Firestore Data Verification")
print("=" * 60)

# Check leagues
leagues = list(db.collection('leagues').stream())
print(f"\n[OK] Leagues: {len(leagues)}")
for doc in sorted(leagues, key=lambda x: int(x.id)):
    data = doc.to_dict()
    print(f"  {doc.id}: {data.get('name', 'N/A')}")

# Check teams
teams = list(db.collection('teams').stream())
print(f"\n[OK] Teams: {len(teams)}")

# Check matches
matches = list(db.collection('matches').stream())
print(f"[OK] Matches: {len(matches)}")

# Check seasons
seasons = list(db.collection('seasons').stream())
print(f"[OK] Seasons: {len(seasons)}")

print("\n" + "=" * 60)
print(f"Total Records: {len(leagues) + len(teams) + len(matches) + len(seasons)}")
print("=" * 60)

