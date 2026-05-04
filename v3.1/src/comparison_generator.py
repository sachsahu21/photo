

# ============================================================
# FILE: src/comparison_generator.py  (#11 - NEW)
# ============================================================
"""
Comparison Generator - HTML side-by-side comparison for duplicate groups.
"""

import logging
import base64
from pathlib import Path
from typing import List, Dict

from .utils import ensure_directory

logger = logging.getLogger(__name__)

try:
    from jinja2 import Template
    JINJA_OK = True
except ImportError:
    JINJA_OK = False

HTML_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>Duplicate Group: {{ group_id }}</title>
<style>
body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
h1 { color: #2E4057; }
.group { display: flex; flex-wrap: wrap; gap: 20px; margin: 20px 0; }
.card { background: white; border-radius: 8px; padding: 15px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        max-width: 350px; flex: 1; min-width: 280px; }
.card.best { border: 3px solid #006400; }
.card.delete { border: 3px solid #8B0000; opacity: 0.7; }
.card img { max-width: 100%; height: auto; border-radius: 4px; }
.meta { font-size: 12px; color: #666; margin-top: 10px; }
.meta table { width: 100%; }
.meta td { padding: 2px 5px; }
.badge { display: inline-block; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; }
.badge-keep { background: #d4edda; color: #155724; }
.badge-delete { background: #f8d7da; color: #721c24; }
</style></head><body>
<h1>Duplicate Group: {{ group_id }}</h1>
<p>{{ members|length }} files in this group</p>
<div class="group">
{% for m in members %}
<div class="card {{ 'best' if m.is_best else 'delete' }}">
  {% if m.thumbnail %}<img src="{{ m.thumbnail }}" alt="{{ m.filename }}">{% endif %}
  <h3>{{ m.filename }}</h3>
  <span class="badge {{ 'badge-keep' if m.is_best else 'badge-delete' }}">
    {{ 'KEEP (Best)' if m.is_best else 'DELETE' }}
  </span>
  <div class="meta"><table>
    <tr><td><b>Size</b></td><td>{{ m.size_mb }} MB</td></tr>
    <tr><td><b>Quality</b></td><td>{{ m.quality_score }}%</td></tr>
    <tr><td><b>Resolution</b></td><td>{{ m.width }}x{{ m.height }}</td></tr>
    <tr><td><b>Date</b></td><td>{{ m.date_taken }}</td></tr>
    <tr><td><b>Path</b></td><td style="word-break:break-all">{{ m.full_path }}</td></tr>
  </table></div>
</div>
{% endfor %}
</div></body></html>"""


class ComparisonGenerator:
    """Generate HTML comparison pages for duplicate groups."""

    def __init__(self, output_folder='./comparisons'):
        self.output_folder = Path(output_folder)
        ensure_directory(self.output_folder)

    def generate(self, records):
        """
        Generate comparison HTML for all duplicate groups.

        Returns:
            List of generated file paths
        """
        # Group records by duplicate_group
        groups = {}
        for r in records:
            grp = r.get('duplicate_group', '')
            if grp and str(r.get('is_duplicate', '')).upper() == 'YES':
                if grp not in groups:
                    groups[grp] = []
                groups[grp].append(r)

        if not groups:
            logger.info("No duplicate groups for comparison")
            return []

        generated = []

        for group_id, members in groups.items():
            try:
                path = self._generate_group(group_id, members)
                if path:
                    generated.append(path)
            except Exception as e:
                logger.error(f"Comparison error for {group_id}: {e}")

        logger.info(f"Generated {len(generated)} comparison pages")
        return generated

    def _generate_group(self, group_id, members):
        """Generate HTML for one group."""
        template_data = []

        for m in members:
            thumb = self._get_thumbnail_data(m)
            template_data.append({
                'filename': m.get('filename', ''),
                'is_best': str(m.get('is_best_in_group', '')).lower() == 'yes',
                'thumbnail': thumb,
                'size_mb': m.get('size_mb', 0),
                'quality_score': m.get('quality_score', 'N/A'),
                'width': m.get('width', '?'),
                'height': m.get('height', '?'),
                'date_taken': str(m.get('date_taken', 'Unknown')),
                'full_path': m.get('full_path', ''),
            })

        html_path = self.output_folder / f"{group_id}.html"

        if JINJA_OK:
            tmpl = Template(HTML_TEMPLATE)
            html = tmpl.render(group_id=group_id, members=template_data)
        else:
            # Simple fallback without Jinja2
            html = self._simple_html(group_id, template_data)

        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html)

        return str(html_path)

    def _get_thumbnail_data(self, record):
        """Get base64 thumbnail or thumbnail path."""
        thumb_path = record.get('thumbnail_path')
        if thumb_path and Path(thumb_path).exists():
            try:
                with open(thumb_path, 'rb') as f:
                    data = base64.b64encode(f.read()).decode()
                return f"data:image/jpeg;base64,{data}"
            except Exception:
                pass

        # Try to generate inline from original
        try:
            from PIL import Image
            import io
            fp = record.get('full_path', '')
            if fp and Path(fp).exists():
                with Image.open(fp) as img:
                    img = img.convert('RGB')
                    img.thumbnail((300, 200), Image.LANCZOS)
                    buf = io.BytesIO()
                    img.save(buf, 'JPEG', quality=60)
                    data = base64.b64encode(buf.getvalue()).decode()
                    return f"data:image/jpeg;base64,{data}"
        except Exception:
            pass

        return None

    def _simple_html(self, group_id, members):
        """Fallback HTML without Jinja2."""
        cards = ""
        for m in members:
            cls = "best" if m['is_best'] else "delete"
            badge = "KEEP (Best)" if m['is_best'] else "DELETE"
            img_tag = f'<img src="{m["thumbnail"]}">' if m['thumbnail'] else ''
            cards += f"""
            <div class="card {cls}">
              {img_tag}
              <h3>{m['filename']}</h3>
              <span class="badge {'badge-keep' if m['is_best'] else 'badge-delete'}">{badge}</span>
              <div class="meta"><table>
                <tr><td><b>Size</b></td><td>{m['size_mb']} MB</td></tr>
                <tr><td><b>Quality</b></td><td>{m['quality_score']}%</td></tr>
                <tr><td><b>Resolution</b></td><td>{m['width']}x{m['height']}</td></tr>
              </table></div>
            </div>"""

        return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>{group_id}</title>
<style>
body {{ font-family: Arial; margin: 20px; }}
.group {{ display: flex; flex-wrap: wrap; gap: 20px; }}
.card {{ background: white; border-radius: 8px; padding: 15px; max-width: 350px;
         box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
.card.best {{ border: 3px solid green; }}
.card.delete {{ border: 3px solid red; opacity: 0.7; }}
.card img {{ max-width: 100%; }}
.badge {{ padding: 3px 8px; border-radius: 4px; font-size: 11px; }}
.badge-keep {{ background: #d4edda; }}
.badge-delete {{ background: #f8d7da; }}
</style></head><body>
<h1>{group_id}</h1>
<div class="group">{cards}</div>
</body></html>"""

