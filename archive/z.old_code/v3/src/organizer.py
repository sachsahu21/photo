
# ============================================================================
# FILE: src/organizer.py
# ============================================================================
"""
Image Organizer - Organizes images into folder structure
"""

import logging
import shutil
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from tqdm import tqdm

from src.utils import ensure_directory, safe_filename

logger = logging.getLogger(__name__)


class ImageOrganizer:
    """Organizes images into folder structure based on date"""

    def __init__(self, config: Dict):
        """
        Initialize organizer

        Args:
            config: Configuration dictionary
        """
        self.config = config 
        self.output_folder = Path(config.get('organization', {}).get('output_folder', './organized_images'))
        self.operation_type = config.get('organization', {}).get('operation_type', 'copy')
        self.folder_structure = config.get('organization', {}).get('folder_structure', 'date_based')
        self.date_format = config.get('organization', {}).get('date_format', 'yyyymmdd')
        self.threshold = config.get('organization', {}).get('threshold_for_daily_folders', 60)
        self.conflict_strategy = config.get('organization', {}).get('handle_conflicts', 'rename')

    def organize(self, records: List[Dict]) -> List[Dict]:
        """
        Organize images into folder structure

        Args:
            records: List of image records

        Returns:
            List of movement results
        """
        logger.info(f"Starting image organization to {self.output_folder}")
        ensure_directory(self.output_folder)

        movements = []

        for record in tqdm(records, desc="Organizing images"):
            # Skip duplicates if configured
            if record.get('is_duplicate') == 'YES':
                continue

            movement = self._move_or_copy_image(record)
            movements.append(movement)

        logger.info(f"Organization complete: {len(movements)} images processed")
        return movements

    def _move_or_copy_image(self, record: Dict) -> Dict:
        """
        Move or copy image to destination folder

        Args:
            record: Image record

        Returns:
            Movement result dictionary
        """
        try:
            source_path = Path(record.get('Full Path', ''))
            if not source_path.exists():
                return {
                    'filename': record.get('Filename'),
                    'source': str(source_path),
                    'destination': '',
                    'status': 'Error: Source file not found'
                }

            # Determine destination folder
            dest_folder = self._get_destination_folder(record)
            ensure_directory(dest_folder)

            # Determine destination filename
            dest_filename = safe_filename(source_path.name)
            dest_path = dest_folder / dest_filename

            # Handle conflicts
            dest_path = self._handle_conflict(dest_path)

            # Move or copy
            if self.operation_type.lower() == 'move':
                shutil.move(str(source_path), str(dest_path))
                operation = 'Moved'
            else:
                shutil.copy2(str(source_path), str(dest_path))
                operation = 'Copied'

            logger.info(f"{operation}: {source_path.name} -> {dest_path}")

            return {
                'filename': record.get('Filename'),
                'source': str(source_path),
                'destination': str(dest_path),
                'status': f'Success: {operation}'
            }

        except Exception as e:
            logger.error(f"Error organizing {record.get('Filename')}: {e}")
            return {
                'filename': record.get('Filename'),
                'source': record.get('Full Path', ''),
                'destination': '',
                'status': f'Error: {str(e)}'
            }

    def _get_destination_folder(self, record: Dict) -> Path:
        """
        New logic:
        - If month > threshold (60): use yyyymmdd
        - Else: use yyyymm00 (flat monthly folder)
        """

        date_obj = record.get('_dt')
        if not date_obj:
            try:
                date_obj = datetime.strptime(record.get('sort_date', ''), "%Y-%m-%d %H:%M:%S")
            except:
                date_obj = datetime.now()

        month_key = date_obj.strftime("%Y%m")
        day_key = date_obj.strftime("%Y%m%d")

        # assume you stored this in organize()
        month_count = record.get('_month_count_map', None)

        # fallback safety
        if not month_count:
            month_count = self.config.get('_month_count_cache', {})

        count = month_count.get(month_key, 0)

        if count > self.threshold:
            # 👉 Many files → daily folders
            folder_name = day_key
        else:
            # 👉 Few files → single monthly folder
            folder_name = f"{month_key}00"

        return self.output_folder / folder_name

    def _handle_conflict(self, dest_path: Path) -> Path:
        """
        Handle filename conflicts

        Args:
            dest_path: Destination path

        Returns:
            Final destination path
        """
        if not dest_path.exists():
            return dest_path

        if self.conflict_strategy == 'skip':
            return dest_path

        elif self.conflict_strategy == 'overwrite':
            return dest_path

        elif self.conflict_strategy == 'rename':
            counter = 1
            stem = dest_path.stem
            suffix = dest_path.suffix

            while dest_path.exists():
                new_name = f"{stem}_{counter}{suffix}"
                dest_path = dest_path.parent / new_name
                counter += 1

            return dest_path

        return dest_path
