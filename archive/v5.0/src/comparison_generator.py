"""Comparison Generator v2.5 - Fixed duplicate page generation"""

import logging
from pathlib import Path
from collections import defaultdict
from datetime import datetime

logger = logging.getLogger(__name__)

try:
    from jinja2 import Template
    JINJA_OK = True
except ImportError:
    JINJA_OK = False

HTML_HEADER = '<!DOCTYPE html><html><head><title>'
HTML_STYLE = '</title><style>'
HTML_CSS = 'body{font-family:Arial,sans-serif;margin:20px;background:#f5f5f5}'
HTML_CSS = HTML_CSS + 'h1{color:#2E4057}'
HTML_CSS = HTML_CSS + '.group{background:white;padding:15px;margin:10px 0;border-radius:8px;box-shadow:0 2px 4px rgba(0,0,0,0.1)}'
HTML_CSS = HTML_CSS + '.group h3{color:#4A148C;margin-top:0}'
HTML_CSS = HTML_CSS + 'table{border-collapse:collapse;width:100%}'
HTML_CSS = HTML_CSS + 'th{background:#2E4057;color:white;padding:8px;text-align:left}'
HTML_CSS = HTML_CSS + 'td{padding:6px 8px;border-bottom:1px solid #ddd}'
HTML_CSS = HTML_CSS + 'tr:nth-child(even){background:#f9f9f9}'
HTML_CSS = HTML_CSS + '.badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:12px;margin:2px}'
HTML_CSS = HTML_CSS + '.dup{background:#FFD6D6;color:#8B0000}'
HTML_CSS = HTML_CSS + '.sim{background:#E8D5F5;color:#4A148C}'
HTML_CSS = HTML_CSS + '.best{background:#D4EDDA;color:#155724}'
HTML_CSS = HTML_CSS + '.del{background:#F8D7DA;color:#721C24}'
HTML_CSS = HTML_CSS + '.stats{background:#E3F2FD;padding:10px;border-radius:5px;margin:10px 0}'


class ComparisonGenerator:

    def __init__(self, output_folder='./comparisons'):
        self.output_folder = Path(output_folder)
        self.output_folder.mkdir(parents=True, exist_ok=True)

    def generate(self, records):
        if not records:
            logger.warning('No records for comparison')
            return []

        pages = []

        dup_page = self._generate_duplicate_page(records)
        if dup_page:
            pages.append(dup_page)

        sim_page = self._generate_similar_page(records)
        if sim_page:
            pages.append(sim_page)

        return pages

    def _is_yes(self, value):
        if value is None:
            return False
        return str(value).strip().upper() in ('YES', 'TRUE', '1')

    def _has_value(self, value):
        if value is None:
            return False
        s = str(value).strip()
        return len(s) > 0 and s.upper() != 'NO' and s.upper() != 'NONE' and s != ''

    def _generate_duplicate_page(self, records):
        groups = defaultdict(list)
        for r in records:
            is_dup = self._is_yes(r.get('is_duplicate'))
            grp = r.get('duplicate_group', '')
            if is_dup and self._has_value(grp):
                groups[str(grp).strip()].append(r)

        if not groups:
            dup_count = sum(1 for r in records if self._is_yes(r.get('is_duplicate')))
            grp_count = sum(1 for r in records if self._has_value(r.get('duplicate_group')))
            logger.info('Duplicate page: is_duplicate=YES count=%d, has_group count=%d', dup_count, grp_count)
            print('    Comparison: No duplicate groups found (dup_yes=' + str(dup_count) + ', has_group=' + str(grp_count) + ')')
            return None

        total_files = sum(len(files) for files in groups.values())
        print('    Comparison: ' + str(len(groups)) + ' duplicate groups, ' + str(total_files) + ' files')

        html = self._build_html('Duplicate Comparison', groups, 'duplicate')
        out = self.output_folder / 'duplicates.html'
        try:
            with open(out, 'w', encoding='utf-8') as f:
                f.write(html)
            return str(out)
        except Exception as e:
            logger.error('Write error: %s', e)
            return None

    def _generate_similar_page(self, records):
        groups = defaultdict(list)
        for r in records:
            is_sim = self._is_yes(r.get('is_similar'))
            grp = r.get('similar_group', '')
            if is_sim and self._has_value(grp):
                groups[str(grp).strip()].append(r)

        if not groups:
            sim_count = sum(1 for r in records if self._is_yes(r.get('is_similar')))
            grp_count = sum(1 for r in records if self._has_value(r.get('similar_group')))
            logger.info('Similar page: is_similar=YES count=%d, has_group count=%d', sim_count, grp_count)
            if sim_count > 0 or grp_count > 0:
                print('    Comparison: No similar groups found (sim_yes=' + str(sim_count) + ', has_group=' + str(grp_count) + ')')
            return None

        total_files = sum(len(files) for files in groups.values())
        print('    Comparison: ' + str(len(groups)) + ' similar groups, ' + str(total_files) + ' files')

        html = self._build_html('Similar Image Comparison', groups, 'similar')
        out = self.output_folder / 'similar.html'
        try:
            with open(out, 'w', encoding='utf-8') as f:
                f.write(html)
            return str(out)
        except Exception as e:
            logger.error('Write error: %s', e)
            return None

    def _build_html(self, title, groups, page_type):
        total = sum(len(files) for files in groups.values())
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        parts = []
        parts.append(HTML_HEADER + title + HTML_STYLE + HTML_CSS)
        parts.append('</style></head><body>')
        parts.append('<h1>' + title + '</h1>')
        parts.append('<div class="stats">')
        parts.append('<strong>Generated:</strong> ' + ts)
        parts.append(' | <strong>Groups:</strong> ' + str(len(groups)))
        parts.append(' | <strong>Total Files:</strong> ' + str(total))
        parts.append('</div>')

        for label in sorted(groups.keys()):
            files = groups[label]
            parts.append('<div class="group">')
            parts.append('<h3>' + str(label) + ' (' + str(len(files)) + ' files)</h3>')
            parts.append('<table>')

            if page_type == 'duplicate':
                parts.append('<tr><th>File</th><th>Size MB</th><th>Quality</th><th>Date</th><th>Best?</th><th>Action</th></tr>')
                for f in files:
                    fn = str(f.get('filename', '?'))
                    sz = str(f.get('size_mb', '?'))
                    q = str(f.get('quality_score', '?'))
                    dt = str(f.get('date_taken', '') or f.get('file_modified', '') or '?')
                    best = str(f.get('is_best_in_group', ''))
                    rec = str(f.get('recommendation', ''))
                    best_badge = '<span class="badge best">KEEP</span>' if best.lower() == 'yes' else '<span class="badge del">DELETE</span>' if best.lower() == 'no' else ''
                    parts.append('<tr>')
                    parts.append('<td>' + fn + '</td>')
                    parts.append('<td>' + sz + '</td>')
                    parts.append('<td>' + q + '</td>')
                    parts.append('<td>' + dt + '</td>')
                    parts.append('<td>' + best_badge + '</td>')
                    parts.append('<td>' + rec + '</td>')
                    parts.append('</tr>')
            else:
                parts.append('<tr><th>File</th><th>Size MB</th><th>Quality</th><th>Date</th><th>Sim Score</th><th>Methods</th></tr>')
                for f in files:
                    fn = str(f.get('filename', '?'))
                    sz = str(f.get('size_mb', '?'))
                    q = str(f.get('quality_score', '?'))
                    dt = str(f.get('date_taken', '') or f.get('file_modified', '') or '?')
                    sc = str(f.get('similar_score', '?'))
                    mt = str(f.get('similar_methods', '?'))
                    parts.append('<tr>')
                    parts.append('<td>' + fn + '</td>')
                    parts.append('<td>' + sz + '</td>')
                    parts.append('<td>' + q + '</td>')
                    parts.append('<td>' + dt + '</td>')
                    parts.append('<td><span class="badge sim">' + sc + '</span></td>')
                    parts.append('<td>' + mt + '</td>')
                    parts.append('</tr>')

            parts.append('</table>')
            parts.append('</div>')

        parts.append('</body></html>')
        return '\n'.join(parts)

