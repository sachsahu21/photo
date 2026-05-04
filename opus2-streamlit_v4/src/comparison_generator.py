# ============================================================
# FILE: src/comparison_generator.py
# ============================================================
"""Comparison v2.4"""
import logging; from pathlib import Path; from collections import defaultdict; from datetime import datetime; logger=logging.getLogger(__name__)
try: from jinja2 import Template; JINJA_OK=True
except ImportError: JINJA_OK=False
HTML_TPL='<!DOCTYPE html><html><head><title>{{ title }}</title><style>body{font-family:Arial;margin:20px}h1{color:#2E4057}.group{background:white;padding:15px;margin:10px 0;border-radius:8px;box-shadow:0 2px 4px rgba(0,0,0,0.1)}table{border-collapse:collapse;width:100%}th{background:#2E4057;color:white;padding:8px}td{padding:6px 8px;border-bottom:1px solid #ddd}</style></head><body><h1>{{ title }}</h1><p>{{ total }} files</p>{% for g in groups %}<div class="group"><h3>{{ g.label }} : {{ g.count }} files</h3><table><tr><th>File</th><th>Size</th><th>Quality</th></tr>{% for f in g.files %}<tr><td>{{ f.fn }}</td><td>{{ f.sz }} MB</td><td>{{ f.q }}</td></tr>{% endfor %}</table></div>{% endfor %}</body></html>'
class ComparisonGenerator:
    def __init__(self, output_folder='./comparisons'):
        self.output_folder=Path(output_folder); self.output_folder.mkdir(parents=True,exist_ok=True)
    def generate(self, records):
        pages=[]
        for flag,gkey,fname in [('is_duplicate','duplicate_group','duplicates.html'),('is_similar','similar_group','similar.html')]:
            groups=defaultdict(list)
            for r in records:
                gv=r.get(gkey,'')
                if gv and gv.strip() and str(r.get(flag,'')).upper()=='YES': groups[gv].append(r)
            if not groups: continue
            gl=[{'label':lb,'count':len(fs),'files':[{'fn':f.get('filename','?'),'sz':f.get('size_mb',0),'q':str(f.get('quality_score','?'))} for f in fs]} for lb,fs in sorted(groups.items())]
            total=sum(g['count'] for g in gl)
            try:
                html=Template(HTML_TPL).render(title=fname.replace('.html','').title(),total=total,groups=gl) if JINJA_OK else '<html><body><h1>'+fname+'</h1></body></html>'
                out=self.output_folder/fname
                with open(out,'w',encoding='utf-8') as f: f.write(html)
                pages.append(str(out))
            except: pass
        return pages
