
# ============================================================
# FILE: src/scanner.py
# ============================================================
"""
Image & Video Scanner - Extracts metadata for images and videos
"""

import os
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Set

from tqdm import tqdm

from .blur_detector import BlurDetector
from .video_metadata import VideoMetadataExtractor
from .utils import (
    calculate_file_hash, safe_string, parse_exif_date,
    parse_gps_coordinates, get_file_modification_date, format_duration
)

logger = logging.getLogger(__name__)

try:
    from PIL import Image
    from PIL.ExifTags import TAGS
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logger.warning("Pillow not available - image metadata limited")


class ImageScanner:
    """Scan folders for images/videos and extract metadata."""

    def __init__(self, config):
        self.config = config

        # Blur detector
        blur_cfg = config.get('blur_detection', {})
        self.blur_enabled = blur_cfg.get('enabled', True)
        self.blur_detector = BlurDetector(threshold=blur_cfg.get('threshold', 100))

        # Video metadata extractor
        self.video_extractor = VideoMetadataExtractor()

        # Hash
        dup_cfg = config.get('duplicates', {})
        self.hash_algorithm = dup_cfg.get('hash_algorithm', 'md5')

        # Extensions
        scan_cfg = config.get('scan', {})
        ext_cfg = scan_cfg.get('extensions', {})

        if isinstance(ext_cfg, dict):
            self.image_exts = self._norm_exts(ext_cfg.get('images', []))
            self.video_exts = self._norm_exts(ext_cfg.get('videos', []))
        else:
            flat_list = scan_cfg.get('supported_extensions', [])
            if isinstance(flat_list, list):
                self.image_exts = self._norm_exts(flat_list)
            else:
                self.image_exts = self._norm_exts([
                    'jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'tif',
                    'webp', 'heic', 'heif', 'raw', 'cr2', 'nef', 'arw', 'dng'
                ])
            self.video_exts = self._norm_exts([
                'mp4', 'mov', 'avi', 'mkv', '3gp', 'm4v', 'mpg', 'mpeg',
                'wmv', 'flv', 'webm', 'mts'
            ])

        self.all_exts = self.image_exts | self.video_exts
        self.recursive = scan_cfg.get('recursive', True)

        proc_cfg = config.get('processing', {})
        self.show_progress = proc_cfg.get('show_progress', True)

    def _norm_exts(self, exts):
        if not exts:
            return set()
        return {f".{e.lower().lstrip('.')}" for e in exts if e}

    def scan(self, folder_path):
        """Scan folder for images and videos, extract metadata."""
        folder = Path(folder_path).expanduser().resolve()

        if not folder.exists():
            raise FileNotFoundError(f"Scan folder not found: {folder}")
        if not folder.is_dir():
            raise NotADirectoryError(f"Not a directory: {folder}")

        logger.info(f"Scanning: {folder}")
        logger.info(f"Image exts: {sorted(self.image_exts)}")
        logger.info(f"Video exts: {sorted(self.video_exts)}")

        files = self._find_files(folder)

        if not files:
            logger.warning("No supported files found")
            self._debug_folder(folder)
            return []

        logger.info(f"Found {len(files)} files")

        records = []
        errors = 0

        it = tqdm(files, desc="Extracting metadata", unit="file",
                  disable=not self.show_progress)

        for fp in it:
            try:
                rec = self._extract(fp)
                records.append(rec)
            except Exception as e:
                errors += 1
                logger.error(f"Error processing {fp}: {e}")
                records.append(self._error_record(fp, str(e)))

        logger.info(f"Scan done: {len(records)} processed, {errors} errors")
        return records

    def _find_files(self, folder):
        files = []
        if self.recursive:
            for dirpath, _, filenames in os.walk(folder):
                for fn in filenames:
                    if Path(fn).suffix.lower() in self.all_exts:
                        fp = Path(dirpath) / fn
                        if fp.is_file():
                            files.append(fp)
        else:
            for item in folder.iterdir():
                if item.is_file() and item.suffix.lower() in self.all_exts:
                    files.append(item)
        return sorted(files)

    def _debug_folder(self, folder):
        try:
            ext_counts = {}
            for f in folder.rglob('*') if self.recursive else folder.iterdir():
                if f.is_file():
                    ext = f.suffix.lower()
                    ext_counts[ext] = ext_counts.get(ext, 0) + 1

            if ext_counts:
                logger.info("Extensions found in folder:")
                for ext, cnt in sorted(ext_counts.items(), key=lambda x: -x[1])[:15]:
                    marker = "✓" if ext in self.all_exts else "✗"
                    logger.info(f"  {marker} {ext}: {cnt}")
            else:
                logger.info("Folder appears empty")
        except Exception as e:
            logger.debug(f"Debug scan error: {e}")

    def _detect_type(self, ext):
        if ext in self.image_exts:
            return "image"
        elif ext in self.video_exts:
            return "video"
        return "other"

    def _extract(self, filepath):
        """Extract metadata from a single file."""
        stat = filepath.stat()
        ext = filepath.suffix.lower()
        file_type = self._detect_type(ext)

        file_hash = calculate_file_hash(filepath, self.hash_algorithm)
        mod_date = get_file_modification_date(filepath)

        record = {
            'filename': filepath.name,
            'folder': str(filepath.parent),
            'full_path': str(filepath),
            'extension': ext.lstrip('.').upper(),
            'file_type': file_type,
            'size_mb': round(stat.st_size / (1024 * 1024), 2),
            'file_modified': mod_date.strftime('%Y-%m-%d %H:%M:%S') if mod_date else '',
            'md5_hash': file_hash,
            'delete_flag': 'No',
            'error': None,
        }

        if file_type == 'image':
            record.update(self._extract_image(filepath))
        elif file_type == 'video':
            record.update(self._extract_video(filepath))
        else:
            record.update({
                'date_taken': None,
                'quality_score': None,
                'quality_issues': 'Unknown file type',
            })

        return record

    def _extract_image(self, filepath):
        """Extract image-specific metadata."""
        meta = {
            'width': None,
            'height': None,
            'mode': None,
            'dpi': None,
            'date_taken': None,
            'camera_make': None,
            'camera_model': None,
            'focal_length': None,
            'aperture': None,
            'iso': None,
            'exposure_time': None,
            'gps_lat': None,
            'gps_lon': None,
            'has_exif': False,
            'is_blurry': None,
            'blur_score': None,
            'quality_rating': 'Unknown',
            'quality_score': None,
            'quality_issues': '',
            # Video fields set to None for images
            'video_duration_sec': None,
            'video_duration_fmt': None,
            'video_width': None,
            'video_height': None,
            'video_fps': None,
            'video_codec': None,
            'video_bitrate_kbps': None,
        }

        if not PIL_AVAILABLE:
            meta['error'] = 'Pillow not installed'
            return meta

        try:
            with Image.open(filepath) as img:
                meta['width'] = img.width
                meta['height'] = img.height
                meta['mode'] = img.mode

                try:
                    dpi = img.info.get('dpi')
                    if dpi and isinstance(dpi, tuple) and len(dpi) >= 2:
                        meta['dpi'] = f"{int(dpi[0])}x{int(dpi[1])}"
                except Exception:
                    pass

                try:
                    exif_raw = img.getexif() if hasattr(img, 'getexif') else None
                    if exif_raw and len(exif_raw) > 0:
                        meta['has_exif'] = True
                        exif = {}
                        for tag_id, val in exif_raw.items():
                            tag_name = TAGS.get(tag_id, str(tag_id))
                            exif[tag_name] = val

                        meta['camera_make'] = safe_string(exif.get('Make', ''))
                        meta['camera_model'] = safe_string(exif.get('Model', ''))
                        meta['date_taken'] = parse_exif_date(exif)

                        fl = exif.get('FocalLength')
                        if fl:
                            try:
                                if isinstance(fl, tuple) and len(fl) == 2 and fl[1]:
                                    meta['focal_length'] = f"{fl[0]/fl[1]:.1f}mm"
                                elif isinstance(fl, (int, float)):
                                    meta['focal_length'] = f"{float(fl):.1f}mm"
                                else:
                                    meta['focal_length'] = str(fl)
                            except Exception:
                                meta['focal_length'] = str(fl)

                        fn = exif.get('FNumber')
                        if fn:
                            try:
                                if isinstance(fn, tuple) and len(fn) == 2 and fn[1]:
                                    meta['aperture'] = f"f/{fn[0]/fn[1]:.1f}"
                                elif isinstance(fn, (int, float)):
                                    meta['aperture'] = f"f/{float(fn):.1f}"
                                else:
                                    meta['aperture'] = str(fn)
                            except Exception:
                                meta['aperture'] = str(fn)

                        iso = exif.get('ISOSpeedRatings') or exif.get('PhotographicSensitivity')
                        if iso:
                            meta['iso'] = str(iso)

                        et = exif.get('ExposureTime')
                        if et:
                            try:
                                if isinstance(et, tuple) and len(et) == 2 and et[1]:
                                    val = et[0] / et[1]
                                    meta['exposure_time'] = f"1/{int(1/val)}s" if val < 1 else f"{val:.1f}s"
                                elif isinstance(et, (int, float)):
                                    meta['exposure_time'] = f"{float(et)}s"
                                else:
                                    meta['exposure_time'] = str(et)
                            except Exception:
                                meta['exposure_time'] = str(et)

                        gps_lat, gps_lon = parse_gps_coordinates(exif.get('GPSInfo'))
                        if gps_lat is not None:
                            meta['gps_lat'] = round(gps_lat, 6)
                        if gps_lon is not None:
                            meta['gps_lon'] = round(gps_lon, 6)

                except Exception as e:
                    logger.debug(f"EXIF error for {filepath}: {e}")

        except Exception as e:
            meta['error'] = str(e)[:120]
            logger.warning(f"PIL error for {filepath}: {e}")

        # Blur detection
        if self.blur_enabled:
            try:
                is_blurry, blur_score, quality_rating = self.blur_detector.detect_blur(str(filepath))
                meta['is_blurry'] = is_blurry
                meta['blur_score'] = blur_score
                meta['quality_rating'] = quality_rating
            except Exception as e:
                logger.debug(f"Blur error for {filepath}: {e}")

        # Quality score
        try:
            q_score, q_issues = self.blur_detector.calculate_quality_score(
                blur_score=meta.get('blur_score'),
                width=meta.get('width'),
                height=meta.get('height'),
                has_exif=meta.get('has_exif', False),
            )
            meta['quality_score'] = q_score
            meta['quality_issues'] = q_issues
        except Exception as e:
            logger.debug(f"Quality score error for {filepath}: {e}")

        return meta

    def _extract_video(self, filepath):
        """Extract video-specific metadata."""
        meta = {
            # Image-only fields set to None
            'width': None,
            'height': None,
            'mode': None,
            'dpi': None,
            'date_taken': None,
            'camera_make': None,
            'camera_model': None,
            'focal_length': None,
            'aperture': None,
            'iso': None,
            'exposure_time': None,
            'gps_lat': None,
            'gps_lon': None,
            'has_exif': False,
            'is_blurry': None,
            'blur_score': None,
            'quality_rating': 'N/A',
            'quality_score': None,
            'quality_issues': 'Video file',
            # Video fields
            'video_duration_sec': None,
            'video_duration_fmt': '',
            'video_width': None,
            'video_height': None,
            'video_fps': None,
            'video_codec': None,
            'video_bitrate_kbps': None,
        }

        try:
            video_meta = self.video_extractor.extract(filepath)
            meta.update(video_meta)

            # Use video resolution as width/height for consistency
            if meta.get('video_width'):
                meta['width'] = meta['video_width']
            if meta.get('video_height'):
                meta['height'] = meta['video_height']

        except Exception as e:
            logger.warning(f"Video metadata error for {filepath}: {e}")
            meta['error'] = str(e)[:120]

        return meta

    def _error_record(self, filepath, error_msg):
        """Create minimal record for failed files."""
        try:
            stat = filepath.stat()
            size_mb = round(stat.st_size / (1024 * 1024), 2)
            mod = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            size_mb = 0
            mod = ''

        return {
            'filename': filepath.name,
            'folder': str(filepath.parent),
            'full_path': str(filepath),
            'extension': filepath.suffix.lstrip('.').upper(),
            'file_type': self._detect_type(filepath.suffix.lower()),
            'size_mb': size_mb,
            'file_modified': mod,
            'md5_hash': '',
            'delete_flag': 'No',
            'date_taken': None,
            'quality_score': 0,
            'quality_issues': f'Error: {error_msg[:80]}',
            'error': error_msg[:120],
            'video_duration_sec': None,
            'video_duration_fmt': '',
            'video_width': None,
            'video_height': None,
            'video_fps': None,
            'video_codec': None,
            'video_bitrate_kbps': None,
        }
