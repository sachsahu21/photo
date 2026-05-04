# ============================================================
# FILE: src/duplicate_handler.py
# ============================================================
"""Duplicate Handler v2.4"""
import logging
from collections import defaultdict
from datetime import datetime
from .utils import parse_datetime_flexible
logger = logging.getLogger(__name__)

class DuplicateHandler:
    def __init__(self, hash_algorithm='md5', selection_criteria=None, match_mode='exact', similarity_threshold=90):
        self.selection_criteria = selection_criteria or ['quality', 'resolution', 'date', 'size']
    def find_duplicates(self, records):
        hm = defaultdict(list)
        for i, r in enumerate(records):
            h = r.get('md5_hash', '')
            if h: hm[h].append(i)
        groups, gid = {}, 1
        for h, idx in hm.items():
            if len(idx) > 1:
                groups[gid] = idx; gid += 1
        return groups
    def select_best(self, records, indices):
        if len(indices) <= 1: return indices[0] if indices else None
        best, bs = indices[0], self._score(records[indices[0]])
        for idx in indices[1:]:
            s = self._score(records[idx])
            if s > bs: bs, best = s, idx
        return best
    def _score(self, r):
        s = 0.0
        for c in self.selection_criteria:
            if c == 'quality':
                q = r.get('quality_score')
                if isinstance(q, (int, float)): s += q * 100
            elif c == 'resolution':
                w, h = r.get('width') or 0, r.get('height') or 0
                if w and h: s += (w * h) / 1e6 * 10
            elif c == 'date':
                dt = r.get('date_taken')
                if isinstance(dt, str): dt = parse_datetime_flexible(dt)
                if isinstance(dt, datetime):
                    try: s += dt.timestamp() / 1e8
                    except Exception: pass
            elif c == 'size':
                sz = r.get('size_mb')
                if isinstance(sz, (int, float)): s += sz
        return s
    def mark_duplicates(self, records):
        for r in records:
            r.setdefault('is_duplicate', 'No'); r.setdefault('duplicate_group', '')
            r.setdefault('is_best_in_group', ''); r.setdefault('recommendation', '')
        groups = self.find_duplicates(records)
        total = 0
        for gid, indices in groups.items():
            label = 'DUP-' + str(gid).zfill(4)
            best = self.select_best(records, indices)
            for idx in indices:
                records[idx]['is_duplicate'] = 'YES'
                records[idx]['duplicate_group'] = label
                total += 1
                if idx == best:
                    records[idx]['is_best_in_group'] = 'Yes'
                    records[idx]['recommendation'] = 'Keep (Best)'
                    records[idx]['delete_flag'] = 'No'
                else:
                    records[idx]['is_best_in_group'] = 'No'
                    records[idx]['recommendation'] = 'Delete (Duplicate)'
                    records[idx]['delete_flag'] = 'Yes'
        for r in records:
            if r.get('is_blurry') is True and r.get('is_duplicate') == 'No' and not r.get('recommendation'):
                r['recommendation'] = 'Review (Blurry)'
        logger.info('Duplicates: %d groups, %d files', len(groups), total)
        return records
