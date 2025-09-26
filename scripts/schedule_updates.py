#!/usr/bin/env python3
"""
Simple scheduler script to run automatic updates for upcoming games.
This can be run via cron, Windows Task Scheduler, or GitHub Actions.
"""

import subprocess
import sys
import os
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('auto_update.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def run_auto_pull():
    """Run the auto pull script with appropriate parameters."""
    try:
        # Get the directory where this script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        auto_pull_script = os.path.join(script_dir, "auto_pull_upcoming.py")
        
        # Run the auto pull script
        cmd = [
            sys.executable, 
            auto_pull_script,
            "--db", "data.sqlite",
            "--days-ahead", "60",  # Look 60 days ahead
            "--verbose"
        ]
        
        logger.info(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=os.path.dirname(script_dir))
        
        if result.returncode == 0:
            logger.info("Auto pull completed successfully")
            logger.info(f"Output: {result.stdout}")
        else:
            logger.error(f"Auto pull failed with return code {result.returncode}")
            logger.error(f"Error: {result.stderr}")
            
        return result.returncode == 0
        
    except Exception as e:
        logger.error(f"Error running auto pull: {e}")
        return False


def main():
    """Main function to run the scheduled update."""
    logger.info("=" * 50)
    logger.info("STARTING SCHEDULED RUGBY DATA UPDATE")
    logger.info(f"Timestamp: {datetime.now()}")
    logger.info("=" * 50)
    
    success = run_auto_pull()
    
    logger.info("=" * 50)
    if success:
        logger.info("SCHEDULED UPDATE COMPLETED SUCCESSFULLY")
    else:
        logger.error("SCHEDULED UPDATE FAILED")
    logger.info(f"Timestamp: {datetime.now()}")
    logger.info("=" * 50)
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
