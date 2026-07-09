"""
Image Scanner Module
Main scanning and metadata extraction
"""

import os
import logging
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
    """Scan images and extract metadata (images + videos supported)"""

    def __init__(self, config: Dict):
        self.config = config

        self.blur_detector = BlurDetector(
            threshold=config.get('blur_detection', {}).get('threshold', 100)
        )

        self.hash_algorithm = config.get('duplicates', {}).get('hash_algorithm', 'md5')

        # Load extensions from config
        scan_cfg = self.config.get('scan', {})
        ext_cfg = scan_cfg.get('extensions', {})

        self.image_exts = self._normalize_exts(ext_cfg.get('images', []))
        self.video_exts = self._normalize_exts(ext_cfg.get('videos', []))

        # Combined for scanning
        self.all_exts = self.image_exts | self.video_exts

    def _normalize_exts(self, exts):
        """Normalize extensions (.jpg, JPG -> .jpg)"""
        return {f".{e.lower().lstrip('.')}" for e in exts}

    def scan(self, folder_path: str) -> List[Dict]:
        folder = Path(folder_path).expanduser().resolve()

        if not folder.exists():
            raise FileNotFoundError(f"Folder not found: {folder}")

        logger.info(f"Scanning: {folder}")

        all_files = self._find_files(folder)

        logger.info(f"Found {len(all_files)} supported files")

        records = []
        show_progress = self.config.get('processing', {}).get('show_progress', True)

        iterator = tqdm(all_files, desc="Extracting metadata", disable=not show_progress)

        for filepath in iterator:
            try:
                record = self._extract_metadata(filepath)
                records.append(record)
            except Exception as e:
                logger.error(f"Error processing {filepath}: {e}")

        return records

    def _find_files(self, folder: Path) -> List[Path]:
        """Find images + videos based on config extensions"""
        files = []

        for dirpath, _, filenames in os.walk(folder):
            for fn in filenames:
                ext = Path(fn).suffix.lower()

                if ext in self.all_exts:
                    files.append(Path(dirpath) / fn)

        return sorted(files)

    def _detect_file_type(self, ext: str) -> str:
        if ext in self.image_exts:
            return "image"
        elif ext in self.video_exts:
            return "video"
        return "other"

    def _extract_metadata(self, filepath: Path) -> Dict:
        stat = filepath.stat()
        md5 = file_hash(str(filepath), self.hash_algorithm)

        ext = filepath.suffix.lower()
        file_type = self._detect_file_type(ext)

        # Default metadata
        record = {
            'filename': filepath.name,
            'folder': str(filepath.parent),
            'full_path': str(filepath),
            'extension': ext.lstrip('.').upper(),
            'file_type': file_type,   # 🔥 NEW COLUMN
            'size_mb': round(stat.st_size / (1024 * 1024), 2),
            'file_modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
            'md5_hash': md5,
            'delete_flag': 'No',
        }

        # IMAGE ONLY processing
        if file_type == "image":
            pil_meta = self._get_pil_metadata(filepath)

            is_blurry, blur_score, quality_rating = self.blur_detector.detect_blur(str(filepath))

            quality_score, issues = self._assess_quality(
                filepath,
                pil_meta['width'],
                pil_meta['height'],
                blur_score
            )

            record.update({
                'is_blurry': is_blurry,
                'blur_score': blur_score,
                'quality_rating': quality_rating,
                'quality_score': quality_score,
                'quality_issues': issues,
                **pil_meta
            })

        else:
            # VIDEO fallback fields
            record.update({
                'is_blurry': None,
                'blur_score': None,
                'quality_rating': "N/A",
                'quality_score': None,
                'quality_issues': "Video file - not analyzed",
                'width': None,
                'height': None,
                'date_taken': None
            })

        return record

    def _get_pil_metadata(self, filepath: Path) -> Dict:
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
            'error': None
        }

        try:
            with Image.open(filepath) as img:
                meta['width'] = img.width
                meta['height'] = img.height
                meta['mode'] = img.mode

                exif_raw = img.getexif() if hasattr(img, 'getexif') else None

                if exif_raw:
                    meta['has_exif'] = True
                    exif = {}

                    for tag_id, val in exif_raw.items():
                        tag = TAGS.get(tag_id, tag_id)
                        exif[tag] = val

                    meta['camera_make'] = safe_string(exif.get('Make', ''))
                    meta['camera_model'] = safe_string(exif.get('Model', ''))

                    meta['date_taken'] = get_date_from_exif(exif)

        except Exception as e:
            meta['error'] = str(e)[:120]

        return meta

    def _assess_quality(self, filepath, width, height, blur_score):
        issues = []
        score = 100

        if width and height:
            mp = (width * height) / 1_000_000
            if mp < 1:
                issues.append("Low resolution")
                score -= 20

        if blur_score and blur_score < 80:
            issues.append("Blurry")
            score -= 20

        return max(0, score), "; ".join(issues) if issues else "None"