# ============================================================
# FILE: src/organizer.py
# ============================================================
"""Image Organizer v2.5 - Fixed folder rename + structure converter"""

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
    is_valid_month_folder, format_pic_count
)

logger = logging.getLogger(__name__)

MONTH_NAMES = {
    1: '01-Jan', 2: '02-Feb', 3: '03-Mar', 4: '04-Apr',
    5: '05-May', 6: '06-Jun', 7: '07-Jul', 8: '08-Aug',
    9: '09-Sep', 10: '10-Oct', 11: '11-Nov', 12: '12-Dec'
}

SCREEN_RES = {
    (1080, 1920), (1080, 2340), (1080, 2400), (1080, 2520),
    (1170, 2532), (1179, 2556), (1284, 2778), (1290, 2796),
    (1440, 2560), (1440, 3040), (1440, 3200), (750, 1334),
    (828, 1792), (1125, 2436), (1920, 1080), (2560, 1440),
    (3840, 2160), (2048, 2732), (1668, 2388), (1620, 2160),
    (1536, 2048), (2160, 1620), (2388, 1668), (2732, 2048), (2048, 1536),
}

RE_PIC = re.compile('^(.*?)-(\\d+)pic(.*)' + chr(36))
RE_DAY = re.compile('^\\d{4}-\\d{2}-(\\d{2})(.*)')
RE_LOC = re.compile('[^a-z0-9]+')
RE_SS = re.compile('screenshot|screen_shot|screen-shot|capture|snip', re.IGNORECASE)
RE_DATE_PREFIX = re.compile('^(\\d{4})-(\\d{2})-(\\d{2})(.*)')
RE_MONTH_PREFIX = re.compile('^(\\d{4})-(\\d{2})-00(.*)')


def _count_files(fp):
    """Count all files in folder including videos subfolder."""
    try:
        fp = Path(fp)
        if not fp.exists():
            return 0
        c = 0
        for item in fp.iterdir():
            if item.is_file():
                c += 1
            elif item.is_dir() and item.name == 'videos':
                c += sum(1 for s in item.iterdir() if s.is_file())
        return c
    except Exception:
        return 0


class ImageOrganizer:

    def __init__(self, config):
        org = config.get('organization', {})
        self.output = Path(org.get('output_folder', './organized_images'))
        self.day_thr = int(org.get('day_threshold', 60))
        self.use_exif = org.get('use_exif_date', True)
        self.op = str(org.get('operation', 'copy')).lower()
        self.conflict = str(org.get('conflict_resolution', 'rename')).lower()
        self.reuse = org.get('reuse_existing_folders', True)
        self.vid_sub = org.get('video_subfolder', True)
        self.show = config.get('processing', {}).get('show_progress', True)
        self.structure = org.get('folder_structure', 'flat')
        self.sep_ss = org.get('separate_screenshots', True)
        ensure_directory(self.output)
        self._cache = None

    # ── Screenshot detection ──

    def _is_ss(self, rec):
        if not self.sep_ss:
            return False
        fn = str(rec.get('filename') or rec.get('Filename') or '')
        if RE_SS.search(fn):
            return True
        w = rec.get('width') or rec.get('Width (px)')
        h = rec.get('height') or rec.get('Height (px)')
        he = rec.get('has_exif') or rec.get('Has EXIF')
        ms = str(rec.get('metadata_status', ''))
        if w and h:
            try:
                iw, ih = int(w), int(h)
                if (iw, ih) in SCREEN_RES or (ih, iw) in SCREEN_RES:
                    if not he or ms in ('No EXIF', 'Minimal EXIF'):
                        return True
            except (ValueError, TypeError):
                pass
        return False

    # ── Scan existing folders ──

    def _scan_ex(self):
        cache = {'daily': {}, 'monthly': {}}
        if not self.output.exists():
            return cache
        try:
            # For flat, scan direct children
            # For nested, scan all subdirs
            if self.structure == 'flat':
                items = list(self.output.iterdir())
            else:
                items = list(self.output.rglob('*'))

            for item in items:
                if not item.is_dir():
                    continue
                # Skip 'videos' subfolder
                if item.name == 'videos':
                    continue
                name = item.name
                dp = is_valid_date_folder(name)
                if dp and dp not in cache['daily']:
                    cache['daily'][dp] = {
                        'name': name,
                        'full_path': str(item),
                        'count': _count_files(item),
                    }
                    continue
                mp = is_valid_month_folder(name)
                if mp and mp not in cache['monthly']:
                    cache['monthly'][mp] = {
                        'name': name,
                        'full_path': str(item),
                        'count': _count_files(item),
                    }
        except Exception as e:
            logger.warning('Scan error: %s', e)
        return cache

    # ── Folder name builders ──

    def _build_fn(self, dk, cnt, loc=''):
        pp = format_pic_count(cnt)
        if loc:
            cl = RE_LOC.sub('-', loc.lower()).strip('-')
            if cl and len(cl) > 1:
                return dk + '-' + pp + '-' + cl
        return dk + '-' + pp

    def _get_loc(self, recs):
        locs = []
        for rec in recs:
            for k in ['location_city', 'location_name', 'Location']:
                v = rec.get(k)
                if v and str(v).strip():
                    locs.append(str(v).strip().lower())
                    break
        if not locs:
            return ''
        mc = Counter(locs).most_common(1)[0]
        return mc[0] if mc[1] >= len(recs) * 0.3 else ''

    # ── Destination path based on structure ──

    def _dest(self, fn, dt, ft):
        if self.structure == 'year-month' and dt:
            d = self.output / str(dt.year) / MONTH_NAMES.get(dt.month, str(dt.month).zfill(2)) / fn
        elif self.structure == 'year-month-day' and dt:
            m = RE_DAY.match(fn)
            if m:
                dn = m.group(1) + m.group(2)
                d = self.output / str(dt.year) / MONTH_NAMES.get(dt.month, str(dt.month).zfill(2)) / dn
            else:
                d = self.output / str(dt.year) / MONTH_NAMES.get(dt.month, str(dt.month).zfill(2)) / fn
        else:
            d = self.output / fn
        if self.vid_sub and ft == 'video':
            d = d / 'videos'
        return d

    # ── Find existing folder for a date key ──

    def _find_ex(self, dk):
        if not self.reuse or not self._cache:
            return None
        ex = self._cache['daily'].get(dk)
        if ex:
            return ex
        if dk.endswith('-00'):
            return self._cache['monthly'].get(dk)
        return None

    # ── Extract date from record ──

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

    # ── Rename existing folder with updated count ──

    def _rename_existing_folder(self, ex, new_total):
        """
        Rename existing folder to update the pic count.
        Returns the NEW folder name and NEW full path.
        Example: 2022-01-30-010pic -> 2022-01-30-020pic
        """
        old_path = Path(ex['full_path'])
        old_name = ex['name']

        m = RE_PIC.match(old_name)
        if not m:
            # No pic count in name, can't rename
            return old_name, str(old_path)

        old_count = int(m.group(2))
        if old_count == new_total:
            # Count already correct
            return old_name, str(old_path)

        # Build new name with updated count
        new_name = m.group(1) + '-' + format_pic_count(new_total) + m.group(3)
        new_path = old_path.parent / new_name

        # If new path already exists and is different folder, skip rename
        if new_path.exists() and str(new_path) != str(old_path):
            logger.warning('Cannot rename %s -> %s: target exists', old_name, new_name)
            return old_name, str(old_path)

        if new_name == old_name:
            return old_name, str(old_path)

        try:
            old_path.rename(new_path)
            logger.info('Renamed folder: %s -> %s', old_name, new_name)
            print('    Renamed: ' + old_name + ' -> ' + new_name)

            # Update cache
            for cache_type in ('daily', 'monthly'):
                for dk, cached in self._cache[cache_type].items():
                    if cached['full_path'] == str(old_path):
                        cached['name'] = new_name
                        cached['full_path'] = str(new_path)
                        cached['count'] = new_total
                        break

            return new_name, str(new_path)
        except Exception as e:
            logger.error('Rename failed %s -> %s: %s', old_name, new_name, e)
            return old_name, str(old_path)

    # ── Main organize entry ──

    def organize(self, records):
        if not records:
            return []
        if self.reuse:
            self._cache = self._scan_ex()
        ss, normal, skip = [], [], 0
        for r in records:
            dv = str(
                r.get('delete_flag', '') or
                r.get('DELETE?', '') or
                r.get('DELETE? (Yes/No)', '') or ''
            ).strip().lower()
            if dv in ('yes', 'true', '1'):
                skip += 1
                continue
            if self._is_ss(r):
                ss.append(r)
            else:
                normal.append(r)

        logger.info('Organizing: %d normal, %d ss, %d skip', len(normal), len(ss), skip)
        mv = []
        if ss:
            print('  Screenshots: ' + str(len(ss)))
            mv.extend(self._org_ss(ss))
        if normal:
            mv.extend(self._org_normal(normal))
        self._fix_counts(mv)
        self._report(mv)
        return mv

    # ── Organize screenshots ──

    def _org_ss(self, ss):
        mv = []
        mg = defaultdict(list)
        for rec in ss:
            dt = self._date(rec)
            mg[dt.strftime('%Y-%m') if dt else 'undated'].append((rec, dt))

        for mk, grp in mg.items():
            fn = ('screenshots-' if mk == 'undated' else mk + '-screenshots-') + format_pic_count(len(grp))
            sdt = grp[0][1]
            for rec, dt in tqdm(grp, desc='  ' + fn, disable=not self.show):
                ft = rec.get('file_type', '')
                if self.structure in ('year-month', 'year-month-day') and sdt:
                    dd = self.output / str(sdt.year) / MONTH_NAMES.get(sdt.month, str(sdt.month).zfill(2)) / fn
                else:
                    dd = self.output / fn
                if self.vid_sub and ft == 'video':
                    dd = dd / 'videos'
                mv.append(self._cp(rec, dd, fn))
        return mv

    # ── Organize normal files ──

    def _org_normal(self, records):
        mv = []
        dated = [(r, self._date(r)) for r in records]
        dc = defaultdict(int)
        dr = defaultdict(list)
        undated = []

        for rec, dt in dated:
            if dt:
                dk = dt.strftime('%Y%m%d')
                dc[dk] += 1
                dr[dk].append((rec, dt))
            else:
                undated.append((rec, None))

        daily = set()
        monthly = defaultdict(list)
        for dk, c in dc.items():
            if c >= self.day_thr:
                daily.add(dk)
            else:
                monthly[dk[:6]].extend(dr[dk])

        # ── Process daily folders ──
        for dk in sorted(daily):
            g = dr[dk]
            sdt = g[0][1]
            ds = sdt.strftime('%Y-%m-%d')
            loc = self._get_loc([r for r, _ in g])
            ex = self._find_ex(ds)

            if ex:
                # EXISTING folder found — rename it FIRST with updated count
                existing_count = ex.get('count', 0)
                new_total = existing_count + len(g)

                fn, dest_base = self._rename_existing_folder(ex, new_total)

                # Now dest_base points to the renamed folder
                logger.info('Adding %d files to existing folder: %s (was %d, now %d)',
                            len(g), fn, existing_count, new_total)
            else:
                # NEW folder
                fn = self._build_fn(ds, len(g), loc)

            for rec, dt in tqdm(g, desc='  ' + fn, disable=not self.show):
                ft = rec.get('file_type') or rec.get('Type') or ''
                mv.append(self._cp(rec, self._dest(fn, dt, ft), fn))

        # ── Process monthly folders ──
        for mk in sorted(monthly):
            g = monthly[mk]
            sdt = g[0][1]
            ds = sdt.strftime('%Y-%m') + '-00'
            loc = self._get_loc([r for r, _ in g])
            ex = self._find_ex(ds)

            if ex:
                existing_count = ex.get('count', 0)
                new_total = existing_count + len(g)

                fn, dest_base = self._rename_existing_folder(ex, new_total)

                logger.info('Adding %d files to existing folder: %s (was %d, now %d)',
                            len(g), fn, existing_count, new_total)
            else:
                fn = self._build_fn(ds, len(g), loc)

            for rec, dt in tqdm(g, desc='  ' + fn, disable=not self.show):
                ft = rec.get('file_type') or rec.get('Type') or ''
                mv.append(self._cp(rec, self._dest(fn, dt, ft), fn))

        # ── Undated ──
        if undated:
            fn = 'undated-' + format_pic_count(len(undated))
            for rec, dt in tqdm(undated, desc='  ' + fn, disable=not self.show):
                dd = self.output / fn
                if self.vid_sub and rec.get('file_type') == 'video':
                    dd = dd / 'videos'
                mv.append(self._cp(rec, dd, fn))

        return mv

    # ── Fix counts after all copies ──

    def _fix_counts(self, mv):
        """After all files copied, verify actual file count matches folder name."""
        fc = defaultdict(int)
        for m in mv:
            if m['status'] == 'Success' and m.get('destination'):
                p = Path(m['destination']).parent
                if p.name == 'videos':
                    p = p.parent
                fc[str(p)] += 1

        for fs in fc:
            fp = Path(fs)
            if not fp.exists():
                continue
            old = fp.name
            m = RE_PIC.match(old)
            if not m:
                continue
            actual = _count_files(fp)
            old_count = int(m.group(2))
            if old_count == actual:
                continue

            nn = m.group(1) + '-' + format_pic_count(actual) + m.group(3)
            np2 = fp.parent / nn
            if (np2.exists() and str(np2) != str(fp)) or nn == old:
                continue
            try:
                fp.rename(np2)
                logger.info('Count fix: %s -> %s', old, nn)
                for x in mv:
                    if x.get('destination') and old in x['destination']:
                        x['destination'] = x['destination'].replace(old, nn)
                    if x.get('folder') == old:
                        x['folder'] = nn
            except Exception as e:
                logger.warning('Count fix failed: %s', e)

    # ── Copy/Move single file ──

    def _cp(self, rec, dest_dir, fl):
        src = rec.get('full_path') or rec.get('Full Path') or ''
        fn = rec.get('filename') or rec.get('Filename') or ''
        if not src:
            return {'filename': fn, 'source': '', 'destination': '',
                    'status': 'Error: No path', 'folder': fl}
        source = Path(src)
        if not source.exists():
            return {'filename': fn, 'source': str(source), 'destination': '',
                    'status': 'Error: Not found', 'folder': fl}
        ensure_directory(dest_dir)
        dest = resolve_filename_conflict(dest_dir / safe_filename(source.name), self.conflict)
        if dest is None:
            return {'filename': source.name, 'source': str(source), 'destination': '',
                    'status': 'Skipped', 'folder': fl}
        try:
            if self.op == 'move':
                shutil.move(str(source), str(dest))
            else:
                shutil.copy2(str(source), str(dest))
            return {'filename': source.name, 'source': str(source),
                    'destination': str(dest), 'status': 'Success', 'folder': fl}
        except Exception as e:
            return {'filename': source.name, 'source': str(source),
                    'destination': str(dest), 'status': 'Error: ' + str(e), 'folder': fl}

    # ── Report ──

    def _report(self, mv):
        try:
            lines = [
                'Organization Report', '=' * 60,
                'Generated: ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'Structure: ' + self.structure,
                'Operation: ' + self.op, ''
            ]
            s = sum(1 for m in mv if m['status'] == 'Success')
            e = sum(1 for m in mv if 'Error' in m['status'])
            lines.extend(['Success: ' + str(s), 'Errors: ' + str(e),
                          'Total: ' + str(len(mv)), '', 'FOLDERS:'])
            fc = defaultdict(int)
            for m in mv:
                if m['status'] == 'Success':
                    fc[m['folder']] += 1
            for f in sorted(fc):
                lines.append('  ' + f + ': ' + str(fc[f]))
            errs = [m for m in mv if 'Error' in m['status']]
            if errs:
                lines.extend(['', 'ERRORS:'])
                for m in errs[:50]:
                    lines.append('  ' + m['filename'] + ': ' + m['status'])
            with open(self.output / 'organization-report.txt', 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════
    # STRUCTURE CONVERTER
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def convert_structure(source_folder, target_structure, target_folder=None):
        """
        Convert existing organized folders from one structure to another.

        Args:
            source_folder: Path to current organized folder
            target_structure: "flat" | "year-month" | "year-month-day"
            target_folder: Output path (None = rename in place)

        Conversions supported:
            flat -> year-month:
                2022-01-30-010pic-beach/ -> 2022/01-Jan/2022-01-30-010pic-beach/
            flat -> year-month-day:
                2022-01-30-010pic-beach/ -> 2022/01-Jan/30-010pic-beach/
            year-month -> flat:
                2022/01-Jan/2022-01-30-010pic/ -> 2022-01-30-010pic/
            year-month -> year-month-day:
                2022/01-Jan/2022-01-30-010pic/ -> 2022/01-Jan/30-010pic/
            year-month-day -> flat:
                2022/01-Jan/30-010pic/ -> 2022-01-30-010pic/  (reconstructed)
            year-month-day -> year-month:
                2022/01-Jan/30-010pic/ -> 2022/01-Jan/2022-01-30-010pic/
        """
        source = Path(source_folder)
        if not source.exists():
            print('  Error: Source folder not found: ' + str(source))
            return False

        if target_folder:
            dest = Path(target_folder)
        else:
            dest = source

        if target_structure not in ('flat', 'year-month', 'year-month-day'):
            print('  Error: Invalid target structure: ' + target_structure)
            return False

        # Detect current structure
        current = _detect_structure(source)
        print('  Current structure: ' + current)
        print('  Target structure:  ' + target_structure)

        if current == target_structure:
            print('  Already in target structure!')
            return True

        # Collect all dated folders with their files
        folders = _collect_folders(source, current)
        if not folders:
            print('  No dated folders found!')
            return False

        print('  Found ' + str(len(folders)) + ' folders to convert')

        if target_folder and str(dest) != str(source):
            ensure_directory(dest)

        moved = 0
        errors = 0

        for fd in tqdm(folders, desc='  Converting', disable=False):
            old_path = Path(fd['path'])
            folder_name = fd['name']
            year = fd.get('year')
            month = fd.get('month')
            day = fd.get('day')

            # Build new path based on target structure
            if target_structure == 'flat':
                # Reconstruct full date name
                if day and day != '00':
                    # From year-month-day: 30-010pic -> 2022-01-30-010pic
                    if not folder_name.startswith(str(year)):
                        new_name = str(year) + '-' + str(month).zfill(2) + '-' + folder_name
                    else:
                        new_name = folder_name
                else:
                    new_name = folder_name
                new_path = dest / new_name

            elif target_structure == 'year-month':
                month_name = MONTH_NAMES.get(int(month), str(month).zfill(2))
                # If from year-month-day, reconstruct: 30-010pic -> 2022-01-30-010pic
                if day and day != '00' and not folder_name.startswith(str(year)):
                    new_name = str(year) + '-' + str(month).zfill(2) + '-' + folder_name
                else:
                    new_name = folder_name
                new_path = dest / str(year) / month_name / new_name

            elif target_structure == 'year-month-day':
                month_name = MONTH_NAMES.get(int(month), str(month).zfill(2))
                # Strip date prefix: 2022-01-30-010pic -> 30-010pic
                dm = RE_DATE_PREFIX.match(folder_name)
                if dm:
                    new_name = dm.group(3).lstrip('-')  # day part + rest
                    if not new_name.startswith(dm.group(3)):
                        new_name = dm.group(3) + '-' + new_name if new_name else dm.group(3)
                    # Ensure day is prefix
                    new_name = day + '-' + new_name.lstrip(day).lstrip('-') if day else new_name
                    # Clean up
                    new_name = re.sub('^-+', '', new_name)
                    if not new_name:
                        new_name = folder_name
                    # Make sure day is at start
                    if not new_name.startswith(day):
                        new_name = day + '-' + new_name
                else:
                    mm = RE_MONTH_PREFIX.match(folder_name)
                    if mm:
                        rest = mm.group(3).lstrip('-')
                        new_name = '00-' + rest if rest else '00'
                    else:
                        new_name = folder_name
                new_path = dest / str(year) / month_name / new_name

            if new_path == old_path:
                continue

            # Move folder
            try:
                ensure_directory(new_path.parent)
                if new_path.exists():
                    # Merge: move files from old into existing new
                    for item in old_path.iterdir():
                        target_item = new_path / item.name
                        if item.is_dir():
                            if target_item.exists():
                                # Merge subdirectory
                                for sub in item.iterdir():
                                    st = target_item / sub.name
                                    if not st.exists():
                                        shutil.move(str(sub), str(st))
                                # Remove empty old subdir
                                try:
                                    item.rmdir()
                                except Exception:
                                    pass
                            else:
                                shutil.move(str(item), str(target_item))
                        else:
                            if not target_item.exists():
                                shutil.move(str(item), str(target_item))
                    # Remove old folder if empty
                    try:
                        old_path.rmdir()
                    except Exception:
                        pass
                else:
                    shutil.move(str(old_path), str(new_path))
                moved += 1
                logger.info('Converted: %s -> %s', str(old_path), str(new_path))
            except Exception as e:
                errors += 1
                logger.error('Convert error %s: %s', old_path, e)

        # Clean up empty parent directories
        _cleanup_empty_dirs(source)
        if target_folder and str(dest) != str(source):
            _cleanup_empty_dirs(dest)

        print('  Converted: ' + str(moved) + ' folders, ' + str(errors) + ' errors')
        return True


def _detect_structure(folder):
    """Detect whether folder uses flat, year-month, or year-month-day structure."""
    folder = Path(folder)

    # Check for year directories (2020, 2021, etc.)
    has_year_dirs = False
    has_flat_dated = False

    for item in folder.iterdir():
        if not item.is_dir():
            continue
        name = item.name
        # Year directory?
        if re.match('^\\d{4}', name):
            has_year_dirs = True
            # Check inside year for month dirs
            for sub in item.iterdir():
                if sub.is_dir():
                    # Check inside month for day-prefixed dirs
                    for subsub in sub.iterdir():
                        if subsub.is_dir():
                            # Does it start with DD- (day prefix)?
                            if re.match('^\\d{2}-', subsub.name) and not re.match('^\\d{4}-', subsub.name):
                                return 'year-month-day'
                            elif re.match('^\\d{4}-\\d{2}-', subsub.name):
                                return 'year-month'
            continue
        # Flat dated folder?
        if is_valid_date_folder(name) or is_valid_month_folder(name):
            has_flat_dated = True

    if has_year_dirs:
        return 'year-month'
    if has_flat_dated:
        return 'flat'
    return 'flat'


def _collect_folders(source, structure):
    """Collect all dated folders with metadata."""
    source = Path(source)
    folders = []

    if structure == 'flat':
        for item in source.iterdir():
            if not item.is_dir() or item.name == 'videos':
                continue
            dp = is_valid_date_folder(item.name)
            if dp:
                parts = dp.split('-')
                folders.append({
                    'path': str(item), 'name': item.name,
                    'year': parts[0], 'month': parts[1], 'day': parts[2],
                })
                continue
            mp = is_valid_month_folder(item.name)
            if mp:
                parts = mp.split('-')
                folders.append({
                    'path': str(item), 'name': item.name,
                    'year': parts[0], 'month': parts[1], 'day': '00',
                })
                continue
            # Screenshots, undated etc - include as-is
            if item.name.startswith('screenshot') or item.name.startswith('undated'):
                folders.append({
                    'path': str(item), 'name': item.name,
                    'year': 'misc', 'month': '00', 'day': '00',
                })

    elif structure == 'year-month':
        for year_dir in sorted(source.iterdir()):
            if not year_dir.is_dir() or not re.match('^\\d{4}', year_dir.name):
                # Non-year dirs (undated, screenshots)
                if year_dir.is_dir() and year_dir.name != 'videos':
                    folders.append({
                        'path': str(year_dir), 'name': year_dir.name,
                        'year': 'misc', 'month': '00', 'day': '00',
                    })
                continue
            year = year_dir.name
            for month_dir in sorted(year_dir.iterdir()):
                if not month_dir.is_dir():
                    continue
                # Extract month number from "01-Jan" format
                mm = re.match('^(\\d{2})', month_dir.name)
                month = mm.group(1) if mm else '00'
                for folder in sorted(month_dir.iterdir()):
                    if not folder.is_dir() or folder.name == 'videos':
                        continue
                    dp = is_valid_date_folder(folder.name)
                    if dp:
                        parts = dp.split('-')
                        day = parts[2]
                    else:
                        day = '00'
                    folders.append({
                        'path': str(folder), 'name': folder.name,
                        'year': year, 'month': month, 'day': day,
                    })

    elif structure == 'year-month-day':
        for year_dir in sorted(source.iterdir()):
            if not year_dir.is_dir() or not re.match('^\\d{4}', year_dir.name):
                if year_dir.is_dir() and year_dir.name != 'videos':
                    folders.append({
                        'path': str(year_dir), 'name': year_dir.name,
                        'year': 'misc', 'month': '00', 'day': '00',
                    })
                continue
            year = year_dir.name
            for month_dir in sorted(year_dir.iterdir()):
                if not month_dir.is_dir():
                    continue
                mm = re.match('^(\\d{2})', month_dir.name)
                month = mm.group(1) if mm else '00'
                for folder in sorted(month_dir.iterdir()):
                    if not folder.is_dir() or folder.name == 'videos':
                        continue
                    # Day-prefixed: "30-010pic-beach"
                    dm = re.match('^(\\d{2})(.*)', folder.name)
                    day = dm.group(1) if dm else '00'
                    folders.append({
                        'path': str(folder), 'name': folder.name,
                        'year': year, 'month': month, 'day': day,
                    })

    return folders


def _cleanup_empty_dirs(folder):
    """Remove empty directories recursively."""
    folder = Path(folder)
    try:
        for item in sorted(folder.rglob('*'), reverse=True):
            if item.is_dir():
                try:
                    # Only remove if truly empty
                    if not any(item.iterdir()):
                        item.rmdir()
                        logger.debug('Removed empty dir: %s', item)
                except Exception:
                    pass
    except Exception:
        pass
