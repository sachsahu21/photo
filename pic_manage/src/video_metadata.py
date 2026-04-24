
# ============================================================
# FILE: src/video_metadata.py        ← NEW MODULE
# ============================================================
"""
Video Metadata Extraction
Extracts duration, resolution, codec, bitrate, frame rate from video files.

Uses OpenCV as primary method (always available if cv2 installed).
Optionally uses pymediainfo for richer metadata (codec name, bitrate).
"""

import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# ── Try OpenCV ──
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    logger.info("OpenCV not available for video metadata")

# ── Try pymediainfo (optional, richer metadata) ──
try:
    from pymediainfo import MediaInfo
    MEDIAINFO_AVAILABLE = True
except ImportError:
    MEDIAINFO_AVAILABLE = False
    logger.info("pymediainfo not available (optional). Install for codec/bitrate info.")


class VideoMetadataExtractor:
    """Extract metadata from video files."""

    def extract(self, filepath) -> Dict:
        """
        Extract video metadata.

        Args:
            filepath: Path to video file (str or Path)

        Returns:
            Dict with keys:
                video_duration_sec  - float seconds
                video_duration_fmt  - formatted string (e.g. '1h 23m 45s')
                video_width         - int pixels
                video_height        - int pixels
                video_fps           - float frames per second
                video_codec         - str codec name
                video_bitrate_kbps  - float kilobits per second
                video_error         - str error message or None
        """
        result = {
            'video_duration_sec': None,
            'video_duration_fmt': '',
            'video_width': None,
            'video_height': None,
            'video_fps': None,
            'video_codec': None,
            'video_bitrate_kbps': None,
            'video_error': None,
        }

        filepath = Path(filepath)
        if not filepath.exists():
            result['video_error'] = 'File not found'
            return result

        # Try pymediainfo first (richer data)
        if MEDIAINFO_AVAILABLE:
            try:
                mi_result = self._extract_mediainfo(filepath)
                if mi_result and mi_result.get('video_duration_sec') is not None:
                    result.update(mi_result)
                    return result
            except Exception as e:
                logger.debug(f"pymediainfo failed for {filepath}: {e}")

        # Fallback to OpenCV
        if CV2_AVAILABLE:
            try:
                cv_result = self._extract_opencv(filepath)
                if cv_result:
                    result.update(cv_result)
                    return result
            except Exception as e:
                logger.debug(f"OpenCV video failed for {filepath}: {e}")

        # Neither worked
        if not CV2_AVAILABLE and not MEDIAINFO_AVAILABLE:
            result['video_error'] = 'No video library available (install opencv-python or pymediainfo)'
        else:
            result['video_error'] = 'Could not extract video metadata'

        return result

    def _extract_opencv(self, filepath) -> Optional[Dict]:
        """
        Extract video metadata using OpenCV.

        Returns duration, resolution, fps, codec (fourcc).
        Does NOT provide bitrate.
        """
        cap = None
        try:
            cap = cv2.VideoCapture(str(filepath))

            if not cap.isOpened():
                logger.debug(f"OpenCV cannot open: {filepath}")
                return None

            # Frame count and FPS
            frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            fps = cap.get(cv2.CAP_PROP_FPS)

            # Duration
            duration_sec = None
            if fps and fps > 0 and frame_count and frame_count > 0:
                duration_sec = round(frame_count / fps, 2)

            # Resolution
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or None
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or None

            # FPS
            fps_val = round(fps, 2) if fps and fps > 0 else None

            # Codec (fourcc)
            fourcc_int = int(cap.get(cv2.CAP_PROP_FOURCC))
            codec = None
            if fourcc_int and fourcc_int > 0:
                try:
                    codec = ''.join([chr((fourcc_int >> 8 * i) & 0xFF) for i in range(4)])
                    codec = codec.strip().strip('\x00')
                    if not codec:
                        codec = None
                except Exception:
                    codec = None

            from .utils import format_duration
            duration_fmt = format_duration(duration_sec) if duration_sec else ''

            return {
                'video_duration_sec': duration_sec,
                'video_duration_fmt': duration_fmt,
                'video_width': width if width and width > 0 else None,
                'video_height': height if height and height > 0 else None,
                'video_fps': fps_val,
                'video_codec': codec,
                'video_bitrate_kbps': None,  # OpenCV doesn't provide bitrate
                'video_error': None,
            }

        except Exception as e:
            logger.debug(f"OpenCV video error for {filepath}: {e}")
            return None

        finally:
            if cap is not None:
                cap.release()

    def _extract_mediainfo(self, filepath) -> Optional[Dict]:
        """
        Extract video metadata using pymediainfo.

        Provides: duration, resolution, fps, codec, bitrate.
        """
        try:
            media_info = MediaInfo.parse(str(filepath))

            video_track = None
            general_track = None

            for track in media_info.tracks:
                if track.track_type == 'Video' and video_track is None:
                    video_track = track
                elif track.track_type == 'General' and general_track is None:
                    general_track = track

            if not video_track and not general_track:
                return None

            # Duration (milliseconds -> seconds)
            duration_sec = None
            duration_ms = None

            if video_track and video_track.duration:
                duration_ms = video_track.duration
            elif general_track and general_track.duration:
                duration_ms = general_track.duration

            if duration_ms is not None:
                try:
                    duration_sec = round(float(duration_ms) / 1000.0, 2)
                except (ValueError, TypeError):
                    pass

            # Resolution
            width = None
            height = None
            if video_track:
                try:
                    width = int(video_track.width) if video_track.width else None
                    height = int(video_track.height) if video_track.height else None
                except (ValueError, TypeError):
                    pass

            # FPS
            fps = None
            if video_track and video_track.frame_rate:
                try:
                    fps = round(float(video_track.frame_rate), 2)
                except (ValueError, TypeError):
                    pass

            # Codec
            codec = None
            if video_track:
                codec = (video_track.codec_id or
                         video_track.format or
                         video_track.commercial_name or
                         None)
                if codec:
                    codec = str(codec).strip()

            # Bitrate (bits/sec -> kbps)
            bitrate_kbps = None
            if video_track and video_track.bit_rate:
                try:
                    bitrate_kbps = round(float(video_track.bit_rate) / 1000.0, 1)
                except (ValueError, TypeError):
                    pass
            elif general_track and general_track.overall_bit_rate:
                try:
                    bitrate_kbps = round(float(general_track.overall_bit_rate) / 1000.0, 1)
                except (ValueError, TypeError):
                    pass

            from .utils import format_duration
            duration_fmt = format_duration(duration_sec) if duration_sec else ''

            return {
                'video_duration_sec': duration_sec,
                'video_duration_fmt': duration_fmt,
                'video_width': width,
                'video_height': height,
                'video_fps': fps,
                'video_codec': codec,
                'video_bitrate_kbps': bitrate_kbps,
                'video_error': None,
            }

        except Exception as e:
            logger.debug(f"pymediainfo error for {filepath}: {e}")
            return None
