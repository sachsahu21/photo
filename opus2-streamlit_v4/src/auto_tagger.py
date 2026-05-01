# ============================================================
# FILE: src/auto_tagger.py
# ============================================================
"""Auto Tagger v2.3"""
import logging
from pathlib import Path
logger = logging.getLogger(__name__)
try:
    from PIL import Image as PILImage
    import numpy as np
    TAG_OK = True
except ImportError:
    TAG_OK = False

class AutoTagger:
    def __init__(self, model='mobilenet', top_k=5, confidence_threshold=0.3):
        self.top_k = top_k

    def tag(self, filepath):
        if not TAG_OK:
            return {}
        try:
            img = PILImage.open(filepath).convert('RGB').resize((64, 64), PILImage.LANCZOS)
            arr = np.array(img)
            tags = []
            rm, gm, bm = arr[:, :, 0].mean(), arr[:, :, 1].mean(), arr[:, :, 2].mean()
            br = (rm + gm + bm) / 3.0
            if br > 200:
                tags.append('bright')
            elif br < 60:
                tags.append('dark')
            if rm > gm + 30 and rm > bm + 30:
                tags.append('warm-tones')
            elif bm > rm + 30 and bm > gm + 30:
                tags.append('cool-tones')
            if gm > rm + 20 and gm > bm + 20:
                tags.append('nature-green')
            if arr.std() > 70:
                tags.append('high-contrast')
            elif arr.std() < 30:
                tags.append('low-contrast')
            w, h = PILImage.open(filepath).size
            r = w / h if h > 0 else 1
            tags.append('landscape' if r > 1.5 else ('portrait' if r < 0.7 else 'square'))
            tags = tags[:self.top_k]
            return {'auto_tags': ', '.join(tags), 'primary_tag': tags[0] if tags else ''}
        except Exception:
            return {}
