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
    family_filter: str = "",
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
    
    active_family_filter = (family_filter or "").strip().lower()
    if not active_family_filter and only_v4:
        active_family_filter = "v4"

    # Find all supported model/report artifacts.
    model_files = []
    allowed_ext = ('.pkl', '.json', '.pt')
    for root, dirs, files in os.walk(models_dir):
        for file in files:
            if not file.endswith(allowed_ext):
                continue
            full_path = os.path.join(root, file)
            if active_family_filter and active_family_filter not in file.lower():
                continue
            model_files.append(full_path)
    
    if not model_files:
        print(f"No model files found in {models_dir}")
        return []
    
    mode_text = f"{active_family_filter.upper()}-only" if active_family_filter else "all supported artifacts"
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
        '--family-filter',
        default='',
        help='Only upload artifacts whose filename contains this family tag (for example: v4 or v5)',
    )
    parser.add_argument(
        '--include-legacy',
        action='store_true',
        help='Include all supported artifacts regardless of model family filter',
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
        family_filter=("" if args.include_legacy else args.family_filter),
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

