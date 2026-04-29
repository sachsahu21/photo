# ============================================================
# FILE: src/organizer.py
# ============================================================
"""
Image Organizer v2.2
- Folder format: YYYY-MM-DD-[xxpic]-[text]
- Configurable date structure: flat | year-month | year-month-day
- Screenshot separation
- Video subfolder
- Reuse existing dated folders
"""

import re
import shutil
import logging
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter

from tqdm import tqdm
from .utils import (
    parse_datetime_flexible, resolve_filename_conflict,
    ensure_directory, safe_filename, is_valid_date_folder,
    is_valid_month_folder
)

logger = logging.getLogger(__name__)

MONTH_NAMES = {
    1: '01-Jan', 2: '02-Feb', 3: '03-Mar', 4: '04-Apr',
    5: '05-May', 6: '06-Jun', 7: '07-Jul', 8: '08-Aug',
    9: '09-Sep', 10: '10-Oct', 11: '11-Nov', 12: '12-Dec'
}

# Common screen resolutions for screenshot detection
SCREEN_RESOLUTIONS = {
    (1080, 1920), (1080, 2340), (1080, 2400), (1080, 2520),
    (1170, 2532), (1179, 2556), (1284, 2778), (1290, 2796),
    (1440, 2560), (1440, 3040), (1440, 3200),
    (750, 1334), (828, 1792), (1125, 2436),
    (1920, 1080), (2560, 1440), (3840, 2160),
    (2048, 2732), (1668, 2388), (1620, 2160),
    (1536, 2048), (2160, 1620), (2388, 1668),
    (2732, 2048), (2048, 1536),
}

WHATSAPP_PATTERN = re.compile(
    r'^(IMG|VID|AUD|PTT|STK)-\d{8}-WA\d+', re.IGNORECASE
)


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

        # v2.2 options
        self.folder_structure = org.get('folder_structure', 'flat')
        self.separate_screenshots = org.get('separate_screenshots', True)

        ensure_directory(self.output_folder)
        self._existing_cache = None

    # ── Screenshot Detection ──

    def _is_screenshot(self, rec):
        """Detect if file is a screenshot."""
        if not self.separate_screenshots:
            return False

        # Check filename keywords
        fn = str(rec.get('filename') or rec.get('Filename') or '').lower()
        if any(kw in fn for kw in ['screenshot', 'screen_shot', 'screen-shot',
                                     'capture', 'snip', 'screen shot']):
            return True

        # Check resolution + no EXIF
        w = rec.get('width') or rec.get('Width (px)')
        h = rec.get('height') or rec.get('Height (px)')
        has_exif = rec.get('has_exif') or rec.get('Has EXIF')
        meta_status = str(rec.get('metadata_status', ''))

        if w and h:
            try:
                dims = (int(w), int(h))
                dims_flip = (int(h), int(w))
                if (dims in SCREEN_RESOLUTIONS or dims_flip in SCREEN_RESOLUTIONS):
                    if not has_exif or meta_status in ('No EXIF', 'Minimal EXIF'):
                        return True
            except (ValueError, TypeError):
                pass

        return False

    # ── Existing Folder Scanning ──

    def _scan_existing_folders(self):
        """Scan output dir for existing YYYY-MM-DD* folders (recursive for year-month)."""
        cache = {'daily': {}, 'monthly': {}}
        try:
            if not self.output_folder.exists():
                return cache

            # Use rglob for nested structures
            search_items = self.output_folder.rglob('*') if self.folder_structure != 'flat' \
                else self.output_folder.iterdir()

            for item in search_items:
                if not item.is_dir():
                    continue
                name = item.name

                date_prefix = is_valid_date_folder(name)
                if date_prefix:
                    if date_prefix not in cache['daily']:
                        cache['daily'][date_prefix] = {
                            'name': name,
                            'rel_path': str(item.relative_to(self.output_folder)),
                            'full_path': str(item),
                        }
                    continue

                month_prefix = is_valid_month_folder(name)
                if month_prefix:
                    if month_prefix not in cache['monthly']:
                        cache['monthly'][month_prefix] = {
                            'name': name,
                            'rel_path': str(item.relative_to(self.output_folder)),
                            'full_path': str(item),
                        }

            if cache['daily'] or cache['monthly']:
                logger.info(f"Existing folders: {len(cache['daily'])} daily, "
                            f"{len(cache['monthly'])} monthly")
        except Exception as e:
            logger.warning(f"Scan existing folders error: {e}")
        return cache

    # ── Folder Name Builder ──

    def _build_folder_name(self, date_key, count, location_hint=''):
        """
        Build folder name: YYYY-MM-DD-XXpic or YYYY-MM-DD-XXpic-text
        Examples:
            2026-03-15-85pic
            2026-03-15-85pic-singapore
            2026-03-00-12pic
        """
        pic_label = f"{count}pic"
        if location_hint:
            clean = re.sub(r'[^a-z0-9]+', '-', location_hint.lower()).strip('-')
            if clean and len(clean) > 1:
                return f"{date_key}-{pic_label}-{clean}"
        return f"{date_key}-{pic_label}"

    def _build_screenshot_folder_name(self, count, dt=None):
        """Build screenshot folder name with count."""
        if dt:
            month_key = dt.strftime('%Y-%m')
            return f"{month_key}-screenshots-{count}pic"
        return f"screenshots-{count}pic"

    def _get_location_hint(self, records):
        """Get most common location from a group of records."""
        locations = []
        for rec in records:
            for key in ['location_city', 'location_name', 'Location']:
                loc = rec.get(key)
                if loc and str(loc).strip():
                    locations.append(str(loc).strip().lower())
                    break
        if not locations:
            return ''
        most_common = Counter(locations).most_common(1)[0]
        # Only use if at least 30% of records have this location
        if most_common[1] >= len(records) * 0.3:
            return most_common[0]
        return ''

    # ── Path Builder ──

    def _build_dest_path(self, folder_name, dt, file_type):
        """
        Build full destination path based on folder_structure.

        flat:           output/2026-03-15-85pic-singapore/
        year-month:     output/2026/03-Mar/2026-03-15-85pic-singapore/
        year-month-day: output/2026/03-Mar/15-85pic-singapore/
        """
        if self.folder_structure == 'year-month' and dt:
            year = str(dt.year)
            month = MONTH_NAMES.get(dt.month, f"{dt.month:02d}")
            dest = self.output_folder / year / month / folder_name
        elif self.folder_structure == 'year-month-day' and dt:
            year = str(dt.year)
            month = MONTH_NAMES.get(dt.month, f"{dt.month:02d}")
            # For year-month-day, replace date prefix with just day
            day_match = re.match(r'^\d{4}-\d{2}-(\d{2})(.*)', folder_name)
            if day_match:
                day_name = day_match.group(1) + day_match.group(2)
                dest = self.output_folder / year / month / day_name
            else:
                dest = self.output_folder / year / month / folder_name
        else:
            # flat
            dest = self.output_folder / folder_name

        # Video subfolder
        if self.video_subfolder and file_type == 'video':
            dest = dest / 'videos'

        return dest

    # ── Resolve Existing ──

    def _find_existing_folder(self, date_key):
        """
        Check if an existing folder matches this date.
        Returns existing folder name or None.
        """
        if not self.reuse_existing or not self._existing_cache:
            return None

        # Check daily
        existing = self._existing_cache['daily'].get(date_key)
        if existing:
            return existing

        # Check monthly
        if date_key.endswith('-00'):
            existing = self._existing_cache['monthly'].get(date_key)
            if existing:
                return existing

        return None

    def _update_folder_name_with_count(self, existing_name, new_count):
        """
        Update the pic count in an existing folder name.
        2026-03-15-85pic-singapore → 2026-03-15-120pic-singapore
        """
        match = re.match(r'^(.*?)-(\d+)pic(.*){formattedValue}#x27;, existing_name)
        match = re.match(r'^(.*?)-(\d+)pic(.*){formattedValue}#x27;, existing_name)

        if match:
            prefix = match.group(1)
            suffix = match.group(3)
            return f"{prefix}-{new_count}pic{suffix}"
        # No pic count found, append it
        return f"{existing_name}-{new_count}pic"

    # ── Date Extraction ──

    def _date(self, r):
        """Extract date from record."""
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

    # ── Main Organize ──

    def organize(self, records):
        if not records:
            return []

        if self.reuse_existing:
            self._existing_cache = self._scan_existing_folders()

        # Separate deleted, screenshots, normal
        screenshots = []
        normal = []
        skipped = 0

        for r in records:
            delete_flag = str(r.get('delete_flag', '') or
                              r.get('DELETE? (Yes/No)', '') or '').strip().lower()
            if delete_flag in ('yes', 'true', '1'):
                skipped += 1
                continue

            if self._is_screenshot(r):
                screenshots.append(r)
            else:
                normal.append(r)

        logger.info(f"Organizing: {len(normal)} normal, {len(screenshots)} screenshots, "
                     f"{skipped} skipped (deleted)")

        movements = []

        # ── Process Screenshots ──
        if screenshots:
            print(f"  📱 Screenshots: {len(screenshots)}")
            movements.extend(self._organize_screenshots(screenshots))

        # ── Process Normal Photos/Videos ──
        if normal:
            movements.extend(self._organize_normal(normal))

        # ── Rename folders with final counts ──
        self._rename_folders_with_counts(movements)

        self._report(movements)

        success = sum(1 for m in movements if m['status'] == 'Success')
        errors = sum(1 for m in movements if 'Error' in m['status'])
        logger.info(f"Organization done: {success} success, {errors} errors")

        return movements

    def _organize_screenshots(self, screenshots):
        """Organize screenshot files into screenshot folders."""
        movements = []

        # Group by month
        month_groups = defaultdict(list)
        for rec in screenshots:
            dt = self._date(rec)
            if dt:
                month_key = dt.strftime('%Y-%m')
                month_groups[month_key].append((rec, dt))
            else:
                month_groups['undated'].append((rec, None))

        for month_key, group in month_groups.items():
            count = len(group)
            if month_key == 'undated':
                folder_name = f"screenshots-{count}pic"
                sample_dt = None
            else:
                folder_name = f"{month_key}-screenshots-{count}pic"
                sample_dt = group[0][1]

            for rec, dt in tqdm(group, desc=f"  {folder_name}",
                                 disable=not self.show_progress):
                file_type = rec.get('file_type') or rec.get('Type') or ''

                if self.folder_structure == 'year-month' and sample_dt:
                    year = str(sample_dt.year)
                    month = MONTH_NAMES.get(sample_dt.month, f"{sample_dt.month:02d}")
                    dest_dir = self.output_folder / year / month / folder_name
                elif self.folder_structure == 'year-month-day' and sample_dt:
                    year = str(sample_dt.year)
                    month = MONTH_NAMES.get(sample_dt.month, f"{sample_dt.month:02d}")
                    dest_dir = self.output_folder / year / month / folder_name
                else:
                    dest_dir = self.output_folder / folder_name

                if self.video_subfolder and file_type == 'video':
                    dest_dir = dest_dir / 'videos'

                movements.append(self._move_file(rec, dest_dir, folder_name))

        return movements

    def _organize_normal(self, records):
        """Organize normal photos and videos by date with pic counts."""
        movements = []

        # Extract dates
        dated = [(r, self._date(r)) for r in records]

        # Count files per day
        day_counts = defaultdict(int)
        day_records = defaultdict(list)
        undated = []

        for rec, dt in dated:
            if dt:
                day_key = dt.strftime('%Y%m%d')
                day_counts[day_key] += 1
                day_records[day_key].append((rec, dt))
            else:
                undated.append((rec, None))

        # Determine which days get daily vs monthly folders
        daily_days = set()
        monthly_buckets = defaultdict(list)

        for day_key, count in day_counts.items():
            if count >= self.day_threshold:
                daily_days.add(day_key)
            else:
                # Group into monthly bucket
                month_key = day_key[:6]  # YYYYMM
                monthly_buckets[month_key].extend(day_records[day_key])

        # ── Process daily folders ──
        daily_count = len(daily_days)
        if daily_count:
            logger.info(f"Daily folders: {daily_count} days with >= {self.day_threshold} files")

        for day_key in sorted(daily_days):
            group = day_records[day_key]
            sample_dt = group[0][1]
            date_str = sample_dt.strftime('%Y-%m-%d')
            count = len(group)

            # Get location hint
            location = self._get_location_hint([r for r, _ in group])

            # Check existing folder
            existing = self._find_existing_folder(date_str)
            if existing:
                # Reuse existing folder path but will rename later with count
                folder_name = existing['name']
                logger.info(f"Reusing existing folder: {folder_name}")
            else:
                folder_name = self._build_folder_name(date_str, count, location)

            desc = f"  {folder_name}"
            for rec, dt in tqdm(group, desc=desc, disable=not self.show_progress):
                file_type = rec.get('file_type') or rec.get('Type') or ''
                dest_dir = self._build_dest_path(folder_name, dt, file_type)
                movements.append(self._move_file(rec, dest_dir, folder_name))

        # ── Process monthly buckets ──
        for month_key in sorted(monthly_buckets):
            group = monthly_buckets[month_key]
            sample_dt = group[0][1]
            date_str = sample_dt.strftime('%Y-%m') + '-00'
            count = len(group)

            location = self._get_location_hint([r for r, _ in group])

            existing = self._find_existing_folder(date_str)
            if existing:
                folder_name = existing['name']
                logger.info(f"Reusing existing folder: {folder_name}")
            else:
                folder_name = self._build_folder_name(date_str, count, location)

            desc = f"  {folder_name}"
            for rec, dt in tqdm(group, desc=desc, disable=not self.show_progress):
                file_type = rec.get('file_type') or rec.get('Type') or ''
                dest_dir = self._build_dest_path(folder_name, dt, file_type)
                movements.append(self._move_file(rec, dest_dir, folder_name))

        # ── Process undated ──
        if undated:
            count = len(undated)
            folder_name = f"undated-{count}pic"
            for rec, dt in tqdm(undated, desc=f"  {folder_name}",
                                 disable=not self.show_progress):
                file_type = rec.get('file_type') or rec.get('Type') or ''
                dest_dir = self.output_folder / folder_name
                if self.video_subfolder and file_type == 'video':
                    dest_dir = dest_dir / 'videos'
                movements.append(self._move_file(rec, dest_dir, folder_name))

        return movements

    # ── Rename Folders With Actual Counts ──

    def _rename_folders_with_counts(self, movements):
        """
        After all files are copied/moved, rename folders to reflect
        actual file counts (in case some were skipped/errored).

        2026-03-15-85pic-singapore → 2026-03-15-82pic-singapore
        (if 3 files had errors)
        """
        # Count successful files per destination folder
        folder_counts = defaultdict(int)
        folder_paths = {}

        for m in movements:
            if m['status'] == 'Success' and m.get('destination'):
                dest = Path(m['destination'])
                parent = dest.parent
                # Skip videos subfolder — count in parent
                if parent.name == 'videos':
                    parent = parent.parent
                folder_counts[str(parent)] += 1
                folder_paths[str(parent)] = parent

        # Rename each folder
        for folder_str, count in folder_counts.items():
            folder = Path(folder_str)
            if not folder.exists():
                continue

            old_name = folder.name
            # Check if name already has pic count
            # match = re.match(r'^(.*?)-(\d+)pic(.*){formattedValue}#x27;, old_name)
            match = re.match(r'^(.*?)-(\d+)pic(.*){formattedValue}#x27;, existing_name)
            if match:
                prefix = match.group(1)
                old_count = int(match.group(2))
                suffix = match.group(3)

                # Only rename if count changed
                if old_count != count:
                    new_name = f"{prefix}-{count}pic{suffix}"
                    new_path = folder.parent / new_name
                    if not new_path.exists():
                        try:
                            folder.rename(new_path)
                            logger.info(f"Renamed: {old_name} → {new_name}")
                            # Update movements
                            for m in movements:
                                if m.get('destination') and folder_str in m['destination']:
                                    m['destination'] = m['destination'].replace(
                                        old_name, new_name)
                                if m.get('folder') == old_name:
                                    m['folder'] = new_name
                        except Exception as e:
                            logger.warning(f"Rename failed {old_name}: {e}")

    # ── File Mover ──

    def _move_file(self, rec, dest_dir, folder_label):
        """Copy or move a single file to destination."""
        src = rec.get('full_path') or rec.get('Full Path') or ''
        fn = rec.get('filename') or rec.get('Filename') or ''

        if not src:
            return {'filename': fn, 'source': '', 'destination': '',
                    'status': 'Error: No path', 'folder': folder_label}
        source = Path(src)
        if not source.exists():
            return {'filename': fn, 'source': str(source), 'destination': '',
                    'status': 'Error: Not found', 'folder': folder_label}

        ensure_directory(dest_dir)
        dest = resolve_filename_conflict(
            dest_dir / safe_filename(source.name), self.conflict)
        if dest is None:
            return {'filename': source.name, 'source': str(source),
                    'destination': '', 'status': 'Skipped (conflict)',
                    'folder': folder_label}

        try:
            if self.operation == 'move':
                shutil.move(str(source), str(dest))
            else:
                shutil.copy2(str(source), str(dest))
            return {'filename': source.name, 'source': str(source),
                    'destination': str(dest), 'status': 'Success',
                    'folder': folder_label}
        except Exception as e:
            return {'filename': source.name, 'source': str(source),
                    'destination': str(dest), 'status': f'Error: {e}',
                    'folder': folder_label}

    # ── Report ──

    def _report(self, movements):
        try:
            rp = self.output_folder / 'organization-report.txt'
            with open(rp, 'w', encoding='utf-8') as f:
                f.write(f"Organization Report\n{'='*60}\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Structure: {self.folder_structure}\n")
                f.write(f"Separate screenshots: {self.separate_screenshots}\n")
                f.write(f"Reuse existing: {self.reuse_existing}\n")
                f.write(f"Video subfolder: {self.video_subfolder}\n")
                f.write(f"Operation: {self.operation}\n")
                f.write(f"Conflict: {self.conflict}\n")
                f.write(f"Day threshold: {self.day_threshold}\n\n")

                s = sum(1 for m in movements if m['status'] == 'Success')
                e = sum(1 for m in movements if 'Error' in m['status'])
                sk = sum(1 for m in movements if 'Skip' in m['status'])
                f.write(f"Success: {s}\nErrors: {e}\nSkipped: {sk}\n"
                        f"Total: {len(movements)}\n\n")

                # Folder distribution
                f.write(f"{'='*60}\nFOLDER DISTRIBUTION\n{'='*60}\n")
                fc = defaultdict(int)
                for m in movements:
                    if m['status'] == 'Success':
                        fc[m['folder']] += 1
                for fld in sorted(fc):
                    f.write(f"  {fld}: {fc[fld]} files\n")

                # Category breakdown
                cats = defaultdict(int)
                for m in movements:
                    if m['status'] == 'Success':
                        folder = m.get('folder', '').lower()
                        if 'screenshot' in folder:
                            cats['Screenshots'] += 1
                        elif 'undated' in folder:
                            cats['Undated'] += 1
                        else:
                            cats['Dated Photos/Videos'] += 1

                if cats:
                    f.write(f"\n{'='*60}\nCATEGORY BREAKDOWN\n{'='*60}\n")
                    for cat, cnt in sorted(cats.items(), key=lambda x: -x[1]):
                        f.write(f"  {cat}: {cnt} files\n")

                # Errors
                err_list = [m for m in movements if 'Error' in m['status']]
                if err_list:
                    f.write(f"\n{'='*60}\nERRORS\n{'='*60}\n")
                    for m in err_list[:50]:  # Limit to 50
                        f.write(f"  {m['filename']}: {m['status']}\n")
                    if len(err_list) > 50:
                        f.write(f"  ... and {len(err_list) - 50} more errors\n")

            logger.info(f"Report saved: {rp}")
        except Exception as e:
            logger.error(f"Report error: {e}")
