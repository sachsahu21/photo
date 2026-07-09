"""
Utility functions
"""

import hashlib
import logging
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


def file_hash(filepath: str, algorithm: str = 'md5') -> Optional[str]:
    """
    Calculate file hash

    Args:
        filepath: Path to file
        algorithm: Hash algorithm (md5, sha256)

    Returns:
        Hash string or None if error
    """
    try:
        if algorithm == 'sha256':
            h = hashlib.sha256()
        else:
            h = hashlib.md5()

        with open(filepath, 'rb') as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
    except Exception as e:
        logger.warning(f"Error calculating hash for {filepath}: {e}")
        return None


def get_gps(exif_data: dict) -> Tuple[Optional[float], Optional[float]]:
    """
    Extract GPS coordinates from EXIF data

    Args:
        exif_data: EXIF data dictionary

    Returns:
        Tuple of (latitude, longitude) or (None, None)
    """
    try:
        gps = exif_data.get('GPSInfo', {})
        if not gps:
            return None, None

        def to_dec(v):
            return float(v[0]) + float(v[1]) / 60 + float(v[2]) / 3600

        lat = to_dec(gps.get(2, (0, 0, 0)))
        lon = to_dec(gps.get(4, (0, 0, 0)))

        if gps.get(1) == 'S':
            lat = -lat
        if gps.get(3) == 'W':
            lon = -lon

        return round(lat, 6), round(lon, 6)
    except Exception as e:
        logger.debug(f"Error extracting GPS: {e}")
        return None, None


def safe_string(value: str, max_length: int = None) -> str:
    """
    Clean string for Excel output

    Args:
        value: String to clean
        max_length: Maximum length

    Returns:
        Cleaned string
    """
    if not isinstance(value, str):
        value = str(value)

    # Remove non-printable characters
    value = ''.join(ch for ch in value if ord(ch) >= 32)

    if max_length:
        value = value[:max_length]

    return value


def format_size(size_bytes: float) -> str:
    """
    Format bytes to human readable size

    Args:
        size_bytes: Size in bytes

    Returns:
        Formatted size string
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} PB"


def ensure_dir(path: Path) -> Path:
    """
    Ensure directory exists

    Args:
        path: Directory path

    Returns:
        Path object
    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_date_from_exif(exif_data: dict) -> Optional[datetime]:
    """
    Extract date from EXIF data

    Args:
        exif_data: EXIF data dictionary

    Returns:
        datetime object or None
    """
    from PIL.ExifTags import TAGS

    for dt_tag in ('DateTimeOriginal', 'DateTime', 'DateTimeDigitized'):
        dt = exif_data.get(dt_tag)
        if dt:
            try:
                return datetime.strptime(str(dt), '%Y:%m:%d %H:%M:%S')
            except Exception:
                pass

    return None