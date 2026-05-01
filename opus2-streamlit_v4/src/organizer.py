
# ============================================================
# FILE: src/organizer.py
# ============================================================
"""Image Organizer v2.3 - 3-digit pic count, folder update"""

import re
import shutil
import logging
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter

from tqdm import tqdm
from .utils import (parse_datetime_flexible, resolve_filename_conflict,
                    ensure_directory, safe_filename, is_valid_date_folder,
                    is_valid_month_folder, format_pic_count)

logger = logging.getLogger(__name__)

MONTH_NAMES = {1: '01-Jan', 2: '02-Feb', 3: '03-Mar', 4: '04-Apr', 5: '05-May', 6: '06-Jun',
               7: '07-Jul', 8: '08-Aug', 9: '09-Sep', 10: '10-Oct', 11: '11-Nov', 12: '12-Dec'}

SCREEN_RES = {(1080, 1920), (1080, 2340), (1080, 2400), (1080, 2520), (1170, 2532), (1179, 2556),
              (1284, 2778), (1290, 2796), (1440, 2560), (1440, 3040), (1440, 3200), (750, 1334),
              (828, 1792), (1125, 2436), (1920, 1080), (2560, 1440), (3840, 2160), (2048, 2732),
              (1668, 2388), (1620, 2160), (1536, 2048), (2160, 1620), (2388, 1668), (2732, 2048), (2048, 1536)}


def _compile_pic():
    return re.compile('^' + '(.*?)' + '-' + '(\\d+)' + 'pic' + '(.*)' + chr(36))

def _compile_day():
    return re.compile('^' + '\\d{4}' + '-' + '\\d{2}' + '-' + '(\\d{2})' + '(.*)')

def _compile_loc():
    return re.compile('[^a-z0-9]+')

def _compile_ss():
    return re.compile('screenshot|screen_shot|screen-shot|capture|snip', re.IGNORECASE)

RE_PIC = _compile_pic()
RE_DAY = _compile_day()
RE_LOC = _compile_loc()
RE_SS = _compile_ss()


def _count_files(folder_path):
    try:
        fp = Path(folder_path)
        if not fp.exists():
            return 0
        count = 0
        for item in fp.iterdir():
            if item.is_file():
                count += 1
            elif item.is_dir() and item.name == 'videos':
                for sub in item.iterdir():
                    if sub.is_file():
                        count += 1
        return count
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

    def _is_ss(self, rec):
        if not self.sep_ss:
            return False
        fn = str(rec.get('filename') or rec.get('Filename') or '')
        if RE_SS.search(fn):
            return True
        w, h = rec.get('width') or rec.get('Width (px)'), rec.get('height') or rec.get('Height (px)')
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

    def _scan_ex(self):
        cache = {'daily': {}, 'monthly': {}}
        try:
            if not self.output.exists():
                return cache
            items = self.output.iterdir() if self.structure == 'flat' else self.output.rglob('*')
            for item in items:
                if not item.is_dir():
                    continue
                name = item.name
                dp = is_valid_date_folder(name)
                if dp and dp not in cache['daily']:
                    cache['daily'][dp] = {'name': name, 'full_path': str(item), 'count': _count_files(item)}
                    continue
                mp = is_valid_month_folder(name)
                if mp and mp not in cache['monthly']:
                    cache['monthly'][mp] = {'name': name, 'full_path': str(item), 'count': _count_files(item)}
        except Exception as e:
            logger.warning('Scan error: %s', e)
        return cache

    def _build_fn(self, dk, cnt, loc=''):
        pp = format_pic_count(cnt)
        if loc:
            cl = RE_LOC.sub('-', loc.lower()).strip('-')
            if cl and len(cl) > 1:
                return dk + '-' + pp + '-' + cl
        return dk + '-' + pp

    def _get_loc(self, records):
        locs = []
        for rec in records:
            for k in ['location_city', 'location_name', 'Location']:
                v = rec.get(k)
                if v and str(v).strip():
                    locs.append(str(v).strip().lower())
                    break
        if not locs:
            return ''
        mc = Counter(locs).most_common(1)[0]
        return mc[0] if mc[1] >= len(records) * 0.3 else ''

    def _dest(self, fn, dt, ft):
        if self.structure == 'year-month' and dt:
            d = self.output / str(dt.year) / MONTH_NAMES.get(dt.month, str(dt.month).zfill(2)) / fn
        elif self.structure == 'year-month-day' and dt:
            m = RE_DAY.match(fn)
            if m:
                d = self.output / str(dt.year) / MONTH_NAMES.get(dt.month, str(dt.month).zfill(2)) / (m.group(1) + m.group(2))
            else:
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
        if self.reuse:
            self._cache = self._scan_ex()
        ss, normal, skip = [], [], 0
        for r in records:
            dv = str(r.get('delete_flag', '') or r.get('DELETE?', '') or r.get('DELETE? (Yes/No)', '') or '').strip().lower()
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

    def _org_ss(self, ss):
        mv = []
        mg = defaultdict(list)
        for rec in ss:
            dt = self._date(rec)
            if dt:
                mg[dt.strftime('%Y-%m')].append((rec, dt))
            else:
                mg['undated'].append((rec, None))
        for mk, grp in mg.items():
            c = len(grp)
            if mk == 'undated':
                fn = 'screenshots-' + format_pic_count(c)
                sdt = None
            else:
                fn = mk + '-screenshots-' + format_pic_count(c)
                sdt = grp[0][1]
            for rec, dt in tqdm(grp, desc='  ' + fn, disable=not self.show):
                ft = rec.get('file_type') or rec.get('Type') or ''
                if self.structure in ('year-month', 'year-month-day') and sdt:
                    dd = self.output / str(sdt.year) / MONTH_NAMES.get(sdt.month, str(sdt.month).zfill(2)) / fn
                else:
                    dd = self.output / fn
                if self.vid_sub and ft == 'video':
                    dd = dd / 'videos'
                mv.append(self._cp(rec, dd, fn))
        return mv

    def _org_normal(self, records):
        mv = []
        dated = [(r, self._date(r)) for r in records]
        dc, dr, undated = defaultdict(int), defaultdict(list), []
        for rec, dt in dated:
            if dt:
                dk = dt.strftime('%Y%m%d')
                dc[dk] += 1
                dr[dk].append((rec, dt))
            else:
                undated.append((rec, None))
        daily, monthly = set(), defaultdict(list)
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
                fn = ex['name']
                ec = ex.get('count', 0)
                nt = ec + len(g)
                m = RE_PIC.match(fn)
                if m:
                    fn = m.group(1) + '-' + format_pic_count(nt) + m.group(3)
                logger.info('Reuse: %s (%d+%d=%d)', ex['name'], ec, len(g), nt)
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
                fn = ex['name']
                ec = ex.get('count', 0)
                nt = ec + len(g)
                m = RE_PIC.match(fn)
                if m:
                    fn = m.group(1) + '-' + format_pic_count(nt) + m.group(3)
                logger.info('Reuse: %s (%d+%d=%d)', ex['name'], ec, len(g), nt)
            else:
                fn = self._build_fn(ds, len(g), loc)
            for rec, dt in tqdm(g, desc='  ' + fn, disable=not self.show):
                ft = rec.get('file_type') or rec.get('Type') or ''
                mv.append(self._cp(rec, self._dest(fn, dt, ft), fn))
        if undated:
            fn = 'undated-' + format_pic_count(len(undated))
            for rec, dt in tqdm(undated, desc='  ' + fn, disable=not self.show):
                ft = rec.get('file_type') or rec.get('Type') or ''
                dd = self.output / fn
                if self.vid_sub and ft == 'video':
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
        for fs, _ in fc.items():
            fp = Path(fs)
            if not fp.exists():
                continue
            old = fp.name
            m = RE_PIC.match(old)
            if not m:
                continue
            actual = _count_files(fp)
            oc = int(m.group(2))
            if oc == actual:
                continue
            nn = m.group(1) + '-' + format_pic_count(actual) + m.group(3)
            np2 = fp.parent / nn
            if np2.exists() and str(np2) != str(fp):
                continue
            if nn == old:
                continue
            try:
                fp.rename(np2)
                logger.info('Renamed: %s -> %s', old, nn)
                for x in mv:
                    if x.get('destination') and old in x['destination']:
                        x['destination'] = x['destination'].replace(old, nn)
                    if x.get('folder') == old:
                        x['folder'] = nn
            except Exception as e:
                logger.warning('Rename: %s', e)

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
            return {'filename': source.name, 'source': str(source), 'destination': str(dest), 'status': 'Success', 'folder': fl}
        except Exception as e:
            return {'filename': source.name, 'source': str(source), 'destination': str(dest), 'status': 'Error: ' + str(e), 'folder': fl}

    def _report(self, mv):
        try:
            rp = self.output / 'organization-report.txt'
            lines = ['Organization Report', '=' * 60, 'Generated: ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                     'Structure: ' + self.structure, 'Operation: ' + self.op, '']
            s = sum(1 for m in mv if m['status'] == 'Success')
            e = sum(1 for m in mv if 'Error' in m['status'])
            lines.extend(['Success: ' + str(s), 'Errors: ' + str(e), 'Total: ' + str(len(mv)), ''])
            lines.extend(['=' * 60, 'FOLDERS', '=' * 60])
            fc = defaultdict(int)
            for m in mv:
                if m['status'] == 'Success':
                    fc[m['folder']] += 1
            for f in sorted(fc):
                lines.append('  ' + f + ': ' + str(fc[f]) + ' files')
            errs = [m for m in mv if 'Error' in m['status']]
            if errs:
                lines.extend(['', '=' * 60, 'ERRORS', '=' * 60])
                for m in errs[:50]:
                    lines.append('  ' + m['filename'] + ': ' + m['status'])
            with open(rp, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
        except Exception as e:
            logger.error('Report: %s', e)
