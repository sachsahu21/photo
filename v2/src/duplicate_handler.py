import logging
from typing import List, Dict
from collections import defaultdict
from datetime import datetime

logger = logging.getLogger(__name__)

class DuplicateHandler:
    def __init__(self, selection_criteria: List[str] = None):
        self.criteria = selection_criteria or ['quality', 'resolution', 'date', 'size']

    def find_duplicates(self, records: List[Dict]) -> Dict[int, List[Dict]]:
        hash_map = defaultdict(list)
        for r in records:
            if r.get('md5_hash'):
                hash_map[r['md5_hash']].append(r)
        dupes = {gid: recs for gid, recs in enumerate(hash_map.values(), 1) if len(recs) > 1}
        logger.info(f"Found {len(dupes)} duplicate groups")
        return dupes

    def select_best(self, group: List[Dict]) -> Dict:
        if not group: return None
        if len(group) == 1: return group[0]
        scored = sorted([(self._score(r), r) for r in group], key=lambda x: x[0], reverse=True)
        return scored[0][1]

    def _score(self, r: Dict) -> float:
        score = 0
        for c in self.criteria:
            if c == 'quality':
                score += (r.get('quality_score') or 0) * 5
            elif c == 'resolution':
                w = r.get('width') or 0
                h = r.get('height') or 0
                score += min((w * h) / 1_000_000 / 20 * 200, 200)
            elif c == 'date':
                try:
                    dt = r.get('date_taken')
                    if isinstance(dt, datetime):
                        days = (datetime.now() - dt).days
                        score += max(0, 100 - days / 365 * 100)
                except: pass
            elif c == 'size':
                score += min((r.get('size_mb') or 0) / 50 * 100, 100)
        return score

    def mark_duplicates(self, records: List[Dict]) -> List[Dict]:
        for r in records:
            r['is_duplicate']    = 'No'
            r['duplicate_group'] = ''
            r['is_best_in_group'] = 'No'

        for gid, group in self.find_duplicates(records).items():
            best = self.select_best(group)
            for r in group:
                r['is_duplicate']    = 'YES'
                r['duplicate_group'] = gid
                if r is best:
                    r['is_best_in_group'] = 'Yes'
                    r['recommendation']   = 'Keep'
                else:
                    r['recommendation'] = 'Delete (Duplicate)'
        return records
