"""Utility Functions v4.1"""

import re
import hashlib
import logging
import threading
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

HASH_BUFFER_SIZE = 8 * 1024 * 1024
_print_lock = threading.Lock()


def thread_safe_print(msg):
    with _print_lock:
        print(msg)


def calculate_file_hash(filepath, algorithm='md5'):
    try:
        filepath = Path(filepath)
        if not filepath.exists():
            return ""
        hasher = hashlib.sha256() if algorithm == 'sha256' else hashlib.md5()
        with open(filepath, 'rb') as f:
            while True:
                chunk = f.read(HASH_BUFFER_SIZE)
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        logger.warning('Hash error %s: %s', filepath, e)
        return ""


def get_file_size_mb(filepath):
    try:
        return Path(filepath).stat().st_size / (1024 * 1024)
    except Exception:
        return 0.0


def get_file_modification_date(filepath):
    try:
        return datetime.fromtimestamp(Path(filepath).stat().st_mtime)
    except Exception:
        return None


def parse_datetime_flexible(value):
    if isinstance(value, datetime):
        return value
    if not value or not isinstance(value, str):
        return None
    cleaned = str(value).strip().replace('\x00', '')
    if not cleaned:
        return None
    for fmt in [
        '%Y-%m-%d %H:%M:%S', '%Y:%m:%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S',
        '%Y/%m/%d %H:%M:%S', '%d/%m/%Y %H:%M:%S', '%Y-%m-%d', '%Y:%m:%d',
    ]:
        try:
            return datetime.strptime(cleaned, fmt)
        except (ValueError, TypeError):
            continue
    return None


def parse_exif_date(exif_data):
    for field in ['DateTimeOriginal', 'DateTimeDigitized', 'DateTime']:
        val = exif_data.get(field)
        if val:
            dt = parse_datetime_flexible(val)
            if dt:
                return dt
    return None


def parse_gps_coordinates(gps_info):
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
    if value is None:
        return ''
    try:
        s = str(value).strip()
        return ''.join(ch for ch in s if ord(ch) >= 32 or ch in ('\n', '\t'))
    except Exception:
        return ''


def format_size_human(size_bytes):
    if not isinstance(size_bytes, (int, float)) or size_bytes < 0:
        return '0 B'
    if size_bytes < 1024:
        return str(int(size_bytes)) + ' B'
    elif size_bytes < 1024 ** 2:
        return str(round(size_bytes / 1024, 1)) + ' KB'
    elif size_bytes < 1024 ** 3:
        return str(round(size_bytes / (1024 ** 2), 1)) + ' MB'
    else:
        return str(round(size_bytes / (1024 ** 3), 2)) + ' GB'


def format_duration(seconds):
    if seconds is None or not isinstance(seconds, (int, float)):
        return ''
    seconds = int(seconds)
    if seconds <= 0:
        return '0s'
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    parts = []
    if h > 0:
        parts.append(str(h) + 'h')
    if m > 0:
        parts.append(str(m) + 'm')
    if s > 0 or not parts:
        parts.append(str(s) + 's')
    return ' '.join(parts)


def format_pic_count(count):
    """Format count with minimum 3 digits: 1->001pic, 85->085pic, 120->120pic."""
    return str(count).zfill(3) + 'pic'


def is_valid_date_folder(folder_name):
    """Check if folder name starts with YYYY-MM-DD pattern."""
    m = re.compile('^(\\d{4}-\\d{2}-\\d{2})').match(str(folder_name))
    if m:
        try:
            datetime.strptime(m.group(1), '%Y-%m-%d')
            return m.group(1)
        except ValueError:
            pass
    return None


def is_valid_month_folder(folder_name):
    """Check if folder name starts with YYYY-MM-00 pattern."""
    m = re.compile('^(\\d{4}-\\d{2}-00)').match(str(folder_name))
    return m.group(1) if m else None


def determine_metadata_status(record):
    if record.get('error'):
        return 'Error'
    ft = record.get('file_type', '')
    if ft == 'video':
        hd = record.get('video_duration_sec') is not None
        hr = record.get('video_width') is not None
        if hd and hr:
            return 'Full Video Meta'
        elif hd or hr:
            return 'Partial Video Meta'
        return 'No Video Meta'
    if ft == 'image':
        if not record.get('has_exif'):
            return 'No EXIF'
        filled = sum(1 for f in [
            'camera_make', 'camera_model', 'date_taken',
            'focal_length', 'aperture', 'iso', 'exposure_time'
        ] if record.get(f))
        if filled >= 5:
            return 'Full EXIF'
        elif filled >= 2:
            return 'Partial EXIF'
        return 'Minimal EXIF'
    return 'Unknown'


def determine_date_source(record):
    if record.get('date_taken'):
        return 'EXIF' if record.get('has_exif') else 'File Modified'
    elif record.get('file_modified'):
        return 'File Modified'
    return 'None'


def ensure_directory(path):
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        logger.error('Cannot create %s: %s', path, e)
        return False


def resolve_filename_conflict(dest_path, strategy='rename'):
    dest_path = Path(dest_path)
    if not dest_path.exists():
        return dest_path
    if strategy == 'overwrite':
        return dest_path
    if strategy == 'skip':
        return None
    stem, suffix, parent = dest_path.stem, dest_path.suffix, dest_path.parent
    for i in range(1, 100000):
        p = parent / (stem + '-' + str(i) + suffix)
        if not p.exists():
            return p
    return None


def safe_filename(filename, max_length=255):
    return re.sub('[<>:"/\\\\|?*]', '-', str(filename))[:max_length]


def get_record_defaults():
    return {
        'filename': '', 'folder': '', 'full_path': '',
        'extension': '', 'file_type': '', 'size_mb': 0.0,
        'file_modified': '', 'md5_hash': '', 'delete_flag': 'No', 'error': None,

        'width': None, 'height': None, 'mode': None, 'dpi': None,
        'date_taken': None, 'date_source': 'None',
        'camera_make': None, 'camera_model': None,
        'focal_length': None, 'aperture': None, 'iso': None, 'exposure_time': None,
        'gps_lat': None, 'gps_lon': None, 'has_exif': False,

        'is_blurry': None, 'blur_score': None, 'quality_rating': 'Unknown',
        'quality_score': None, 'quality_issues': '',

        'video_duration_sec': None, 'video_duration_fmt': '',
        'video_width': None, 'video_height': None, 'video_fps': None,
        'video_codec': None, 'video_bitrate_kbps': None,
        'video_meta_source': '',
        'video_meta_error': '',

        'is_duplicate': 'No', 'duplicate_group': '', 'is_best_in_group': '',
        'recommendation': '',

        'face_count': 0, 'face_category': 'No People',
        'thumbnail_path': None, 'cluster_id': None, 'cluster_label': None,
        'location_city': None, 'location_country': None, 'location_name': None,
        'auto_tags': None, 'primary_tag': None,

        'metadata_status': 'Unknown',
        'is_similar': 'No', 'similar_group': '',
        'similar_methods': '', 'similar_score': '',
    }

