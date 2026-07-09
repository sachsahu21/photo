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
    """Scan images and extract metadata"""

    IMAGE_EXTENSIONS = {
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif',
        '.webp', '.heic', '.heif', '.raw', '.cr2', '.nef', '.arw',
        '.dng', '.orf', '.rw2', '.pef', '.svg', '.ico', '.psd',
        '.avif', '.jfif'
    }

    def __init__(self, config: Dict):
        """
        Initialize scanner

        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.blur_detector = BlurDetector(
            threshold=config.get('blur_detection.threshold', 100)
        )
        self.hash_algorithm = config.get('duplicates.hash_algorithm', 'md5')

    def scan(self, folder_path: str) -> List[Dict]:
        """
        Scan folder for images and extract metadata

        Args:
            folder_path: Path to scan

        Returns:
            List of image records
        """
        folder = Path(folder_path).expanduser().resolve()
        # print(folder)

        if not folder.exists():
            logger.error(f"Folder not found: {folder}")
            raise FileNotFoundError(f"Folder not found: {folder}")

        logger.info(f"Scanning: {folder}")

        # Find all image files
        print(folder)
        all_files = self._find_images(folder)
        logger.info(f"Found {len(all_files)} images")

        if not all_files:
            logger.warning("No images found")
            return []

        # Extract metadata
        records = []
        show_progress = self.config.get('processing.show_progress', True)

        iterator = tqdm(all_files, desc="Extracting metadata", disable=not show_progress)

        for filepath in iterator:
            try:
                record = self._extract_metadata(filepath)
                records.append(record)
            except Exception as e:
                logger.error(f"Error processing {filepath}: {e}")

        logger.info(f"Extracted metadata from {len(records)} images")
        return records

    def _find_images(self, folder: Path) -> List[Path]:
        """Find all image files in folder"""
        # extensions = self.config.get('scan.extensions', [])        
        extensions = self.config.get('scan',{}).get('extensions')  
        extensions = {f'.{ext.lower()}' for ext in extensions}

        all_files = []
        for dirpath, _, filenames in os.walk(folder):
            for fn in filenames:
                if Path(fn).suffix.lower() in extensions:
                    all_files.append(Path(dirpath) / fn)

        return sorted(all_files)

    # def _find_images(self, folder: Path) -> List[Path]:
    #     """Find all image files in folder - DEBUG VERSION"""
    #     print("CONFIG:", self.config)
    #     print("KEY EXISTS:", 'scan.extensions' in self.config)
    #     print("RAW VALUE:", self.config.get('scan',{}).get('extensions') )

    #     extensions = self.config.get('scan',{}).get('extensions')  
    #     extensions = {f'.{ext.lower()}' for ext in extensions} 

    #     print("\n" + "="*60)
    #     print("DEBUG: _find_images")
    #     print("="*60)
    #     print(f"Folder: {folder}")
    #     print(f"Folder exists: {folder.exists()}")
    #     print(f"Is directory: {folder.is_dir()}")
    #     print(f"Extensions to find: {extensions}")
    #     print("="*60)

    #     all_files = []
    #     total_files_checked = 0

    #     for dirpath, dirnames, filenames in os.walk(folder):
    #         print(f"\nScanning: {dirpath}")
    #         print(f"  Subdirs: {len(dirnames)}")
    #         print(f"  Files: {len(filenames)}")

    #         total_files_checked += len(filenames)

    #         for fn in filenames:
    #             file_ext = Path(fn).suffix.lower()

    #             if file_ext in extensions:
    #                 full_path = Path(dirpath) / fn
    #                 all_files.append(full_path)
    #                 print(f"  ✓ MATCH: {fn} ({file_ext})")
    #             # else:
    #             #     if file_ext:  # Only show if has extension
    #             #         print(f"  ✗ SKIP: {fn} ({file_ext})")

    #     print("\n" + "="*60)
    #     print(f"SUMMARY:")
    #     print(f"  Total files checked: {total_files_checked}")
    #     print(f"  Image files found: {len(all_files)}")
    #     print(f"  Recursive: {self.config.get('scan.recursive', True)}")
    #     print("="*60 + "\n")

    #     return sorted(all_files)

    def _extract_metadata(self, filepath: Path) -> Dict:
        """Extract metadata from single image"""
        stat = filepath.stat()
        md5 = file_hash(str(filepath), self.hash_algorithm)

        # Get PIL metadata
        pil_meta = self._get_pil_metadata(filepath)

        # Detect blur
        is_blurry, blur_score, quality_rating = self.blur_detector.detect_blur(str(filepath))

        # Calculate quality score
        quality_score, issues = self._assess_quality(
            filepath,
            pil_meta['width'],
            pil_meta['height'],
            blur_score
        )

        record = {
            'filename': filepath.name,
            'folder': str(filepath.parent),
            'full_path': str(filepath),
            'extension': filepath.suffix.lower().lstrip('.').upper(),
            'size_mb': round(stat.st_size / (1024 * 1024), 2),
            'file_modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
            'md5_hash': md5,
            'is_blurry': is_blurry,
            'blur_score': blur_score,
            'quality_rating': quality_rating,
            'quality_score': quality_score,
            'quality_issues': issues,
            'delete_flag': 'No',
            'recommendation': '',
            **pil_meta
        }

        return record

    def _get_pil_metadata(self, filepath: Path) -> Dict:
        """Extract metadata using PIL"""
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

                dpi = img.info.get('dpi')
                if dpi:
                    meta['dpi'] = f"{int(dpi[0])}x{int(dpi[1])}"

                # Extract EXIF
                exif_raw = None
                if hasattr(img, 'getexif'):
                    exif_raw = img.getexif()
                elif hasattr(img, '_getexif'):
                    exif_raw = img._getexif()

                if exif_raw:
                    meta['has_exif'] = True
                    exif = {}

                    for tag_id, val in exif_raw.items():
                        tag = TAGS.get(tag_id, tag_id)
                        if tag == 'GPSInfo' and isinstance(val, dict):
                            exif['GPSInfo'] = val
                        else:
                            exif[tag] = val

                    # Parse EXIF fields
                    meta['camera_make'] = safe_string(exif.get('Make', '') or '')
                    meta['camera_model'] = safe_string(exif.get('Model', '') or '')

                    date_taken = get_date_from_exif(exif)
                    if date_taken:
                        meta['date_taken'] = date_taken

                    fl = exif.get('FocalLength')
                    if fl:
                        try:
                            meta['focal_length'] = f"{float(fl):.1f}mm"
                        except:
                            meta['focal_length'] = str(fl)

                    fn = exif.get('FNumber')
                    if fn:
                        try:
                            meta['aperture'] = f"f/{float(fn):.1f}"
                        except:
                            meta['aperture'] = str(fn)

                    iso = exif.get('ISOSpeedRatings') or exif.get('PhotographicSensitivity')
                    if iso:
                        meta['iso'] = str(iso)

                    exp = exif.get('ExposureTime')
                    if exp:
                        try:
                            fv = float(exp)
                            meta['exposure_time'] = f"1/{round(1/fv)}s" if fv < 1 else f"{fv}s"
                        except:
                            meta['exposure_time'] = str(exp)

                    meta['gps_lat'], meta['gps_lon'] = get_gps(exif)

        except Exception as e:
            meta['error'] = str(e)[:120]
            logger.warning(f"Error extracting metadata from {filepath}: {e}")

        return meta

    def _assess_quality(self, filepath: Path, width: int, height: int,
                       blur_score: float) -> tuple:
        """Assess overall image quality"""
        issues = []
        score = 100

        # Resolution check
        if width and height:
            megapixels = (width * height) / 1_000_000
            if megapixels < 1:
                issues.append("Low resolution")
                score -= 20
            elif megapixels < 2:
                issues.append("Below 2MP")
                score -= 10

        # Blur check
        if blur_score is not None:
            if blur_score < 50:
                issues.append("Very blurry")
                score -= 30
            elif blur_score < 100:
                issues.append("Slightly blurry")
                score -= 15

        # File size check
        try:
            size_mb = filepath.stat().st_size / (1024 * 1024)
            if size_mb < 0.05:
                issues.append("Suspiciously small")
                score -= 15
        except:
            pass

        return max(0, score), '; '.join(issues) if issues else 'None'