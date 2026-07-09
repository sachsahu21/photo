
# ============================================================================
# FILE: src/utils.py
# ============================================================================
"""
Utility functions for image processing
"""

import hashlib
import logging
from pathlib import Path
from typing import Tuple, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


def calculate_file_hash(filepath: Path, algorithm: str = 'md5', chunk_size: int = 8192) -> str:
    """
    Calculate file hash using streaming for memory efficiency

    Args:
        filepath: Path to file
        algorithm: Hash algorithm ('md5', 'sha256')
        chunk_size: Chunk size for reading file

    Returns:
        Hex digest of file hash
    """
    try:
        if algorithm == 'md5':
            hasher = hashlib.md5()
        elif algorithm == 'sha256':
            hasher = hashlib.sha256()
        else:
            raise ValueError(f"Unsupported algorithm: {algorithm}")

        with open(filepath, 'rb') as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                hasher.update(chunk)

        return hasher.hexdigest()

    except Exception as e:
        logger.error(f"Error calculating hash for {filepath}: {e}")
        return ""


def get_file_size_mb(filepath: Path) -> float:
    """Get file size in megabytes"""
    try:
        return filepath.stat().st_size / (1024 * 1024)
    except Exception as e:
        logger.error(f"Error getting file size: {e}")
        return 0.0


def get_file_modification_date(filepath: Path) -> Optional[datetime]:
    """Get file modification date"""
    try:
        timestamp = filepath.stat().st_mtime
        return datetime.fromtimestamp(timestamp)
    except Exception as e:
        logger.error(f"Error getting modification date: {e}")
        return None


def parse_gps_coordinates(gps_ifd: dict) -> Tuple[Optional[float], Optional[float]]:
    """
    Parse GPS coordinates from EXIF IFD

    Args:
        gps_ifd: GPS IFD dictionary from piexif

    Returns:
        Tuple of (latitude, longitude) or (None, None)
    """
    try:
        if not gps_ifd:
            return None, None

        def convert_to_degrees(value):
            d, m, s = value
            return d[0] / d[1] + (m[0] / m[1]) / 60.0 + (s[0] / s[1]) / 3600.0

        lat = convert_to_degrees(gps_ifd.get(2, [[0, 1], [0, 1], [0, 1]]))
        lon = convert_to_degrees(gps_ifd.get(4, [[0, 1], [0, 1], [0, 1]]))

        lat_ref = gps_ifd.get(1, [b'N'])[0]
        lon_ref = gps_ifd.get(3, [b'E'])[0]

        if lat_ref == b'S':
            lat = -lat
        if lon_ref == b'W':
            lon = -lon

        return lat, lon

    except Exception as e:
        logger.debug(f"Error parsing GPS coordinates: {e}")
        return None, None


def format_timestamp(dt: Optional[datetime]) -> str:
    """Format datetime to string"""
    if not dt:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def get_timestamp_string() -> str:
    """Get current timestamp as string"""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def ensure_directory(path: Path) -> bool:
    """Ensure directory exists"""
    try:
        path.mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        logger.error(f"Error creating directory {path}: {e}")
        return False


def safe_filename(filename: str, max_length: int = 255) -> str:
    """
    Make filename safe for filesystem

    Args:
        filename: Original filename
        max_length: Maximum filename length

    Returns:
        Safe filename
    """
    import re
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    filename = filename[:max_length]
    return filename
