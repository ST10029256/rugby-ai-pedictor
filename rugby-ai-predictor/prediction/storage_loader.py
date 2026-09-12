"""
Helper module for loading models from Cloud Storage only
"""

import os
import tempfile
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

LIVE_MODEL_FAMILY = os.getenv("LIVE_MODEL_FAMILY", "v4").strip().lower()
# Default to strict runtime-first loading. Set ALLOW_LEGACY_MODEL_FALLBACK=1 to opt in.
ALLOW_LEGACY_MODEL_FALLBACK = os.getenv("ALLOW_LEGACY_MODEL_FALLBACK", "0").strip().lower() not in {"0", "false", "no"}


def _load_runtime_assets_from_storage(
    league_id: int,
    bucket_name: str,
    family: str,
) -> Optional[Dict[str, Any]]:
    """
    Download runtime assets for a model family (meta + all seed .pt files).

    Returns None when the required runtime assets are not present.
    """
    if not bucket_name:
        return None
    try:
        from google.cloud import storage  # type: ignore
    except Exception as import_error:
        logger.warning("Could not import google.cloud.storage for %s assets: %s", family, import_error)
        return None

    family_s = str(family or "v4").strip().lower()
    if family_s not in {"v4", "v5"}:
        return None

    clean_bucket_name = bucket_name.replace('gs://', '').replace('https://', '').replace('http://', '').split('/')[0]
    client = storage.Client()
    bucket = client.bucket(clean_bucket_name)

    meta_candidates = [
        f"models/league_{league_id}_model_maz_maxed_{family_s}_meta.pkl",
        f"models/artifacts/league_{league_id}_model_maz_maxed_{family_s}_meta.pkl",
    ]
    meta_blob = None
    for path in meta_candidates:
        b = bucket.blob(path)
        if b.exists():
            meta_blob = b
            break
    if meta_blob is None:
        return None

    seed_prefix = f"models/league_{league_id}_model_maz_maxed_{family_s}_seed_"
    seed_blobs: List[Any] = [
        b for b in bucket.list_blobs(prefix=seed_prefix)
        if b.name.endswith(".pt")
    ]
    if not seed_blobs:
        return None

    # Deterministic order helps reproducibility.
    seed_blobs = sorted(seed_blobs, key=lambda b: b.name)
    temp_dir = tempfile.mkdtemp(prefix=f"{family_s}_assets_league_{league_id}_")
    meta_local = os.path.join(temp_dir, os.path.basename(meta_blob.name))
    meta_blob.download_to_filename(meta_local)
    seed_local_paths: List[str] = []
    for blob in seed_blobs:
        local_path = os.path.join(temp_dir, os.path.basename(blob.name))
        blob.download_to_filename(local_path)
        seed_local_paths.append(local_path)

    return {
        "league_id": int(league_id),
        "meta_path": meta_local,
        "seed_model_paths": seed_local_paths,
        "bucket_name": clean_bucket_name,
        "model_family": family_s,
    }


def load_v4_assets_from_storage(league_id: int, bucket_name: str) -> Optional[Dict[str, Any]]:
    """Backwards-compatible V4 runtime asset loader."""
    return _load_runtime_assets_from_storage(league_id=league_id, bucket_name=bucket_name, family="v4")


def load_v5_assets_from_storage(league_id: int, bucket_name: str) -> Optional[Dict[str, Any]]:
    """V5 runtime asset loader."""
    return _load_runtime_assets_from_storage(league_id=league_id, bucket_name=bucket_name, family="v5")


def model_exists_in_storage(
    league_id: int,
    bucket_name: str,
    preferred_family: Optional[str] = None,
) -> bool:
    """Return True when a trained model is published for this league (no download)."""
    if not bucket_name:
        return False
    try:
        from google.cloud import storage  # type: ignore
    except Exception:
        return False

    clean_bucket_name = (
        bucket_name.replace("gs://", "").replace("https://", "").replace("http://", "").split("/")[0]
    )
    client = storage.Client()
    bucket = client.bucket(clean_bucket_name)

    family = (preferred_family or LIVE_MODEL_FAMILY).strip().lower()
    families: List[str] = [family]
    if family == "v5":
        families.append("v4")

    for fam in families:
        meta_candidates = [
            f"models/league_{league_id}_model_maz_maxed_{fam}_meta.pkl",
            f"models/artifacts/league_{league_id}_model_maz_maxed_{fam}_meta.pkl",
        ]
        meta_found = False
        for path in meta_candidates:
            if bucket.blob(path).exists():
                meta_found = True
                break
        if not meta_found:
            continue
        seed_prefix = f"models/league_{league_id}_model_maz_maxed_{fam}_seed_"
        if any(b.name.endswith(".pt") for b in bucket.list_blobs(prefix=seed_prefix)):
            return True

    if not ALLOW_LEGACY_MODEL_FALLBACK:
        return False

    legacy_blob_paths = [
        f"models/league_{league_id}_model_maz_maxed_v4_runtime.pkl",
        f"models/artifacts/league_{league_id}_model_maz_maxed_v4_runtime.pkl",
        f"models/league_{league_id}_model_xgboost.pkl",
        f"models/artifacts/league_{league_id}_model_xgboost.pkl",
        f"models/league_{league_id}_model_optimized.pkl",
        f"models/artifacts_optimized/league_{league_id}_model_optimized.pkl",
    ]
    return any(bucket.blob(path).exists() for path in legacy_blob_paths)


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
        
        # V4-first path order. Runtime-compatible V4 `.pkl` adapters can be published
        # under these names while retaining legacy fallback support.
        v4_blob_paths = [
            f"models/league_{league_id}_model_maz_maxed_v4_runtime.pkl",
            f"models/artifacts/league_{league_id}_model_maz_maxed_v4_runtime.pkl",
            f"league_{league_id}_model_maz_maxed_v4_runtime.pkl",
            f"artifacts/league_{league_id}_model_maz_maxed_v4_runtime.pkl",
            f"models/league_{league_id}_model_v4.pkl",
            f"models/artifacts/league_{league_id}_model_v4.pkl",
            f"league_{league_id}_model_v4.pkl",
            f"artifacts/league_{league_id}_model_v4.pkl",
        ]
        legacy_blob_paths = [
            f"models/league_{league_id}_model_xgboost.pkl",
            f"models/artifacts/league_{league_id}_model_xgboost.pkl",
            f"league_{league_id}_model_xgboost.pkl",
            f"artifacts/league_{league_id}_model_xgboost.pkl",
            f"models/league_{league_id}_model_optimized.pkl",
            f"models/artifacts_optimized/league_{league_id}_model_optimized.pkl",
            f"league_{league_id}_model_optimized.pkl",
            f"artifacts_optimized/league_{league_id}_model_optimized.pkl",
            f"models/league_{league_id}_model.pkl",
            f"models/artifacts/league_{league_id}_model.pkl",
            f"league_{league_id}_model.pkl",
            f"artifacts/league_{league_id}_model.pkl",
        ]
        if LIVE_MODEL_FAMILY == "v4":
            blob_paths = v4_blob_paths + (legacy_blob_paths if ALLOW_LEGACY_MODEL_FALLBACK else [])
        else:
            blob_paths = legacy_blob_paths

        logger.info(
            "Model family preference=%s, legacy fallback=%s",
            LIVE_MODEL_FAMILY,
            "enabled" if ALLOW_LEGACY_MODEL_FALLBACK else "disabled",
        )
        
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


def _killer_local_dirs() -> List[str]:
    env_dir = str(os.getenv("KILLER_ARTIFACT_DIR") or "").strip()
    here = os.path.dirname(os.path.abspath(__file__))
    functions_root = os.path.dirname(here)
    repo_root = os.path.dirname(functions_root)
    dirs = []
    if env_dir:
        dirs.append(env_dir)
    dirs.extend(
        [
            os.path.join(functions_root, "artifacts_killer_v2"),
            os.path.join(repo_root, "artifacts_killer_v2"),
        ]
    )
    return dirs


def _killer_dir_is_ready(path: str) -> bool:
    if not path or not os.path.isdir(path):
        return False
    if not os.path.isfile(os.path.join(path, "FROZEN.json")):
        return False
    seeds = [
        os.path.join(path, "live_A5_seed_42.pt"),
        os.path.join(path, "live_A5_seed_1337.pt"),
        os.path.join(path, "live_A5_seed_9001.pt"),
    ]
    return all(os.path.isfile(p) for p in seeds)


def _killer_assets_from_dir(path: str) -> Dict[str, Any]:
    return {
        "artifacts_dir": path,
        "seed_model_paths": [
            os.path.join(path, "live_A5_seed_42.pt"),
            os.path.join(path, "live_A5_seed_1337.pt"),
            os.path.join(path, "live_A5_seed_9001.pt"),
        ],
        "model_family": "killer",
    }


def load_local_killer_assets() -> Optional[Dict[str, Any]]:
    """Load Killer V2 freeze weights from disk when present."""
    for path in _killer_local_dirs():
        if _killer_dir_is_ready(path):
            logger.info("Loaded Killer V2 assets from %s", path)
            return _killer_assets_from_dir(path)
    return None


def load_killer_assets_from_storage(bucket_name: Optional[str]) -> Optional[Dict[str, Any]]:
    """Download Killer V2 freeze weights from Cloud Storage, or use a local copy."""
    local = load_local_killer_assets()
    if local:
        return local
    if not bucket_name:
        return None
    try:
        from google.cloud import storage  # type: ignore
    except Exception as import_error:
        logger.warning("Could not import google.cloud.storage for Killer assets: %s", import_error)
        return None

    clean_bucket_name = (
        bucket_name.replace("gs://", "").replace("https://", "").replace("http://", "").split("/")[0]
    )
    client = storage.Client()
    bucket = client.bucket(clean_bucket_name)
    prefixes = ("models/killer_v2/", "models/artifacts_killer_v2/", "killer_v2/")
    required = ("FROZEN.json", "live_A5_seed_42.pt", "live_A5_seed_1337.pt", "live_A5_seed_9001.pt")
    found_prefix = None
    for prefix in prefixes:
        if all(bucket.blob(f"{prefix}{name}").exists() for name in required):
            found_prefix = prefix
            break
    if found_prefix is None:
        logger.warning("Killer V2 freeze weights not found in bucket %s", clean_bucket_name)
        return None

    temp_dir = tempfile.mkdtemp(prefix="killer_v2_assets_")
    for name in required:
        local_path = os.path.join(temp_dir, name)
        bucket.blob(f"{found_prefix}{name}").download_to_filename(local_path)
    logger.info("Downloaded Killer V2 assets from gs://%s/%s", clean_bucket_name, found_prefix)
    return _killer_assets_from_dir(temp_dir)


def killer_assets_available(bucket_name: Optional[str] = None) -> bool:
    if load_local_killer_assets():
        return True
    if not bucket_name:
        return False
    try:
        from google.cloud import storage  # type: ignore
    except Exception:
        return False
    clean_bucket_name = (
        bucket_name.replace("gs://", "").replace("https://", "").replace("http://", "").split("/")[0]
    )
    client = storage.Client()
    bucket = client.bucket(clean_bucket_name)
    required = ("FROZEN.json", "live_A5_seed_42.pt", "live_A5_seed_1337.pt", "live_A5_seed_9001.pt")
    for prefix in ("models/killer_v2/", "models/artifacts_killer_v2/", "killer_v2/"):
        if all(bucket.blob(f"{prefix}{name}").exists() for name in required):
            return True
    return False

