# ============================================================
# FILE: src/organizer.py
# ============================================================
"""
Image Organizer v2.1
- Hyphen date folders (YYYY-MM-DD)
- Reuse existing YYYY-MM-DD-[text] folders
- Video subfolder
"""

import shutil
import logging
from pathlib import Path
from datetime import datetime
from collections import defaultdict

from tqdm import tqdm
from .utils import (
    parse_datetime_flexible, resolve_filename_conflict,
    ensure_directory, safe_filename, is_valid_date_folder,
    is_valid_month_folder
)

logger = logging.getLogger(__name__)


class ImageOrganizer:

    def __init__(self, config):
        org = config.get('organization', {})
        self.output_folder = Path(org.get('output_folder', './organized_images'))
        self.day_threshold = int(org.get('day_threshold', 60))
        self.use_exif = org.get('use_exif_date', True)
        self.operation = str(org.get('operation', 'copy')).lower()
        self.conflict = str(org.get('conflict_resolution', 'rename')).lower()
        self.reuse_existing = org.get('reuse_existing_folders', True)
        self.video_subfolder = org.get('video_subfolder', True)
        self.show_progress = config.get('processing', {}).get('show_progress', True)
        ensure_directory(self.output_folder)
        self._existing_cache = None

    def _scan_existing_folders(self):
        """Scan output dir for existing YYYY-MM-DD* and YYYY-MM-00* folders."""
        cache = {'daily': {}, 'monthly': {}}
        try:
            if not self.output_folder.exists():
                return cache
            for item in self.output_folder.iterdir():
                if not item.is_dir():
                    continue
                name = item.name
                date_prefix = is_valid_date_folder(name)
                if date_prefix:
                    if date_prefix not in cache['daily']:
                        cache['daily'][date_prefix] = name
                    continue
                month_prefix = is_valid_month_folder(name)
                if month_prefix:
                    if month_prefix not in cache['monthly']:
                        cache['monthly'][month_prefix] = name

            if cache['daily'] or cache['monthly']:
                logger.info(f"Existing folders: {len(cache['daily'])} daily, "
                            f"{len(cache['monthly'])} monthly")
        except Exception as e:
            logger.warning(f"Scan existing folders error: {e}")
        return cache

    def _resolve_folder_name(self, dt, day_counts):
        """Determine target folder. Reuses existing YYYY-MM-DD-[text] if found."""
        if dt is None:
            return 'undated'

        date_key = dt.strftime('%Y-%m-%d')
        month_key = dt.strftime('%Y-%m') + '-00'
        day_count_key = dt.strftime('%Y%m%d')
        is_daily = day_counts.get(day_count_key, 0) >= self.day_threshold

        if is_daily:
            if self.reuse_existing and self._existing_cache:
                existing = self._existing_cache['daily'].get(date_key)
                if existing:
                    return existing
            return date_key
        else:
            if self.reuse_existing and self._existing_cache:
                existing_month = self._existing_cache['monthly'].get(month_key)
                if existing_month:
                    return existing_month
                existing_daily = self._existing_cache['daily'].get(date_key)
                if existing_daily:
                    return existing_daily
            return month_key

    def organize(self, records):
        if not records:
            return []

        if self.reuse_existing:
            self._existing_cache = self._scan_existing_folders()

        active = [r for r in records
                   if str(r.get('delete_flag', '') or
                          r.get('DELETE? (Yes/No)', '') or '').strip().lower()
                   not in ('yes', 'true', '1')]

        logger.info(f"Organizing {len(active)} files "
                     f"(skipped {len(records) - len(active)} marked for deletion)")

        dated = [(r, self._date(r)) for r in active]

        day_counts = defaultdict(int)
        for _, dt in dated:
            if dt:
                day_counts[dt.strftime('%Y%m%d')] += 1

        daily_count = sum(1 for c in day_counts.values() if c >= self.day_threshold)
        logger.info(f"Days: {len(day_counts)} total, {daily_count} with >= {self.day_threshold} files")

        movements = []
        desc = 'Copying' if self.operation == 'copy' else 'Moving'
        for rec, dt in tqdm(dated, desc=desc, disable=not self.show_progress):
            folder_name = self._resolve_folder_name(dt, day_counts)
            movements.append(self._process(rec, folder_name))

        self._report(movements, day_counts)

        success = sum(1 for m in movements if m['status'] == 'Success')
        errors = sum(1 for m in movements if 'Error' in m['status'])
        logger.info(f"Organization done: {success} success, {errors} errors")

        return movements

    def _date(self, r):
        if self.use_exif:
            for k in ['date_taken', 'Date Taken']:
                v = r.get(k)
                if v:
                    dt = parse_datetime_flexible(v)
                    if dt:
                        return dt
        for k in ['file_modified', 'File Modified']:
            v = r.get(k)
            if v:
                dt = parse_datetime_flexible(v)
                if dt:
                    return dt
        return None

    def _process(self, rec, folder_name):
        src = rec.get('full_path') or rec.get('Full Path') or ''
        fn = rec.get('filename') or rec.get('Filename') or ''
        file_type = rec.get('file_type') or rec.get('Type') or ''

        if not src:
            return {'filename': fn, 'source': '', 'destination': '',
                    'status': 'Error: No path', 'folder': ''}
        source = Path(src)
        if not source.exists():
            return {'filename': fn, 'source': str(source), 'destination': '',
                    'status': 'Error: Not found', 'folder': ''}

        dest_dir = self.output_folder / folder_name

        # Video subfolder
        if self.video_subfolder and file_type == 'video':
            dest_dir = dest_dir / 'videos'

        ensure_directory(dest_dir)
        dest = resolve_filename_conflict(dest_dir / safe_filename(source.name), self.conflict)
        if dest is None:
            return {'filename': source.name, 'source': str(source),
                    'destination': '', 'status': 'Skipped (conflict)', 'folder': folder_name}

        try:
            if self.operation == 'move':
                shutil.move(str(source), str(dest))
            else:
                shutil.copy2(str(source), str(dest))
            return {'filename': source.name, 'source': str(source),
                    'destination': str(dest), 'status': 'Success', 'folder': folder_name}
        except Exception as e:
            return {'filename': source.name, 'source': str(source),
                    'destination': str(dest), 'status': f'Error: {e}', 'folder': folder_name}

    def _report(self, movements, day_counts):
        try:
            rp = self.output_folder / 'organization-report.txt'
            with open(rp, 'w', encoding='utf-8') as f:
                f.write(f"Organization Report\n{'='*60}\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Reuse existing folders: {self.reuse_existing}\n")
                f.write(f"Video subfolder: {self.video_subfolder}\n")
                f.write(f"Day threshold: {self.day_threshold}\n")
                f.write(f"Operation: {self.operation}\n\n")

                s = sum(1 for m in movements if m['status'] == 'Success')
                e = sum(1 for m in movements if 'Error' in m['status'])
                sk = sum(1 for m in movements if 'Skip' in m['status'])
                f.write(f"Success: {s}\nErrors: {e}\nSkipped: {sk}\nTotal: {len(movements)}\n\n")

                f.write(f"{'='*60}\nFOLDER DISTRIBUTION\n{'='*60}\n")
                fc = defaultdict(int)
                for m in movements:
                    if m['status'] == 'Success':
                        fc[m['folder']] += 1
                for fld in sorted(fc):
                    f.write(f"  {fld}: {fc[fld]} files\n")

                f.write(f"\n{'='*60}\nDAY ANALYSIS\n{'='*60}\n")
                for dk in sorted(day_counts):
                    cnt = day_counts[dk]
                    marker = " *** DAILY" if cnt >= self.day_threshold else ""
                    f.write(f"  {dk}: {cnt} files{marker}\n")

                err_list = [m for m in movements if 'Error' in m['status']]
                if err_list:
                    f.write(f"\n{'='*60}\nERRORS\n{'='*60}\n")
                    for m in err_list:
                        f.write(f"  {m['filename']}: {m['status']}\n")

            logger.info(f"Report saved: {rp}")
        except Exception as e:
            logger.error(f"Report error: {e}")
