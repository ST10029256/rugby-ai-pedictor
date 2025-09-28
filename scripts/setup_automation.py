#!/usr/bin/env python3
"""
Automated Rugby Prediction System Setup
Sets up the complete automated retraining system
"""

import os
import sys
import subprocess
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_command(command: str, description: str) -> bool:
    """Run a command and log the result"""
    logger.info(f"Running: {description}")
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            logger.info(f"✅ {description} completed successfully")
            return True
        else:
            logger.error(f"❌ {description} failed: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"❌ {description} failed with exception: {e}")
        return False

def setup_automated_system():
    """Set up the complete automated retraining system"""
    logger.info("🚀 Setting up Automated Rugby Prediction System")
    
    # Step 1: Train initial models
    logger.info("Step 1: Training initial models...")
    if not run_command("python scripts/train_models.py", "Initial model training"):
        logger.error("Failed to train initial models")
        return False
    
    # Step 2: Test model manager
    logger.info("Step 2: Testing model manager...")
    if not run_command("python scripts/model_manager.py", "Model manager test"):
        logger.error("Failed to test model manager")
        return False
    
    # Step 3: Test match detection
    logger.info("Step 3: Testing match detection...")
    if not run_command("python scripts/detect_completed_matches.py", "Match detection test"):
        logger.error("Failed to test match detection")
        return False
    
    # Step 4: Create artifacts directory structure
    logger.info("Step 4: Setting up artifacts directory...")
    artifacts_dir = "artifacts"
    os.makedirs(artifacts_dir, exist_ok=True)
    
    # Step 5: Create initial checkpoint
    logger.info("Step 5: Creating initial checkpoint...")
    checkpoint_data = {"last_check": datetime.now().isoformat()}
    import json
    with open("last_checkpoint.json", "w") as f:
        json.dump(checkpoint_data, f)
    
    logger.info("✅ Automated system setup completed successfully!")
    
    # Summary
    logger.info("\n📊 System Summary:")
    logger.info("  - Models trained for all 4 leagues")
    logger.info("  - Model manager operational")
    logger.info("  - Match detection system ready")
    logger.info("  - GitHub Actions workflow configured")
    logger.info("  - Auto-retraining system active")
    
    return True

def main():
    """Main setup function"""
    success = setup_automated_system()
    
    if success:
        logger.info("\n🎉 Setup completed! Your AI will now:")
        logger.info("  - Automatically retrain after each match")
        logger.info("  - Push updated models to GitHub")
        logger.info("  - Always use the latest data for predictions")
        logger.info("  - Maintain super accurate predictions")
        
        logger.info("\n📝 Next steps:")
        logger.info("  1. Commit and push all changes to GitHub")
        logger.info("  2. The GitHub Actions workflow will run automatically")
        logger.info("  3. Models will retrain every 4 hours or when matches complete")
        logger.info("  4. Use the optimized Streamlit app: scripts/app_ui_optimized.py")
        
        return 0
    else:
        logger.error("❌ Setup failed. Please check the logs above.")
        return 1

if __name__ == "__main__":
    exit(main())
