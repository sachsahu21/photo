
# ============================================================================
# FILE: src/duplicate_handler.py
# ============================================================================
"""
Duplicate Handler - Detects and marks duplicate images
"""

import logging
from pathlib import Path
from typing import List, Dict, Optional
from collections import defaultdict
from src.utils import calculate_file_hash

logger = logging.getLogger(__name__)


class DuplicateHandler:
    """Handles duplicate detection and selection"""

    def __init__(self, hash_algorithm: str = 'md5', selection_criteria: Optional[List[str]] = None):
        """
        Initialize duplicate handler

        Args:
            hash_algorithm: Hash algorithm to use ('md5' or 'sha256')
            selection_criteria: Criteria for selecting best image from duplicates
        """
        self.hash_algorithm = hash_algorithm
        self.selection_criteria = selection_criteria or ['quality', 'resolution', 'date', 'size']

    def mark_duplicates(self, records: List[Dict]) -> List[Dict]:
        """
        Mark duplicate images in records

        Args:
            records: List of image records

        Returns:
            Updated records with duplicate information
        """
        logger.info("Starting duplicate detection...")

        hash_groups = defaultdict(list)

        for idx, record in enumerate(records):
            filepath = Path(record.get('full_path', ''))

            if not filepath.exists():
                logger.warning(f"File not found: {filepath}")
                continue

            file_hash = calculate_file_hash(filepath, self.hash_algorithm)
            record['file_hash'] = file_hash
            hash_groups[file_hash].append(idx)

        duplicate_group_counter = 0

        for file_hash, indices in hash_groups.items():
            if len(indices) > 1:
                duplicate_group_counter += 1
                group_id = f"DUP_{duplicate_group_counter:04d}"

                best_idx = self._select_best_image(records, indices)

                for idx in indices:
                    records[idx]['duplicate_group'] = group_id
                    if idx == best_idx:
                        records[idx]['is_duplicate'] = 'NO'
                        records[idx]['is_best_of_duplicates'] = True
                    else:
                        records[idx]['is_duplicate'] = 'YES'
                        records[idx]['is_best_of_duplicates'] = False

                logger.info(f"Group {group_id}: {len(indices)} duplicates, best: {records[best_idx].get('filename')}")

        logger.info(f"Duplicate detection complete: {duplicate_group_counter} groups found")
        return records

    def _select_best_image(self, records: List[Dict], indices: List[int]) -> int:
        """
        Select best image from duplicate group

        Args:
            records: List of all records
            indices: Indices of duplicate images

        Returns:
            Index of best image
        """
        best_idx = indices[0]
        best_score = self._calculate_selection_score(records[best_idx])

        for idx in indices[1:]:
            score = self._calculate_selection_score(records[idx])
            if score > best_score:
                best_score = score
                best_idx = idx

        return best_idx

    def _calculate_selection_score(self, record: Dict) -> float:
        """
        Calculate selection score based on criteria

        Args:
            record: Image record

        Returns:
            Selection score
        """
        score = 0.0

        if 'quality' in self.selection_criteria:
            quality = record.get('quality_score', 0)
            score += quality * 100

        if 'resolution' in self.selection_criteria:
            width = record.get('width', 0)
            height = record.get('height', 0)
            megapixels = (width * height) / 1_000_000
            score += megapixels * 10

        if 'date' in self.selection_criteria:
            from datetime import datetime
            date_str = record.get('date_taken', '')
            try:
                date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                score += date.timestamp()
            except:
                pass

        if 'size' in self.selection_criteria:
            file_size = record.get('file_size_mb', 0)
            score += file_size

        return score
