
# ============================================================
# FILE: src/duplicate_handler.py
# ============================================================
"""
Duplicate Handler - Detects duplicates (exact or similar) and selects best.
"""

import logging
from typing import List, Dict, Optional
from collections import defaultdict
from datetime import datetime

from .utils import calculate_file_hash, parse_datetime_flexible

logger = logging.getLogger(__name__)

try:
    from PIL import Image
    import numpy as np
    PHASH_AVAILABLE = True
except ImportError:
    PHASH_AVAILABLE = False


class DuplicateHandler:
    """Detect duplicates and select best image per group."""

    def __init__(self, hash_algorithm='md5', selection_criteria=None,
                 match_mode='exact', similarity_threshold=90):
        self.hash_algorithm = hash_algorithm
        self.selection_criteria = selection_criteria or ['quality', 'resolution', 'date', 'size']
        self.match_mode = match_mode
        self.similarity_threshold = similarity_threshold

    def find_duplicates(self, records):
        if self.match_mode == 'similar' and PHASH_AVAILABLE:
            return self._find_similar(records)
        return self._find_exact(records)

    def _find_exact(self, records):
        hash_map = defaultdict(list)
        for idx, rec in enumerate(records):
            h = rec.get('md5_hash', '')
            if h:
                hash_map[h].append(idx)

        groups = {}
        gid = 1
        for h, indices in hash_map.items():
            if len(indices) > 1:
                groups[gid] = indices
                gid += 1
        return groups

    def _find_similar(self, records):
        if not PHASH_AVAILABLE:
            logger.warning("PIL/numpy not available, falling back to exact match")
            return self._find_exact(records)

        logger.info("Computing perceptual hashes...")
        hashes = []
        for idx, rec in enumerate(records):
            if rec.get('file_type') != 'image' or not rec.get('full_path'):
                hashes.append((idx, None))
                continue
            try:
                phash = self._avg_hash(rec['full_path'])
                hashes.append((idx, phash))
            except Exception:
                hashes.append((idx, None))

        used = set()
        groups = {}
        gid = 1
        threshold = self.similarity_threshold / 100.0

        for i in range(len(hashes)):
            if i in used or hashes[i][1] is None:
                continue
            group = [hashes[i][0]]
            used.add(i)

            for j in range(i + 1, len(hashes)):
                if j in used or hashes[j][1] is None:
                    continue
                sim = self._hash_sim(hashes[i][1], hashes[j][1])
                if sim >= threshold:
                    group.append(hashes[j][0])
                    used.add(j)

            if len(group) > 1:
                groups[gid] = group
                gid += 1

        return groups

    def _avg_hash(self, filepath, size=8):
        img = Image.open(filepath).convert('L').resize((size, size), Image.LANCZOS)
        pixels = np.array(img, dtype=float)
        return (pixels > pixels.mean()).flatten()

    def _hash_sim(self, h1, h2):
        if h1 is None or h2 is None:
            return 0.0
        return float(np.sum(h1 == h2)) / len(h1)

    def select_best(self, records, indices):
        if not indices:
            return None
        if len(indices) == 1:
            return indices[0]

        best_idx = indices[0]
        best_score = self._score(records[best_idx])

        for idx in indices[1:]:
            s = self._score(records[idx])
            if s > best_score:
                best_score = s
                best_idx = idx

        return best_idx

    def _score(self, record):
        score = 0.0
        for criterion in self.selection_criteria:
            if criterion == 'quality':
                q = record.get('quality_score')
                if isinstance(q, (int, float)):
                    score += q * 100

            elif criterion == 'resolution':
                w = record.get('width') or 0
                h = record.get('height') or 0
                if w and h:
                    score += (w * h) / 1_000_000 * 10

            elif criterion == 'date':
                dt = record.get('date_taken')
                if isinstance(dt, datetime):
                    try:
                        score += dt.timestamp() / 1e8
                    except Exception:
                        pass
                elif isinstance(dt, str):
                    parsed = parse_datetime_flexible(dt)
                    if parsed:
                        try:
                            score += parsed.timestamp() / 1e8
                        except Exception:
                            pass

            elif criterion == 'size':
                sz = record.get('size_mb')
                if isinstance(sz, (int, float)):
                    score += sz

        return score

    def mark_duplicates(self, records):
        """Mark all records with duplicate info. ALL group members shown."""
        logger.info("Starting duplicate detection...")

        for rec in records:
            rec.setdefault('is_duplicate', 'No')
            rec.setdefault('duplicate_group', '')
            rec.setdefault('is_best_in_group', '')
            rec.setdefault('recommendation', '')

        groups = self.find_duplicates(records)
        total_dup = 0

        for gid, indices in groups.items():
            label = f"DUP_{gid:04d}"
            best_idx = self.select_best(records, indices)

            for idx in indices:
                records[idx]['is_duplicate'] = 'YES'
                records[idx]['duplicate_group'] = label
                total_dup += 1

                if idx == best_idx:
                    records[idx]['is_best_in_group'] = 'Yes'
                    records[idx]['recommendation'] = 'Keep (Best)'
                    records[idx]['delete_flag'] = 'No'
                else:
                    records[idx]['is_best_in_group'] = 'No'
                    records[idx]['recommendation'] = 'Delete (Duplicate)'
                    records[idx]['delete_flag'] = 'Yes'

        for rec in records:
            if rec.get('is_blurry') is True and rec.get('is_duplicate') == 'No':
                if not rec.get('recommendation'):
                    rec['recommendation'] = 'Review (Blurry)'

        logger.info(f"Duplicate detection done: {len(groups)} groups, {total_dup} files")
        return records

