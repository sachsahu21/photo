"""
Image Organization Module
Organize images into smart folder structure
"""

import logging
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict
from collections import defaultdict

logger = logging.getLogger(__name__)


class ImageOrganizer:
    """Organize images into smart folder structure"""

    def __init__(self, config: Dict):
        self.config = config.get('organization', {})

        output_path = self.config.get('output_folder')
        if not output_path:
            raise ValueError("Missing organization.output_folder in config")

        self.output_folder = Path(output_path)
        self.operation = self.config.get('operation', 'copy')

        # 🔥 Threshold for day folder creation
        self.day_threshold = self.config.get('day_threshold', 60)

        # Will store counts like: {'20260204': 75}
        self.date_counts = defaultdict(int)

    # =====================================================
    # MAIN ENTRY
    # =====================================================
    def organize(self, records: List[Dict]) -> List[Dict]:
        """Organize images into folder structure"""

        self.output_folder.mkdir(parents=True, exist_ok=True)

        # 🔥 STEP 1: Pre-calculate counts per day
        self._calculate_date_counts(records)

        movements = []

        for record in records:

            # Skip deleted files
            if str(record.get('DELETE? (Yes/No)', '')).strip().lower() == 'yes':
                continue

            try:
                movement = self._move_or_copy_file(record)
                movements.append(movement)

            except Exception as e:
                filename = record.get('Filename') or record.get('filename')
                logger.error(f"Error organizing {filename}: {e}")

                movements.append({
                    'source_filename': filename,
                    'source_path': record.get('Full Path') or record.get('full_path'),
                    'destination_path': '',
                    'folder_path': '',
                    'status': f'Error: {str(e)[:50]}'
                })

        logger.info(f"Organized {len(movements)} images")
        return movements

    # =====================================================
    # STEP 1: COUNT IMAGES PER DAY
    # =====================================================
    def _calculate_date_counts(self, records: List[Dict]):
        """Count number of images per day"""

        for record in records:
            dt = self._extract_datetime(record)
            key = dt.strftime('%Y%m%d')
            self.date_counts[key] += 1

        logger.info(f"Date distribution: {dict(self.date_counts)}")

    # =====================================================
    # MOVE/COPY FILE
    # =====================================================
    def _move_or_copy_file(self, record: Dict) -> Dict:
        """Move or copy single file"""

        src = record.get('Full Path') or record.get('full_path')
        if not src:
            raise ValueError("Missing Full Path")

        src_path = Path(src)

        dest_folder = self._get_destination_folder(record)
        dest_folder.mkdir(parents=True, exist_ok=True)

        dest_path = self._get_destination_path(src_path, dest_folder)

        if self.operation == 'move':
            shutil.move(str(src_path), str(dest_path))
        else:
            shutil.copy2(str(src_path), str(dest_path))

        return {
            'source_filename': src_path.name,
            'source_path': str(src_path),
            'destination_path': str(dest_path),
            'folder_path': str(dest_folder.relative_to(self.output_folder)),
            'status': 'Success'
        }

    # =====================================================
    # DATE EXTRACTION
    # =====================================================
    def _extract_datetime(self, record: Dict) -> datetime:
        """Extract datetime safely from record"""

        date_value = (
            record.get('Date Taken')
            or record.get('date_taken')
            or record.get('file_modified')
        )

        if isinstance(date_value, datetime):
            return date_value

        if isinstance(date_value, str):
            for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
                try:
                    return datetime.strptime(date_value.strip(), fmt)
                except:
                    continue

        return datetime.now()

    # =====================================================
    # FOLDER LOGIC (CORE)
    # =====================================================
    def _get_destination_folder(self, record: Dict) -> Path:
        """Smart folder logic:
        - If >= threshold → yyyymmdd
        - Else → yyyymm00
        """

        dt = self._extract_datetime(record)

        day_key = dt.strftime('%Y%m%d')
        month_key = dt.strftime('%Y%m')

        count = self.date_counts.get(day_key, 0)

        if count >= self.day_threshold:
            folder_name = day_key  # e.g., 20260204
        else:
            folder_name = f"{month_key}00"  # e.g., 20260200

        return self.output_folder / folder_name

    # =====================================================
    # OVERWRITE LOGIC
    # =====================================================
    def _get_destination_path(self, src_path: Path, dest_folder: Path) -> Path:
        """Overwrite existing files"""

        dest_path = dest_folder / src_path.name

        if dest_path.exists():
            dest_path.unlink()  # overwrite

        return dest_path