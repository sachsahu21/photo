"""Video Metadata v2.6 - Multiple fallback methods for duration"""

import os
import logging
import subprocess
import json
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import cv2
    CV2_OK = True
except ImportError:
    CV2_OK = False


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
        if Path(p).exists():
            return p
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
    logger.info('ffprobe not found - video duration may be incomplete for some formats')


class VideoMetadataExtractor:

    def extract(self, filepath):
        filepath = Path(filepath)
        if not filepath.exists():
            return {}

        meta = {}
        errors = []

        cv2_meta = self._extract_cv2(filepath)
        if cv2_meta:
            meta.update(cv2_meta)

        if FFPROBE_CMD:
            ff_meta = self._extract_ffprobe(filepath)
            if ff_meta:
                if ff_meta.get('video_duration_sec') and not meta.get('video_duration_sec'):
                    meta['video_duration_sec'] = ff_meta['video_duration_sec']
                    meta['video_duration_fmt'] = ff_meta.get('video_duration_fmt', '')

                if ff_meta.get('video_duration_sec') and meta.get('video_duration_sec'):
                    ff_dur = ff_meta['video_duration_sec']
                    cv_dur = meta['video_duration_sec']
                    if ff_dur > cv_dur * 1.1:
                        meta['video_duration_sec'] = ff_dur
                        meta['video_duration_fmt'] = ff_meta.get('video_duration_fmt', '')

                if ff_meta.get('video_width') and not meta.get('video_width'):
                    meta['video_width'] = ff_meta['video_width']
                if ff_meta.get('video_height') and not meta.get('video_height'):
                    meta['video_height'] = ff_meta['video_height']
                if ff_meta.get('video_fps') and not meta.get('video_fps'):
                    meta['video_fps'] = ff_meta['video_fps']
                if ff_meta.get('video_codec') and not meta.get('video_codec'):
                    meta['video_codec'] = ff_meta['video_codec']
                if ff_meta.get('video_bitrate_kbps') and not meta.get('video_bitrate_kbps'):
                    meta['video_bitrate_kbps'] = ff_meta['video_bitrate_kbps']

        if meta.get('video_duration_sec') and not meta.get('video_duration_fmt'):
            meta['video_duration_fmt'] = self._format_duration(meta['video_duration_sec'])

        if not meta.get('video_bitrate_kbps') and meta.get('video_duration_sec'):
            try:
                size_bytes = filepath.stat().st_size
                dur = meta['video_duration_sec']
                if dur > 0:
                    meta['video_bitrate_kbps'] = round((size_bytes * 8) / (dur * 1000), 0)
            except Exception:
                pass

        if not meta.get('video_duration_sec') and not FFPROBE_CMD:
            meta['video_duration_fmt'] = 'ffprobe needed'

        logger.debug('Video meta for %s: dur=%s w=%s h=%s fps=%s codec=%s',
                     filepath.name,
                     meta.get('video_duration_sec'),
                     meta.get('video_width'),
                     meta.get('video_height'),
                     meta.get('video_fps'),
                     meta.get('video_codec'))

        return meta

    def _extract_cv2(self, filepath):
        meta = {}
        if not CV2_OK:
            return meta

        cap = None
        try:
            cap = cv2.VideoCapture(str(filepath))
            if not cap.isOpened():
                logger.debug('cv2 cannot open: %s', filepath)
                return meta

            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if w > 0:
                meta['video_width'] = w
            if h > 0:
                meta['video_height'] = h

            fps = cap.get(cv2.CAP_PROP_FPS)
            if fps and fps > 0 and fps < 1000:
                meta['video_fps'] = round(fps, 2)
            else:
                fps = 0

            frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)

            # Method 1: frames / fps
            if fps > 0 and frames and frames > 0:
                dur = frames / fps
                if 0 < dur < 86400 * 30:
                    meta['video_duration_sec'] = round(dur, 1)
                    meta['video_duration_fmt'] = self._format_duration(dur)

            # Method 2: seek to end using AVI ratio
            if not meta.get('video_duration_sec'):
                try:
                    cap.set(cv2.CAP_PROP_POS_AVI_RATIO, 1)
                    end_msec = cap.get(cv2.CAP_PROP_POS_MSEC)
                    if end_msec and end_msec > 0:
                        dur = end_msec / 1000.0
                        if 0 < dur < 86400 * 30:
                            meta['video_duration_sec'] = round(dur, 1)
                            meta['video_duration_fmt'] = self._format_duration(dur)
                    cap.set(cv2.CAP_PROP_POS_AVI_RATIO, 0)
                except Exception:
                    pass

            # Method 3: seek to last frame and read timestamp
            if not meta.get('video_duration_sec'):
                try:
                    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                    if total > 0:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, total - 1)
                        ret = cap.grab()
                        if ret:
                            msec = cap.get(cv2.CAP_PROP_POS_MSEC)
                            if msec and msec > 0:
                                dur = msec / 1000.0
                                if 0 < dur < 86400 * 30:
                                    meta['video_duration_sec'] = round(dur, 1)
                                    meta['video_duration_fmt'] = self._format_duration(dur)
                except Exception:
                    pass

            # Method 4: binary search for last readable frame
            if not meta.get('video_duration_sec') and fps > 0:
                try:
                    dur = self._binary_search_duration(cap, fps)
                    if dur and 0 < dur < 86400 * 30:
                        meta['video_duration_sec'] = round(dur, 1)
                        meta['video_duration_fmt'] = self._format_duration(dur)
                except Exception:
                    pass

            # Codec
            fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
            if fourcc > 0:
                try:
                    codec = ''.join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)])
                    codec = codec.strip()
                    if codec and len(codec) > 0 and codec.isprintable():
                        meta['video_codec'] = codec
                except Exception:
                    pass

        except Exception as e:
            logger.debug('cv2 error %s: %s', filepath, e)
        finally:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass

        return meta

    def _binary_search_duration(self, cap, fps):
        low = 0
        high = 100000
        last_valid_msec = 0

        for attempt in range(20):
            mid = (low + high) // 2
            cap.set(cv2.CAP_PROP_POS_FRAMES, mid)
            ret = cap.grab()
            if ret:
                msec = cap.get(cv2.CAP_PROP_POS_MSEC)
                if msec and msec > 0:
                    last_valid_msec = msec
                    low = mid + 1
                else:
                    high = mid - 1
            else:
                high = mid - 1

            if low >= high:
                break

        if last_valid_msec > 0:
            return last_valid_msec / 1000.0
        return None

    def _extract_ffprobe(self, filepath):
        meta = {}
        if not FFPROBE_CMD:
            return meta

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
                logger.debug('ffprobe failed for %s: %s', filepath, result.stderr[:200] if result.stderr else '')
                return meta

            data = json.loads(result.stdout)

            # Duration from format
            fmt = data.get('format', {})
            dur_str = fmt.get('duration')
            if dur_str:
                try:
                    dur = float(dur_str)
                    if 0 < dur < 86400 * 30:
                        meta['video_duration_sec'] = round(dur, 1)
                        meta['video_duration_fmt'] = self._format_duration(dur)
                except (ValueError, TypeError):
                    pass

            # Bitrate from format
            bit_rate = fmt.get('bit_rate')
            if bit_rate:
                try:
                    meta['video_bitrate_kbps'] = round(float(bit_rate) / 1000, 0)
                except (ValueError, TypeError):
                    pass

            # Stream info
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

                # FPS from r_frame_rate
                fps_str = video_stream.get('r_frame_rate', '')
                if fps_str and '/' in fps_str:
                    try:
                        num, den = fps_str.split('/')
                        num = int(num)
                        den = int(den)
                        if den > 0:
                            fps = num / den
                            if 0 < fps < 1000:
                                meta['video_fps'] = round(fps, 2)
                    except (ValueError, ZeroDivisionError):
                        pass

                # FPS fallback from avg_frame_rate
                if not meta.get('video_fps'):
                    fps_str = video_stream.get('avg_frame_rate', '')
                    if fps_str and '/' in fps_str:
                        try:
                            num, den = fps_str.split('/')
                            num = int(num)
                            den = int(den)
                            if den > 0:
                                fps = num / den
                                if 0 < fps < 1000:
                                    meta['video_fps'] = round(fps, 2)
                        except (ValueError, ZeroDivisionError):
                            pass

                # Duration from stream if not from format
                if not meta.get('video_duration_sec'):
                    sdur = video_stream.get('duration')
                    if sdur:
                        try:
                            dur = float(sdur)
                            if 0 < dur < 86400 * 30:
                                meta['video_duration_sec'] = round(dur, 1)
                                meta['video_duration_fmt'] = self._format_duration(dur)
                        except (ValueError, TypeError):
                            pass

                # Duration from nb_frames / fps
                if not meta.get('video_duration_sec') and meta.get('video_fps'):
                    nb_frames = video_stream.get('nb_frames')
                    if nb_frames:
                        try:
                            frames = int(nb_frames)
                            fps = meta['video_fps']
                            if frames > 0 and fps > 0:
                                dur = frames / fps
                                if 0 < dur < 86400 * 30:
                                    meta['video_duration_sec'] = round(dur, 1)
                                    meta['video_duration_fmt'] = self._format_duration(dur)
                        except (ValueError, TypeError):
                            pass

                # Duration from tags
                if not meta.get('video_duration_sec'):
                    tags = video_stream.get('tags', {})
                    dur_tag = tags.get('DURATION') or tags.get('duration')
                    if dur_tag:
                        dur = self._parse_duration_tag(dur_tag)
                        if dur and 0 < dur < 86400 * 30:
                            meta['video_duration_sec'] = round(dur, 1)
                            meta['video_duration_fmt'] = self._format_duration(dur)

            # Duration from format tags
            if not meta.get('video_duration_sec'):
                fmt_tags = fmt.get('tags', {})
                dur_tag = fmt_tags.get('DURATION') or fmt_tags.get('duration')
                if dur_tag:
                    dur = self._parse_duration_tag(dur_tag)
                    if dur and 0 < dur < 86400 * 30:
                        meta['video_duration_sec'] = round(dur, 1)
                        meta['video_duration_fmt'] = self._format_duration(dur)

        except subprocess.TimeoutExpired:
            logger.debug('ffprobe timeout: %s', filepath)
        except json.JSONDecodeError:
            logger.debug('ffprobe json error: %s', filepath)
        except FileNotFoundError:
            logger.debug('ffprobe not found')
        except Exception as e:
            logger.debug('ffprobe error %s: %s', filepath, e)

        return meta

    def _parse_duration_tag(self, tag_value):
        try:
            tag_value = str(tag_value).strip()
            if ':' in tag_value:
                parts = tag_value.split(':')
                if len(parts) == 3:
                    h = float(parts[0])
                    m = float(parts[1])
                    s_part = parts[2]
                    if '.' in s_part:
                        s = float(s_part)
                    else:
                        s = float(s_part)
                    return h * 3600 + m * 60 + s
                elif len(parts) == 2:
                    m = float(parts[0])
                    s = float(parts[1])
                    return m * 60 + s
            else:
                return float(tag_value)
        except (ValueError, TypeError):
            return None

    def _format_duration(self, seconds):
        if not seconds or seconds <= 0:
            return ''
        try:
            seconds = float(seconds)
        except (ValueError, TypeError):
            return ''
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        parts = []
        if h > 0:
            parts.append(str(h) + 'h')
        if m > 0:
            parts.append(str(m) + 'm')
        parts.append(str(s) + 's')
        return ' '.join(parts)
