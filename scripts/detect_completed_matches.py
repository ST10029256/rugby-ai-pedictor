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

# League configurations
LEAGUE_CONFIGS = {
    4986: {"name": "Rugby Championship"},
    4446: {"name": "United Rugby Championship"},
    5069: {"name": "Currie Cup"},
    4574: {"name": "Rugby World Cup"},
}

def get_last_checkpoint() -> Optional[datetime]:
    """Get the last checkpoint timestamp"""
    checkpoint_file = os.path.join(project_root, "last_checkpoint.json")
    if os.path.exists(checkpoint_file):
        try:
            with open(checkpoint_file, 'r') as f:
                data = json.load(f)
                return datetime.fromisoformat(data["last_check"])
        except Exception as e:
            logger.warning(f"Failed to read checkpoint file: {e}")
    return None

def save_checkpoint(timestamp: datetime) -> None:
    """Save checkpoint timestamp"""
    checkpoint_file = os.path.join(project_root, "last_checkpoint.json")
    try:
        with open(checkpoint_file, 'w') as f:
            json.dump({"last_check": timestamp.isoformat()}, f)
        logger.info(f"Saved checkpoint: {timestamp.isoformat()}")
    except Exception as e:
        logger.error(f"Failed to save checkpoint: {e}")

def detect_completed_matches(db_path: str, last_check: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Detect matches that have been completed since last check"""
    conn = sqlite3.connect(db_path)
    
    # Query for matches that have scores but were previously without scores
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
    
    if last_check:
        query += " AND e.date_event >= ?"
        params = (last_check.strftime('%Y-%m-%d'),)
    else:
        # If no last check, look at matches from last 7 days
        query += " AND e.date_event >= date('now', '-7 days')"
        params = ()
    
    query += " ORDER BY e.date_event DESC"
    
    cursor = conn.cursor()
    cursor.execute(query, params)
    results = cursor.fetchall()
    
    completed_matches = []
    for row in results:
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
    return completed_matches

def get_league_retraining_status() -> tuple[Dict[int, bool], List[Dict[str, Any]]]:
    """Check which leagues need retraining based on completed matches"""
    db_path = os.path.join(project_root, "data.sqlite")
    last_check = get_last_checkpoint()
    
    completed_matches = detect_completed_matches(db_path, last_check)
    
    # Group by league
    leagues_with_new_matches = set()
    for match in completed_matches:
        leagues_with_new_matches.add(match["league_id"])
    
    # Check if any league has new matches
    retraining_needed = {}
    for league_id in LEAGUE_CONFIGS.keys():
        retraining_needed[league_id] = league_id in leagues_with_new_matches
    
    return retraining_needed, completed_matches

def trigger_model_retraining(leagues_to_retrain: List[int]) -> bool:
    """Trigger model retraining for specific leagues"""
    if not leagues_to_retrain:
        logger.info("No leagues need retraining")
        return True
    
    logger.info(f"Triggering retraining for leagues: {leagues_to_retrain}")
    
    # Run the training script
    train_script = os.path.join(project_root, "scripts", "train_models.py")
    
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
    logger.info("Starting match completion detection and retraining")
    
    # Check for completed matches
    retraining_needed, completed_matches = get_league_retraining_status()
    
    if not completed_matches:
        logger.info("No new completed matches found")
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
    
    # Create retraining flag file
    retrain_flag_file = os.path.join(project_root, "retrain_needed.flag")
    try:
        with open(retrain_flag_file, 'w') as f:
            json.dump({
                "leagues_to_retrain": leagues_to_retrain,
                "completed_matches": completed_matches,
                "timestamp": datetime.now().isoformat(),
                "reason": "completed_matches"
            }, f, indent=2)
        logger.info(f"Created retraining flag file: {retrain_flag_file}")
        logger.info(f"Leagues to retrain: {leagues_to_retrain}")
        save_checkpoint(datetime.now())
        return 0
    except Exception as e:
        logger.error(f"Failed to create retraining flag file: {e}")
        return 1

if __name__ == "__main__":
    exit(main())
