"""Video Metadata v4.1 - ffprobe + MediaInfo + OpenCV fallbacks."""

import os
import logging
import subprocess
import json
from pathlib import Path

from .utils import format_duration

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


def _find_ffprobe():
    try:
        result = subprocess.run(
            ['ffprobe', '-version'],
            capture_output=True,
            timeout=5
        )
        if result.returncode == 0:
            return True
    except FileNotFoundError:
        pass
    except Exception:
        pass

    common_paths = [
        'C:\\ffmpeg\\bin\\ffprobe.exe',
        'C:\\Program Files\\ffmpeg\\bin\\ffprobe.exe',
        'C:\\Users\\' + os.environ.get('USERNAME', '') + '\\ffmpeg\\bin\\ffprobe.exe',
        '/usr/bin/ffprobe',
        '/usr/local/bin/ffprobe',
    ]
    for p in common_paths:
        try:
            if Path(p).exists():
                return p
        except Exception:
            pass
    return False


FFPROBE_PATH = _find_ffprobe()
if FFPROBE_PATH is True:
    FFPROBE_CMD = 'ffprobe'
elif FFPROBE_PATH and FFPROBE_PATH is not False:
    FFPROBE_CMD = str(FFPROBE_PATH)
else:
    FFPROBE_CMD = None

if FFPROBE_CMD:
    logger.info('ffprobe found: %s', FFPROBE_CMD)
else:
    logger.info('ffprobe not found - will rely on mediainfo/cv2')


class VideoMetadataExtractor:

    def extract(self, filepath):
        filepath = Path(filepath)
        if not filepath.exists():
            return {
                'video_meta_source': 'none',
                'video_meta_error': 'not_found',
            }

        # 1) ffprobe (best coverage when available)
        if FFPROBE_CMD:
            ff = self._extract_ffprobe(filepath)
            if ff and (ff.get('video_duration_sec') is not None or ff.get('video_width') is not None):
                ff['video_meta_source'] = 'ffprobe'
                ff.setdefault('video_meta_error', '')
                return ff

        # 2) mediainfo (works even when cv2 can’t decode)
        if MI_OK:
            mi = self._extract_mediainfo(filepath)
            if mi and (mi.get('video_duration_sec') is not None or mi.get('video_width') is not None):
                mi['video_meta_source'] = 'mediainfo'
                mi.setdefault('video_meta_error', '')
                return mi

        # 3) cv2 last resort
        if CV2_OK:
            cv = self._extract_cv2(filepath)
            if cv and (cv.get('video_duration_sec') is not None or cv.get('video_width') is not None):
                cv['video_meta_source'] = 'cv2'
                cv.setdefault('video_meta_error', '')
                return cv

        err = 'no_backend'
        if not FFPROBE_CMD and not MI_OK and not CV2_OK:
            err = 'no_video_libs'
        elif not FFPROBE_CMD and MI_OK is False and CV2_OK:
            err = 'ffprobe_missing'
        return {
            'video_meta_source': 'none',
            'video_meta_error': err,
            'video_duration_sec': None,
            'video_duration_fmt': '',
            'video_width': None,
            'video_height': None,
            'video_fps': None,
            'video_codec': None,
            'video_bitrate_kbps': None,
        }

    def _extract_mediainfo(self, fp):
        try:
            mi = MediaInfo.parse(str(fp))
            vt = gt = None
            for t in mi.tracks:
                if t.track_type == 'Video' and not vt:
                    vt = t
                elif t.track_type == 'General' and not gt:
                    gt = t
            if not vt and not gt:
                return {}
            dur_ms = (vt.duration if vt and vt.duration else gt.duration if gt and gt.duration else None)
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
            return {
                'video_duration_sec': dur,
                'video_duration_fmt': format_duration(dur) if dur else '',
                'video_width': w,
                'video_height': h,
                'video_fps': fps,
                'video_codec': str(codec).strip() if codec else None,
                'video_bitrate_kbps': br,
            }
        except Exception as e:
            logger.debug('mediainfo error %s: %s', fp, e)
            return {}

    def _extract_cv2(self, fp):
        if not CV2_OK:
            return {}
        cap = None
        try:
            cap = cv2.VideoCapture(str(fp))
            if not cap.isOpened():
                return {}
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or None
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or None
            fps = cap.get(cv2.CAP_PROP_FPS)
            fps_v = round(float(fps), 2) if fps and fps > 0 and fps < 1000 else None
            frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            dur = None
            if fps_v and frames and frames > 0:
                dur = round(float(frames) / float(fps_v), 2)
            fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
            codec = None
            if fourcc > 0:
                try:
                    codec = ''.join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)]).strip()
                except Exception:
                    codec = None
            return {
                'video_duration_sec': dur,
                'video_duration_fmt': format_duration(dur) if dur else '',
                'video_width': w if w and w > 0 else None,
                'video_height': h if h and h > 0 else None,
                'video_fps': fps_v,
                'video_codec': codec or None,
                'video_bitrate_kbps': None,
            }
        except Exception as e:
            logger.debug('cv2 video meta error %s: %s', fp, e)
            return {}
        finally:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass

    def _extract_ffprobe(self, filepath):
        meta = {}
        try:
            cmd = [
                FFPROBE_CMD,
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                str(filepath)
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            if result.returncode != 0:
                return meta
            data = json.loads(result.stdout)

            fmt = data.get('format', {})
            dur_str = fmt.get('duration')
            if dur_str:
                try:
                    dur = float(dur_str)
                    meta['video_duration_sec'] = round(dur, 2)
                    meta['video_duration_fmt'] = format_duration(dur)
                except (ValueError, TypeError):
                    pass

            bit_rate = fmt.get('bit_rate')
            if bit_rate:
                try:
                    meta['video_bitrate_kbps'] = round(float(bit_rate) / 1000, 0)
                except (ValueError, TypeError):
                    pass

            streams = data.get('streams', [])
            video_stream = None
            for stream in streams:
                if stream.get('codec_type') == 'video':
                    video_stream = stream
                    break

            if video_stream:
                w = video_stream.get('width')
                h = video_stream.get('height')
                if w:
                    try:
                        meta['video_width'] = int(w)
                    except (ValueError, TypeError):
                        pass
                if h:
                    try:
                        meta['video_height'] = int(h)
                    except (ValueError, TypeError):
                        pass

                codec = video_stream.get('codec_name')
                if codec:
                    meta['video_codec'] = str(codec)

                fps_str = video_stream.get('avg_frame_rate') or video_stream.get('r_frame_rate') or ''
                if fps_str and '/' in fps_str:
                    try:
                        num, den = fps_str.split('/')
                        num = int(num)
                        den = int(den)
                        if den > 0:
                            fps = num / den
                            if 0 < fps < 1000:
                                meta['video_fps'] = round(fps, 2)
                    except Exception:
                        pass

                if meta.get('video_duration_sec') is None:
                    sdur = video_stream.get('duration')
                    if sdur:
                        try:
                            dur = float(sdur)
                            meta['video_duration_sec'] = round(dur, 2)
                            meta['video_duration_fmt'] = format_duration(dur)
                        except (ValueError, TypeError):
                            pass

        except Exception as e:
            logger.debug('ffprobe error %s: %s', filepath, e)

        return meta

