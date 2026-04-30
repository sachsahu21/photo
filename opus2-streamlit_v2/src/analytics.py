
# ============================================================
# FILE: src/analytics.py  (#8 - NEW)
# ============================================================
"""
Storage Analytics - Analyze disk usage patterns.
"""

import logging
from collections import Counter, defaultdict
from typing import List, Dict
from datetime import datetime

from .utils import parse_datetime_flexible, format_size_human

logger = logging.getLogger(__name__)


class StorageAnalytics:
    """Analyze storage usage patterns."""

    def analyze(self, records):
        """
        Generate comprehensive analytics from records.

        Returns:
            Dict with analytics data
        """
        if not records:
            return {}

        total_size = sum(r.get('size_mb', 0) or 0 for r in records)
        total_files = len(records)

        # By format
        by_format = Counter()
        size_by_format = defaultdict(float)
        for r in records:
            ext = r.get('extension', '?')
            by_format[ext] += 1
            size_by_format[ext] += r.get('size_mb', 0) or 0

        # By year
        by_year = Counter()
        size_by_year = defaultdict(float)
        for r in records:
            dt = self._get_date(r)
            if dt:
                year = dt.year
                by_year[year] += 1
                size_by_year[year] += r.get('size_mb', 0) or 0

        # By folder
        by_folder = Counter()
        size_by_folder = defaultdict(float)
        for r in records:
            folder = r.get('folder', 'Unknown')
            by_folder[folder] += 1
            size_by_folder[folder] += r.get('size_mb', 0) or 0

        # By camera
        by_camera = Counter()
        for r in records:
            make = r.get('camera_make', '') or ''
            model = r.get('camera_model', '') or ''
            cam = f"{make} {model}".strip()
            if cam:
                by_camera[cam] += 1

        # Largest files
        sorted_by_size = sorted(records, key=lambda x: x.get('size_mb', 0) or 0, reverse=True)
        top_10_largest = sorted_by_size[:10]

        # Duplicate savings
        dup_records = [r for r in records if str(r.get('is_duplicate', '')).upper() == 'YES'
                       and str(r.get('is_best_in_group', '')).lower() != 'yes']
        dup_savings_mb = sum(r.get('size_mb', 0) or 0 for r in dup_records)

        # Type breakdown
        images = sum(1 for r in records if r.get('file_type') == 'image')
        videos = sum(1 for r in records if r.get('file_type') == 'video')
        img_size = sum(r.get('size_mb', 0) or 0 for r in records if r.get('file_type') == 'image')
        vid_size = sum(r.get('size_mb', 0) or 0 for r in records if r.get('file_type') == 'video')

        # Resolution distribution
        res_buckets = {'4K+': 0, '1080p': 0, '720p': 0, 'SD': 0, 'Unknown': 0}
        for r in records:
            w = r.get('width') or 0
            h = r.get('height') or 0
            mp = (w * h) / 1e6
            if mp >= 8:
                res_buckets['4K+'] += 1
            elif mp >= 2:
                res_buckets['1080p'] += 1
            elif mp >= 0.9:
                res_buckets['720p'] += 1
            elif mp > 0:
                res_buckets['SD'] += 1
            else:
                res_buckets['Unknown'] += 1

        return {
            'total_files': total_files,
            'total_size_mb': round(total_size, 1),
            'total_size_human': format_size_human(int(total_size * 1024 * 1024)),
            'images': images,
            'videos': videos,
            'image_size_mb': round(img_size, 1),
            'video_size_mb': round(vid_size, 1),
            'by_format': dict(by_format.most_common(20)),
            'size_by_format': {k: round(v, 1) for k, v in
                               sorted(size_by_format.items(), key=lambda x: -x[1])[:20]},
            'by_year': dict(sorted(by_year.items())),
            'size_by_year': {k: round(v, 1) for k, v in sorted(size_by_year.items())},
            'by_folder': dict(by_folder.most_common(20)),
            'size_by_folder': {k: round(v, 1) for k, v in
                               sorted(size_by_folder.items(), key=lambda x: -x[1])[:20]},
            'by_camera': dict(by_camera.most_common(15)),
            'top_10_largest': [
                {'filename': r.get('filename'), 'size_mb': r.get('size_mb'),
                 'folder': r.get('folder')}
                for r in top_10_largest
            ],
            'duplicate_savings_mb': round(dup_savings_mb, 1),
            'resolution_distribution': res_buckets,
        }

    def _get_date(self, record):
        dt = record.get('date_taken')
        if dt:
            return parse_datetime_flexible(dt) if isinstance(dt, str) else dt
        fm = record.get('file_modified')
        if fm:
            return parse_datetime_flexible(fm)
        return None
