
# ============================================================
# FILE: src/utils.py
# ============================================================
"""
Utility Functions - Common helpers used across all modules.
Enhanced with thread-safe operations and new helpers.
"""

import os
import re
import hashlib
import logging
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, Any, Dict, List

logger = logging.getLogger(__name__)

HASH_BUFFER_SIZE = 8 * 1024 * 1024
_print_lock = threading.Lock()


def thread_safe_print(msg):
    """Thread-safe print."""
    with _print_lock:
        print(msg)


def calculate_file_hash(filepath, algorithm='md5'):
    """Calculate file hash using streaming."""
    try:
        filepath = Path(filepath)
        if not filepath.exists():
            return ""
        if algorithm == 'sha256':
            hasher = hashlib.sha256()
        else:
            hasher = hashlib.md5()
        with open(filepath, 'rb') as f:
            while True:
                chunk = f.read(HASH_BUFFER_SIZE)
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        logger.warning(f"Hash error {filepath}: {e}")
        return ""


def get_file_size_mb(filepath):
    """Get file size in MB."""
    try:
        return Path(filepath).stat().st_size / (1024 * 1024)
    except Exception:
        return 0.0


def get_file_modification_date(filepath):
    """Get file modification datetime."""
    try:
        return datetime.fromtimestamp(Path(filepath).stat().st_mtime)
    except Exception:
        return None


def parse_datetime_flexible(value):
    """Parse datetime from various formats."""
    if isinstance(value, datetime):
        return value
    if not value or not isinstance(value, str):
        return None
    cleaned = str(value).strip().replace('\x00', '')
    if not cleaned:
        return None
    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y:%m:%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S',
                '%Y/%m/%d %H:%M:%S', '%d/%m/%Y %H:%M:%S', '%Y-%m-%d', '%Y:%m:%d']:
        try:
            return datetime.strptime(cleaned, fmt)
        except (ValueError, TypeError):
            continue
    return None


def parse_exif_date(exif_data):
    """Extract date from EXIF dict."""
    for field in ['DateTimeOriginal', 'DateTimeDigitized', 'DateTime']:
        val = exif_data.get(field)
        if val:
            dt = parse_datetime_flexible(val)
            if dt:
                return dt
    return None


def parse_gps_coordinates(gps_info):
    """Parse GPS from EXIF GPSInfo."""
    try:
        if not gps_info or not isinstance(gps_info, dict):
            return None, None

        def to_deg(v):
            if isinstance(v, (list, tuple)) and len(v) == 3:
                return float(v[0]) + float(v[1]) / 60.0 + float(v[2]) / 3600.0
            return None

        lat = to_deg(gps_info.get(2))
        lon = to_deg(gps_info.get(4))
        if lat and str(gps_info.get(1, '')).strip().upper() == 'S':
            lat = -lat
        if lon and str(gps_info.get(3, '')).strip().upper() == 'W':
            lon = -lon
        return lat, lon
    except Exception:
        return None, None


def safe_string(value):
    """Clean string."""
    if value is None:
        return ''
    try:
        s = str(value).strip()
        return ''.join(ch for ch in s if ord(ch) >= 32 or ch in ('\n', '\t'))
    except Exception:
        return ''


def format_size_human(size_bytes):
    """Format bytes to human string."""
    if not isinstance(size_bytes, (int, float)) or size_bytes < 0:
        return '0 B'
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / (1024 ** 2):.1f} MB"
    else:
        return f"{size_bytes / (1024 ** 3):.2f} GB"


def format_duration(seconds):
    """Format seconds to human duration."""
    if seconds is None or not isinstance(seconds, (int, float)):
        return ''
    seconds = int(seconds)
    if seconds <= 0:
        return '0s'
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    parts = []
    if h > 0:
        parts.append(f"{h}h")
    if m > 0:
        parts.append(f"{m}m")
    if s > 0 or not parts:
        parts.append(f"{s}s")
    return ' '.join(parts)


def ensure_directory(path):
    """Create directory."""
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        logger.error(f"Cannot create {path}: {e}")
        return False


def resolve_filename_conflict(dest_path, strategy='rename'):
    """Resolve filename conflict."""
    dest_path = Path(dest_path)
    if not dest_path.exists():
        return dest_path
    if strategy == 'overwrite':
        return dest_path
    if strategy == 'skip':
        return None
    stem, suffix, parent = dest_path.stem, dest_path.suffix, dest_path.parent
    for i in range(1, 100000):
        p = parent / f"{stem}_{i}{suffix}"
        if not p.exists():
            return p
    return None


def safe_filename(filename, max_length=255):
    """Filesystem-safe filename."""
    return re.sub(r'[<>:"/\\|?*]', '_', str(filename))[:max_length]


def get_timestamp_string():
    """Current timestamp string."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def get_record_defaults():
    """Return default record dict with ALL possible keys.
    Every module should use this to ensure consistent schema."""
    return {
        # Core
        'filename': '', 'folder': '', 'full_path': '',
        'extension': '', 'file_type': '', 'size_mb': 0.0,
        'file_modified': '', 'md5_hash': '', 'delete_flag': 'No', 'error': None,
        # Image
        'width': None, 'height': None, 'mode': None, 'dpi': None,
        'date_taken': None, 'camera_make': None, 'camera_model': None,
        'focal_length': None, 'aperture': None, 'iso': None, 'exposure_time': None,
        'gps_lat': None, 'gps_lon': None, 'has_exif': False,
        # Blur
        'is_blurry': None, 'blur_score': None, 'quality_rating': 'Unknown',
        'quality_score': None, 'quality_issues': '',
        # Video
        'video_duration_sec': None, 'video_duration_fmt': '',
        'video_width': None, 'video_height': None, 'video_fps': None,
        'video_codec': None, 'video_bitrate_kbps': None,
        # Duplicates
        'is_duplicate': 'No', 'duplicate_group': '', 'is_best_in_group': '',
        'recommendation': '',
        # Face detection (#1)
        'face_count': 0, 'face_category': 'No People',
        # Thumbnails (#2)
        'thumbnail_path': None,
        # Clustering (#7)
        'cluster_id': None, 'cluster_label': None,
        # Geocoding (#10)
        'location_city': None, 'location_country': None, 'location_name': None,
        # Auto-tagging (#12)
        'auto_tags': None, 'primary_tag': None,
    }
