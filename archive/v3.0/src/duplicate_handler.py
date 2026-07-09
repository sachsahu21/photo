
# ============================================================
# FILE: src/duplicate_handler.py
# ============================================================
"""Duplicate Handler - exact or similar match."""

import logging
from collections import defaultdict
from datetime import datetime

from .utils import parse_datetime_flexible

logger = logging.getLogger(__name__)

try:
    from PIL import Image
    import numpy as np
    PHASH_OK = True
except ImportError:
    PHASH_OK = False


class DuplicateHandler:
    def __init__(self, hash_algorithm='md5', selection_criteria=None,
                 match_mode='exact', similarity_threshold=90):
        self.hash_algorithm = hash_algorithm
        self.selection_criteria = selection_criteria or ['quality', 'resolution', 'date', 'size']
        self.match_mode = match_mode
        self.similarity_threshold = similarity_threshold

    def find_duplicates(self, records):
        if self.match_mode == 'similar' and PHASH_OK:
            return self._find_similar(records)
        return self._find_exact(records)

    def _find_exact(self, records):
        hm = defaultdict(list)
        for i, r in enumerate(records):
            h = r.get('md5_hash', '')
            if h:
                hm[h].append(i)
        groups = {}
        gid = 1
        for h, indices in hm.items():
            if len(indices) > 1:
                groups[gid] = indices
                gid += 1
        return groups

    def _find_similar(self, records):
        if not PHASH_OK:
            return self._find_exact(records)
        hashes = []
        for i, r in enumerate(records):
            if r.get('file_type') != 'image' or not r.get('full_path'):
                hashes.append((i, None))
                continue
            try:
                img = Image.open(r['full_path']).convert('L').resize((8, 8), Image.LANCZOS)
                px = np.array(img, dtype=float)
                hashes.append((i, (px > px.mean()).flatten()))
            except Exception:
                hashes.append((i, None))

        used = set()
        groups = {}
        gid = 1
        thr = self.similarity_threshold / 100.0
        for i in range(len(hashes)):
            if i in used or hashes[i][1] is None:
                continue
            grp = [hashes[i][0]]
            used.add(i)
            for j in range(i + 1, len(hashes)):
                if j in used or hashes[j][1] is None:
                    continue
                sim = float(np.sum(hashes[i][1] == hashes[j][1])) / len(hashes[i][1])
                if sim >= thr:
                    grp.append(hashes[j][0])
                    used.add(j)
            if len(grp) > 1:
                groups[gid] = grp
                gid += 1
        return groups

    def select_best(self, records, indices):
        if not indices:
            return None
        if len(indices) == 1:
            return indices[0]
        best = indices[0]
        bs = self._score(records[best])
        for idx in indices[1:]:
            s = self._score(records[idx])
            if s > bs:
                bs = s
                best = idx
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
        logger.info("Detecting duplicates...")
        for r in records:
            r.setdefault('is_duplicate', 'No')
            r.setdefault('duplicate_group', '')
            r.setdefault('is_best_in_group', '')
            r.setdefault('recommendation', '')

        groups = self.find_duplicates(records)
        total = 0
        for gid, indices in groups.items():
            label = f"DUP_{gid:04d}"
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

        logger.info(f"Duplicates: {len(groups)} groups, {total} files")
        return records
