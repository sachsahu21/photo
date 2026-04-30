# ============================================================
# FILE: src/organizer.py
# ============================================================
"""
Image Organizer v2.2
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
    1: '01-Jan',
    2: '02-Feb',
    3: '03-Mar',
    4: '04-Apr',
    5: '05-May',
    6: '06-Jun',
    7: '07-Jul',
    8: '08-Aug',
    9: '09-Sep',
    10: '10-Oct',
    11: '11-Nov',
    12: '12-Dec'
}

SCREEN_RESOLUTIONS = {
    (1080, 1920),
    (1080, 2340),
    (1080, 2400),
    (1080, 2520),
    (1170, 2532),
    (1179, 2556),
    (1284, 2778),
    (1290, 2796),
    (1440, 2560),
    (1440, 3040),
    (1440, 3200),
    (750, 1334),
    (828, 1792),
    (1125, 2436),
    (1920, 1080),
    (2560, 1440),
    (3840, 2160),
    (2048, 2732),
    (1668, 2388),
    (1620, 2160),
    (1536, 2048),
    (2160, 1620),
    (2388, 1668),
    (2732, 2048),
    (2048, 1536),
}


def _compile_pic_count():
    p = '^' + '(.*?)' + '-' + '(\\d+)' + 'pic' + '(.*)' + chr(36)
    return re.compile(p)


def _compile_day_extract():
    p = '^' + '\\d{4}' + '-' + '\\d{2}' + '-' + '(\\d{2})' + '(.*)'
    return re.compile(p)


def _compile_location_clean():
    return re.compile('[^a-z0-9]+')


def _compile_screenshot_kw():
    words = 'screenshot|screen_shot|screen-shot|capture|snip'
    return re.compile(words, re.IGNORECASE)


RE_PIC_COUNT = _compile_pic_count()
RE_DAY_EXTRACT = _compile_day_extract()
RE_LOCATION_CLEAN = _compile_location_clean()
RE_SCREENSHOT_KW = _compile_screenshot_kw()


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
        self.folder_structure = org.get('folder_structure', 'flat')
        self.separate_screenshots = org.get('separate_screenshots', True)

        ensure_directory(self.output_folder)
        self._existing_cache = None

    def _is_screenshot(self, rec):
        if not self.separate_screenshots:
            return False

        fn = str(rec.get('filename') or rec.get('Filename') or '')
        if RE_SCREENSHOT_KW.search(fn):
            return True

        w = rec.get('width') or rec.get('Width (px)')
        h = rec.get('height') or rec.get('Height (px)')
        has_exif = rec.get('has_exif') or rec.get('Has EXIF')
        meta_status = str(rec.get('metadata_status', ''))

        if w and h:
            try:
                iw = int(w)
                ih = int(h)
                if (iw, ih) in SCREEN_RESOLUTIONS or (ih, iw) in SCREEN_RESOLUTIONS:
                    if not has_exif or meta_status in ('No EXIF', 'Minimal EXIF'):
                        return True
            except (ValueError, TypeError):
                pass

        return False

    def _scan_existing_folders(self):
        cache = {'daily': {}, 'monthly': {}}
        try:
            if not self.output_folder.exists():
                return cache

            if self.folder_structure == 'flat':
                items = self.output_folder.iterdir()
            else:
                items = self.output_folder.rglob('*')

            for item in items:
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

            total = len(cache['daily']) + len(cache['monthly'])
            if total > 0:
                logger.info(
                    'Existing folders: %d daily, %d monthly',
                    len(cache['daily']),
                    len(cache['monthly'])
                )
        except Exception as e:
            logger.warning('Scan existing folders error: %s', e)
        return cache

    def _build_folder_name(self, date_key, count, location_hint=''):
        pic_part = str(count) + 'pic'
        if location_hint:
            clean = RE_LOCATION_CLEAN.sub('-', location_hint.lower()).strip('-')
            if clean and len(clean) > 1:
                return date_key + '-' + pic_part + '-' + clean
        return date_key + '-' + pic_part

    def _get_location_hint(self, records):
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
        if most_common[1] >= len(records) * 0.3:
            return most_common[0]
        return ''

    def _update_folder_name_count(self, existing_name, new_count):
        m = RE_PIC_COUNT.match(existing_name)
        if m:
            prefix = m.group(1)
            suffix = m.group(3)
            return prefix + '-' + str(new_count) + 'pic' + suffix
        return existing_name + '-' + str(new_count) + 'pic'

    def _build_dest_path(self, folder_name, dt, file_type):
        if self.folder_structure == 'year-month' and dt:
            year = str(dt.year)
            month = MONTH_NAMES.get(dt.month, str(dt.month).zfill(2))
            dest = self.output_folder / year / month / folder_name

        elif self.folder_structure == 'year-month-day' and dt:
            year = str(dt.year)
            month = MONTH_NAMES.get(dt.month, str(dt.month).zfill(2))
            m = RE_DAY_EXTRACT.match(folder_name)
            if m:
                day_name = m.group(1) + m.group(2)
                dest = self.output_folder / year / month / day_name
            else:
                dest = self.output_folder / year / month / folder_name

        else:
            dest = self.output_folder / folder_name

        if self.video_subfolder and file_type == 'video':
            dest = dest / 'videos'

        return dest

    def _find_existing_folder(self, date_key):
        if not self.reuse_existing or not self._existing_cache:
            return None

        existing = self._existing_cache['daily'].get(date_key)
        if existing:
            return existing

        if date_key.endswith('-00'):
            existing = self._existing_cache['monthly'].get(date_key)
            if existing:
                return existing

        return None

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

    def organize(self, records):
        if not records:
            return []

        if self.reuse_existing:
            self._existing_cache = self._scan_existing_folders()

        screenshots = []
        normal = []
        skipped = 0

        for r in records:
            delete_val = str(
                r.get('delete_flag', '') or r.get('DELETE? (Yes/No)', '') or ''
            ).strip().lower()
            if delete_val in ('yes', 'true', '1'):
                skipped += 1
                continue

            if self._is_screenshot(r):
                screenshots.append(r)
            else:
                normal.append(r)

        logger.info(
            'Organizing: %d normal, %d screenshots, %d skipped',
            len(normal), len(screenshots), skipped
        )

        movements = []

        if screenshots:
            print('  Screenshots: ' + str(len(screenshots)))
            movements.extend(self._organize_screenshots(screenshots))

        if normal:
            movements.extend(self._organize_normal(normal))

        self._rename_folders_with_counts(movements)
        self._report(movements)

        success = sum(1 for m in movements if m['status'] == 'Success')
        errors = sum(1 for m in movements if 'Error' in m['status'])
        logger.info('Organization done: %d success, %d errors', success, errors)

        return movements

    def _organize_screenshots(self, screenshots):
        movements = []

        month_groups = defaultdict(list)
        for rec in screenshots:
            dt = self._date(rec)
            if dt:
                mk = dt.strftime('%Y-%m')
                month_groups[mk].append((rec, dt))
            else:
                month_groups['undated'].append((rec, None))

        for month_key, group in month_groups.items():
            count = len(group)
            if month_key == 'undated':
                folder_name = 'screenshots-' + str(count) + 'pic'
                sample_dt = None
            else:
                folder_name = month_key + '-screenshots-' + str(count) + 'pic'
                sample_dt = group[0][1]

            for rec, dt in tqdm(group, desc='  ' + folder_name,
                                disable=not self.show_progress):
                file_type = rec.get('file_type') or rec.get('Type') or ''

                if self.folder_structure == 'year-month' and sample_dt:
                    year = str(sample_dt.year)
                    month = MONTH_NAMES.get(sample_dt.month, str(sample_dt.month).zfill(2))
                    dest_dir = self.output_folder / year / month / folder_name
                elif self.folder_structure == 'year-month-day' and sample_dt:
                    year = str(sample_dt.year)
                    month = MONTH_NAMES.get(sample_dt.month, str(sample_dt.month).zfill(2))
                    dest_dir = self.output_folder / year / month / folder_name
                else:
                    dest_dir = self.output_folder / folder_name

                if self.video_subfolder and file_type == 'video':
                    dest_dir = dest_dir / 'videos'

                movements.append(self._move_file(rec, dest_dir, folder_name))

        return movements

    def _organize_normal(self, records):
        movements = []

        dated = [(r, self._date(r)) for r in records]

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

        daily_days = set()
        monthly_buckets = defaultdict(list)

        for day_key, count in day_counts.items():
            if count >= self.day_threshold:
                daily_days.add(day_key)
            else:
                month_key = day_key[:6]
                monthly_buckets[month_key].extend(day_records[day_key])

        if daily_days:
            logger.info(
                'Daily folders: %d days with >= %d files',
                len(daily_days), self.day_threshold
            )

        for day_key in sorted(daily_days):
            group = day_records[day_key]
            sample_dt = group[0][1]
            date_str = sample_dt.strftime('%Y-%m-%d')
            count = len(group)

            location = self._get_location_hint([r for r, _ in group])

            existing = self._find_existing_folder(date_str)
            if existing:
                folder_name = existing['name']
                logger.info('Reusing existing folder: %s', folder_name)
            else:
                folder_name = self._build_folder_name(date_str, count, location)

            for rec, dt in tqdm(group, desc='  ' + folder_name,
                                disable=not self.show_progress):
                file_type = rec.get('file_type') or rec.get('Type') or ''
                dest_dir = self._build_dest_path(folder_name, dt, file_type)
                movements.append(self._move_file(rec, dest_dir, folder_name))

        for month_key in sorted(monthly_buckets):
            group = monthly_buckets[month_key]
            sample_dt = group[0][1]
            date_str = sample_dt.strftime('%Y-%m') + '-00'
            count = len(group)

            location = self._get_location_hint([r for r, _ in group])

            existing = self._find_existing_folder(date_str)
            if existing:
                folder_name = existing['name']
                logger.info('Reusing existing folder: %s', folder_name)
            else:
                folder_name = self._build_folder_name(date_str, count, location)

            for rec, dt in tqdm(group, desc='  ' + folder_name,
                                disable=not self.show_progress):
                file_type = rec.get('file_type') or rec.get('Type') or ''
                dest_dir = self._build_dest_path(folder_name, dt, file_type)
                movements.append(self._move_file(rec, dest_dir, folder_name))

        if undated:
            count = len(undated)
            folder_name = 'undated-' + str(count) + 'pic'
            for rec, dt in tqdm(undated, desc='  ' + folder_name,
                                disable=not self.show_progress):
                file_type = rec.get('file_type') or rec.get('Type') or ''
                dest_dir = self.output_folder / folder_name
                if self.video_subfolder and file_type == 'video':
                    dest_dir = dest_dir / 'videos'
                movements.append(self._move_file(rec, dest_dir, folder_name))

        return movements

    def _rename_folders_with_counts(self, movements):
        folder_counts = defaultdict(int)

        for m in movements:
            if m['status'] == 'Success' and m.get('destination'):
                dest = Path(m['destination'])
                parent = dest.parent
                if parent.name == 'videos':
                    parent = parent.parent
                folder_counts[str(parent)] += 1

        for folder_str, count in folder_counts.items():
            folder_path = Path(folder_str)
            if not folder_path.exists():
                continue

            old_name = folder_path.name
            m = RE_PIC_COUNT.match(old_name)
            if not m:
                continue

            old_count = int(m.group(2))
            if old_count == count:
                continue

            prefix = m.group(1)
            suffix = m.group(3)
            new_name = prefix + '-' + str(count) + 'pic' + suffix
            new_path = folder_path.parent / new_name

            if new_path.exists():
                continue

            try:
                folder_path.rename(new_path)
                logger.info('Renamed: %s -> %s', old_name, new_name)

                for mv in movements:
                    if mv.get('destination') and old_name in mv['destination']:
                        mv['destination'] = mv['destination'].replace(old_name, new_name)
                    if mv.get('folder') == old_name:
                        mv['folder'] = new_name
            except Exception as e:
                logger.warning('Rename failed %s: %s', old_name, e)

    def _move_file(self, rec, dest_dir, folder_label):
        src = rec.get('full_path') or rec.get('Full Path') or ''
        fn = rec.get('filename') or rec.get('Filename') or ''

        if not src:
            return {
                'filename': fn,
                'source': '',
                'destination': '',
                'status': 'Error: No path',
                'folder': folder_label
            }

        source = Path(src)
        if not source.exists():
            return {
                'filename': fn,
                'source': str(source),
                'destination': '',
                'status': 'Error: Not found',
                'folder': folder_label
            }

        ensure_directory(dest_dir)
        dest = resolve_filename_conflict(
            dest_dir / safe_filename(source.name),
            self.conflict
        )
        if dest is None:
            return {
                'filename': source.name,
                'source': str(source),
                'destination': '',
                'status': 'Skipped (conflict)',
                'folder': folder_label
            }

        try:
            if self.operation == 'move':
                shutil.move(str(source), str(dest))
            else:
                shutil.copy2(str(source), str(dest))
            return {
                'filename': source.name,
                'source': str(source),
                'destination': str(dest),
                'status': 'Success',
                'folder': folder_label
            }
        except Exception as e:
            return {
                'filename': source.name,
                'source': str(source),
                'destination': str(dest),
                'status': 'Error: ' + str(e),
                'folder': folder_label
            }

    def _report(self, movements):
        try:
            rp = self.output_folder / 'organization-report.txt'
            lines = []
            lines.append('Organization Report')
            lines.append('=' * 60)
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            lines.append('Generated: ' + now_str)
            lines.append('Structure: ' + self.folder_structure)
            lines.append('Separate screenshots: ' + str(self.separate_screenshots))
            lines.append('Reuse existing: ' + str(self.reuse_existing))
            lines.append('Video subfolder: ' + str(self.video_subfolder))
            lines.append('Operation: ' + self.operation)
            lines.append('Conflict: ' + self.conflict)
            lines.append('Day threshold: ' + str(self.day_threshold))
            lines.append('')

            s = sum(1 for m in movements if m['status'] == 'Success')
            e = sum(1 for m in movements if 'Error' in m['status'])
            sk = sum(1 for m in movements if 'Skip' in m['status'])
            lines.append('Success: ' + str(s))
            lines.append('Errors: ' + str(e))
            lines.append('Skipped: ' + str(sk))
            lines.append('Total: ' + str(len(movements)))
            lines.append('')

            lines.append('=' * 60)
            lines.append('FOLDER DISTRIBUTION')
            lines.append('=' * 60)
            fc = defaultdict(int)
            for m in movements:
                if m['status'] == 'Success':
                    fc[m['folder']] += 1
            for fld in sorted(fc):
                lines.append('  ' + fld + ': ' + str(fc[fld]) + ' files')

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
                lines.append('')
                lines.append('=' * 60)
                lines.append('CATEGORY BREAKDOWN')
                lines.append('=' * 60)
                for cat in sorted(cats, key=lambda x: -cats[x]):
                    lines.append('  ' + cat + ': ' + str(cats[cat]) + ' files')

            err_list = [m for m in movements if 'Error' in m['status']]
            if err_list:
                lines.append('')
                lines.append('=' * 60)
                lines.append('ERRORS')
                lines.append('=' * 60)
                for m in err_list[:50]:
                    lines.append('  ' + m['filename'] + ': ' + m['status'])
                if len(err_list) > 50:
                    remaining = len(err_list) - 50
                    lines.append('  ... and ' + str(remaining) + ' more errors')

            with open(rp, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))

            logger.info('Report saved: %s', rp)
        except Exception as e:
            logger.error('Report error: %s', e)
