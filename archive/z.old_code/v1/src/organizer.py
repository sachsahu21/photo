"""
Image Organization Module - Smart Date-based Folder Logic
- >= day_threshold pics in a day → YYYYMMDD
- <  day_threshold pics in a day → YYYYMM00  (monthly bucket)
"""

import logging
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict
from collections import defaultdict

logger = logging.getLogger(__name__)


class ImageOrganizer:

    def __init__(self, config: Dict):
        self.config = config.get('organization', {})

        output_path = self.config.get('output_folder')
        if not output_path:
            raise ValueError("Missing organization.output_folder in config")

        self.output_folder = Path(output_path)
        self.operation     = self.config.get('operation', 'copy')
        self.day_threshold = self.config.get('day_threshold', 60)
        self.date_counts: Dict[str, int] = defaultdict(int)   # key = YYYYMMDD

    # ------------------------------------------------------------------
    # PUBLIC
    # ------------------------------------------------------------------
    def organize(self, records: List[Dict]) -> List[Dict]:
        self.output_folder.mkdir(parents=True, exist_ok=True)

        # Pass 1 – count images per calendar day
        self._calculate_date_counts(records)

        movements = []
        for record in records:
            # Respect delete flag (handles both key variants from Excel / direct scan)
            delete_val = (
                record.get('DELETE? (Yes/No)')
                or record.get('delete_flag', '')
            )
            if str(delete_val).strip().lower() == 'yes':
                continue

            try:
                movements.append(self._move_or_copy_file(record))
            except Exception as e:
                filename = record.get('Filename') or record.get('filename', '?')
                src      = record.get('Full Path') or record.get('full_path', '')
                logger.error(f"Error organising {filename}: {e}")
                movements.append({
                    'source_filename': filename,
                    'source_path':     src,
                    'destination_path': '',
                    'folder_path':      '',
                    'status': f'Error: {str(e)[:50]}'
                })

        logger.info(f"Organised {len(movements)} files")
        return movements

    # ------------------------------------------------------------------
    # PRIVATE – date counting
    # ------------------------------------------------------------------
    def _calculate_date_counts(self, records: List[Dict]):
        for record in records:
            dt  = self._extract_datetime(record)
            key = dt.strftime('%Y%m%d')
            self.date_counts[key] += 1
        logger.info(f"Date distribution: {dict(self.date_counts)}")

    # ------------------------------------------------------------------
    # PRIVATE – core folder logic
    # ------------------------------------------------------------------
    def _get_destination_folder(self, record: Dict) -> Path:
        """
        Key logic:
          count(day) >= day_threshold  →  YYYYMMDD   e.g. 20260204
          count(day) <  day_threshold  →  YYYYMM00   e.g. 20260200
        """
        dt      = self._extract_datetime(record)
        day_key = dt.strftime('%Y%m%d')           # e.g. "20260204"
        mon_key = dt.strftime('%Y%m')             # e.g. "202602"

        if self.date_counts.get(day_key, 0) >= self.day_threshold:
            folder_name = day_key                 # 20260204
        else:
            folder_name = f"{mon_key}00"          # 20260200

        return self.output_folder / folder_name

    # ------------------------------------------------------------------
    # PRIVATE – file move/copy
    # ------------------------------------------------------------------
    def _move_or_copy_file(self, record: Dict) -> Dict:
        src = record.get('Full Path') or record.get('full_path')
        if not src:
            raise ValueError("Missing full_path in record")

        src_path    = Path(src)
        dest_folder = self._get_destination_folder(record)
        dest_folder.mkdir(parents=True, exist_ok=True)

        dest_path = dest_folder / src_path.name
        if dest_path.exists():
            dest_path.unlink()          # overwrite

        if self.operation == 'move':
            shutil.move(str(src_path), str(dest_path))
        else:
            shutil.copy2(str(src_path), str(dest_path))

        return {
            'source_filename':  src_path.name,
            'source_path':      str(src_path),
            'destination_path': str(dest_path),
            'folder_path':      str(dest_folder.relative_to(self.output_folder)),
            'status': 'Success'
        }

    # ------------------------------------------------------------------
    # PRIVATE – datetime extraction
    # ------------------------------------------------------------------
    def _extract_datetime(self, record: Dict) -> datetime:
        """Try EXIF date first, fall back to file-modified, then now()."""
        date_value = (
            record.get('Date Taken')        # from Excel header
            or record.get('date_taken')     # from direct scan
            or record.get('File Modified')
            or record.get('file_modified')
        )

        if isinstance(date_value, datetime):
            return date_value

        if isinstance(date_value, str):
            for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
                try:
                    return datetime.strptime(date_value.strip(), fmt)
                except ValueError:
                    continue

        return datetime.now()