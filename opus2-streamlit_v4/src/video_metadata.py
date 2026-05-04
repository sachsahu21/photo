# ============================================================
# FILE: src/video_metadata.py
# ============================================================
"""Video Metadata v2.4"""
import logging
from pathlib import Path
logger = logging.getLogger(__name__)
try:
    import cv2
    CV2_OK = True
except ImportError:
    CV2_OK = False

class VideoMetadataExtractor:
    def extract(self, filepath):
        meta = {}
        if not CV2_OK: return meta
        try:
            cap = cv2.VideoCapture(str(filepath))
            if not cap.isOpened(): return meta
            meta['video_width'] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            meta['video_height'] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            meta['video_fps'] = round(cap.get(cv2.CAP_PROP_FPS), 2)
            frames, fps = cap.get(cv2.CAP_PROP_FRAME_COUNT), meta['video_fps']
            if fps and fps > 0 and frames and frames > 0:
                dur = frames / fps
                meta['video_duration_sec'] = round(dur, 1)
                h, m, s = int(dur // 3600), int((dur % 3600) // 60), int(dur % 60)
                meta['video_duration_fmt'] = (str(h) + 'h ' if h else '') + (str(m) + 'm ' if m else '') + str(s) + 's'
            fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
            if fourcc > 0:
                meta['video_codec'] = ''.join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)]).strip()
            try:
                dur = meta.get('video_duration_sec', 0)
                if dur > 0:
                    meta['video_bitrate_kbps'] = round((Path(filepath).stat().st_size * 8) / (dur * 1000), 0)
            except Exception: pass
            cap.release()
        except Exception: pass
        return meta
