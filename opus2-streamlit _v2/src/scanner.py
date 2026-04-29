
# ============================================================
# FILE: src/scanner.py  (ENHANCED - parallel, checkpoint, face, tags, clusters, geo)
# ============================================================
"""
Image & Video Scanner - Enhanced with parallel processing, checkpoints,
face detection, auto-tagging, clustering, and geocoding.
"""

import os
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict

from tqdm import tqdm

from .blur_detector import BlurDetector
from .video_metadata import VideoMetadataExtractor
from .utils import (
    calculate_file_hash, safe_string, parse_exif_date,
    parse_gps_coordinates, get_file_modification_date,
    format_duration, get_record_defaults
)

logger = logging.getLogger(__name__)

try:
    from PIL import Image
    from PIL.ExifTags import TAGS
    PIL_OK = True
except ImportError:
    PIL_OK = False


class ImageScanner:
    """Enhanced scanner with all feature integrations."""

    def __init__(self, config):
        self.config = config

        # Core
        blur_cfg = config.get('blur_detection', {})
        self.blur_enabled = blur_cfg.get('enabled', True)
        self.blur_detector = BlurDetector(threshold=blur_cfg.get('threshold', 100))
        self.video_extractor = VideoMetadataExtractor()
        self.hash_algorithm = config.get('duplicates', {}).get('hash_algorithm', 'md5')

        # Extensions
        scan_cfg = config.get('scan', {})
        ext_cfg = scan_cfg.get('extensions', {})
        if isinstance(ext_cfg, dict):
            self.image_exts = self._norm(ext_cfg.get('images', []))
            self.video_exts = self._norm(ext_cfg.get('videos', []))
        else:
            flat = scan_cfg.get('supported_extensions', [])
            self.image_exts = self._norm(flat if isinstance(flat, list) else [
                'jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'webp', 'heic', 'raw', 'cr2', 'nef', 'arw', 'dng'])
            self.video_exts = self._norm(['mp4', 'mov', 'avi', 'mkv', '3gp', 'm4v', 'mpg', 'mpeg', 'wmv', 'flv', 'webm', 'mts'])
        self.all_exts = self.image_exts | self.video_exts
        self.recursive = scan_cfg.get('recursive', True)

        proc_cfg = config.get('processing', {})
        self.show_progress = proc_cfg.get('show_progress', True)
        self.parallel_workers = proc_cfg.get('threads', 0)
        self.checkpoint_enabled = proc_cfg.get('checkpoint_enabled', False)
        self.checkpoint_interval = proc_cfg.get('checkpoint_interval', 100)

        # Feature flags
        self.face_enabled = config.get('face_detection', {}).get('enabled', False)
        self.thumb_enabled = config.get('thumbnails', {}).get('enabled', False)
        self.tag_enabled = config.get('auto_tagging', {}).get('enabled', False)
        self.geo_enabled = config.get('geocoding', {}).get('enabled', False)

        # Lazy-init feature modules
        self._face_detector = None
        self._thumb_generator = None
        self._auto_tagger = None
        self._geocoder = None

    def _norm(self, exts):
        if not exts:
            return set()
        return {f".{e.lower().lstrip('.')}" for e in exts if e}

    def _init_features(self):
        """Lazy-initialize optional feature modules."""
        if self.face_enabled and self._face_detector is None:
            try:
                from .face_detector import FaceDetector
                self._face_detector = FaceDetector(
                    method=self.config.get('face_detection', {}).get('method', 'opencv'))
                logger.info("Face detection enabled")
            except Exception as e:
                logger.warning(f"Face detection init failed: {e}")
                self.face_enabled = False

        if self.thumb_enabled and self._thumb_generator is None:
            try:
                from .thumbnail_generator import ThumbnailGenerator
                thumb_cfg = self.config.get('thumbnails', {})
                self._thumb_generator = ThumbnailGenerator(
                    output_folder=thumb_cfg.get('output_folder', './thumbnails'),
                    size=thumb_cfg.get('size', [150, 100]))
                logger.info("Thumbnail generation enabled")
            except Exception as e:
                logger.warning(f"Thumbnail init failed: {e}")
                self.thumb_enabled = False

        if self.tag_enabled and self._auto_tagger is None:
            try:
                from .auto_tagger import AutoTagger
                tag_cfg = self.config.get('auto_tagging', {})
                self._auto_tagger = AutoTagger(
                    model=tag_cfg.get('model', 'mobilenet'),
                    top_k=tag_cfg.get('top_k', 5),
                    confidence_threshold=tag_cfg.get('confidence_threshold', 0.3))
                logger.info("Auto-tagging enabled")
            except Exception as e:
                logger.warning(f"Auto-tagger init failed: {e}")
                self.tag_enabled = False

        if self.geo_enabled and self._geocoder is None:
            try:
                from .geocoder import Geocoder
                self._geocoder = Geocoder(
                    method=self.config.get('geocoding', {}).get('method', 'offline'))
                logger.info("Geocoding enabled")
            except Exception as e:
                logger.warning(f"Geocoder init failed: {e}")
                self.geo_enabled = False

    def scan(self, folder_path):
        """Scan folder with all enhancements."""
        folder = Path(folder_path).expanduser().resolve()
        if not folder.exists():
            raise FileNotFoundError(f"Not found: {folder}")
        if not folder.is_dir():
            raise NotADirectoryError(f"Not a directory: {folder}")

        logger.info(f"Scanning: {folder}")
        self._init_features()

        files = self._find_files(folder)
        if not files:
            logger.warning("No files found")
            self._debug_folder(folder)
            return []

        logger.info(f"Found {len(files)} files")

        # Checkpoint
        checkpoint = None
        if self.checkpoint_enabled:
            from .checkpoint_manager import CheckpointManager
            checkpoint = CheckpointManager(interval=self.checkpoint_interval)
            if checkpoint.load():
                files = [f for f in files if not checkpoint.is_processed(str(f))]
                logger.info(f"Resuming: {len(files)} files remaining")

        # Process (parallel or sequential)
        if self.parallel_workers != 1 and len(files) > 50:
            records = self._scan_parallel(files, checkpoint)
        else:
            records = self._scan_sequential(files, checkpoint)

        # Post-processing: batch geocoding
        if self.geo_enabled and self._geocoder:
            self._batch_geocode(records)

        if checkpoint:
            checkpoint.save()
            checkpoint.clear()

        logger.info(f"Scan complete: {len(records)} records")
        return records

    def _scan_sequential(self, files, checkpoint):
        records = []
        it = tqdm(files, desc="Scanning", unit="file", disable=not self.show_progress)
        for fp in it:
            try:
                rec = self._extract(fp)
                records.append(rec)
                if checkpoint:
                    checkpoint.mark_processed(str(fp))
            except Exception as e:
                logger.error(f"Error {fp}: {e}")
                records.append(self._error_record(fp, str(e)))
        return records

    def _scan_parallel(self, files, checkpoint):
        from .parallel_processor import ParallelProcessor
        workers = self.parallel_workers if self.parallel_workers > 0 else None
        pp = ParallelProcessor(max_workers=workers or 4, show_progress=self.show_progress)

        def process_one(fp):
            try:
                rec = self._extract(fp)
                if checkpoint:
                    checkpoint.mark_processed(str(fp))
                return rec
            except Exception as e:
                logger.error(f"Error {fp}: {e}")
                return self._error_record(fp, str(e))

        results = pp.process(files, process_one, desc="Scanning (parallel)")
        return [r for r in results if r is not None]

    def _find_files(self, folder):
        files = []
        if self.recursive:
            for dp, _, fns in os.walk(folder):
                for fn in fns:
                    if Path(fn).suffix.lower() in self.all_exts:
                        fp = Path(dp) / fn
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
            gen = folder.rglob('*') if self.recursive else folder.iterdir()
            for f in gen:
                if f.is_file():
                    ext_counts[f.suffix.lower()] = ext_counts.get(f.suffix.lower(), 0) + 1
            if ext_counts:
                logger.info("Extensions found:")
                for ext, cnt in sorted(ext_counts.items(), key=lambda x: -x[1])[:15]:
                    logger.info(f"  {'✓' if ext in self.all_exts else '✗'} {ext}: {cnt}")
        except Exception:
            pass

    def _detect_type(self, ext):
        if ext in self.image_exts:
            return "image"
        elif ext in self.video_exts:
            return "video"
        return "other"

    def _extract(self, filepath):
        """Extract metadata from one file."""
        defaults = get_record_defaults()
        stat = filepath.stat()
        ext = filepath.suffix.lower()
        file_type = self._detect_type(ext)
        mod_date = get_file_modification_date(filepath)

        defaults.update({
            'filename': filepath.name,
            'folder': str(filepath.parent),
            'full_path': str(filepath),
            'extension': ext.lstrip('.').upper(),
            'file_type': file_type,
            'size_mb': round(stat.st_size / (1024 * 1024), 2),
            'file_modified': mod_date.strftime('%Y-%m-%d %H:%M:%S') if mod_date else '',
            'md5_hash': calculate_file_hash(filepath, self.hash_algorithm),
        })

        if file_type == 'image':
            defaults.update(self._extract_image(filepath))
        elif file_type == 'video':
            defaults.update(self._extract_video(filepath))

        # Thumbnail
        if self.thumb_enabled and self._thumb_generator:
            try:
                if file_type == 'image':
                    defaults['thumbnail_path'] = self._thumb_generator.generate(filepath)
                elif file_type == 'video':
                    defaults['thumbnail_path'] = self._thumb_generator.generate_for_video(filepath)
            except Exception as e:
                logger.debug(f"Thumbnail error {filepath}: {e}")

        # Face detection (images only)
        if self.face_enabled and self._face_detector and file_type == 'image':
            try:
                face_result = self._face_detector.detect(filepath)
                defaults.update(face_result)
            except Exception as e:
                logger.debug(f"Face error {filepath}: {e}")

        # Auto-tagging (images only)
        if self.tag_enabled and self._auto_tagger and file_type == 'image':
            try:
                tag_result = self._auto_tagger.tag(filepath)
                defaults.update(tag_result)
            except Exception as e:
                logger.debug(f"Tag error {filepath}: {e}")

        return defaults

    def _extract_image(self, filepath):
        meta = {}
        if not PIL_OK:
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
                        exif = {TAGS.get(tid, str(tid)): v for tid, v in exif_raw.items()}
                        meta['camera_make'] = safe_string(exif.get('Make', ''))
                        meta['camera_model'] = safe_string(exif.get('Model', ''))
                        meta['date_taken'] = parse_exif_date(exif)

                        fl = exif.get('FocalLength')
                        if fl:
                            try:
                                if isinstance(fl, tuple) and len(fl) == 2 and fl[1]:
                                    meta['focal_length'] = f"{fl[0]/fl[1]:.1f}mm"
                                else:
                                    meta['focal_length'] = f"{float(fl):.1f}mm"
                            except Exception:
                                meta['focal_length'] = str(fl)

                        fn = exif.get('FNumber')
                        if fn:
                            try:
                                if isinstance(fn, tuple) and len(fn) == 2 and fn[1]:
                                    meta['aperture'] = f"f/{fn[0]/fn[1]:.1f}"
                                else:
                                    meta['aperture'] = f"f/{float(fn):.1f}"
                            except Exception:
                                meta['aperture'] = str(fn)

                        iso = exif.get('ISOSpeedRatings') or exif.get('PhotographicSensitivity')
                        if iso:
                            meta['iso'] = str(iso)

                        et = exif.get('ExposureTime')
                        if et:
                            try:
                                if isinstance(et, tuple) and len(et) == 2 and et[1]:
                                    v = et[0] / et[1]
                                    meta['exposure_time'] = f"1/{int(1/v)}s" if v < 1 else f"{v:.1f}s"
                                else:
                                    meta['exposure_time'] = f"{float(et)}s"
                            except Exception:
                                meta['exposure_time'] = str(et)

                        gps_lat, gps_lon = parse_gps_coordinates(exif.get('GPSInfo'))
                        if gps_lat is not None:
                            meta['gps_lat'] = round(gps_lat, 6)
                        if gps_lon is not None:
                            meta['gps_lon'] = round(gps_lon, 6)
                except Exception as e:
                    logger.debug(f"EXIF error {filepath}: {e}")

        except Exception as e:
            meta['error'] = str(e)[:120]

        # Blur
        if self.blur_enabled:
            try:
                b, s, r = self.blur_detector.detect_blur(str(filepath))
                meta['is_blurry'] = b
                meta['blur_score'] = s
                meta['quality_rating'] = r
            except Exception:
                pass

        # Quality score
        try:
            qs, qi = self.blur_detector.calculate_quality_score(
                meta.get('blur_score'), meta.get('width'), meta.get('height'), meta.get('has_exif', False))
            meta['quality_score'] = qs
            meta['quality_issues'] = qi
        except Exception:
            pass

        return meta

    def _extract_video(self, filepath):
        meta = {'quality_issues': 'Video file'}
        try:
            vm = self.video_extractor.extract(filepath)
            meta.update(vm)
            if meta.get('video_width'):
                meta['width'] = meta['video_width']
            if meta.get('video_height'):
                meta['height'] = meta['video_height']
        except Exception as e:
            meta['error'] = str(e)[:120]
        return meta

    def _batch_geocode(self, records):
        """Batch geocode all records with GPS data."""
        coords = []
        indices = []
        for i, r in enumerate(records):
            lat, lon = r.get('gps_lat'), r.get('gps_lon')
            if lat is not None and lon is not None:
                coords.append((lat, lon))
                indices.append(i)

        if not coords:
            return

        logger.info(f"Geocoding {len(coords)} locations...")
        try:
            results = self._geocoder.geocode_batch(coords)
            for i, geo in zip(indices, results):
                records[i].update(geo)
            logger.info("Geocoding complete")
        except Exception as e:
            logger.error(f"Batch geocode error: {e}")

    def _error_record(self, filepath, msg):
        rec = get_record_defaults()
        try:
            stat = filepath.stat()
            rec['size_mb'] = round(stat.st_size / (1024 * 1024), 2)
            rec['file_modified'] = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            pass
        rec.update({
            'filename': filepath.name, 'folder': str(filepath.parent),
            'full_path': str(filepath), 'extension': filepath.suffix.lstrip('.').upper(),
            'file_type': self._detect_type(filepath.suffix.lower()),
            'error': msg[:120], 'quality_score': 0,
            'quality_issues': f'Error: {msg[:80]}',
        })
        return rec
