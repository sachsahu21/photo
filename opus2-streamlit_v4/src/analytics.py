# ============================================================
# FILE: src/analytics.py
# ============================================================
"""Storage Analytics v2.3"""
import logging
from collections import Counter, defaultdict
from .utils import format_size_human
logger = logging.getLogger(__name__)

class StorageAnalytics:
    def analyze(self, records):
        if not records:
            return {}
        tb = sum((r.get('size_mb', 0) or 0) for r in records) * 1024 * 1024
        db = sum((r.get('size_mb', 0) or 0) for r in records if str(r.get('is_duplicate', '')).upper() == 'YES' and r.get('is_best_in_group') != 'Yes') * 1024 * 1024
        return {'total_files': len(records), 'total_size_bytes': tb, 'total_size_human': format_size_human(tb),
                'images': sum(1 for r in records if r.get('file_type') == 'image'),
                'videos': sum(1 for r in records if r.get('file_type') == 'video'),
                'duplicates': sum(1 for r in records if str(r.get('is_duplicate', '')).upper() == 'YES'),
                'blurry': sum(1 for r in records if r.get('is_blurry') is True),
                'similar': sum(1 for r in records if r.get('is_similar') == 'YES'),
                'duplicate_waste_human': format_size_human(db)}
