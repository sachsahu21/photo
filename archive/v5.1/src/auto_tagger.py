"""Auto Tagger v2.4"""

import logging

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
            arr = np.array(
                PILImage.open(filepath).convert('RGB').resize((64, 64), PILImage.LANCZOS)
            )
            tags = []
            rm, gm, bm = arr[:, :, 0].mean(), arr[:, :, 1].mean(), arr[:, :, 2].mean()
            br = (rm + gm + bm) / 3
            if br > 200:
                tags.append('bright')
            elif br < 60:
                tags.append('dark')
            if rm > gm + 30 and rm > bm + 30:
                tags.append('warm')
            elif bm > rm + 30:
                tags.append('cool')
            if gm > rm + 20 and gm > bm + 20:
                tags.append('green')
            w, h = PILImage.open(filepath).size
            r = w / h if h > 0 else 1
            tags.append('landscape' if r > 1.5 else ('portrait' if r < 0.7 else 'square'))
            return {'auto_tags': ','.join(tags[:self.top_k]), 'primary_tag': tags[0] if tags else ''}
        except Exception:
            return {}

