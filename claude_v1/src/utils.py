import hashlib, logging
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

def file_hash(filepath: str, algorithm: str = 'md5') -> Optional[str]:
    try:
        h = hashlib.sha256() if algorithm == 'sha256' else hashlib.md5()
        with open(filepath, 'rb') as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
    except Exception as e:
        logger.warning(f"Hash error {filepath}: {e}")
        return None

def get_gps(exif_data: dict) -> Tuple[Optional[float], Optional[float]]:
    try:
        gps = exif_data.get('GPSInfo', {})
        if not gps:
            return None, None
        def to_dec(v):
            return float(v[0]) + float(v[1])/60 + float(v[2])/3600
        lat = to_dec(gps.get(2, (0,0,0)))
        lon = to_dec(gps.get(4, (0,0,0)))
        if gps.get(1) == 'S': lat = -lat
        if gps.get(3) == 'W': lon = -lon
        return round(lat, 6), round(lon, 6)
    except Exception as e:
        logger.debug(f"GPS error: {e}")
        return None, None

def safe_string(value: str, max_length: int = None) -> str:
    if not isinstance(value, str):
        value = str(value)
    value = ''.join(ch for ch in value if ord(ch) >= 32)
    if max_length:
        value = value[:max_length]
    return value

def get_date_from_exif(exif_data: dict) -> Optional[datetime]:
    for dt_tag in ('DateTimeOriginal', 'DateTime', 'DateTimeDigitized'):
        dt = exif_data.get(dt_tag)
        if dt:
            try:
                return datetime.strptime(str(dt), '%Y:%m:%d %H:%M:%S')
            except Exception:
                pass
    return None
