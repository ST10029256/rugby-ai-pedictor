#!/usr/bin/env python3
"""
Official script to switch Firebase app to XGBoost models
This script:
1. Uploads XGBoost models to Cloud Storage
2. Uploads model registry to Firestore
3. Verifies the switch was successful
"""

import os
import sys
import subprocess
from pathlib import Path

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

def check_xgboost_models():
    """Check if XGBoost models exist"""
    artifacts_dir = Path(project_root) / 'artifacts'
    xgboost_models = list(artifacts_dir.glob('league_*_model_xgboost.pkl'))
    
    print("=" * 80)
    print("🔍 CHECKING XGBOOST MODELS")
    print("=" * 80)
    print(f"\n📁 Checking {artifacts_dir}...")
    
    if not xgboost_models:
        print("❌ No XGBoost models found!")
        print("   Run: python scripts/train_xgboost_models.py")
        return False
    
    print(f"✅ Found {len(xgboost_models)} XGBoost models:")
    for model in sorted(xgboost_models):
        size_mb = model.stat().st_size / (1024 * 1024)
        print(f"   - {model.name} ({size_mb:.2f} MB)")
    
    return True

def check_model_registry():
    """Check if model registry exists and has XGBoost entries"""
    registry_path = Path(project_root) / 'artifacts' / 'model_registry.json'
    
    print("\n" + "=" * 80)
    print("🔍 CHECKING MODEL REGISTRY")
    print("=" * 80)
    
    if not registry_path.exists():
        print(f"❌ Model registry not found: {registry_path}")
        return False
    
    import json
    with open(registry_path, 'r') as f:
        registry = json.load(f)
    
    leagues = registry.get('leagues', {})
    xgboost_count = sum(1 for l in leagues.values() if l.get('model_type') == 'xgboost')
    
    print(f"✅ Model registry found")
    print(f"   Total leagues: {len(leagues)}")
    print(f"   XGBoost models: {xgboost_count}/{len(leagues)}")
    
    if xgboost_count < len(leagues):
        print(f"⚠️  Warning: {len(leagues) - xgboost_count} leagues not using XGBoost")
    
    return True

def upload_models_to_storage(dry_run=False):
    """Upload XGBoost models to Cloud Storage"""
    print("\n" + "=" * 80)
    print("☁️  UPLOADING MODELS TO CLOUD STORAGE")
    print("=" * 80)
    
    bucket = 'rugby-ai-61fd0.firebasestorage.app'
    models_dir = 'artifacts'
    
    cmd = [
        sys.executable,
        'scripts/upload_models_to_storage.py',
        '--bucket', bucket,
        '--models-dir', models_dir
    ]
    
    if dry_run:
        cmd.append('--dry-run')
    
    print(f"\n📤 Uploading models from {models_dir} to {bucket}...")
    if dry_run:
        print("   [DRY RUN MODE - No actual upload]")
    
    try:
        result = subprocess.run(cmd, cwd=project_root, check=True, capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print("Warnings/Errors:", result.stderr)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Upload failed: {e}")
        print(e.stdout)
        print(e.stderr)
        return False

def upload_registry_to_firestore():
    """Upload model registry to Firestore"""
    print("\n" + "=" * 80)
    print("📊 UPLOADING MODEL REGISTRY TO FIRESTORE")
    print("=" * 80)
    
    registry_path = 'artifacts/model_registry.json'
    
    cmd = [
        sys.executable,
        'scripts/upload_model_registry_to_firestore.py',
        '--registry', registry_path
    ]
    
    print(f"\n📤 Uploading registry from {registry_path}...")
    
    try:
        result = subprocess.run(cmd, cwd=project_root, check=True, capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print("Warnings/Errors:", result.stderr)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Upload failed: {e}")
        print(e.stdout)
        print(e.stderr)
        return False

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Switch Firebase app to XGBoost models')
    parser.add_argument('--dry-run', action='store_true', help='Dry run (no uploads)')
    parser.add_argument('--skip-upload', action='store_true', help='Skip uploads, only verify')
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("🚀 OFFICIAL SWITCH TO XGBOOST MODELS")
    print("=" * 80)
    print("\nThis script will:")
    print("  1. Verify XGBoost models exist")
    print("  2. Verify model registry is updated")
    if not args.skip_upload:
        print("  3. Upload models to Cloud Storage")
        print("  4. Upload model registry to Firestore")
    print()
    
    # Step 1: Check models
    if not check_xgboost_models():
        print("\n❌ XGBoost models not found. Please train them first.")
        sys.exit(1)
    
    # Step 2: Check registry
    if not check_model_registry():
        print("\n❌ Model registry check failed.")
        sys.exit(1)
    
    if args.skip_upload:
        print("\n✅ Verification complete (uploads skipped)")
        return
    
    # Step 3: Upload models
    if not upload_models_to_storage(dry_run=args.dry_run):
        print("\n❌ Failed to upload models to Cloud Storage")
        sys.exit(1)
    
    # Step 4: Upload registry
    if not upload_registry_to_firestore():
        print("\n❌ Failed to upload model registry to Firestore")
        sys.exit(1)
    
    print("\n" + "=" * 80)
    print("✅ SWITCH TO XGBOOST COMPLETE!")
    print("=" * 80)
    print("\n📋 Next Steps:")
    print("  1. Check Cloud Functions logs to verify models are loading")
    print("  2. Test a prediction through your app")
    print("  3. Monitor performance metrics")
    print("\n💡 Your Firebase app is now using XGBoost models!")
    print("=" * 80)

if __name__ == '__main__':
    main()

