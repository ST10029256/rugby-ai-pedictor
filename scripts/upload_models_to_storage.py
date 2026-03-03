#!/usr/bin/env python3
"""
Upload ML models to Firebase Cloud Storage
"""

import os
import sys
from pathlib import Path
from google.cloud import storage
from typing import List

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def upload_models_to_storage(
    bucket_name: str = 'rugby-ai-61fd0.firebasestorage.app',
    models_dir: str = 'artifacts',
    dry_run: bool = False,
    only_v4: bool = True,
) -> List[str]:
    """
    Upload all model files to Cloud Storage
    
    Args:
        bucket_name: Name of the Cloud Storage bucket
        models_dir: Directory containing model files
        dry_run: If True, only print what would be uploaded
        
    Returns:
        List of uploaded file paths
    """
    if not os.path.exists(models_dir):
        print(f"Error: Models directory not found: {models_dir}")
        return []
    
    # Find all supported model/report artifacts.
    # V4 runtime assets are primarily .pt + .pkl (meta) plus .json reports.
    model_files = []
    allowed_ext = ('.pkl', '.json', '.pt')
    for root, dirs, files in os.walk(models_dir):
        for file in files:
            if not file.endswith(allowed_ext):
                continue
            full_path = os.path.join(root, file)
            if only_v4 and 'v4' not in file.lower():
                continue
            model_files.append(full_path)
    
    if not model_files:
        print(f"No model files found in {models_dir}")
        return []
    
    mode_text = "V4-only" if only_v4 else "all supported artifacts"
    print(f"Found {len(model_files)} model files to upload ({mode_text})")
    
    if dry_run:
        print("\n[DRY RUN] Would upload:")
        for file_path in model_files:
            print(f"  {file_path}")
        return []
    
    # Initialize Cloud Storage client
    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)
    except Exception as e:
        print(f"Error connecting to Cloud Storage: {e}")
        print("Make sure you're authenticated: gcloud auth application-default login")
        return []
    
    uploaded = []
    
    for file_path in model_files:
        try:
            # Get relative path from models_dir
            rel_path = os.path.relpath(file_path, models_dir)
            blob_name = f"models/{rel_path}"
            
            # Upload file
            blob = bucket.blob(blob_name)
            blob.upload_from_filename(file_path)
            
            print(f"[OK] Uploaded: {blob_name} ({os.path.getsize(file_path) / 1024 / 1024:.2f} MB)")
            uploaded.append(blob_name)
        except Exception as e:
            print(f"[ERROR] Failed to upload {file_path}: {e}")
    
    return uploaded


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Upload ML model artifacts to Cloud Storage")
    parser.add_argument('--bucket', default='rugby-ai-61fd0.firebasestorage.app', help='Cloud Storage bucket name')
    parser.add_argument('--models-dir', default='artifacts', help='Directory containing model artifacts')
    parser.add_argument('--dry-run', action='store_true', help='Dry run (no upload)')
    parser.add_argument(
        '--include-legacy',
        action='store_true',
        help='Include non-v4 artifacts (default behavior uploads only files with v4 in filename)',
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Upload ML Models to Cloud Storage")
    print("=" * 60)
    print(f"Bucket: {args.bucket}")
    print(f"Models Directory: {args.models_dir}")
    print()
    
    uploaded = upload_models_to_storage(
        bucket_name=args.bucket,
        models_dir=args.models_dir,
        dry_run=args.dry_run,
        only_v4=not args.include_legacy,
    )
    
    if not args.dry_run:
        print("\n" + "=" * 60)
        print(f"[OK] Uploaded {len(uploaded)} files")
        print("=" * 60)
    else:
        print("\n[DRY RUN] No files were uploaded")
        print("Run without --dry-run to perform actual upload")


if __name__ == '__main__':
    main()

