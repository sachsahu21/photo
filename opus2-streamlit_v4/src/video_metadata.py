
# ============================================================
# FILE: src/video_metadata.py
# ============================================================
"""Video Metadata v2.3"""

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
        if not CV2_OK:
            return meta
        try:
            cap = cv2.VideoCapture(str(filepath))
            if not cap.isOpened():
                return meta
            meta['video_width'] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            meta['video_height'] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            meta['video_fps'] = round(cap.get(cv2.CAP_PROP_FPS), 2)
            frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            fps = meta['video_fps']
            if fps and fps > 0 and frames and frames > 0:
                dur = frames / fps
                meta['video_duration_sec'] = round(dur, 1)
                h = int(dur // 3600)
                m = int((dur % 3600) // 60)
                s = int(dur % 60)
                if h > 0:
                    meta['video_duration_fmt'] = str(h) + 'h ' + str(m) + 'm ' + str(s) + 's'
                elif m > 0:
                    meta['video_duration_fmt'] = str(m) + 'm ' + str(s) + 's'
                else:
                    meta['video_duration_fmt'] = str(s) + 's'
            fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
            if fourcc > 0:
                codec = ''.join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)])
                meta['video_codec'] = codec.strip()
            try:
                size = Path(filepath).stat().st_size
                dur = meta.get('video_duration_sec', 0)
                if dur and dur > 0:
                    meta['video_bitrate_kbps'] = round((size * 8) / (dur * 1000), 0)
            except Exception:
                pass
            cap.release()
        except Exception as e:
            logger.debug('Video error %s: %s', filepath, e)
        return meta
