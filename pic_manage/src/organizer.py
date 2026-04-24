

# ============================================================
# FILE: src/organizer.py
# ============================================================
"""
Image Organizer - Date-based folder organization

Logic:
  1. Parse date for each file (EXIF preferred, fallback to file_modified)
  2. Count files per calendar day
  3. >= day_threshold files -> YYYYMMDD folder
  4. < day_threshold files  -> YYYYMM00 monthly bucket
"""

import shutil
import logging
from pathlib import Path
from datetime import datetime
from collections import defaultdict

from tqdm import tqdm

from .utils import (
    parse_datetime_flexible, resolve_filename_conflict,
    ensure_directory, safe_filename
)

logger = logging.getLogger(__name__)


class ImageOrganizer:
    """Organize images into date-based folder structure."""

    def __init__(self, config):
        org_cfg = config.get('organization', {})

        self.output_folder = Path(org_cfg.get('output_folder', './organized_images'))
        self.day_threshold = int(org_cfg.get('day_threshold', 60))
        self.use_exif_date = org_cfg.get('use_exif_date', True)
        self.operation = str(org_cfg.get('operation', 'copy')).lower()
        self.conflict_strategy = str(org_cfg.get('conflict_resolution', 'rename')).lower()

        proc_cfg = config.get('processing', {})
        self.show_progress = proc_cfg.get('show_progress', True)

        ensure_directory(self.output_folder)

        logger.info(f"Organizer: output={self.output_folder}, threshold={self.day_threshold}, "
                     f"operation={self.operation}")

    def organize(self, records):
        if not records:
            logger.warning("No records to organize")
            return []

        active = []
        for r in records:
            flag = str(r.get('delete_flag', '') or
                       r.get('DELETE? (Yes/No)', '') or '').strip().lower()
            if flag not in ('yes', 'true', '1'):
                active.append(r)

        logger.info(f"Organizing {len(active)} files "
                     f"(skipped {len(records) - len(active)} marked for deletion)")

        dated = []
        for rec in active:
            dt = self._get_date(rec)
            dated.append((rec, dt))

        day_counts = defaultdict(int)
        for rec, dt in dated:
            if dt:
                day_counts[dt.strftime('%Y%m%d')] += 1

        day_to_folder = {}
        for day_key, count in day_counts.items():
            if count >= self.day_threshold:
                day_to_folder[day_key] = day_key
            else:
                day_to_folder[day_key] = day_key[:6] + '00'

        logger.info(f"Unique days: {len(day_counts)}, "
                     f"days >= {self.day_threshold}: "
                     f"{sum(1 for c in day_counts.values() if c >= self.day_threshold)}")

        movements = []
        desc = 'Copying' if self.operation == 'copy' else 'Moving'

        it = tqdm(dated, desc=f"{desc} files", unit="file",
                  disable=not self.show_progress)

        for rec, dt in it:
            mv = self._process_file(rec, dt, day_to_folder)
            movements.append(mv)

        success = sum(1 for m in movements if m['status'] == 'Success')
        errors = sum(1 for m in movements if 'Error' in m['status'])
        skipped = sum(1 for m in movements if 'Skip' in m['status'])

        logger.info(f"Organization done: {success} success, {skipped} skipped, {errors} errors")
        self._write_report(movements, day_counts, day_to_folder)

        return movements

    def _get_date(self, record):
        if self.use_exif_date:
            for key in ['date_taken', 'Date Taken']:
                val = record.get(key)
                if val:
                    dt = parse_datetime_flexible(val)
                    if dt:
                        return dt

        for key in ['file_modified', 'File Modified']:
            val = record.get(key)
            if val:
                dt = parse_datetime_flexible(val)
                if dt:
                    return dt

        return None

    def _process_file(self, record, dt, day_to_folder):
        source_str = (record.get('full_path') or record.get('Full Path') or '')
        filename = (record.get('filename') or record.get('Filename') or '')

        if not source_str:
            return {
                'filename': filename or 'unknown',
                'source': '', 'destination': '',
                'status': 'Error: No source path', 'folder': '',
            }

        source = Path(source_str)
        if not source.exists():
            return {
                'filename': filename or source.name,
                'source': str(source), 'destination': '',
                'status': 'Error: Source not found', 'folder': '',
            }

        if dt:
            day_key = dt.strftime('%Y%m%d')
            folder_name = day_to_folder.get(day_key, day_key[:6] + '00')
        else:
            folder_name = 'undated'

        dest_folder = self.output_folder / folder_name
        ensure_directory(dest_folder)

        dest_path = dest_folder / safe_filename(source.name)
        resolved = resolve_filename_conflict(dest_path, self.conflict_strategy)

        if resolved is None:
            return {
                'filename': source.name,
                'source': str(source), 'destination': str(dest_path),
                'status': 'Skipped (conflict)', 'folder': folder_name,
            }

        try:
            if self.operation == 'move':
                shutil.move(str(source), str(resolved))
            else:
                shutil.copy2(str(source), str(resolved))

            return {
                'filename': source.name,
                'source': str(source), 'destination': str(resolved),
                'status': 'Success', 'folder': folder_name,
            }
        except Exception as e:
            logger.error(f"Error organizing {source.name}: {e}")
            return {
                'filename': source.name,
                'source': str(source), 'destination': str(resolved),
                'status': f'Error: {str(e)[:80]}', 'folder': folder_name,
            }

    def _write_report(self, movements, day_counts, day_to_folder):
        report_path = self.output_folder / 'organization_report.txt'
        try:
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write("=" * 70 + "\n")
                f.write("IMAGE ORGANIZATION REPORT\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 70 + "\n\n")

                success = sum(1 for m in movements if m['status'] == 'Success')
                errors = sum(1 for m in movements if 'Error' in m['status'])

                f.write(f"Total processed: {len(movements)}\n")
                f.write(f"Success: {success}\n")
                f.write(f"Errors: {errors}\n")
                f.write(f"Day threshold: {self.day_threshold}\n")
                f.write(f"Operation: {self.operation}\n\n")

                f.write("-" * 50 + "\nFOLDER DISTRIBUTION\n" + "-" * 50 + "\n")
                folder_counts = defaultdict(int)
                for m in movements:
                    if m['status'] == 'Success':
                        folder_counts[m['folder']] += 1
                for folder in sorted(folder_counts.keys()):
                    f.write(f"  {folder}: {folder_counts[folder]} files\n")

                f.write(f"\n{'-' * 50}\nDAY ANALYSIS\n{'-' * 50}\n")
                for day_key in sorted(day_counts.keys()):
                    count = day_counts[day_key]
                    folder = day_to_folder.get(day_key, 'unknown')
                    marker = " *** DAILY" if count >= self.day_threshold else ""
                    f.write(f"  {day_key}: {count} files -> {folder}{marker}\n")

                error_list = [m for m in movements if 'Error' in m['status']]
                if error_list:
                    f.write(f"\n{'-' * 50}\nERRORS\n{'-' * 50}\n")
                    for m in error_list:
                        f.write(f"  {m['filename']}: {m['status']}\n")

            logger.info(f"Report saved: {report_path}")
        except Exception as e:
            logger.error(f"Error writing report: {e}")
