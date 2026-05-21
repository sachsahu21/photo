"""Image Organizer v4.1 - flat / year / year-month-date with converter and merge."""

import re
import json
import shutil
import logging
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter

from tqdm import tqdm
from .metadata_paths import apply_media_path_to_doc
from .metadata_store import _ensure_json_serializable
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

DEFAULT_SCREEN_RES = {
    (1080, 1920), (1080, 2340), (1080, 2400), (1080, 2520),
    (1170, 2532), (1179, 2556), (1284, 2778), (1290, 2796),
    (1440, 2560), (1440, 3040), (1440, 3200), (750, 1334),
    (828, 1792), (1125, 2436), (1920, 1080), (2560, 1440),
    (3840, 2160), (2048, 2732), (1668, 2388), (1620, 2160),
    (1536, 2048), (2160, 1620), (2388, 1668), (2732, 2048), (2048, 1536),
}

_END = chr(36)

RE_PIC = re.compile('^(.*?)-(\\d+)pic(.*)' + _END)
RE_LOC = re.compile('[^a-z0-9]+')
RE_DATE_PREFIX = re.compile('^(\\d{4})-(\\d{2})-(\\d{2})(.*)')
RE_MONTH_PREFIX = re.compile('^(\\d{4})-(\\d{2})-00(.*)')
RE_YEAR_DIR = re.compile('^\\d{4}' + _END)
RE_MONTH_DIR = re.compile('^(\\d{2})')
RE_SS_FOLDER = re.compile('screenshot', re.IGNORECASE)
RE_DATE_KEY = re.compile('^(\\d{4}-\\d{2}-\\d{2})')
RE_MONTH_KEY = re.compile('^(\\d{4}-\\d{2}-00)')


def _build_ss_regex(keywords):
    if not keywords:
        return re.compile('screenshot|screen_shot|screen-shot|capture|snip', re.IGNORECASE)
    escaped = [re.escape(k) for k in keywords]
    pattern = '|'.join(escaped)
    return re.compile(pattern, re.IGNORECASE)


def _build_screen_res(custom_res):
    res = set(DEFAULT_SCREEN_RES)
    if custom_res:
        for item in custom_res:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                try:
                    res.add((int(item[0]), int(item[1])))
                except (ValueError, TypeError):
                    pass
    return res


def _is_probable_camera_name(name):
    up = str(name or '').upper()
    prefixes = ('FB_IMG', 'IMG_', 'DSC_', 'PXL_', 'MVIMG_', 'VID_', 'PHOTO_')
    return up.startswith(prefixes)


def _count_files(fp):
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


def _extract_date_key(folder_name):
    if RE_SS_FOLDER.search(folder_name):
        return None
    m = RE_MONTH_KEY.match(folder_name)
    if m:
        return m.group(1)
    m = RE_DATE_KEY.match(folder_name)
    if m:
        return m.group(1)
    return None


def _extract_text_suffix(folder_name):
    m = RE_PIC.match(folder_name)
    if m:
        suffix = m.group(3)
        if suffix:
            suffix = suffix.strip('-')
            if suffix:
                return suffix
    return ''


def _should_skip_merge_for_suffix_conflict(group_folders):
    """True if two+ folders have different non-empty text suffixes (do not merge)."""
    texts = set()
    for folder in group_folders:
        t = _extract_text_suffix(folder.name)
        if t:
            texts.add(t)
    return len(texts) > 1


def _normalize_unaligned_folder_name(folder_path):
    folder_path = Path(folder_path)
    if not folder_path.exists() or not folder_path.is_dir():
        return None
    old_name = folder_path.name
    actual_count = _count_files(folder_path)
    if actual_count < 0:
        return None
    m = RE_PIC.match(old_name)
    if m:
        new_name = m.group(1) + '-' + format_pic_count(actual_count) + m.group(3)
    else:
        if '-' in old_name:
            prefix, suffix = old_name.split('-', 1)
            suffix = suffix.strip()
            if suffix:
                new_name = prefix.strip() + '-' + format_pic_count(actual_count) + '-' + suffix
            else:
                new_name = prefix.strip() + '-' + format_pic_count(actual_count)
        else:
            new_name = old_name.strip() + '-' + format_pic_count(actual_count)
    if not new_name or new_name == old_name:
        return None
    new_path = folder_path.parent / new_name
    if new_path.exists() and str(new_path) != str(folder_path):
        return None
    try:
        folder_path.rename(new_path)
        return str(new_path)
    except Exception:
        return None


class ImageOrganizer:

    def __init__(self, config):
        self.config = config or {}
        org = config.get('organization', {})
        self.output = Path(org.get('output_folder', './organized_images'))
        self.day_thr = int(org.get('day_threshold', 60))
        self.use_exif = org.get('use_exif_date', True)
        self.op = str(org.get('operation', 'copy')).lower()
        self.conflict = str(org.get('conflict_resolution', 'rename')).lower()
        self.reuse = org.get('reuse_existing_folders', True)
        self.vid_sub = org.get('video_subfolder', True)
        self.show = config.get('processing', {}).get('show_progress', True)
        self.structure = org.get('folder_structure', 'year')
        self.sep_ss = org.get('separate_screenshots', True)
        ss_keywords = org.get('screenshot_keywords', None)
        self.re_ss = _build_ss_regex(ss_keywords)
        self.ss_by_res = org.get('screenshot_detect_by_resolution', True)
        custom_res = org.get('screenshot_custom_resolutions', [])
        self.screen_res = _build_screen_res(custom_res)
        ensure_directory(self.output)
        self._cache = None
        meta_cfg = config.get("metadata") or {}
        rf = str(meta_cfg.get("root_folder", "") or "").strip()
        self._metadata_vault_root = (
            Path(rf).expanduser().resolve() if rf else None
        )

    def _is_ss(self, rec):
        if not self.sep_ss:
            return False
        fn = str(rec.get('filename') or rec.get('Filename') or '')
        if fn.upper().startswith('FB_IMG'):
            return False
        if self.re_ss.search(fn):
            return True
        if not self.ss_by_res:
            return False
        w = rec.get('width') or rec.get('Width (px)')
        h = rec.get('height') or rec.get('Height (px)')
        he = rec.get('has_exif') or rec.get('Has EXIF')
        ms = str(rec.get('metadata_status', ''))
        if w and h:
            try:
                iw, ih = int(w), int(h)
                if (iw, ih) in self.screen_res or (ih, iw) in self.screen_res:
                    if (not he or ms in ('No EXIF', 'Minimal EXIF')) and not _is_probable_camera_name(fn):
                        return True
            except (ValueError, TypeError):
                pass
        return False

    def _scan_ex(self):
        cache = {'daily': {}, 'monthly': {}, 'screenshot': {}}
        if not self.output.exists():
            return cache
        try:
            items = list(self.output.rglob('*')) if self.structure != 'flat' else list(self.output.iterdir())
            for item in items:
                if not item.is_dir():
                    continue
                if item.name == 'videos':
                    continue
                name = item.name
                if RE_SS_FOLDER.search(name):
                    cache['screenshot'][name] = {'name': name, 'full_path': str(item), 'count': _count_files(item)}
                    continue
                dp = is_valid_date_folder(name)
                if dp and dp not in cache['daily']:
                    cache['daily'][dp] = {'name': name, 'full_path': str(item), 'count': _count_files(item)}
                    continue
                mp = is_valid_month_folder(name)
                if mp and mp not in cache['monthly']:
                    cache['monthly'][mp] = {'name': name, 'full_path': str(item), 'count': _count_files(item)}
        except Exception:
            pass
        return cache

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

    def _dest(self, fn, dt, ft):
        if self.structure == 'year' and dt:
            d = self.output / str(dt.year) / fn
        elif self.structure == 'year-month-date' and dt:
            d = self.output / str(dt.year) / MONTH_NAMES.get(dt.month, str(dt.month).zfill(2)) / fn
        else:
            d = self.output / fn
        if self.vid_sub and ft == 'video':
            d = d / 'videos'
        return d

    def _find_ex(self, dk):
        if not self.reuse or not self._cache:
            return None
        ex = self._cache['daily'].get(dk)
        if ex:
            return ex
        if dk.endswith('-00'):
            return self._cache['monthly'].get(dk)
        return None

    def _find_ss_ex(self, ss_key):
        if not self.reuse or not self._cache:
            return None
        for name, data in self._cache['screenshot'].items():
            if ss_key in name:
                return data
        return None

    def _date(self, r):
        for k in ['manual_date_override', 'Manual Date Override']:
            v = r.get(k)
            if v:
                dt = parse_datetime_flexible(v)
                if dt:
                    return dt
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

    def _rename_existing_folder(self, ex, new_total):
        old_path = Path(ex['full_path'])
        old_name = ex['name']
        m = RE_PIC.match(old_name)
        if not m:
            return old_name, str(old_path)
        old_count = int(m.group(2))
        if old_count == new_total:
            return old_name, str(old_path)
        new_name = m.group(1) + '-' + format_pic_count(new_total) + m.group(3)
        new_path = old_path.parent / new_name
        if new_path.exists() and str(new_path) != str(old_path):
            return old_name, str(old_path)
        if new_name == old_name:
            return old_name, str(old_path)
        try:
            old_path.rename(new_path)
            for cache_type in ('daily', 'monthly', 'screenshot'):
                for dk, cached in self._cache[cache_type].items():
                    if cached['full_path'] == str(old_path):
                        cached['name'] = new_name
                        cached['full_path'] = str(new_path)
                        cached['count'] = new_total
                        break
            return new_name, str(new_path)
        except Exception:
            return old_name, str(old_path)

    def organize(self, records):
        if not records:
            return []
        if self.reuse:
            self._cache = self._scan_ex()
        ss, normal = [], []
        for r in records:
            dv = str(
                r.get('delete_flag', '') or r.get('DELETE?', '') or r.get('DELETE? (Yes/No)', '') or ''
            ).strip().lower()
            if dv in ('yes', 'true', '1'):
                continue
            if self._is_ss(r):
                ss.append(r)
            else:
                normal.append(r)
        mv = []
        if ss:
            mv.extend(self._org_ss(ss))
        if normal:
            mv.extend(self._org_normal(normal))
        self._fix_counts(mv)
        self._report(mv)
        return mv

    def _org_ss(self, ss):
        mv = []
        mg = defaultdict(list)
        for rec in ss:
            dt = self._date(rec)
            mg[dt.strftime('%Y-%m') if dt else 'undated'].append((rec, dt))
        for mk, grp in mg.items():
            new_count = len(grp)
            if mk == 'undated':
                ss_key = 'screenshots'
                base_fn = 'screenshots-' + format_pic_count(new_count)
            else:
                ss_key = mk + '-screenshots'
                base_fn = mk + '-screenshots-' + format_pic_count(new_count)
            ex = self._find_ss_ex(ss_key)
            if ex:
                existing_count = ex.get('count', 0)
                new_total = existing_count + new_count
                fn, _ = self._rename_existing_folder(ex, new_total)
            else:
                fn = base_fn
            sdt = grp[0][1]
            for rec, dt in tqdm(grp, desc='  ' + fn, disable=not self.show):
                ft = rec.get('file_type', '')
                dd = (self.output / str(sdt.year) / fn) if (self.structure == 'year' and sdt) else (self.output / fn)
                if self.structure == 'year-month-date' and sdt:
                    dd = self.output / str(sdt.year) / MONTH_NAMES.get(sdt.month, str(sdt.month).zfill(2)) / fn
                if self.vid_sub and ft == 'video':
                    dd = dd / 'videos'
                mv.append(self._cp(rec, dd, fn))
        return mv

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

        for dk in sorted(daily):
            g = dr[dk]
            sdt = g[0][1]
            ds = sdt.strftime('%Y-%m-%d')
            loc = self._get_loc([r for r, _ in g])
            ex = self._find_ex(ds)
            if ex:
                existing_count = ex.get('count', 0)
                new_total = existing_count + len(g)
                fn, _ = self._rename_existing_folder(ex, new_total)
            else:
                fn = self._build_fn(ds, len(g), loc)
            for rec, dt in tqdm(g, desc='  ' + fn, disable=not self.show):
                ft = rec.get('file_type') or rec.get('Type') or ''
                mv.append(self._cp(rec, self._dest(fn, dt, ft), fn))

        for mk in sorted(monthly):
            g = monthly[mk]
            sdt = g[0][1]
            ds = sdt.strftime('%Y-%m') + '-00'
            loc = self._get_loc([r for r, _ in g])
            ex = self._find_ex(ds)
            if ex:
                existing_count = ex.get('count', 0)
                new_total = existing_count + len(g)
                fn, _ = self._rename_existing_folder(ex, new_total)
            else:
                fn = self._build_fn(ds, len(g), loc)
            for rec, dt in tqdm(g, desc='  ' + fn, disable=not self.show):
                ft = rec.get('file_type') or rec.get('Type') or ''
                mv.append(self._cp(rec, self._dest(fn, dt, ft), fn))

        if undated:
            fn = 'undated-' + format_pic_count(len(undated))
            for rec, dt in tqdm(undated, desc='  ' + fn, disable=not self.show):
                dd = self.output / fn
                if self.vid_sub and rec.get('file_type') == 'video':
                    dd = dd / 'videos'
                mv.append(self._cp(rec, dd, fn))
        return mv

    def _fix_counts(self, mv):
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
                for x in mv:
                    if x.get('destination') and old in x['destination']:
                        x['destination'] = x['destination'].replace(old, nn)
                    if x.get('folder') == old:
                        x['folder'] = nn
            except Exception:
                pass

    def _cp(self, rec, dest_dir, fl):
        src = rec.get('full_path') or rec.get('Full Path') or ''
        fn = rec.get('filename') or rec.get('Filename') or ''
        if not src:
            return {'filename': fn, 'source': '', 'destination': '', 'status': 'Error: No path', 'folder': fl}
        source = Path(src)
        if not source.exists():
            return {'filename': fn, 'source': str(source), 'destination': '', 'status': 'Error: Not found', 'folder': fl}
        ensure_directory(dest_dir)
        dest = resolve_filename_conflict(dest_dir / safe_filename(source.name), self.conflict)
        if dest is None:
            return {'filename': source.name, 'source': str(source), 'destination': '', 'status': 'Skipped', 'folder': fl}
        try:
            if self.op == 'move':
                shutil.move(str(source), str(dest))
            else:
                shutil.copy2(str(source), str(dest))
            self._sync_metadata_json(rec, dest)
            return {'filename': source.name, 'source': str(source), 'destination': str(dest), 'status': 'Success', 'folder': fl}
        except Exception as e:
            return {'filename': source.name, 'source': str(source), 'destination': str(dest), 'status': 'Error: ' + str(e), 'folder': fl}

    def _sync_metadata_json(self, rec, media_dest):
        try:
            meta_path = rec.get('metadata_json_path') or rec.get('Metadata JSON Path')
            if not meta_path:
                return
            src_meta = Path(str(meta_path))
            if not src_meta.exists():
                return
            media_dest = Path(media_dest)

            vault_in_place = False
            if self._metadata_vault_root is not None:
                try:
                    src_meta.resolve().relative_to(self._metadata_vault_root.resolve())
                    vault_in_place = True
                except ValueError:
                    pass
                except OSError:
                    pass

            if vault_in_place:
                meta_dest = src_meta.resolve()
                try:
                    data = json.loads(meta_dest.read_text(encoding="utf-8"))
                    apply_media_path_to_doc(data, media_dest, self.config, meta_dest)
                    data = _ensure_json_serializable(data)
                    meta_dest.write_text(
                        json.dumps(data, indent=2, ensure_ascii=True), encoding="utf-8"
                    )
                    try:
                        from .vault_maintenance import retire_scan_json_for_organized_file

                        md5 = str(rec.get("md5_hash") or rec.get("MD5 Hash") or "")
                        retire_scan_json_for_organized_file(
                            self.config, media_dest, meta_dest, md5_hash=md5
                        )
                    except Exception:
                        pass
                except Exception:
                    pass
                return

            folder_root = (
                media_dest.parent.parent
                if media_dest.parent.name == "videos"
                else media_dest.parent
            )
            meta_dir = folder_root / "metadata"
            ensure_directory(meta_dir)
            meta_dest = resolve_filename_conflict(meta_dir / src_meta.name, self.conflict)
            if meta_dest is None:
                return
            if self.op == "move":
                shutil.move(str(src_meta), str(meta_dest))
            else:
                shutil.copy2(str(src_meta), str(meta_dest))

            try:
                data = json.loads(meta_dest.read_text(encoding="utf-8"))
                apply_media_path_to_doc(data, media_dest, self.config, meta_dest)
                data = _ensure_json_serializable(data)
                meta_dest.write_text(
                    json.dumps(data, indent=2, ensure_ascii=True), encoding="utf-8"
                )
            except Exception:
                pass
        except Exception:
            pass

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
            lines.extend(['Success: ' + str(s), 'Errors: ' + str(e), 'Total: ' + str(len(mv)), '', 'FOLDERS:'])
            fc = defaultdict(int)
            for m in mv:
                if m['status'] == 'Success':
                    fc[m['folder']] += 1
            for f in sorted(fc):
                lines.append('  ' + f + ': ' + str(fc[f]))
            with open(self.output / 'organization-report.txt', 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
        except Exception:
            pass

    @staticmethod
    def convert_structure(source_folder, target_structure, target_folder=None):
        source = Path(source_folder)
        if not source.exists():
            print('  Error: Source not found: ' + str(source))
            return False
        dest = Path(target_folder) if target_folder else source
        if target_structure not in ('flat', 'year', 'year-month-date'):
            print('  Error: Invalid target: ' + target_structure)
            return False
        print('  Scanning all folders...')
        folders = _collect_all_folders(source)
        if not folders:
            print('  No dated folders found!')
            return False
        if target_folder and str(dest) != str(source):
            ensure_directory(dest)
        moved = 0
        errors = 0
        renamed = 0
        for fd in tqdm(folders, desc='  Converting', disable=False):
            old_path = Path(fd['path'])
            if fd['current'] == 'misc':
                if target_folder and str(dest) != str(source):
                    new_path = dest / fd['name']
                    if str(new_path) != str(old_path):
                        try:
                            ensure_directory(new_path.parent)
                            if new_path.exists():
                                _merge_folders(old_path, new_path)
                            else:
                                shutil.move(str(old_path), str(new_path))
                            moved += 1
                        except Exception:
                            errors += 1
                continue
            if fd.get('current') == 'unaligned':
                updated_path = _normalize_unaligned_folder_name(old_path)
                if updated_path:
                    renamed += 1
                continue
            new_path = _build_target_path(dest, target_structure, fd)
            if str(new_path) == str(old_path):
                continue
            try:
                ensure_directory(new_path.parent)
                if new_path.exists():
                    _merge_folders(old_path, new_path)
                    new_total = _count_files(new_path)
                    updated_name = _update_pic_count(new_path, new_total)
                    if updated_name:
                        renamed += 1
                    moved += 1
                else:
                    shutil.move(str(old_path), str(new_path))
                    moved += 1
            except Exception:
                errors += 1
        _cleanup_empty_dirs(source)
        if target_folder and str(dest) != str(source):
            _cleanup_empty_dirs(dest)
        print('  Converted: ' + str(moved) + ' moved, ' + str(renamed) + ' count-updated, ' + str(errors) + ' errors')
        return True

    @staticmethod
    def merge_duplicate_dates(source_folder, structure='flat'):
        source = Path(source_folder)
        if not source.exists():
            print('  Error: Source not found: ' + str(source))
            return False
        print('  Scanning for same-date folders...')
        merge_count = _merge_same_date_folders(source, structure)
        if merge_count > 0:
            print('  Merged: ' + str(merge_count) + ' folder groups')
        else:
            print('  No duplicate-date folders found')
        return True

    @staticmethod
    def detect_structure(root_folder):
        return detect_structure(root_folder)


def _merge_same_date_folders(root, structure):
    root = Path(root)
    merge_count = 0
    if structure == 'flat':
        merge_count += _merge_same_date_in_dir(root)
    elif structure == 'year':
        merge_count += _merge_same_date_in_dir(root)
        for year_dir in sorted(root.iterdir()):
            if year_dir.is_dir() and RE_YEAR_DIR.match(year_dir.name):
                merge_count += _merge_same_date_in_dir(year_dir)
    elif structure == 'year-month-date':
        merge_count += _merge_same_date_in_dir(root)
        for year_dir in sorted(root.iterdir()):
            if not year_dir.is_dir() or not RE_YEAR_DIR.match(year_dir.name):
                continue
            merge_count += _merge_same_date_in_dir(year_dir)
            for month_dir in sorted(year_dir.iterdir()):
                if month_dir.is_dir():
                    merge_count += _merge_same_date_in_dir(month_dir)
    return merge_count


def _merge_same_date_in_dir(parent_dir):
    parent_dir = Path(parent_dir)
    if not parent_dir.exists():
        return 0
    merge_count = 0
    date_groups = defaultdict(list)
    for item in sorted(parent_dir.iterdir()):
        if not item.is_dir() or item.name == 'videos':
            continue
        if RE_SS_FOLDER.search(item.name):
            continue
        if RE_YEAR_DIR.match(item.name):
            continue
        mm = RE_MONTH_DIR.match(item.name)
        if mm and not RE_DATE_PREFIX.match(item.name) and not RE_MONTH_PREFIX.match(item.name):
            continue
        dk = _extract_date_key(item.name)
        if dk:
            date_groups[dk].append(item)
    for dk, group_folders in sorted(date_groups.items()):
        if len(group_folders) < 2:
            continue
        if _should_skip_merge_for_suffix_conflict(group_folders):
            continue
        best_text = ''
        best_count = 0
        best_folder = group_folders[0]
        for folder in group_folders:
            text = _extract_text_suffix(folder.name)
            count = _count_files(folder)
            if text and not best_text:
                best_text = text
                best_folder = folder
                best_count = count
            elif text and count > best_count:
                best_text = text
                best_folder = folder
                best_count = count
            elif not best_text and count > best_count:
                best_folder = folder
                best_count = count
        for folder in group_folders:
            if folder == best_folder:
                continue
            try:
                _merge_folders(folder, best_folder)
            except Exception:
                pass
        total = _count_files(best_folder)
        new_name = dk + '-' + format_pic_count(total) + (('-' + best_text) if best_text else '')
        if new_name != best_folder.name:
            new_path = best_folder.parent / new_name
            if not (new_path.exists() and str(new_path) != str(best_folder)):
                try:
                    best_folder.rename(new_path)
                except Exception:
                    pass
        merge_count += 1
    return merge_count


def _build_target_path(dest, target_structure, fd):
    folder_name = fd['name']
    year = fd.get('year', '')
    month = fd.get('month', '')
    if target_structure == 'flat':
        return dest / folder_name
    elif target_structure == 'year':
        return dest / str(year) / folder_name
    elif target_structure == 'year-month-date':
        try:
            month_int = int(month)
        except (ValueError, TypeError):
            month_int = 0
        month_name = MONTH_NAMES.get(month_int, str(month).zfill(2))
        return dest / str(year) / month_name / folder_name
    return dest / folder_name


def _update_pic_count(folder_path, new_count):
    folder_path = Path(folder_path)
    old_name = folder_path.name
    m = RE_PIC.match(old_name)
    if not m:
        return None
    old_count = int(m.group(2))
    if old_count == new_count:
        return None
    new_name = m.group(1) + '-' + format_pic_count(new_count) + m.group(3)
    new_path = folder_path.parent / new_name
    if new_path.exists() and str(new_path) != str(folder_path):
        return None
    if new_name == old_name:
        return None
    try:
        folder_path.rename(new_path)
        return new_name
    except Exception:
        return None


def _collect_all_folders(source):
    source = Path(source)
    folders = []
    seen_paths = set()
    for item in source.iterdir():
        if not item.is_dir() or item.name == 'videos':
            continue
        name = item.name
        if RE_YEAR_DIR.match(name):
            _scan_year_dir(item, folders, seen_paths)
            continue
        info = _extract_folder_info(item)
        if info and str(item) not in seen_paths:
            if 'current' not in info:
                info['current'] = 'flat'
            folders.append(info)
            seen_paths.add(str(item))
            continue
        # Unaligned folders (e.g., "WhatsApp Images") should be moved to Misc bucket
        if str(item) not in seen_paths:
            folders.append({'path': str(item), 'name': name, 'year': 'misc', 'month': '00', 'current': 'unaligned'})
            seen_paths.add(str(item))
    return folders


def _scan_year_dir(year_dir, folders, seen_paths):
    year = year_dir.name
    for sub in year_dir.iterdir():
        if not sub.is_dir() or sub.name == 'videos':
            continue
        mm = RE_MONTH_DIR.match(sub.name)
        has_date_prefix = RE_DATE_PREFIX.match(sub.name)
        has_month_prefix = RE_MONTH_PREFIX.match(sub.name)
        has_ss = RE_SS_FOLDER.search(sub.name)
        is_month_dir = mm and not has_date_prefix and not has_month_prefix and not has_ss
        if is_month_dir:
            month = mm.group(1)
            for leaf in sub.iterdir():
                if not leaf.is_dir() or leaf.name == 'videos':
                    continue
                if str(leaf) in seen_paths:
                    continue
                info = _extract_folder_info(leaf)
                if info:
                    info['current'] = 'year-month-date'
                    if not info.get('year') or info['year'] == 'misc':
                        info['year'] = year
                    if not info.get('month') or info['month'] == '00':
                        info['month'] = month
                    folders.append(info)
                    seen_paths.add(str(leaf))
                else:
                    # Unaligned leaf inside month dir -> Misc bucket, keep trace of origin
                    folders.append({'path': str(leaf), 'name': leaf.name, 'year': 'misc', 'month': '00', 'current': 'unaligned'})
                    seen_paths.add(str(leaf))
        else:
            if str(sub) in seen_paths:
                continue
            info = _extract_folder_info(sub)
            if info:
                info['current'] = 'year'
                if not info.get('year') or info['year'] == 'misc':
                    info['year'] = year
                folders.append(info)
                seen_paths.add(str(sub))
            else:
                # Unaligned folder inside year dir -> Misc bucket
                folders.append({'path': str(sub), 'name': sub.name, 'year': 'misc', 'month': '00', 'current': 'unaligned'})
                seen_paths.add(str(sub))


def _extract_folder_info(item):
    name = item.name
    dp = is_valid_date_folder(name)
    if dp:
        parts = dp.split('-')
        return {'path': str(item), 'name': name, 'year': parts[0], 'month': parts[1]}
    mp = is_valid_month_folder(name)
    if mp:
        parts = mp.split('-')
        return {'path': str(item), 'name': name, 'year': parts[0], 'month': parts[1]}
    ss_match = re.match('^(\\d{4})-(\\d{2})-(.*)', name)
    if ss_match and RE_SS_FOLDER.search(name):
        return {'path': str(item), 'name': name, 'year': ss_match.group(1), 'month': ss_match.group(2)}
    if name.startswith('undated') or name.startswith('screenshot'):
        return {'path': str(item), 'name': name, 'year': 'misc', 'month': '00', 'current': 'misc'}
    return None


def _merge_folders(old_path, new_path):
    old_path = Path(old_path)
    new_path = Path(new_path)
    for item in old_path.iterdir():
        target_item = new_path / item.name
        if item.is_dir():
            if target_item.exists():
                for sub in item.iterdir():
                    st = target_item / sub.name
                    if not st.exists():
                        shutil.move(str(sub), str(st))
                    else:
                        stem = sub.stem
                        suffix = sub.suffix
                        for i in range(1, 100000):
                            alt = target_item / (stem + '-' + str(i) + suffix)
                            if not alt.exists():
                                shutil.move(str(sub), str(alt))
                                break
                try:
                    if not any(item.iterdir()):
                        item.rmdir()
                except Exception:
                    pass
            else:
                shutil.move(str(item), str(target_item))
        else:
            if not target_item.exists():
                shutil.move(str(item), str(target_item))
            else:
                stem = item.stem
                suffix = item.suffix
                for i in range(1, 100000):
                    alt = new_path / (stem + '-' + str(i) + suffix)
                    if not alt.exists():
                        shutil.move(str(item), str(alt))
                        break
    try:
        if old_path.exists() and not any(old_path.iterdir()):
            old_path.rmdir()
    except Exception:
        pass


def _cleanup_empty_dirs(folder):
    folder = Path(folder)
    try:
        for item in sorted(folder.rglob('*'), reverse=True):
            if item.is_dir():
                try:
                    if not any(item.iterdir()):
                        item.rmdir()
                except Exception:
                    pass
    except Exception:
        pass


def detect_structure(root_folder):
    root = Path(root_folder)
    if not root.exists():
        return 'flat'
    top_dirs = [d for d in root.iterdir() if d.is_dir() and d.name != 'videos']
    year_dirs = [d for d in top_dirs if RE_YEAR_DIR.match(d.name)]
    if year_dirs:
        for year_dir in year_dirs:
            for sub in year_dir.iterdir():
                if not sub.is_dir():
                    continue
                if RE_MONTH_DIR.match(sub.name) and not RE_DATE_PREFIX.match(sub.name) and not RE_MONTH_PREFIX.match(sub.name):
                    return 'year-month-date'
        return 'year'
    return 'flat'

