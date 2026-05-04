
# ============================================================
# FILE: src/utils.py
# ============================================================
"""
Utility Functions - Common helpers used across all modules
"""

import os
import re
import hashlib
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, Any

logger = logging.getLogger(__name__)

HASH_BUFFER_SIZE = 8 * 1024 * 1024


def calculate_file_hash(filepath, algorithm='md5'):
    """Calculate file hash using streaming for large files."""
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
        logger.warning(f"Error hashing {filepath}: {e}")
        return ""


def get_file_size_mb(filepath):
    """Get file size in megabytes."""
    try:
        return Path(filepath).stat().st_size / (1024 * 1024)
    except Exception:
        return 0.0


def get_file_modification_date(filepath):
    """Get file modification date as datetime."""
    try:
        ts = Path(filepath).stat().st_mtime
        return datetime.fromtimestamp(ts)
    except Exception:
        return None


def parse_datetime_flexible(value):
    """Parse datetime from various string formats."""
    if isinstance(value, datetime):
        return value

    if not value or not isinstance(value, str):
        return None

    cleaned = str(value).strip().replace('\x00', '')
    if not cleaned:
        return None

    formats = [
        '%Y-%m-%d %H:%M:%S',
        '%Y:%m:%d %H:%M:%S',
        '%Y-%m-%dT%H:%M:%S',
        '%Y/%m/%d %H:%M:%S',
        '%d/%m/%Y %H:%M:%S',
        '%Y-%m-%d',
        '%Y:%m:%d',
    ]

    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt)
        except (ValueError, TypeError):
            continue

    return None


def parse_exif_date(exif_data):
    """Extract date from EXIF data dictionary."""
    date_fields = ['DateTimeOriginal', 'DateTimeDigitized', 'DateTime']

    for field in date_fields:
        val = exif_data.get(field)
        if val:
            dt = parse_datetime_flexible(val)
            if dt:
                return dt

    return None


def parse_gps_coordinates(gps_info):
    """Parse GPS coordinates from EXIF GPSInfo."""
    try:
        if not gps_info or not isinstance(gps_info, dict):
            return None, None

        def to_degrees(value):
            if isinstance(value, (list, tuple)) and len(value) == 3:
                d = float(value[0])
                m = float(value[1])
                s = float(value[2])
                return d + m / 60.0 + s / 3600.0
            return None

        lat_val = gps_info.get(2)
        lat_ref = gps_info.get(1)
        lon_val = gps_info.get(4)
        lon_ref = gps_info.get(3)

        lat = to_degrees(lat_val) if lat_val else None
        lon = to_degrees(lon_val) if lon_val else None

        if lat is not None and lat_ref:
            ref = str(lat_ref).strip().upper()
            if ref == 'S':
                lat = -lat

        if lon is not None and lon_ref:
            ref = str(lon_ref).strip().upper()
            if ref == 'W':
                lon = -lon

        return lat, lon

    except Exception as e:
        logger.debug(f"GPS parse error: {e}")
        return None, None


def safe_string(value):
    """Convert value to clean string, removing control chars."""
    if value is None:
        return ''
    try:
        s = str(value).strip()
        return ''.join(ch for ch in s if ord(ch) >= 32 or ch in ('\n', '\t'))
    except Exception:
        return ''


def format_size_human(size_bytes):
    """Format bytes to human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / (1024 ** 2):.1f} MB"
    else:
        return f"{size_bytes / (1024 ** 3):.2f} GB"


def format_duration(seconds):
    """
    Format seconds into human-readable duration string.

    Args:
        seconds: Duration in seconds (int or float)

    Returns:
        Formatted string like '1h 23m 45s' or '2m 30s'
    """
    if seconds is None or not isinstance(seconds, (int, float)):
        return ''

    seconds = int(seconds)
    if seconds <= 0:
        return '0s'

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 or not parts:
        parts.append(f"{secs}s")

    return ' '.join(parts)


def ensure_directory(path):
    """Create directory if it doesn't exist."""
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        logger.error(f"Cannot create directory {path}: {e}")
        return False


def resolve_filename_conflict(dest_path, strategy='rename'):
    """Resolve filename conflict at destination."""
    dest_path = Path(dest_path)

    if not dest_path.exists():
        return dest_path

    if strategy == 'overwrite':
        return dest_path

    if strategy == 'skip':
        return None

    stem = dest_path.stem
    suffix = dest_path.suffix
    parent = dest_path.parent
    counter = 1

    while True:
        new_path = parent / f"{stem}_{counter}{suffix}"
        if not new_path.exists():
            return new_path
        counter += 1
        if counter > 99999:
            logger.error(f"Too many conflicts for {dest_path}")
            return None


def safe_filename(filename, max_length=255):
    """Make filename filesystem-safe."""
    filename = re.sub(r'[<>:"/\\|?*]', '_', str(filename))
    return filename[:max_length]


def get_timestamp_string():
    """Get current timestamp as string."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")
