"""
Helper module for loading models from Cloud Storage only
"""

import os
import tempfile
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def load_model_from_storage(
    league_id: int,
    bucket_name: str
) -> str:
    """
    Load model file from Cloud Storage only
    
    Args:
        league_id: League ID
        bucket_name: Cloud Storage bucket name (required)
        
    Returns:
        Path to model file (local temp path, downloaded from Cloud Storage)
        
    Raises:
        FileNotFoundError: If model not found in Cloud Storage
        ValueError: If bucket_name is not provided
    """
    logger.info(f"=== load_model_from_storage called ===")
    logger.info(f"league_id={league_id}, bucket_name={bucket_name}")
    
    if not bucket_name:
        error_msg = "bucket_name is required. Cannot load models without Cloud Storage bucket."
        logger.error(f"❌ {error_msg}")
        raise ValueError(error_msg)
    
    blob_paths = []
    logger.info(f"Attempting to load from Cloud Storage bucket: {bucket_name}")
    
    try:
        from google.cloud import storage  # type: ignore
        logger.info("google.cloud.storage imported successfully")
    except ImportError as import_error:
        error_msg = f"google-cloud-storage not available: {import_error}. Cannot load models from Cloud Storage."
        logger.error(f"❌ {error_msg}")
        raise ImportError(error_msg) from import_error
    
    # Handle bucket name format - remove gs:// prefix if present
    clean_bucket_name = bucket_name.replace('gs://', '').replace('https://', '').replace('http://', '').split('/')[0]
    logger.info(f"Cleaned bucket name: {clean_bucket_name}")
    
    try:
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
        
        # Not found in Cloud Storage
        blob_paths_str = str(blob_paths[:10]) if len(blob_paths) > 10 else str(blob_paths)
        if len(blob_paths) > 10:
            blob_paths_str += f" ... and {len(blob_paths) - 10} more"
        
        error_msg = (
            f"No model found for league {league_id} in Cloud Storage bucket '{bucket_name}'. "
            f"Checked paths: {blob_paths_str}"
        )
        logger.error(f"❌ {error_msg}")
        raise FileNotFoundError(error_msg)
        
    except FileNotFoundError:
        # Re-raise FileNotFoundError as-is
        raise
    except Exception as e:
        # Any other error from Cloud Storage
        error_msg = f"Error accessing Cloud Storage bucket '{bucket_name}': {e}"
        logger.error(f"❌ {error_msg}", exc_info=True)
        raise RuntimeError(error_msg) from e

