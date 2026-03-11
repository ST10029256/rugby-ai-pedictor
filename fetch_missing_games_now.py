#!/usr/bin/env python3
"""Quick script to fetch all missing games right now"""

import subprocess
import sys

print("=" * 80)
print("Fetching All Missing Games")
print("=" * 80)
print()
print("This will:")
print("  1. Fetch all upcoming games from all leagues (automatic round scanning)")
print("  2. Update the database with missing games")
print("  3. Show you how many games were added")
print()
print("Running enhanced_auto_update.py...")
print("-" * 80)

try:
    # Run the update script
    result = subprocess.run(
        [sys.executable, "scripts/enhanced_auto_update.py", "--db", "data.sqlite", "--days-ahead", "365", "--days-back", "14"],
        capture_output=True,
        text=True
    )
    
    print(result.stdout)
    if result.stderr:
        print("Errors:", result.stderr)
    
    print("-" * 80)
    print("✅ Update complete!")
    print()
    print("Next steps:")
    print("  1. Run 'python check_missing_games_all_leagues.py' again to verify")
    print("  2. Run 'python scripts/sync_to_firestore.py' to sync to Firestore")
    print()
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
