import os, logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict
from tqdm import tqdm
from PIL import Image
from PIL.ExifTags import TAGS
from .blur_detector import BlurDetector
from .utils import file_hash, get_gps, get_date_from_exif, safe_string

logger = logging.getLogger(__name__)

class ImageScanner:
    def __init__(self, config: Dict):
        self.config = config
        self.blur_detector = BlurDetector(
            threshold=config.get('blur_detection', {}).get('threshold', 100)
        )
        self.hash_algorithm = config.get('duplicates', {}).get('hash_algorithm', 'md5')

        scan_cfg = config.get('scan', {})
        ext_cfg  = scan_cfg.get('extensions', {})

        # Support both old flat list and new images/videos split
        if isinstance(ext_cfg, dict):
            self.image_exts = self._norm(ext_cfg.get('images', []))
            self.video_exts = self._norm(ext_cfg.get('videos', []))
        else:
            self.image_exts = self._norm(ext_cfg)
            self.video_exts = set()

        self.all_exts = self.image_exts | self.video_exts

    def _norm(self, exts):
        return {f".{e.lower().lstrip('.')}" for e in exts}

    def scan(self, folder_path: str) -> List[Dict]:
        folder = Path(folder_path).expanduser().resolve()
        if not folder.exists():
            raise FileNotFoundError(f"Folder not found: {folder}")
        logger.info(f"Scanning: {folder}")
        files = self._find_files(folder)
        logger.info(f"Found {len(files)} files")
        records = []
        show = self.config.get('processing', {}).get('show_progress', True)
        for fp in tqdm(files, desc="Extracting metadata", disable=not show):
            try:
                records.append(self._extract(fp))
            except Exception as e:
                logger.error(f"Error processing {fp}: {e}")
        return records

    def _find_files(self, folder: Path) -> List[Path]:
        files = []
        for dirpath, _, filenames in os.walk(folder):
            for fn in filenames:
                if Path(fn).suffix.lower() in self.all_exts:
                    files.append(Path(dirpath) / fn)
        return sorted(files)

    def _file_type(self, ext: str) -> str:
        if ext in self.image_exts: return "image"
        if ext in self.video_exts: return "video"
        return "other"

    def _extract(self, filepath: Path) -> Dict:
        stat = filepath.stat()
        ext  = filepath.suffix.lower()
        ftype = self._file_type(ext)
        md5  = file_hash(str(filepath), self.hash_algorithm)

        record = {
            'filename':      filepath.name,
            'folder':        str(filepath.parent),
            'full_path':     str(filepath),
            'extension':     ext.lstrip('.').upper(),
            'file_type':     ftype,
            'size_mb':       round(stat.st_size / (1024*1024), 2),
            'file_modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
            'md5_hash':      md5,
            'delete_flag':   'No',
            'recommendation': '',
        }

        if ftype == "image":
            pil = self._pil_meta(filepath)
            is_blurry, blur_score, quality_rating = self.blur_detector.detect_blur(str(filepath))
            quality_score, issues = self._quality(filepath, pil['width'], pil['height'], blur_score)
            record.update({
                'is_blurry':     is_blurry,
                'blur_score':    blur_score,
                'quality_rating': quality_rating,
                'quality_score': quality_score,
                'quality_issues': issues,
                **pil
            })
        else:
            record.update({
                'is_blurry': None, 'blur_score': None,
                'quality_rating': 'N/A', 'quality_score': None,
                'quality_issues': 'Video - not analysed',
                'width': None, 'height': None, 'date_taken': None,
                'mode': None, 'dpi': None, 'has_exif': False,
                'camera_make': None, 'camera_model': None,
                'focal_length': None, 'aperture': None, 'iso': None,
                'exposure_time': None, 'gps_lat': None, 'gps_lon': None,
                'error': None,
            })
        return record

    def _pil_meta(self, filepath: Path) -> Dict:
        meta = {
            'width': None, 'height': None, 'mode': None, 'dpi': None,
            'date_taken': None, 'camera_make': None, 'camera_model': None,
            'focal_length': None, 'aperture': None, 'iso': None,
            'exposure_time': None, 'gps_lat': None, 'gps_lon': None,
            'has_exif': False, 'error': None
        }
        try:
            with Image.open(filepath) as img:
                meta['width']  = img.width
                meta['height'] = img.height
                meta['mode']   = img.mode
                dpi = img.info.get('dpi')
                if dpi:
                    meta['dpi'] = f"{int(dpi[0])}x{int(dpi[1])}"

                exif_raw = img.getexif() if hasattr(img, 'getexif') else None
                if exif_raw:
                    meta['has_exif'] = True
                    exif = {}
                    for tag_id, val in exif_raw.items():
                        tag = TAGS.get(tag_id, tag_id)
                        exif[tag] = val

                    meta['camera_make']  = safe_string(exif.get('Make', '') or '')
                    meta['camera_model'] = safe_string(exif.get('Model', '') or '')
                    meta['date_taken']   = get_date_from_exif(exif)

                    fl = exif.get('FocalLength')
                    if fl:
                        try:    meta['focal_length'] = f"{float(fl):.1f}mm"
                        except: meta['focal_length'] = str(fl)

                    fn = exif.get('FNumber')
                    if fn:
                        try:    meta['aperture'] = f"f/{float(fn):.1f}"
                        except: meta['aperture'] = str(fn)

                    iso = exif.get('ISOSpeedRatings') or exif.get('PhotographicSensitivity')
                    if iso:
                        meta['iso'] = str(iso)

                    exp = exif.get('ExposureTime')
                    if exp:
                        try:
                            fv = float(exp)
                            meta['exposure_time'] = f"1/{round(1/fv)}s" if fv < 1 else f"{fv}s"
                        except: meta['exposure_time'] = str(exp)

                    meta['gps_lat'], meta['gps_lon'] = get_gps(exif)
        except Exception as e:
            meta['error'] = str(e)[:120]
        return meta

    def _quality(self, filepath: Path, width, height, blur_score) -> tuple:
        issues, score = [], 100
        if width and height:
            mp = (width * height) / 1_000_000
            if mp < 1:
                issues.append("Low resolution"); score -= 20
            elif mp < 2:
                issues.append("Below 2MP"); score -= 10
        if blur_score is not None:
            if blur_score < 50:
                issues.append("Very blurry"); score -= 30
            elif blur_score < 100:
                issues.append("Slightly blurry"); score -= 15
        try:
            if filepath.stat().st_size / (1024*1024) < 0.05:
                issues.append("Suspiciously small"); score -= 15
        except: pass
        return max(0, score), '; '.join(issues) if issues else 'None'
