#!/usr/bin/env python3
"""
Complete Automation Script for All 4 Leagues
Automatically pulls results, retrains AI, and updates predictions for all leagues
"""

import argparse
import sqlite3
import os
import sys
import logging
import subprocess
from datetime import datetime
from typing import Dict, List, Any

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, os.pardir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# All 4 leagues configuration
ALL_LEAGUES = {
    4986: {"name": "Rugby Championship", "sportsdb_id": 4986},
    4446: {"name": "United Rugby Championship", "sportsdb_id": 4446}, 
    5069: {"name": "Currie Cup", "sportsdb_id": 5069},
    4574: {"name": "Rugby World Cup", "sportsdb_id": 4574}
}

def run_script(script_name: str, description: str) -> bool:
    """Run a script and return success status."""
    try:
        logger.info(f"🔄 {description}...")
        result = subprocess.run([
            sys.executable, 
            os.path.join(script_dir, script_name)
        ], capture_output=True, text=True, cwd=project_root)
        
        if result.returncode == 0:
            logger.info(f"✅ {description} completed successfully")
            if result.stdout:
                logger.debug(f"Output: {result.stdout}")
            return True
        else:
            logger.error(f"❌ {description} failed")
            if result.stderr:
                logger.error(f"Error: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error running {script_name}: {e}")
        return False

def check_database_status() -> Dict[str, Any]:
    """Check the current status of all leagues in the database."""
    conn = sqlite3.connect('data.sqlite')
    cursor = conn.cursor()
    
    status = {}
    
    for league_id, league_info in ALL_LEAGUES.items():
        league_name = league_info['name']
        
        # Count total games
        cursor.execute("SELECT COUNT(*) FROM event WHERE league_id = ?", (league_id,))
        total_games = cursor.fetchone()[0]
        
        # Count completed games
        cursor.execute("""
            SELECT COUNT(*) FROM event 
            WHERE league_id = ? AND home_score IS NOT NULL AND away_score IS NOT NULL
        """, (league_id,))
        completed_games = cursor.fetchone()[0]
        
        # Count upcoming games
        cursor.execute("""
            SELECT COUNT(*) FROM event 
            WHERE league_id = ? AND (home_score IS NULL OR away_score IS NULL)
        """, (league_id,))
        upcoming_games = cursor.fetchone()[0]
        
        # Get latest game date
        cursor.execute("""
            SELECT MAX(date_event) FROM event WHERE league_id = ?
        """, (league_id,))
        latest_date = cursor.fetchone()[0]
        
        status[league_name] = {
            'total_games': total_games,
            'completed_games': completed_games,
            'upcoming_games': upcoming_games,
            'latest_date': latest_date,
            'completion_rate': completed_games / total_games * 100 if total_games > 0 else 0
        }
    
    conn.close()
    return status

def main():
    """Main automation function for all leagues."""
    parser = argparse.ArgumentParser(description='Complete automation for all 4 rugby leagues')
    parser.add_argument('--db', default='data.sqlite', help='Database file path')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    parser.add_argument('--skip-update', action='store_true', help='Skip data update, only retrain')
    parser.add_argument('--skip-retrain', action='store_true', help='Skip retraining, only update data')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    logger.info("🚀 Starting complete automation for ALL 4 rugby leagues")
    logger.info("🏉 Leagues: Rugby Championship, URC, Currie Cup, Rugby World Cup")
    
    # Check initial database status
    logger.info("\n📊 INITIAL DATABASE STATUS:")
    initial_status = check_database_status()
    for league_name, stats in initial_status.items():
        logger.info(f"   {league_name}: {stats['completed_games']}/{stats['total_games']} completed ({stats['completion_rate']:.1f}%)")
    
    success_count = 0
    total_steps = 0
    
    # Step 1: Update all games from TheSportsDB
    if not args.skip_update:
        total_steps += 1
        if run_script('enhanced_auto_update.py', 'Updating all games from TheSportsDB'):
            success_count += 1
    
    # Step 2: Check for completed matches
    if not args.skip_update:
        total_steps += 1
        if run_script('detect_completed_matches.py', 'Detecting completed matches'):
            success_count += 1
    
    # Step 3: Retrain models for all leagues
    if not args.skip_retrain:
        total_steps += 1
        if run_script('train_models.py', 'Retraining AI models for all leagues'):
            success_count += 1
    
    # Step 4: Verify model updates
    if not args.skip_retrain:
        total_steps += 1
        if run_script('test_frontend_integration.py', 'Verifying model updates'):
            success_count += 1
    
    # Check final database status
    logger.info("\n📊 FINAL DATABASE STATUS:")
    final_status = check_database_status()
    for league_name, stats in final_status.items():
        logger.info(f"   {league_name}: {stats['completed_games']}/{stats['total_games']} completed ({stats['completion_rate']:.1f}%)")
    
    # Summary
    logger.info(f"\n🎉 AUTOMATION COMPLETE!")
    logger.info(f"   Steps completed: {success_count}/{total_steps}")
    logger.info(f"   Success rate: {success_count/total_steps*100:.1f}%" if total_steps > 0 else "   No steps executed")
    
    if success_count == total_steps:
        logger.info("✅ All leagues updated and AI retrained successfully!")
        logger.info("🔄 The system will automatically:")
        logger.info("   - Pull new results every 2 hours")
        logger.info("   - Retrain AI when games are completed")
        logger.info("   - Update predictions in the frontend")
        logger.info("   - Push changes to GitHub")
    else:
        logger.warning("⚠️ Some steps failed - check logs for details")
    
    return success_count == total_steps

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
