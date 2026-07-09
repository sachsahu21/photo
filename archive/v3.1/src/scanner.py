# ============================================================
# FILE: src/scanner.py
# ============================================================
"""
Image & Video Scanner v2.1
- Single image load (pass to blur, face, thumb, tagger)
- fast_mode support
- skip_video_hash support
- metadata_status and date_source columns
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
    format_duration, get_record_defaults,
    determine_metadata_status, determine_date_source
)

logger = logging.getLogger(__name__)

try:
    from PIL import Image as PILImage
    from PIL.ExifTags import TAGS
    PIL_OK = True
except ImportError:
    PIL_OK = False

try:
    import cv2
    CV2_OK = True
except ImportError:
    CV2_OK = False


class ImageScanner:

    def __init__(self, config):
        self.config = config

        # Core - Blur
        blur_cfg = config.get('blur_detection', {})
        self.blur_enabled = blur_cfg.get('enabled', True)
        self.blur_detector = BlurDetector(threshold=blur_cfg.get('threshold', 100))

        # Core - Video
        self.video_extractor = VideoMetadataExtractor()

        # Core - Duplicates
        dup_cfg = config.get('duplicates', {})
        self.hash_algorithm = dup_cfg.get('hash_algorithm', 'md5')
        self.duplicates_enabled = dup_cfg.get('enabled', True)

        # Extensions
        scan_cfg = config.get('scan', {})
        ext_cfg = scan_cfg.get('extensions', {})
        if isinstance(ext_cfg, dict):
            self.image_exts = self._norm(ext_cfg.get('images', []))
            self.video_exts = self._norm(ext_cfg.get('videos', []))
        else:
            self.image_exts = self._norm([
                'jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'webp',
                'heic', 'raw', 'cr2', 'nef', 'arw', 'dng'])
            self.video_exts = self._norm([
                'mp4', 'mov', 'avi', 'mkv', '3gp', 'm4v', 'mpg',
                'mpeg', 'wmv', 'flv', 'webm', 'mts'])
        self.all_exts = self.image_exts | self.video_exts
        self.recursive = scan_cfg.get('recursive', True)

        # Processing
        proc_cfg = config.get('processing', {})
        self.show_progress = proc_cfg.get('show_progress', True)
        self.parallel_workers = proc_cfg.get('threads', 0)
        self.checkpoint_enabled = proc_cfg.get('checkpoint_enabled', False)
        self.checkpoint_interval = proc_cfg.get('checkpoint_interval', 100)
        self.fast_mode = proc_cfg.get('fast_mode', False)
        self.skip_video_hash = proc_cfg.get('skip_video_hash', True)

        # Feature flags (disabled in fast_mode)
        if self.fast_mode:
            self.face_enabled = False
            self.thumb_enabled = False
            self.tag_enabled = False
            self.blur_enabled = False
            self.geo_enabled = config.get('geocoding', {}).get('enabled', False)
            logger.info("Fast mode ON: blur, face, tags, thumbnails disabled")
        else:
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
        if self.fast_mode:
            logger.info("FAST MODE: blur, face, tags, thumbnails disabled")

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
                before = len(files)
                files = [f for f in files if not checkpoint.is_processed(str(f))]
                logger.info(f"Resuming: {len(files)} remaining (skipped {before - len(files)})")

        # Process (parallel or sequential)
        if self.parallel_workers != 1 and len(files) > 50 and not self.fast_mode:
            records = self._scan_parallel(files, checkpoint)
        else:
            records = self._scan_sequential(files, checkpoint)

        # Batch geocoding
        if self.geo_enabled and self._geocoder:
            self._batch_geocode(records)

        # Set metadata_status and date_source for all records
        for rec in records:
            rec['metadata_status'] = determine_metadata_status(rec)
            rec['date_source'] = determine_date_source(rec)

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
        workers = self.parallel_workers if self.parallel_workers > 0 else 4
        pp = ParallelProcessor(max_workers=workers, show_progress=self.show_progress)

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
                    logger.info(f"  {'Y' if ext in self.all_exts else 'N'} {ext}: {cnt}")
        except Exception:
            pass

    def _detect_type(self, ext):
        if ext in self.image_exts:
            return "image"
        elif ext in self.video_exts:
            return "video"
        return "other"

    def _extract(self, filepath):
        """Extract metadata - single file load optimization."""
        defaults = get_record_defaults()
        stat = filepath.stat()
        ext = filepath.suffix.lower()
        file_type = self._detect_type(ext)
        mod_date = get_file_modification_date(filepath)

        # Hash - skip for videos if configured, skip entirely if duplicates disabled
        file_hash = ''
        if file_type == 'video' and self.skip_video_hash:
            file_hash = ''
        elif self.duplicates_enabled:
            file_hash = calculate_file_hash(filepath, self.hash_algorithm)

        defaults.update({
            'filename': filepath.name,
            'folder': str(filepath.parent),
            'full_path': str(filepath),
            'extension': ext.lstrip('.').upper(),
            'file_type': file_type,
            'size_mb': round(stat.st_size / (1024 * 1024), 2),
            'file_modified': mod_date.strftime('%Y-%m-%d %H:%M:%S') if mod_date else '',
            'md5_hash': file_hash,
        })

        if file_type == 'image':
            # ── SINGLE LOAD OPTIMIZATION ──
            # Load PIL and CV2 images ONCE, pass to all processors
            pil_img = None
            cv2_img = None

            # Load PIL image (for metadata, thumbnail, tagging)
            if PIL_OK:
                try:
                    pil_img = PILImage.open(filepath)
                except Exception as e:
                    defaults['error'] = str(e)[:120]

            # Load CV2 image ONCE (for blur + face detection)
            if CV2_OK and (self.blur_enabled or self.face_enabled):
                try:
                    cv2_img = cv2.imread(str(filepath))
                except Exception:
                    pass

            # Extract image metadata using loaded PIL image
            if pil_img:
                defaults.update(self._extract_image_from_pil(filepath, pil_img))

            # Blur detection using loaded CV2 image (no re-read)
            if self.blur_enabled and cv2_img is not None:
                try:
                    gray = cv2.cvtColor(cv2_img, cv2.COLOR_BGR2GRAY)
                    score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
                    is_blurry, blur_score, quality_rating = self.blur_detector._classify(score)
                    defaults['is_blurry'] = is_blurry
                    defaults['blur_score'] = blur_score
                    defaults['quality_rating'] = quality_rating
                except Exception as e:
                    logger.debug(f"Blur error {filepath}: {e}")

            # Quality score
            try:
                qs, qi = self.blur_detector.calculate_quality_score(
                    defaults.get('blur_score'),
                    defaults.get('width'),
                    defaults.get('height'),
                    defaults.get('has_exif', False))
                defaults['quality_score'] = qs
                defaults['quality_issues'] = qi
            except Exception:
                pass

            # Face detection using loaded CV2 image (no re-read)
            if self.face_enabled and self._face_detector and cv2_img is not None:
                try:
                    gray_face = cv2.cvtColor(cv2_img, cv2.COLOR_BGR2GRAY)
                    h_img, w_img = gray_face.shape
                    scale = 1.0
                    if max(h_img, w_img) > 1200:
                        scale = 1200.0 / max(h_img, w_img)
                        gray_face = cv2.resize(gray_face, None, fx=scale, fy=scale)
                    if self._face_detector._cascade is not None:
                        faces = self._face_detector._cascade.detectMultiScale(
                            gray_face, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
                        count = len(faces) if faces is not None else 0
                        defaults['face_count'] = count
                        if count == 0:
                            defaults['face_category'] = 'No People'
                        elif count == 1:
                            defaults['face_category'] = 'Portrait'
                        elif count <= 4:
                            defaults['face_category'] = 'Small Group'
                        else:
                            defaults['face_category'] = 'Large Group'
                except Exception as e:
                    logger.debug(f"Face error {filepath}: {e}")

            # Thumbnail using loaded PIL image (no re-read)
            if self.thumb_enabled and self._thumb_generator and pil_img:
                try:
                    thumb_name = f"thumb-{filepath.stem}-{stat.st_size}.jpg"
                    thumb_path = Path(self._thumb_generator.output_folder) / thumb_name
                    if not thumb_path.exists():
                        img_copy = pil_img.copy().convert('RGB')
                        img_copy.thumbnail(self._thumb_generator.size, PILImage.LANCZOS)
                        img_copy.save(thumb_path, 'JPEG', quality=75)
                    defaults['thumbnail_path'] = str(thumb_path)
                except Exception as e:
                    logger.debug(f"Thumb error {filepath}: {e}")

            # Auto-tagging using loaded PIL image
            if self.tag_enabled and self._auto_tagger and pil_img:
                try:
                    tag_result = self._auto_tagger.tag(filepath)
                    defaults.update(tag_result)
                except Exception as e:
                    logger.debug(f"Tag error {filepath}: {e}")

            # Close PIL image to free memory
            if pil_img:
                try:
                    pil_img.close()
                except Exception:
                    pass

        elif file_type == 'video':
            defaults.update(self._extract_video(filepath))

            # Video thumbnail
            if self.thumb_enabled and self._thumb_generator:
                try:
                    defaults['thumbnail_path'] = self._thumb_generator.generate_for_video(filepath)
                except Exception as e:
                    logger.debug(f"Video thumb error {filepath}: {e}")

        return defaults

    def _extract_image_from_pil(self, filepath, pil_img):
        """Extract image metadata from already-loaded PIL image."""
        meta = {}
        try:
            meta['width'] = pil_img.width
            meta['height'] = pil_img.height
            meta['mode'] = pil_img.mode

            # DPI
            try:
                dpi = pil_img.info.get('dpi')
                if dpi and isinstance(dpi, tuple) and len(dpi) >= 2:
                    meta['dpi'] = f"{int(dpi[0])}x{int(dpi[1])}"
            except Exception:
                pass

            # EXIF
            try:
                exif_raw = pil_img.getexif() if hasattr(pil_img, 'getexif') else None
                if exif_raw and len(exif_raw) > 0:
                    meta['has_exif'] = True
                    exif = {TAGS.get(tid, str(tid)): v for tid, v in exif_raw.items()}

                    meta['camera_make'] = safe_string(exif.get('Make', ''))
                    meta['camera_model'] = safe_string(exif.get('Model', ''))
                    meta['date_taken'] = parse_exif_date(exif)

                    # Focal Length
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

                    # Aperture
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

                    # ISO
                    iso = exif.get('ISOSpeedRatings') or exif.get('PhotographicSensitivity')
                    if iso:
                        meta['iso'] = str(iso)

                    # Exposure Time
                    et = exif.get('ExposureTime')
                    if et:
                        try:
                            if isinstance(et, tuple) and len(et) == 2 and et[1]:
                                v = et[0] / et[1]
                                meta['exposure_time'] = f"1/{int(1/v)}s" if v < 1 else f"{v:.1f}s"
                            elif isinstance(et, (int, float)):
                                meta['exposure_time'] = f"{float(et)}s"
                            else:
                                meta['exposure_time'] = str(et)
                        except Exception:
                            meta['exposure_time'] = str(et)

                    # GPS
                    gps_lat, gps_lon = parse_gps_coordinates(exif.get('GPSInfo'))
                    if gps_lat is not None:
                        meta['gps_lat'] = round(gps_lat, 6)
                    if gps_lon is not None:
                        meta['gps_lon'] = round(gps_lon, 6)

            except Exception as e:
                logger.debug(f"EXIF error {filepath}: {e}")

        except Exception as e:
            meta['error'] = str(e)[:120]

        return meta

    def _extract_video(self, filepath):
        """Extract video-specific metadata."""
        meta = {'quality_issues': 'Video file'}
        try:
            vm = self.video_extractor.extract(filepath)
            meta.update(vm)
            # Map video resolution to width/height for consistency
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
        """Create minimal record for failed files."""
        rec = get_record_defaults()
        try:
            stat = filepath.stat()
            rec['size_mb'] = round(stat.st_size / (1024 * 1024), 2)
            rec['file_modified'] = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            pass
        rec.update({
            'filename': filepath.name,
            'folder': str(filepath.parent),
            'full_path': str(filepath),
            'extension': filepath.suffix.lstrip('.').upper(),
            'file_type': self._detect_type(filepath.suffix.lower()),
            'error': msg[:120],
            'quality_score': 0,
            'quality_issues': f'Error: {msg[:80]}',
            'metadata_status': 'Error',
            'date_source': 'None',
        })
        return rec
