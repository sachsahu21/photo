

# ============================================================
# FILE: src/cloud_scanner.py  (#15 - NEW)
# ============================================================
"""
Cloud Scanner - Scan images from cloud storage (S3, GCS).
Downloads metadata without full file download where possible.
"""

import os
import logging
import tempfile
from pathlib import Path
from typing import List, Dict, Optional

from .utils import ensure_directory

logger = logging.getLogger(__name__)

try:
    import boto3
    BOTO3_OK = True
except ImportError:
    BOTO3_OK = False

try:
    from google.cloud import storage as gcs_storage
    GCS_OK = True
except ImportError:
    GCS_OK = False


class CloudScanner:
    """Scan images from cloud storage."""

    def __init__(self, config):
        cloud_cfg = config.get('cloud', {})
        self.provider = cloud_cfg.get('provider', 'none').lower()
        self.bucket_name = cloud_cfg.get('bucket', '')
        self.prefix = cloud_cfg.get('prefix', '')
        self.credentials_path = cloud_cfg.get('credentials_path', '')
        self.temp_dir = Path(tempfile.mkdtemp(prefix='imgscan_cloud_'))
        self.image_exts = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.heic'}
        self.video_exts = {'.mp4', '.mov', '.avi', '.mkv', '.3gp'}
        self.all_exts = self.image_exts | self.video_exts

    def is_available(self):
        """Check if cloud provider is configured and available."""
        if self.provider == 's3':
            return BOTO3_OK and bool(self.bucket_name)
        elif self.provider == 'gcs':
            return GCS_OK and bool(self.bucket_name)
        return False

    def list_files(self):
        """
        List files in cloud storage.

        Returns:
            List of dicts with 'key', 'size', 'last_modified'
        """
        if self.provider == 's3':
            return self._list_s3()
        elif self.provider == 'gcs':
            return self._list_gcs()
        return []

    def download_file(self, key, local_path=None):
        """
        Download a file from cloud storage.

        Returns:
            Local file path or None
        """
        if not local_path:
            local_path = self.temp_dir / Path(key).name

        ensure_directory(local_path.parent)

        try:
            if self.provider == 's3':
                return self._download_s3(key, local_path)
            elif self.provider == 'gcs':
                return self._download_gcs(key, local_path)
        except Exception as e:
            logger.error(f"Cloud download error {key}: {e}")

        return None

    def _list_s3(self):
        """List files in S3 bucket."""
        if not BOTO3_OK:
            logger.error("boto3 not installed")
            return []

        try:
            s3 = boto3.client('s3')
            files = []
            paginator = s3.get_paginator('list_objects_v2')

            params = {'Bucket': self.bucket_name}
            if self.prefix:
                params['Prefix'] = self.prefix

            for page in paginator.paginate(**params):
                for obj in page.get('Contents', []):
                    key = obj['Key']
                    ext = Path(key).suffix.lower()
                    if ext in self.all_exts:
                        files.append({
                            'key': key,
                            'size': obj['Size'],
                            'last_modified': obj['LastModified'],
                        })

            logger.info(f"S3: Found {len(files)} files in {self.bucket_name}")
            return files

        except Exception as e:
            logger.error(f"S3 list error: {e}")
            return []

    def _list_gcs(self):
        """List files in GCS bucket."""
        if not GCS_OK:
            logger.error("google-cloud-storage not installed")
            return []

        try:
            if self.credentials_path:
                client = gcs_storage.Client.from_service_account_json(self.credentials_path)
            else:
                client = gcs_storage.Client()

            bucket = client.bucket(self.bucket_name)
            blobs = bucket.list_blobs(prefix=self.prefix if self.prefix else None)

            files = []
            for blob in blobs:
                ext = Path(blob.name).suffix.lower()
                if ext in self.all_exts:
                    files.append({
                        'key': blob.name,
                        'size': blob.size,
                        'last_modified': blob.updated,
                    })

            logger.info(f"GCS: Found {len(files)} files in {self.bucket_name}")
            return files

        except Exception as e:
            logger.error(f"GCS list error: {e}")
            return []

    def _download_s3(self, key, local_path):
        s3 = boto3.client('s3')
        s3.download_file(self.bucket_name, key, str(local_path))
        return str(local_path)

    def _download_gcs(self, key, local_path):
        if self.credentials_path:
            client = gcs_storage.Client.from_service_account_json(self.credentials_path)
        else:
            client = gcs_storage.Client()
        bucket = client.bucket(self.bucket_name)
        blob = bucket.blob(key)
        blob.download_to_filename(str(local_path))
        return str(local_path)

    def cleanup(self):
        """Remove temporary downloaded files."""
        import shutil
        try:
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir)
        except Exception as e:
            logger.warning(f"Cleanup error: {e}")
