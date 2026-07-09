"""Duplicate Handler v2.4"""

import logging
from collections import defaultdict
from datetime import datetime

from .utils import parse_datetime_flexible

logger = logging.getLogger(__name__)


class DuplicateHandler:
    def __init__(self, hash_algorithm='md5', selection_criteria=None, match_mode='exact', similarity_threshold=90):
        self.hash_algorithm = str(hash_algorithm or 'md5').strip().lower()
        self.hash_field = self.hash_algorithm + '_hash'
        self.match_mode = str(match_mode or 'exact').strip().lower()
        self.similarity_threshold = similarity_threshold
        self.selection_criteria = selection_criteria or ['quality', 'resolution', 'date', 'size']

    def find_duplicates(self, records):
        hm = defaultdict(list)
        for i, r in enumerate(records):
            h = r.get(self.hash_field, '')
            if h:
                hm[str(h).strip().lower()].append(i)
        groups = {}
        for h, idx in sorted(hm.items()):
            if len(idx) > 1:
                groups[self.hash_algorithm.upper() + '-' + h[:12].upper()] = idx
        return groups

    def select_best(self, records, indices):
        if len(indices) <= 1:
            return indices[0] if indices else None
        best, bs = indices[0], self._score(records[indices[0]])
        for idx in indices[1:]:
            s = self._score(records[idx])
            if s > bs:
                bs, best = s, idx
        return best

    def _score(self, r):
        s = 0.0
        for c in self.selection_criteria:
            if c == 'quality':
                q = r.get('quality_score')
                if isinstance(q, (int, float)):
                    s += q * 100
            elif c == 'resolution':
                w, h = r.get('width') or 0, r.get('height') or 0
                if w and h:
                    s += (w * h) / 1e6 * 10
            elif c == 'date':
                dt = r.get('date_taken')
                if isinstance(dt, str):
                    dt = parse_datetime_flexible(dt)
                if isinstance(dt, datetime):
                    try:
                        s += dt.timestamp() / 1e8
                    except Exception:
                        pass
            elif c == 'size':
                sz = r.get('size_mb')
                if isinstance(sz, (int, float)):
                    s += sz
        return s

    def mark_duplicates(self, records):
        for r in records:
            r['is_duplicate'] = 'No'
            r['duplicate_group'] = ''
            r['duplicate_type'] = ''
            r['master_media_id'] = ''
            r['is_best_in_group'] = ''
            prev_rec = str(r.get('recommendation', ''))
            if prev_rec.startswith(('Keep (Best)', 'Delete (Duplicate)', 'Review (Blurry)')):
                r['recommendation'] = ''
            # Clear delete_flag only when it was set by a previous duplicate run, not by the user manually.
            # A dup-set flag always comes with recommendation='Delete (Duplicate)'.
            if prev_rec == 'Delete (Duplicate)' and str(r.get('delete_flag', '')).strip().lower() in ('yes', 'true', '1'):
                r['delete_flag'] = 'No'
        groups = self.find_duplicates(records)
        total = 0
        for label, indices in groups.items():
            best = self.select_best(records, indices)
            master_media_id = ''
            if best is not None:
                master_media_id = str(records[best].get('media_id') or records[best].get(self.hash_field) or '').strip()
            for idx in indices:
                records[idx]['is_duplicate'] = 'YES'
                records[idx]['duplicate_group'] = label
                records[idx]['duplicate_type'] = 'exact_' + self.hash_algorithm
                records[idx]['master_media_id'] = master_media_id
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

