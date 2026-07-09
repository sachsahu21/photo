"""
Image and Video Scanner v4.1
"""

import os
import logging
from pathlib import Path
from datetime import datetime

from tqdm import tqdm

from .blur_detector import BlurDetector
from .video_metadata import VideoMetadataExtractor
from .utils import (
    calculate_file_hash, safe_string, parse_exif_date,
    parse_gps_coordinates, get_file_modification_date,
    get_record_defaults, determine_metadata_status, determine_date_source
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

try:
    import numpy as np
    NP_OK = True
except ImportError:
    NP_OK = False


class ImageScanner:

    def __init__(self, config):
        self.config = config

        blur_cfg = config.get('blur_detection', {})
        self.blur_enabled = blur_cfg.get('enabled', True)
        self.blur_detector = BlurDetector(threshold=blur_cfg.get('threshold', 100))

        self.video_extractor = VideoMetadataExtractor()

        dup_cfg = config.get('duplicates', {})
        self.hash_algorithm = dup_cfg.get('hash_algorithm', 'md5')
        self.duplicates_enabled = dup_cfg.get('enabled', True)

        scan_cfg = config.get('scan', {})
        ext_cfg = scan_cfg.get('extensions', {})
        if isinstance(ext_cfg, dict):
            self.image_exts = self._norm(ext_cfg.get('images', []))
            self.video_exts = self._norm(ext_cfg.get('videos', []))
        else:
            self.image_exts = self._norm([
                'jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'webp',
                'heic', 'raw', 'cr2', 'nef', 'arw', 'dng'
            ])
            self.video_exts = self._norm([
                'mp4', 'mov', 'avi', 'mkv', '3gp', 'm4v', 'mpg',
                'mpeg', 'wmv', 'flv', 'webm', 'mts'
            ])
        self.all_exts = self.image_exts | self.video_exts
        self.recursive = scan_cfg.get('recursive', True)

        proc_cfg = config.get('processing', {})
        self.show_progress = proc_cfg.get('show_progress', True)
        self.parallel_workers = proc_cfg.get('threads', 0)
        self.checkpoint_enabled = proc_cfg.get('checkpoint_enabled', False)
        self.checkpoint_interval = proc_cfg.get('checkpoint_interval', 100)
        self.checkpoint_file = proc_cfg.get('checkpoint_file')
        self.fast_mode = proc_cfg.get('fast_mode', False)
        self.skip_video_hash = proc_cfg.get('skip_video_hash', True)

        if self.fast_mode:
            self.face_enabled = False
            self.thumb_enabled = False
            self.tag_enabled = False
            self.blur_enabled = False
            self.geo_enabled = config.get('geocoding', {}).get('enabled', False)
        else:
            self.face_enabled = config.get('face_detection', {}).get('enabled', False)
            self.thumb_enabled = config.get('thumbnails', {}).get('enabled', False)
            self.tag_enabled = config.get('auto_tagging', {}).get('enabled', False)
            self.geo_enabled = config.get('geocoding', {}).get('enabled', False)

        self._face_detector = None
        self._thumb_generator = None
        self._auto_tagger = None
        self._geocoder = None

    def _norm(self, exts):
        if not exts:
            return set()
        result = set()
        for e in exts:
            if e:
                clean = str(e).lower().lstrip('.')
                result.add('.' + clean)
        return result

    def _init_features(self):
        if self.face_enabled and self._face_detector is None:
            try:
                from .face_detector import FaceDetector
                fd = self.config.get('face_detection', {}) or {}
                fd_kw: dict = {'method': fd.get('method', 'opencv')}
                if fd.get('min_face_size') is not None:
                    fd_kw['min_face_size'] = int(fd['min_face_size'])
                if fd.get('min_neighbors') is not None:
                    fd_kw['min_neighbors'] = int(fd['min_neighbors'])
                if fd.get('scale_factor') is not None:
                    fd_kw['scale_factor'] = float(fd['scale_factor'])
                self._face_detector = FaceDetector(**fd_kw)
            except Exception:
                self.face_enabled = False

        if self.thumb_enabled and self._thumb_generator is None:
            try:
                from .thumbnail_generator import ThumbnailGenerator
                thumb_cfg = self.config.get('thumbnails', {})
                self._thumb_generator = ThumbnailGenerator(
                    output_folder=thumb_cfg.get('output_folder'),
                    size=thumb_cfg.get('size', [150, 100])
                )
            except Exception:
                self.thumb_enabled = False

        if self.tag_enabled and self._auto_tagger is None:
            try:
                from .auto_tagger import AutoTagger
                tag_cfg = self.config.get('auto_tagging', {})
                self._auto_tagger = AutoTagger(
                    model=tag_cfg.get('model', 'mobilenet'),
                    top_k=tag_cfg.get('top_k', 5),
                    confidence_threshold=tag_cfg.get('confidence_threshold', 0.3)
                )
            except Exception:
                self.tag_enabled = False

        if self.geo_enabled and self._geocoder is None:
            try:
                from .geocoder import Geocoder
                method = self.config.get('geocoding', {}).get('method', 'offline')
                self._geocoder = Geocoder(method=method)
            except Exception:
                self.geo_enabled = False

    def scan(self, folder_path):
        folder = Path(folder_path).expanduser().resolve()
        if not folder.exists():
            raise FileNotFoundError('Not found: ' + str(folder))
        if not folder.is_dir():
            raise NotADirectoryError('Not a directory: ' + str(folder))

        self._init_features()

        files = self._find_files(folder)
        if not files:
            return []

        checkpoint = None
        if self.checkpoint_enabled:
            if not self.checkpoint_file:
                raise ValueError(
                    'processing.checkpoint_file not resolved; set workspace.root in config.yaml'
                )
            from .checkpoint_manager import CheckpointManager
            checkpoint = CheckpointManager(
                interval=self.checkpoint_interval,
                file_path=self.checkpoint_file,
            )
            if checkpoint.load():
                files = [f for f in files if not checkpoint.is_processed(str(f))]

        if self.parallel_workers != 1 and len(files) > 50 and not self.fast_mode:
            records = self._scan_parallel(files, checkpoint)
        else:
            records = self._scan_sequential(files, checkpoint)

        if self.geo_enabled and self._geocoder:
            self._batch_geocode(records)

        for rec in records:
            rec['metadata_status'] = determine_metadata_status(rec)
            rec['date_source'] = determine_date_source(rec)

        if checkpoint:
            checkpoint.save()
            checkpoint.clear()

        return records

    def _scan_sequential(self, files, checkpoint):
        records = []
        it = tqdm(files, desc='Scanning', unit='file', disable=not self.show_progress)
        for fp in it:
            try:
                rec = self._extract(fp)
                records.append(rec)
                if checkpoint:
                    checkpoint.mark_processed(str(fp))
            except Exception as e:
                logger.error('Error %s: %s', fp, e)
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
                logger.error('Error %s: %s', fp, e)
                return self._error_record(fp, str(e))

        results = pp.process(files, process_one, desc='Scanning (parallel)')
        return [r for r in results if r is not None]

    def _find_files(self, folder):
        files = []
        if self.recursive:
            for dp, _, fns in os.walk(folder):
                for fn in fns:
                    ext = Path(fn).suffix.lower()
                    if ext in self.all_exts:
                        fp = Path(dp) / fn
                        if fp.is_file():
                            files.append(fp)
        else:
            for item in folder.iterdir():
                if item.is_file() and item.suffix.lower() in self.all_exts:
                    files.append(item)
        return sorted(files)

    def _detect_type(self, ext):
        if ext in self.image_exts:
            return 'image'
        elif ext in self.video_exts:
            return 'video'
        return 'other'

    @staticmethod
    def _bgr_from_pil(pil_img):
        """BGR ndarray for OpenCV when cv2.imread fails (e.g. HEIC via Pillow)."""
        if not (CV2_OK and NP_OK and pil_img is not None):
            return None
        try:
            rgb = np.asarray(pil_img.convert('RGB'), dtype=np.uint8)
            return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        except Exception:
            return None

    def _extract(self, filepath):
        defaults = get_record_defaults()
        stat = filepath.stat()
        ext = filepath.suffix.lower()
        file_type = self._detect_type(ext)
        mod_date = get_file_modification_date(filepath)

        file_data = None
        if file_type == 'image' and not self.fast_mode:
            try:
                # BOLT: Read image data once to avoid multiple disk I/O hits
                with open(filepath, 'rb') as f:
                    file_data = f.read()
            except Exception as e:
                logger.warning(f"Failed to read {filepath}: {e}")

        file_hash = ''
        if file_type == 'video' and self.skip_video_hash:
            file_hash = ''
        elif self.duplicates_enabled:
            file_hash = calculate_file_hash(filepath, self.hash_algorithm, data=file_data)

        mod_str = mod_date.strftime('%Y-%m-%d %H:%M:%S') if mod_date else ''

        defaults.update({
            'filename': filepath.name,
            'folder': str(filepath.parent),
            'full_path': str(filepath),
            'extension': ext.lstrip('.').upper(),
            'file_type': file_type,
            'size_mb': round(stat.st_size / (1024 * 1024), 2),
            'file_modified': mod_str,
            'md5_hash': file_hash,
        })

        if file_type == 'image':
            pil_img = None
            cv2_img = None

            import io
            if PIL_OK:
                try:
                    if file_data:
                        pil_img = PILImage.open(io.BytesIO(file_data))
                    else:
                        pil_img = PILImage.open(filepath)
                except Exception as e:
                    defaults['error'] = str(e)[:120]

            if CV2_OK and (self.blur_enabled or self.face_enabled):
                try:
                    if file_data:
                        nparr = np.frombuffer(file_data, np.uint8)
                        cv2_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    else:
                        cv2_img = cv2.imread(str(filepath))
                except Exception:
                    pass

            if pil_img:
                img_meta = self._extract_image_from_pil(filepath, pil_img)
                defaults.update(img_meta)

            if self.blur_enabled and cv2_img is not None:
                try:
                    gray = cv2.cvtColor(cv2_img, cv2.COLOR_BGR2GRAY)
                    score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
                    blur_result = self.blur_detector._classify(score)
                    defaults['is_blurry'] = blur_result[0]
                    defaults['blur_score'] = blur_result[1]
                    defaults['quality_rating'] = blur_result[2]
                except Exception:
                    pass

            try:
                qs_result = self.blur_detector.calculate_quality_score(
                    defaults.get('blur_score'),
                    defaults.get('width'),
                    defaults.get('height'),
                    defaults.get('has_exif', False)
                )
                defaults['quality_score'] = qs_result[0]
                defaults['quality_issues'] = qs_result[1]
            except Exception:
                pass

            if self.face_enabled and self._face_detector:
                bgr = cv2_img
                if bgr is None:
                    bgr = self._bgr_from_pil(pil_img)
                if bgr is not None:
                    try:
                        count, category, _boxes = self._face_detector.detect_from_image(bgr)
                        defaults['face_count'] = int(count)
                        defaults['face_category'] = category
                    except Exception:
                        pass

            if self.thumb_enabled and self._thumb_generator and pil_img:
                try:
                    thumb_name = 'thumb-' + filepath.stem + '-' + str(stat.st_size) + '.jpg'
                    thumb_dir = Path(self._thumb_generator.output_folder)
                    thumb_path = thumb_dir / thumb_name
                    if not thumb_path.exists():
                        img_copy = pil_img.copy().convert('RGB')
                        thumb_size = self._thumb_generator.size
                        img_copy.thumbnail(thumb_size, PILImage.LANCZOS)
                        img_copy.save(thumb_path, 'JPEG', quality=75)
                    defaults['thumbnail_path'] = str(thumb_path)
                except Exception:
                    pass

            if self.tag_enabled and self._auto_tagger and pil_img:
                try:
                    defaults.update(self._auto_tagger.tag(filepath))
                except Exception:
                    pass

            if pil_img:
                try:
                    pil_img.close()
                except Exception:
                    pass

        elif file_type == 'video':
            video_meta = self._extract_video(filepath)
            defaults.update(video_meta)

            if self.thumb_enabled and self._thumb_generator:
                try:
                    thumb = self._thumb_generator.generate_for_video(filepath)
                    defaults['thumbnail_path'] = thumb
                except Exception:
                    pass

        return defaults

    def _extract_image_from_pil(self, filepath, pil_img):
        meta = {}
        try:
            meta['width'] = pil_img.width
            meta['height'] = pil_img.height
            meta['mode'] = pil_img.mode

            try:
                dpi = pil_img.info.get('dpi')
                if dpi and isinstance(dpi, tuple) and len(dpi) >= 2:
                    meta['dpi'] = str(int(dpi[0])) + 'x' + str(int(dpi[1]))
            except Exception:
                pass

            try:
                exif_raw = pil_img.getexif() if hasattr(pil_img, 'getexif') else None
                if exif_raw and len(exif_raw) > 0:
                    meta['has_exif'] = True
                    exif = {TAGS.get(tid, str(tid)): v for tid, v in exif_raw.items()}
                    meta['camera_make'] = safe_string(exif.get('Make', ''))
                    meta['camera_model'] = safe_string(exif.get('Model', ''))
                    meta['date_taken'] = parse_exif_date(exif)

                    gps_lat, gps_lon = parse_gps_coordinates(exif.get('GPSInfo'))
                    if gps_lat is not None:
                        meta['gps_lat'] = round(gps_lat, 6)
                    if gps_lon is not None:
                        meta['gps_lon'] = round(gps_lon, 6)
            except Exception:
                pass

        except Exception as e:
            meta['error'] = str(e)[:120]
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
            meta['video_meta_source'] = 'none'
            meta['video_meta_error'] = 'exception'
        return meta

    def _batch_geocode(self, records):
        coords = []
        indices = []
        for i, r in enumerate(records):
            lat = r.get('gps_lat')
            lon = r.get('gps_lon')
            if lat is not None and lon is not None:
                coords.append((lat, lon))
                indices.append(i)

        if not coords:
            return

        try:
            results = self._geocoder.geocode_batch(coords)
            for i, geo in zip(indices, results):
                records[i].update(geo)
        except Exception:
            pass

    def _error_record(self, filepath, msg):
        rec = get_record_defaults()
        try:
            stat = filepath.stat()
            rec['size_mb'] = round(stat.st_size / (1024 * 1024), 2)
            mod_time = datetime.fromtimestamp(stat.st_mtime)
            rec['file_modified'] = mod_time.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            pass
        rec['filename'] = filepath.name
        rec['folder'] = str(filepath.parent)
        rec['full_path'] = str(filepath)
        rec['extension'] = filepath.suffix.lstrip('.').upper()
        rec['file_type'] = self._detect_type(filepath.suffix.lower())
        rec['error'] = msg[:120]
        rec['quality_score'] = 0
        rec['quality_issues'] = 'Error: ' + msg[:80]
        rec['metadata_status'] = 'Error'
        rec['date_source'] = 'None'
        return rec

