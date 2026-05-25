import logging
import os
from pathlib import Path
from typing import Optional, Any, List
from app.core.config import get_settings
from app.core.observability import log_json

logger = logging.getLogger(__name__)
settings = get_settings()

try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False

# Module-level singleton — avoids re-creating the HTTP client on every request
_supabase_client: Optional[Any] = None

def resolve_bucket_and_path(bucket: str, path: str):
    if path and path.startswith("MAIL_ATTACHMENTS/"):
        return "MAIL_ATTACHMENTS", path.replace("MAIL_ATTACHMENTS/", "", 1)
    return bucket, path

def get_supabase_client() -> Optional[Any]:
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client
    if settings.supabase_url and settings.supabase_key and SUPABASE_AVAILABLE:
        try:
            _supabase_client = create_client(settings.supabase_url, settings.supabase_key)
            return _supabase_client
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
    return None

def upload_file(bucket: str, path: str, content: bytes, content_type: str = "application/octet-stream") -> Optional[str]:
    original_path = path
    bucket, path = resolve_bucket_and_path(bucket, path)
    client = get_supabase_client()
    if client:
        try:
            client.storage.from_(bucket).upload(
                path, 
                content, 
                {"content-type": content_type, "upsert": "true"}
            )
            logger.info(f"STORAGE: Uploaded to Supabase bucket: {bucket}")
            return original_path
        except Exception as e:
            logger.error(f"STORAGE: Supabase upload failed for {bucket}/{path}: {e}")
            return None
    logger.error("Supabase client unavailable for upload")
    return None

def download_file(bucket: str, path: str) -> Optional[bytes]:
    bucket, path = resolve_bucket_and_path(bucket, path)
    client = get_supabase_client()
    if client:
        try:
            logger.info(f"STORAGE: Fetching from cloud for {bucket}/{path}")
            return client.storage.from_(bucket).download(path)
        except Exception as e:
            logger.error(f"STORAGE: Cloud download failed for {bucket}/{path}: {e}")
            return None
    return None

def delete_file(bucket: str, path: str):
    bucket, path = resolve_bucket_and_path(bucket, path)
    client = get_supabase_client()
    if client:
        try:
            return client.storage.from_(bucket).remove([path])
        except Exception:
            return []
    return []

def get_signed_url(bucket: str, path: str, expires_in: int = 3600) -> Optional[str]:
    if not path:
        return None
    bucket, path = resolve_bucket_and_path(bucket, path)
    client = get_supabase_client()
    if client:
        try:
            res = client.storage.from_(bucket).create_signed_url(path, expires_in)
            if isinstance(res, dict):
                return res.get("signedURL") or res.get("signedUrl")
            elif isinstance(res, str):
                return res
        except Exception as e:
            logger.warning(f"STORAGE: Failed to get signed URL from cloud: {e}")
    return None

def get_signed_urls(bucket: str, paths: List[str], expires_in: int = 3600) -> dict:
    if not paths:
        return {}
    client = get_supabase_client()
    result_map = {}
    if client:
        try:
            # We must group by actual bucket after resolution
            bucket_groups = {}
            for p in paths:
                b, resolved_p = resolve_bucket_and_path(bucket, p)
                bucket_groups.setdefault(b, []).append((p, resolved_p))
                
            for b, path_pairs in bucket_groups.items():
                resolved_paths = [rp for _, rp in path_pairs]
                res = client.storage.from_(b).create_signed_urls(resolved_paths, expires_in)
                if isinstance(res, list):
                    for i, item in enumerate(res):
                        if not item.get("error"):
                            orig_path = path_pairs[i][0]
                            result_map[orig_path] = item.get("signedURL") or item.get("signedUrl")
        except Exception as e:
            logger.warning(f"STORAGE: Failed to get signed URLs from cloud: {e}")
    return result_map

def get_public_url(bucket: str, path: str) -> Optional[str]:
    if not path:
        return None
    bucket, path = resolve_bucket_and_path(bucket, path)
    client = get_supabase_client()
    if client:
        try:
            res = client.storage.from_(bucket).get_public_url(path)
            if isinstance(res, str):
                return res
        except Exception as e:
            logger.warning(f"STORAGE: Failed to get public URL from cloud: {e}")
    
    return None
