
# ============================================================
# FILE: src/video_metadata.py
# ============================================================
"""Video Metadata Extraction."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import cv2
    CV2_OK = True
except ImportError:
    CV2_OK = False

try:
    from pymediainfo import MediaInfo
    MI_OK = True
except ImportError:
    MI_OK = False


class VideoMetadataExtractor:
    def extract(self, filepath):
        result = {
            'video_duration_sec': None, 'video_duration_fmt': '',
            'video_width': None, 'video_height': None, 'video_fps': None,
            'video_codec': None, 'video_bitrate_kbps': None, 'video_error': None,
        }
        filepath = Path(filepath)
        if not filepath.exists():
            result['video_error'] = 'Not found'
            return result

        if MI_OK:
            try:
                r = self._mediainfo(filepath)
                if r and r.get('video_duration_sec') is not None:
                    result.update(r)
                    return result
            except Exception:
                pass

        if CV2_OK:
            try:
                r = self._opencv(filepath)
                if r:
                    result.update(r)
                    return result
            except Exception:
                pass

        result['video_error'] = 'No video library'
        return result

    def _opencv(self, fp):
        cap = None
        try:
            cap = cv2.VideoCapture(str(fp))
            if not cap.isOpened():
                return None
            fc = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            fps = cap.get(cv2.CAP_PROP_FPS)
            dur = round(fc / fps, 2) if fps and fps > 0 and fc > 0 else None
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or None
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or None
            fv = round(fps, 2) if fps and fps > 0 else None
            fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
            codec = None
            if fourcc > 0:
                try:
                    codec = ''.join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)]).strip('\x00').strip()
                except Exception:
                    pass
            from .utils import format_duration
            return {
                'video_duration_sec': dur, 'video_duration_fmt': format_duration(dur),
                'video_width': w if w and w > 0 else None,
                'video_height': h if h and h > 0 else None,
                'video_fps': fv, 'video_codec': codec or None,
                'video_bitrate_kbps': None, 'video_error': None,
            }
        except Exception:
            return None
        finally:
            if cap:
                cap.release()

    def _mediainfo(self, fp):
        try:
            mi = MediaInfo.parse(str(fp))
            vt = gt = None
            for t in mi.tracks:
                if t.track_type == 'Video' and not vt:
                    vt = t
                elif t.track_type == 'General' and not gt:
                    gt = t
            if not vt and not gt:
                return None
            dur_ms = (vt.duration if vt and vt.duration else
                      gt.duration if gt and gt.duration else None)
            dur = round(float(dur_ms) / 1000, 2) if dur_ms else None
            w = int(vt.width) if vt and vt.width else None
            h = int(vt.height) if vt and vt.height else None
            fps = round(float(vt.frame_rate), 2) if vt and vt.frame_rate else None
            codec = (vt.codec_id or vt.format or None) if vt else None
            br = None
            if vt and vt.bit_rate:
                br = round(float(vt.bit_rate) / 1000, 1)
            elif gt and gt.overall_bit_rate:
                br = round(float(gt.overall_bit_rate) / 1000, 1)
            from .utils import format_duration
            return {
                'video_duration_sec': dur, 'video_duration_fmt': format_duration(dur),
                'video_width': w, 'video_height': h, 'video_fps': fps,
                'video_codec': str(codec).strip() if codec else None,
                'video_bitrate_kbps': br, 'video_error': None,
            }
        except Exception:
            return None

