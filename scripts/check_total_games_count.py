#!/usr/bin/env python3
"""Check total games count in database"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from prediction.config import LEAGUE_MAPPINGS

db_path = Path(__file__).parent.parent / 'data.sqlite'
if not db_path.exists():
    db_path = Path(__file__).parent.parent / 'rugby-ai-predictor' / 'data.sqlite'

if not db_path.exists():
    print(f"❌ Database not found at {db_path}")
    sys.exit(1)

conn = sqlite3.connect(str(db_path))

# Count total completed games (with scores) across all leagues
league_ids = list(LEAGUE_MAPPINGS.keys())
cursor = conn.execute("""
    SELECT COUNT(*) 
    FROM event 
    WHERE home_score IS NOT NULL 
    AND away_score IS NOT NULL
    AND league_id IN ({})
""".format(','.join(map(str, league_ids))))

total_games = cursor.fetchone()[0]

# Count per league
print("=" * 70)
print("Game Count Analysis:")
print("=" * 70)
print(f"\nTotal completed games across all leagues: {total_games}")
print(f"Threshold for XGBoost training: 900 games")
status = "Meets threshold" if total_games >= 900 else "Below threshold"
status_symbol = "[OK]" if total_games >= 900 else "[FAIL]"
print(f"Status: {status_symbol} {status}")

print(f"\nGames per league:")
for league_id, league_name in LEAGUE_MAPPINGS.items():
    cursor = conn.execute("""
        SELECT COUNT(*) 
        FROM event 
        WHERE home_score IS NOT NULL 
        AND away_score IS NOT NULL
        AND league_id = ?
    """, (league_id,))
    count = cursor.fetchone()[0]
    print(f"  - {league_id} ({league_name}): {count} games")

conn.close()

print("\n" + "=" * 70)
if total_games >= 900:
    print("[OK] Ready to train with XGBoost! Run:")
    print("   python scripts/train_xgboost_models.py --all-leagues")
else:
    print(f"[FAIL] Need {900 - total_games} more games before training XGBoost")
print("=" * 70)

