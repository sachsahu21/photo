"""
Date enrichment for records missing date_taken.

Two cheap sources (no file re-read required):
  1. Google Takeout supplemental-metadata sidecar  (<file>.supplemental-metadata.json)
  2. Filename date pattern parsing                  (IMG_20230619_123456.jpg → 2023-06-19)
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Filename patterns — ordered most-specific first
# ---------------------------------------------------------------------------

_PATTERNS: List[Tuple[re.Pattern, bool]] = [
    # Google Pixel video: PXL_20220904_132750092.mp4 (9-digit sub-seconds after HHMMSS)
    (re.compile(
        r'(?:PXL)[-_](\d{4})(\d{2})(\d{2})[_\-T](\d{2})(\d{2})(\d{2})\d*',
        re.IGNORECASE,
    ), True),
    # IMG_20230619_123456 / VID_20230619_123456 / V_20141129_171455 / Screenshot_20230619-123456
    (re.compile(
        r'(?:IMG|VID|V|PANO|BURST|MOV|MVI|DSC|MVIMG|Screenshot|Photo|photo)[-_]'
        r'(\d{4})(\d{2})(\d{2})[_\-T](\d{2})(\d{2})(\d{2})',
        re.IGNORECASE,
    ), True),
    # WhatsApp: IMG-20230619-WA0132 / VID-20190115-WA0001
    (re.compile(
        r'(?:IMG|VID)[-_](\d{4})(\d{2})(\d{2})[-_](?:WA|wa)\d+',
        re.IGNORECASE,
    ), False),
    # Plain timestamp without prefix: 20230619_123456
    (re.compile(r'(?<!\d)(\d{4})(\d{2})(\d{2})[_\-T](\d{2})(\d{2})(\d{2})(?!\d)'), True),
    # ISO date with prefix: IMG_2023-06-19 or similar
    (re.compile(
        r'(?:IMG|VID|Photo|photo|Screenshot)[-_](\d{4})-(\d{2})-(\d{2})',
        re.IGNORECASE,
    ), False),
    # ISO date anywhere in stem: 2023-06-19 or 2023_06_19
    (re.compile(r'(?<!\d)(\d{4})[_\-](\d{2})[_\-](\d{2})(?!\d)'), False),
    # Plain YYYYMMDD (must start with 19xx/20xx): 20230619
    (re.compile(r'(?<!\d)(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?!\d)'), False),
]

_YEAR_RANGE = range(1990, 2031)


def _parse_filename_date(filename: str) -> Optional[str]:
    """Return 'YYYY-MM-DD HH:MM:SS' or 'YYYY-MM-DD' parsed from filename, or None."""
    stem = Path(filename).stem
    for pattern, has_time in _PATTERNS:
        m = pattern.search(stem)
        if not m:
            continue
        g = m.groups()
        try:
            year, month, day = int(g[0]), int(g[1]), int(g[2])
        except (ValueError, IndexError):
            continue
        if year not in _YEAR_RANGE or not (1 <= month <= 12) or not (1 <= day <= 31):
            continue
        if has_time and len(g) >= 6:
            try:
                hour, minute, sec = int(g[3]), int(g[4]), int(g[5])
                if 0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= sec <= 59:
                    return f'{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{sec:02d}'
            except (ValueError, IndexError):
                pass
        return f'{year:04d}-{month:02d}-{day:02d}'
    return None


def _read_sidecar(file_path: Path) -> Optional[str]:
    """Read Google Takeout sidecar JSON and return the photoTakenTime as a date string."""
    candidates = [
        file_path.parent / (file_path.name + '.supplemental-metadata.json'),
        file_path.parent / (file_path.name + '.json'),
        file_path.parent / (file_path.stem + '.json'),
    ]
    for sidecar in candidates:
        if not sidecar.exists():
            continue
        try:
            doc = json.loads(sidecar.read_text(encoding='utf-8'))
        except Exception:
            continue
        # photoTakenTime is the actual capture time; fall back to creationTime
        for key in ('photoTakenTime', 'creationTime'):
            entry = doc.get(key)
            if not isinstance(entry, dict):
                continue
            ts = entry.get('timestamp')
            if not ts:
                continue
            try:
                dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
                return dt.strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                continue
    return None


def _missing(value: Any) -> bool:
    if value is None:
        return True
    s = str(value).strip().lower()
    return s in ('', 'none', 'unknown', 'no exif')


def enrich_dates(
    records: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Fill date_taken for records that are missing it.

    Tries in order:
      1. Google Takeout supplemental-metadata sidecar (photoTakenTime)
      2. Filename date pattern parsing

    Returns (enriched_records, stats).
    enriched_records contains only records that gained a date (shallow copies).
    stats keys: 'sidecar', 'filename', 'still_missing'.
    """
    stats: Dict[str, int] = {'sidecar': 0, 'filename': 0, 'still_missing': 0}
    enriched: List[Dict[str, Any]] = []

    for rec in records:
        if not _missing(rec.get('date_taken')):
            continue
        fp = str(rec.get('full_path') or '').strip()
        if not fp:
            continue
        file_path = Path(fp)

        date_str = _read_sidecar(file_path)
        if date_str:
            updated = dict(rec)
            updated['date_taken'] = date_str
            updated['date_source'] = 'sidecar'
            stats['sidecar'] += 1
            enriched.append(updated)
            continue

        date_str = _parse_filename_date(file_path.name)
        if date_str:
            updated = dict(rec)
            updated['date_taken'] = date_str
            updated['date_source'] = 'filename'
            stats['filename'] += 1
            enriched.append(updated)
            continue

        stats['still_missing'] += 1

    return enriched, stats
