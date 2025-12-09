"""
Helper module for loading models from Cloud Storage or local filesystem
"""

import os
import tempfile
import logging
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def load_model_from_storage_or_local(
    league_id: int,
    bucket_name: Optional[str] = None,
    local_artifacts_dir: str = 'artifacts_optimized',
    local_artifacts_alt: str = 'artifacts'
) -> str:
    """
    Load model file path, trying Cloud Storage first, then local filesystem
    
    Args:
        league_id: League ID
        bucket_name: Cloud Storage bucket name (if None, only tries local)
        local_artifacts_dir: Primary local directory for models
        local_artifacts_alt: Alternative local directory for models
        
    Returns:
        Path to model file (local path, downloaded from Cloud Storage if needed)
        
    Raises:
        FileNotFoundError: If model not found in any location
    """
    logger.info(f"=== load_model_from_storage_or_local called ===")
    logger.info(f"league_id={league_id}, bucket_name={bucket_name}, local_artifacts_dir={local_artifacts_dir}")
    
    blob_paths = []  # Initialize to avoid unbound variable error
    # Try Cloud Storage first (if bucket_name provided)
    if bucket_name:
        logger.info(f"Attempting to load from Cloud Storage bucket: {bucket_name}")
        try:
            from google.cloud import storage  # type: ignore
            logger.info("google.cloud.storage imported successfully")
            
            # Handle bucket name format - remove gs:// prefix if present
            clean_bucket_name = bucket_name.replace('gs://', '').replace('https://', '').replace('http://', '').split('/')[0]
            logger.info(f"Cleaned bucket name: {clean_bucket_name}")
            
            client = storage.Client()
            logger.info(f"Created storage client, accessing bucket: {clean_bucket_name}")
            bucket = client.bucket(clean_bucket_name)
            
            # First, list what's actually in the bucket for debugging
            logger.info("Listing all blobs in bucket (first 20) for debugging...")
            try:
                all_blobs = list(bucket.list_blobs(max_results=20))
                logger.info(f"Found {len(all_blobs)} blobs in bucket (showing first 20):")
                for blob in all_blobs:
                    logger.info(f"  - {blob.name}")
                
                # Also check for models directory specifically
                models_blobs = list(bucket.list_blobs(prefix="models/", max_results=20))
                logger.info(f"Found {len(models_blobs)} blobs in 'models/' prefix:")
                for blob in models_blobs:
                    logger.info(f"  - {blob.name}")
            except Exception as list_err:
                logger.warning(f"Could not list bucket contents: {list_err}")
            
            # Try optimized model first - check multiple possible paths
            blob_paths = [
                f"models/league_{league_id}_model_optimized.pkl",  # Most likely from upload script
                f"models/artifacts_optimized/league_{league_id}_model_optimized.pkl",
                f"league_{league_id}_model_optimized.pkl",  # Direct in bucket root
                f"artifacts_optimized/league_{league_id}_model_optimized.pkl",  # In artifacts_optimized folder
                f"models/league_{league_id}_model.pkl",
                f"models/artifacts/league_{league_id}_model.pkl",
                f"league_{league_id}_model.pkl",  # Direct in bucket root
                f"artifacts/league_{league_id}_model.pkl"  # In artifacts folder
            ]
            
            logger.info(f"Checking {len(blob_paths)} blob paths in Cloud Storage for league {league_id}...")
            for blob_path in blob_paths:
                logger.debug(f"Checking blob path: {blob_path}")
                try:
                    blob = bucket.blob(blob_path)
                    if blob.exists():
                        logger.info(f"✅ Found model in Cloud Storage: {blob_path}")
                        # Download to temp file
                        temp_dir = tempfile.gettempdir()
                        local_path = os.path.join(temp_dir, f"league_{league_id}_model.pkl")
                        logger.info(f"Downloading to: {local_path}")
                        blob.download_to_filename(local_path)
                        logger.info(f"✅ Model downloaded successfully to {local_path}")
                        return local_path
                    else:
                        logger.debug(f"Blob does not exist: {blob_path}")
                except Exception as blob_error:
                    logger.warning(f"Error checking blob {blob_path}: {blob_error}")
                    continue
            
            logger.warning(f"❌ Model not found in Cloud Storage. Checked {len(blob_paths)} paths.")
        except ImportError as import_error:
            # google-cloud-storage not available, skip Cloud Storage
            logger.warning(f"google-cloud-storage not available: {import_error}")
            logger.warning("Falling back to local filesystem only")
        except Exception as e:
            # Cloud Storage failed, try local
            logger.error(f"❌ Cloud Storage error: {e}", exc_info=True)
            logger.warning("Cloud Storage lookup failed, falling back to local filesystem")
            # Continue to local filesystem check below
    
    # Try local filesystem
    logger.info("Trying local filesystem...")
    local_paths = [
        os.path.join(local_artifacts_dir, f'league_{league_id}_model_optimized.pkl'),
        os.path.join(local_artifacts_alt, f'league_{league_id}_model_optimized.pkl'),
        os.path.join(local_artifacts_dir, f'league_{league_id}_model.pkl'),
        os.path.join(local_artifacts_alt, f'league_{league_id}_model.pkl')
    ]
    
    logger.info(f"Checking {len(local_paths)} local paths...")
    for path in local_paths:
        logger.debug(f"Checking local path: {path}")
        if os.path.exists(path):
            logger.info(f"✅ Found model locally: {path}")
            return path
        else:
            logger.debug(f"Local path does not exist: {path}")
    
    # Not found anywhere
    # Format blob_paths for error message (limit length to avoid huge error messages)
    blob_paths_str = str(blob_paths[:10]) if blob_paths else 'N/A'
    if len(blob_paths) > 10:
        blob_paths_str += f" ... and {len(blob_paths) - 10} more"
    
    error_msg = (
        f"No model found for league {league_id}. "
        f"Checked Cloud Storage bucket '{bucket_name}' (paths: {blob_paths_str}) "
        f"and local paths: {local_paths}"
    )
    logger.error(f"❌ {error_msg}")
    raise FileNotFoundError(error_msg)

