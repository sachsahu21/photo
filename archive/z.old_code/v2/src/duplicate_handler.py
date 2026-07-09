"""
Duplicate Detection and Handling
"""

import logging
from typing import List, Dict, Tuple
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)


class DuplicateHandler:
    """Handle duplicate image detection and best selection"""

    def __init__(self, selection_criteria: List[str] = None):
        """
        Initialize duplicate handler

        Args:
            selection_criteria: List of criteria for best selection
                               (quality, resolution, date, size)
        """
        self.selection_criteria = selection_criteria or ['quality', 'resolution', 'date', 'size']

    def find_duplicates(self, records: List[Dict]) -> Dict[int, List[Dict]]:
        """
        Find duplicate images by MD5 hash

        Args:
            records: List of image records

        Returns:
            Dictionary mapping group_id to list of duplicate records
        """
        hash_map = defaultdict(list)

        for record in records:
            md5 = record.get('md5_hash')
            if md5:
                hash_map[md5].append(record)

        # Filter to only groups with duplicates
        duplicates = {
            gid: records
            for gid, records in enumerate(hash_map.values(), 1)
            if len(records) > 1
        }

        logger.info(f"Found {len(duplicates)} duplicate groups")
        return duplicates

    def select_best(self, duplicate_group: List[Dict]) -> Dict:
        """
        Select best image from duplicate group

        Args:
            duplicate_group: List of duplicate records

        Returns:
            Best record
        """
        if not duplicate_group:
            return None

        if len(duplicate_group) == 1:
            return duplicate_group[0]

        # Score each image
        scores = []
        for record in duplicate_group:
            score = self._calculate_score(record)
            scores.append((score, record))

        # Sort by score (descending) and return best
        scores.sort(key=lambda x: x[0], reverse=True)
        best = scores[0][1]

        logger.debug(f"Selected best from {len(duplicate_group)} duplicates: {best['filename']}")
        return best

    def _calculate_score(self, record: Dict) -> float:
        """
        Calculate overall score for image selection

        Args:
            record: Image record

        Returns:
            Score (0-1000)
        """
        score = 0

        for criterion in self.selection_criteria:
            if criterion == 'quality':
                quality = record.get('quality_score', 0)
                score += quality * 5  # Weight: 0-500

            elif criterion == 'resolution':
                width = record.get('width', 0) or 0
                height = record.get('height', 0) or 0
                megapixels = (width * height) / 1_000_000
                # Normalize to 0-200 (assuming max 20MP)
                score += min(megapixels / 20 * 200, 200)

            elif criterion == 'date':
                # Prefer newer files
                try:
                    from datetime import datetime
                    date_str = record.get('date_taken')
                    if isinstance(date_str, datetime):
                        # Newer = higher score
                        days_old = (datetime.now() - date_str).days
                        score += max(0, 100 - (days_old / 365 * 100))
                except:
                    pass

            elif criterion == 'size':
                # Prefer larger files (usually better quality)
                size_mb = record.get('size_mb', 0) or 0
                # Normalize to 0-100 (assuming max 50MB)
                score += min(size_mb / 50 * 100, 100)

        return score

    def mark_duplicates(self, records: List[Dict]) -> List[Dict]:
        """
        Mark duplicates and select best in each group

        Args:
            records: List of image records

        Returns:
            Updated records with duplicate info
        """
        duplicates = self.find_duplicates(records)

        # Mark all records
        for record in records:
            record['is_duplicate'] = 'No'
            record['duplicate_group'] = ''
            record['is_best_in_group'] = 'No'

        # Mark duplicates and best
        for group_id, dup_group in duplicates.items():
            best = self.select_best(dup_group)

            for record in dup_group:
                record['is_duplicate'] = 'YES'
                record['duplicate_group'] = group_id

                if record == best:
                    record['is_best_in_group'] = 'Yes'
                    record['recommendation'] = 'Keep'
                else:
                    record['recommendation'] = 'Delete (Duplicate)'

        return records