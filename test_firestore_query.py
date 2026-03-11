#!/usr/bin/env python3
"""Test Firestore query exactly like the Cloud Function does"""

import os
import sys
from datetime import datetime, timezone

try:
    from google.cloud import firestore
except ImportError:
    print("❌ google-cloud-firestore not installed")
    print("   Install with: pip install google-cloud-firestore")
    sys.exit(1)

# Test with URC (league_id 4446)
LEAGUE_ID = 4446
LEAGUE_NAME = "United Rugby Championship"
PROJECT_ID = 'rugby-ai-61fd0'

print("=" * 80)
print(f"TESTING FIRESTORE QUERY FOR {LEAGUE_NAME} (ID: {LEAGUE_ID})")
print("=" * 80)

try:
    db = firestore.Client(project=PROJECT_ID)
    matches_ref = db.collection('matches')
    
    print(f"\n1. Querying matches collection for league_id={LEAGUE_ID}...")
    
    # Apply league_id filter (exactly like Cloud Function)
    matches_ref = matches_ref.where('league_id', '==', int(LEAGUE_ID))
    matches_ref = matches_ref.limit(200)
    
    print("2. Streaming matches from Firestore...")
    
    matches = []
    now = datetime.now(timezone.utc)
    total_checked = 0
    with_scores = 0
    past_dates = 0
    no_date = 0
    date_parse_failures = 0
    league_mismatches = 0
    
    for doc in matches_ref.stream():
        total_checked += 1
        match_data = doc.to_dict()
        
        # Check league_id (safety check)
        match_league_id = match_data.get('league_id')
        if match_league_id != int(LEAGUE_ID):
            league_mismatches += 1
            print(f"   ⚠️  League mismatch: {match_league_id} != {LEAGUE_ID} (doc: {doc.id})")
            continue
        
        # Filter out matches with scores
        if match_data.get('home_score') is not None or match_data.get('away_score') is not None:
            with_scores += 1
            continue
        
        # Check date
        date_event = match_data.get('date_event')
        if date_event:
            match_date = None
            is_date_only = False
            
            try:
                # Handle Firestore Timestamp
                if hasattr(date_event, 'timestamp') and callable(getattr(date_event, 'to_datetime', None)):
                    try:
                        match_date = date_event.to_datetime()
                        if match_date.tzinfo is None:
                            match_date = match_date.replace(tzinfo=timezone.utc)
                    except AttributeError:
                        match_date = datetime.fromtimestamp(date_event.timestamp(), tz=timezone.utc)
                elif isinstance(date_event, datetime):
                    match_date = date_event
                    if match_date.tzinfo is None:
                        match_date = match_date.replace(tzinfo=timezone.utc)
                elif isinstance(date_event, str):
                    if 'T' in date_event:
                        match_date = datetime.fromisoformat(date_event.replace('Z', '+00:00'))
                    else:
                        is_date_only = True
                        match_date = datetime.strptime(date_event, '%Y-%m-%d')
                        match_date = match_date.replace(tzinfo=timezone.utc)
            except Exception as e:
                date_parse_failures += 1
                print(f"   ⚠️  Date parse failure for doc {doc.id}: {e}")
                continue
            
            if match_date:
                should_include = False
                if is_date_only:
                    should_include = match_date.date() >= now.date()
                else:
                    should_include = match_date > now
                
                if should_include:
                    matches.append({
                        'id': doc.id,
                        'date_event': match_date.isoformat() if not is_date_only else match_date.date().isoformat(),
                        'home_team_id': match_data.get('home_team_id'),
                        'away_team_id': match_data.get('away_team_id'),
                        'home_team_name': match_data.get('home_team_name'),
                        'away_team_name': match_data.get('away_team_name'),
                    })
                else:
                    past_dates += 1
            else:
                no_date += 1
        else:
            no_date += 1
    
    print("\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80)
    print(f"Total documents checked: {total_checked}")
    print(f"League mismatches: {league_mismatches}")
    print(f"Matches with scores (filtered out): {with_scores}")
    print(f"Past dates (filtered out): {past_dates}")
    print(f"No date: {no_date}")
    print(f"Date parse failures: {date_parse_failures}")
    print(f"\n✅ UPCOMING MATCHES FOUND: {len(matches)}")
    
    if matches:
        print(f"\n📊 First 5 matches:")
        for i, match in enumerate(matches[:5], 1):
            print(f"   {i}. {match.get('home_team_name', 'Unknown')} vs {match.get('away_team_name', 'Unknown')}")
            print(f"      Date: {match.get('date_event')}")
            print(f"      ID: {match.get('id')}")
    else:
        print("\n⚠️  NO MATCHES FOUND!")
        print("\nPossible issues:")
        print("  1. All matches have scores (completed)")
        print("  2. All matches are in the past")
        print("  3. Date parsing is failing")
        print("  4. League ID type mismatch")
        
        # Check a sample document
        print("\n🔍 Checking a sample document...")
        sample_ref = db.collection('matches').where('league_id', '==', int(LEAGUE_ID)).limit(1)
        for doc in sample_ref.stream():
            sample = doc.to_dict()
            print(f"   Sample doc ID: {doc.id}")
            print(f"   league_id: {sample.get('league_id')} (type: {type(sample.get('league_id'))})")
            print(f"   home_score: {sample.get('home_score')}")
            print(f"   away_score: {sample.get('away_score')}")
            print(f"   date_event: {sample.get('date_event')} (type: {type(sample.get('date_event'))})")
            print(f"   home_team_name: {sample.get('home_team_name')}")
            print(f"   away_team_name: {sample.get('away_team_name')}")
            break
    
    print("=" * 80)
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
