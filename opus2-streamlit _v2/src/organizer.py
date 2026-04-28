
# ============================================================
# FILE: src/organizer.py
# ============================================================
"""Image Organizer - Date-based folder organization."""

import shutil
import logging
from pathlib import Path
from datetime import datetime
from collections import defaultdict

from tqdm import tqdm
from .utils import (parse_datetime_flexible, resolve_filename_conflict,
                    ensure_directory, safe_filename)

logger = logging.getLogger(__name__)


class ImageOrganizer:
    def __init__(self, config):
        org = config.get('organization', {})
        self.output_folder = Path(org.get('output_folder', './organized_images'))
        self.day_threshold = int(org.get('day_threshold', 60))
        self.use_exif = org.get('use_exif_date', True)
        self.operation = str(org.get('operation', 'copy')).lower()
        self.conflict = str(org.get('conflict_resolution', 'rename')).lower()
        self.show_progress = config.get('processing', {}).get('show_progress', True)
        ensure_directory(self.output_folder)

    def organize(self, records):
        if not records:
            return []

        active = [r for r in records
                   if str(r.get('delete_flag', '') or r.get('DELETE? (Yes/No)', '') or '').strip().lower()
                   not in ('yes', 'true', '1')]

        dated = [(r, self._date(r)) for r in active]
        day_counts = defaultdict(int)
        for _, dt in dated:
            if dt:
                day_counts[dt.strftime('%Y-%m-%d')] += 1

        d2f = {}
        for dk, cnt in day_counts.items():
            # d2f[dk] = dk if cnt >= self.day_threshold else dk[:6] + '00'
            month_key = dk[:7]  # YYYY-MM
            d2f[dk] = dk if cnt >= self.day_threshold else f"{month_key}-00"

        movements = []
        desc = 'Copying' if self.operation == 'copy' else 'Moving'
        for rec, dt in tqdm(dated, desc=desc, disable=not self.show_progress):
            movements.append(self._process(rec, dt, d2f))

        self._report(movements, day_counts, d2f)
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

    def _process(self, rec, dt, d2f):
        src = rec.get('full_path') or rec.get('Full Path') or ''
        fn = rec.get('filename') or rec.get('Filename') or ''
        if not src:
            return {'filename': fn, 'source': '', 'destination': '', 'status': 'Error: No path', 'folder': ''}
        source = Path(src)
        if not source.exists():
            return {'filename': fn, 'source': str(source), 'destination': '', 'status': 'Error: Not found', 'folder': ''}

        # folder = d2f.get(dt.strftime('%Y%m%d'), dt.strftime('%Y%m') + '00') if dt else 'undated'
        folder = d2f.get(
                        dt.strftime('%Y-%m-%d'),
                        dt.strftime('%Y-%m') + '-00'
                    ) if dt else 'undated'
        
        dest_dir = self.output_folder / folder
        ensure_directory(dest_dir)
        dest = resolve_filename_conflict(dest_dir / safe_filename(source.name), self.conflict)
        if dest is None:
            return {'filename': source.name, 'source': str(source), 'destination': '', 'status': 'Skipped', 'folder': folder}

        try:
            (shutil.move if self.operation == 'move' else shutil.copy2)(str(source), str(dest))
            return {'filename': source.name, 'source': str(source), 'destination': str(dest), 'status': 'Success', 'folder': folder}
        except Exception as e:
            return {'filename': source.name, 'source': str(source), 'destination': str(dest), 'status': f'Error: {e}', 'folder': folder}

    def _report(self, movements, day_counts, d2f):
        try:
            rp = self.output_folder / 'organization_report.txt'
            with open(rp, 'w', encoding='utf-8') as f:
                f.write(f"Organization Report - {datetime.now()}\n{'='*60}\n")
                s = sum(1 for m in movements if m['status'] == 'Success')
                e = sum(1 for m in movements if 'Error' in m['status'])
                f.write(f"Success: {s}, Errors: {e}, Total: {len(movements)}\n\n")
                fc = defaultdict(int)
                for m in movements:
                    if m['status'] == 'Success':
                        fc[m['folder']] += 1
                for fld in sorted(fc):
                    f.write(f"  {fld}: {fc[fld]} files\n")
        except Exception:
            pass
