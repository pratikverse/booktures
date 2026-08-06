"""
Storage provider abstraction for generated output files (illustrations).
Local disk by default; Supabase Storage or Cloudflare R2 for deployments
on ephemeral/read-only filesystems. Selected via STORAGE_PROVIDER.
"""

import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

STORAGE_ROOT = Path(__file__).resolve().parents[1] / "storage"


class StorageProvider:
    def save(self, data: bytes, key: str, content_type: str = "application/octet-stream") -> Optional[str]:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError


class LocalStorageProvider(StorageProvider):
    """Writes to the local storage/ dir, served via the /storage static mount."""

    def save(self, data: bytes, key: str, content_type: str = "application/octet-stream") -> Optional[str]:
        path = STORAGE_ROOT / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return f"storage/{key}"

    def delete(self, key: str) -> None:
        path = STORAGE_ROOT / key
        try:
            path.unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"Local delete failed for {key}: {e}")


class SupabaseStorageProvider(StorageProvider):
    """Uploads to a Supabase Storage bucket via its REST API."""

    def save(self, data: bytes, key: str, content_type: str = "application/octet-stream") -> Optional[str]:
        import httpx

        base_url = os.getenv("SUPABASE_URL", "").rstrip("/")
        service_key = os.getenv("SUPABASE_SERVICE_KEY")
        bucket = os.getenv("SUPABASE_BUCKET", "booktures")
        if not base_url or not service_key:
            logger.warning("SUPABASE_URL/SUPABASE_SERVICE_KEY not set; skipping upload.")
            return None

        try:
            response = httpx.put(
                f"{base_url}/storage/v1/object/{bucket}/{key}",
                headers={
                    "Authorization": f"Bearer {service_key}",
                    "apikey": service_key,
                    "Content-Type": content_type,
                    "x-upsert": "true",
                },
                content=data,
                timeout=60.0,
            )
            response.raise_for_status()
            return f"{base_url}/storage/v1/object/public/{bucket}/{key}"
        except Exception as e:
            logger.error(f"Supabase upload failed for {key}: {e}")
            return None

    def delete(self, key: str) -> None:
        import httpx

        base_url = os.getenv("SUPABASE_URL", "").rstrip("/")
        service_key = os.getenv("SUPABASE_SERVICE_KEY")
        bucket = os.getenv("SUPABASE_BUCKET", "booktures")
        if not base_url or not service_key:
            return
        try:
            httpx.delete(
                f"{base_url}/storage/v1/object/{bucket}/{key}",
                headers={"Authorization": f"Bearer {service_key}", "apikey": service_key},
                timeout=30.0,
            )
        except Exception as e:
            logger.warning(f"Supabase delete failed for {key}: {e}")


class CloudflareR2Provider(StorageProvider):
    """Uploads to a Cloudflare R2 bucket via its S3-compatible API."""

    def save(self, data: bytes, key: str, content_type: str = "application/octet-stream") -> Optional[str]:
        import boto3

        account_id = os.getenv("R2_ACCOUNT_ID")
        bucket = os.getenv("R2_BUCKET")
        public_base = os.getenv("R2_PUBLIC_URL", "").rstrip("/")
        if not account_id or not bucket:
            logger.warning("R2_ACCOUNT_ID/R2_BUCKET not set; skipping upload.")
            return None

        try:
            client = boto3.client(
                "s3",
                endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
                aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
                aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
                region_name="auto",
            )
            client.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)
            return f"{public_base}/{key}" if public_base else None
        except Exception as e:
            logger.error(f"R2 upload failed for {key}: {e}")
            return None

    def delete(self, key: str) -> None:
        import boto3

        account_id = os.getenv("R2_ACCOUNT_ID")
        bucket = os.getenv("R2_BUCKET")
        if not account_id or not bucket:
            return
        try:
            client = boto3.client(
                "s3",
                endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
                aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
                aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
                region_name="auto",
            )
            client.delete_object(Bucket=bucket, Key=key)
        except Exception as e:
            logger.warning(f"R2 delete failed for {key}: {e}")


_providers = {
    "local": LocalStorageProvider,
    "supabase": SupabaseStorageProvider,
    "r2": CloudflareR2Provider,
}

_instance_cache = {}


def get_storage_provider() -> StorageProvider:
    name = os.getenv("STORAGE_PROVIDER", "local").strip().lower()
    cls = _providers.get(name, LocalStorageProvider)
    if name not in _instance_cache:
        _instance_cache[name] = cls()
    return _instance_cache[name]
