#!/usr/bin/env python3
"""
Match Completion Detector and Retraining Trigger
Detects completed matches and triggers model retraining
"""

import os
import sys
import sqlite3
import json
import logging
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import subprocess

# Add project root to path
script_dir = os.path.dirname(__file__)
project_root = os.path.abspath(os.path.join(script_dir, os.pardir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('match_detection.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

CHECKPOINT_FILE = os.path.join(project_root, "last_checkpoint.json")

# League configurations
LEAGUE_CONFIGS = {
    4986: {"name": "Rugby Championship"},
    4446: {"name": "United Rugby Championship"},
    5069: {"name": "Currie Cup"},
    4574: {"name": "Rugby World Cup"},
    4551: {"name": "Super Rugby"},
    4430: {"name": "French Top 14"},
    4414: {"name": "English Premiership Rugby"},
    4714: {"name": "Six Nations Championship"},
    5479: {"name": "Rugby Union International Friendlies"},
}

def get_last_checkpoint() -> Optional[datetime]:
    """Get the last checkpoint timestamp"""
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, 'r') as f:
                data = json.load(f)
                return datetime.fromisoformat(data["last_check"])
        except Exception as e:
            logger.warning(f"Failed to read checkpoint file: {e}")
    return None


def _read_checkpoint_payload() -> Dict[str, Any]:
    """Read checkpoint payload from disk."""
    if not os.path.exists(CHECKPOINT_FILE):
        return {}
    try:
        with open(CHECKPOINT_FILE, "r") as f:
            payload = json.load(f)
            return payload if isinstance(payload, dict) else {}
    except Exception as e:
        logger.warning(f"Failed to read checkpoint payload: {e}")
        return {}


def completion_state_initialized() -> bool:
    """Return whether completion state has been initialized at least once."""
    payload = _read_checkpoint_payload()
    return bool(payload.get("completion_state_initialized"))

def save_checkpoint(timestamp: datetime) -> None:
    """Save checkpoint timestamp"""
    try:
        with open(CHECKPOINT_FILE, 'w') as f:
            json.dump({"last_check": timestamp.isoformat()}, f)
        logger.info(f"Saved checkpoint: {timestamp.isoformat()}")
    except Exception as e:
        logger.error(f"Failed to save checkpoint: {e}")

def load_completion_state() -> Dict[str, str]:
    """
    Load persisted completion state:
      { "<event_id>": "<home_score>-<away_score>" }
    """
    payload = _read_checkpoint_payload()
    raw = payload.get("completion_state")
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items()}


def save_completion_state(state: Dict[str, str]) -> None:
    """Persist completion state in checkpoint JSON for CI-friendly commits."""
    try:
        payload = _read_checkpoint_payload()
        payload["completion_state"] = state
        payload["completion_state_initialized"] = True
        # Preserve existing checkpoint timestamp if present.
        if "last_check" not in payload:
            payload["last_check"] = datetime.now().isoformat()
        with open(CHECKPOINT_FILE, "w") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
    except Exception as e:
        logger.error(f"Failed to save completion state: {e}")


def detect_completed_matches(db_path: str, previous_state: Dict[str, str]) -> tuple[List[Dict[str, Any]], Dict[str, str]]:
    """
    Detect matches that are newly completed OR whose final score changed.

    Why this method:
    - Avoids missing backfilled past fixtures (e.g., old date_event updated with new scores).
    - Avoids relying on date_event >= checkpoint, which can skip legitimate score updates.
    """
    conn = sqlite3.connect(db_path)
    
    # Query all completed matches. We compare against persisted score state to
    # determine what is new/changed since last run.
    query = """
    SELECT 
        e.id,
        e.league_id,
        e.date_event,
        e.home_team_id,
        e.away_team_id,
        e.home_score,
        e.away_score,
        t1.name as home_team_name,
        t2.name as away_team_name
    FROM event e
    LEFT JOIN team t1 ON e.home_team_id = t1.id
    LEFT JOIN team t2 ON e.away_team_id = t2.id
    WHERE e.home_score IS NOT NULL 
    AND e.away_score IS NOT NULL
    AND e.date_event <= date('now')
    """

    query += " ORDER BY e.date_event DESC"
    
    cursor = conn.cursor()
    cursor.execute(query)
    results = cursor.fetchall()
    
    completed_matches: List[Dict[str, Any]] = []
    current_state: Dict[str, str] = {}

    for row in results:
        match_id = str(row[0])
        score_sig = f"{row[5]}-{row[6]}"
        current_state[match_id] = score_sig

        # New completion or corrected final score -> retrain needed.
        if previous_state.get(match_id) == score_sig:
            continue

        match = {
            "id": row[0],
            "league_id": row[1],
            "date_event": row[2],
            "home_team_id": row[3],
            "away_team_id": row[4],
            "home_score": row[5],
            "away_score": row[6],
            "home_team_name": row[7],
            "away_team_name": row[8],
        }
        completed_matches.append(match)
    
    conn.close()
    return completed_matches, current_state

def get_league_retraining_status(db_path: str) -> tuple[Dict[int, bool], List[Dict[str, Any]], Dict[str, str]]:
    """Check which leagues need retraining based on completed matches"""
    previous_state = load_completion_state()
    completed_matches, current_state = detect_completed_matches(db_path, previous_state)
    
    # Group by league
    leagues_with_new_matches = set()
    for match in completed_matches:
        leagues_with_new_matches.add(match["league_id"])
    
    # Check if any league has new matches
    retraining_needed = {}
    for league_id in LEAGUE_CONFIGS.keys():
        retraining_needed[league_id] = league_id in leagues_with_new_matches
    
    return retraining_needed, completed_matches, current_state

def trigger_model_retraining(leagues_to_retrain: List[int]) -> bool:
    """Trigger model retraining for specific leagues"""
    if not leagues_to_retrain:
        logger.info("No leagues need retraining")
        return True
    
    logger.info(f"Triggering retraining for leagues: {leagues_to_retrain}")
    
    # Run the training script
    train_script = os.path.join(project_root, "scripts", "train_xgboost_models.py")
    
    try:
        result = subprocess.run(
            [sys.executable, train_script],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=1800  # 30 minutes timeout
        )
        
        if result.returncode == 0:
            logger.info("Model retraining completed successfully")
            return True
        else:
            logger.error(f"Model retraining failed: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("Model retraining timed out")
        return False
    except Exception as e:
        logger.error(f"Failed to trigger model retraining: {e}")
        return False

def commit_and_push_changes() -> bool:
    """Commit and push model changes to GitHub"""
    try:
        # Add artifacts directory
        subprocess.run(["git", "add", "artifacts/"], cwd=project_root, check=True)
        
        # Check if there are changes to commit
        result = subprocess.run(
            ["git", "diff", "--staged", "--quiet"], 
            cwd=project_root, 
            capture_output=True
        )
        
        if result.returncode == 0:
            logger.info("No changes to commit")
            return True
        
        # Commit changes
        commit_message = f"Auto-retrain: Updated models after match completion - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        subprocess.run(
            ["git", "commit", "-m", commit_message],
            cwd=project_root,
            check=True
        )
        
        # Push changes
        subprocess.run(["git", "push"], cwd=project_root, check=True)
        
        logger.info("Successfully committed and pushed model updates")
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Git operation failed: {e}")
        return False
    except Exception as e:
        logger.error(f"Failed to commit/push changes: {e}")
        return False

def update_model_registry(completed_matches: List[Dict[str, Any]]) -> None:
    """Update model registry with completion information"""
    registry_file = os.path.join(project_root, "artifacts", "model_registry.json")
    
    if not os.path.exists(registry_file):
        logger.warning("Model registry not found")
        return
    
    try:
        with open(registry_file, 'r') as f:
            registry = json.load(f)
        
        # Add completion tracking
        if "completion_tracking" not in registry:
            registry["completion_tracking"] = {}
        
        for match in completed_matches:
            league_id = match["league_id"]
            if league_id not in registry["completion_tracking"]:
                registry["completion_tracking"][league_id] = []
            
            registry["completion_tracking"][league_id].append({
                "match_id": match["id"],
                "date": match["date_event"],
                "home_team": match["home_team_name"],
                "away_team": match["away_team_name"],
                "home_score": match["home_score"],
                "away_score": match["away_score"],
                "completed_at": datetime.now().isoformat()
            })
        
        # Keep only last 50 completions per league
        for league_id in registry["completion_tracking"]:
            registry["completion_tracking"][league_id] = registry["completion_tracking"][league_id][-50:]
        
        with open(registry_file, 'w') as f:
            json.dump(registry, f, indent=2)
        
        logger.info("Updated model registry with completion tracking")
        
    except Exception as e:
        logger.error(f"Failed to update model registry: {e}")

def main():
    """Main detection and retraining function"""
    parser = argparse.ArgumentParser(description="Detect completed matches and trigger retraining.")
    parser.add_argument("--db", default=os.path.join(project_root, "data.sqlite"), help="Path to SQLite DB.")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("Starting match completion detection and retraining")
    db_path = args.db

    # One-time bootstrap: initialize completion state snapshot without triggering
    # a massive retrain on first run after upgrading detection logic.
    if not completion_state_initialized():
        logger.info("Completion state not initialized - bootstrapping snapshot (no retrain this run)")
        _, current_state = detect_completed_matches(db_path, previous_state={})
        save_completion_state(current_state)
        save_checkpoint(datetime.now())
        logger.info(f"Initialized completion state with {len(current_state)} completed matches")
        return 0
    
    # Check for completed matches
    retraining_needed, completed_matches, current_state = get_league_retraining_status(db_path)
    
    if not completed_matches:
        logger.info("No new completed matches found")
        save_completion_state(current_state)
        save_checkpoint(datetime.now())
        return 0
    
    logger.info(f"Found {len(completed_matches)} completed matches")
    
    # Log completed matches
    for match in completed_matches:
        league_name = LEAGUE_CONFIGS.get(match["league_id"], {}).get("name", "Unknown")
        logger.info(f"Completed: {match['home_team_name']} {match['home_score']}-{match['away_score']} {match['away_team_name']} ({league_name})")
    
    # Determine which leagues need retraining
    leagues_to_retrain = [league_id for league_id, needs_retrain in retraining_needed.items() if needs_retrain]
    
    if not leagues_to_retrain:
        logger.info("No leagues need retraining")
        save_checkpoint(datetime.now())
        return 0
    
    # Create retraining flag file - ALWAYS retrain when completed matches are found
    retrain_flag_file = os.path.join(project_root, "retrain_needed.flag")
    try:
        with open(retrain_flag_file, 'w') as f:
            json.dump({
                "leagues_to_retrain": leagues_to_retrain,
                "completed_matches": completed_matches,
                "timestamp": datetime.now().isoformat(),
                "reason": "completed_matches",
                "trigger": "match_completion_detection",
                "description": f"Found {len(completed_matches)} completed matches - retraining models to capture latest results",
                "match_details": [
                    {
                        "league": LEAGUE_CONFIGS.get(match["league_id"], {}).get("name", "Unknown"),
                        "match": f"{match['home_team_name']} {match['home_score']}-{match['away_score']} {match['away_team_name']}",
                        "date": match["date_event"]
                    } for match in completed_matches
                ]
            }, f, indent=2)
        logger.info(f"Created retraining flag file: {retrain_flag_file}")
        logger.info(f"Leagues to retrain: {leagues_to_retrain}")
        logger.info("🤖 Models will be retrained to capture latest completed match results")
        save_completion_state(current_state)
        save_checkpoint(datetime.now())
        return 0
    except Exception as e:
        logger.error(f"Failed to create retraining flag file: {e}")
        return 1

if __name__ == "__main__":
    exit(main())
