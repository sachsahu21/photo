# ============================================================
# FILE: src/analytics.py
# ============================================================
"""Analytics v2.4"""
from .utils import format_size_human
class StorageAnalytics:
    def analyze(self, records):
        if not records: return {}
        tb=sum((r.get('size_mb',0) or 0) for r in records)*1024*1024
        db=sum((r.get('size_mb',0) or 0) for r in records if str(r.get('is_duplicate','')).upper()=='YES' and r.get('is_best_in_group')!='Yes')*1024*1024
        return {'total_files':len(records),'total_size_bytes':tb,'total_size_human':format_size_human(tb),'duplicate_waste_human':format_size_human(db)}
