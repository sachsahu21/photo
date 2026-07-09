
# ============================================================================
# FILE: src/scanner.py
# ============================================================================
"""
Image Scanner - Scans folders and extracts metadata
"""

import logging
import piexif
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

from src.blur_detector import BlurDetector
from src.utils import (
    calculate_file_hash,
    get_file_size_mb,
    get_file_modification_date,
    parse_gps_coordinates,
    format_timestamp
)

try:
    from PIL import Image
    from PIL.ExifTags import TAGS
except ImportError:
    Image = None
    TAGS = {}

logger = logging.getLogger(__name__)


class ImageScanner:
    """Scans folders for images and extracts metadata"""

    def __init__(self, config: Dict):
        """
        Initialize scanner

        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.supported_extensions = config.get('scan', {}).get('supported_extensions', [])
        self.recursive = config.get('scan', {}).get('recursive', True)
        self.thread_count = config.get('processing', {}).get('thread_count', 4)
        self.blur_detector = BlurDetector(
            threshold=config.get('blur_detection', {}).get('threshold', 100),
            quality_thresholds=config.get('blur_detection', {}).get('quality_thresholds', {})
        )
        self.hash_algorithm = config.get('duplicates', {}).get('hash_algorithm', 'md5')

    def scan(self, folder_path: str) -> List[Dict]:
        """
        Scan folder for images and extract metadata

        Args:
            folder_path: Path to folder to scan

        Returns:
            List of image records
        """
        logger.info(f"Starting scan of {folder_path}")

        folder = Path(folder_path)
        if not folder.exists():
            logger.error(f"Folder not found: {folder_path}")
            return []

        image_files = self._find_images(folder)
        logger.info(f"Found {len(image_files)} image files")

        if not image_files:
            logger.warning("No images found")
            return []

        records = []
        with ThreadPoolExecutor(max_workers=self.thread_count) as executor:
            futures = {
                executor.submit(self._extract_metadata, filepath): filepath
                for filepath in image_files
            }

            for future in tqdm(as_completed(futures), total=len(futures), desc="Extracting metadata"):
                try:
                    record = future.result()
                    if record:
                        records.append(record)
                except Exception as e:
                    logger.error(f"Error processing {futures[future]}: {e}")

        logger.info(f"Extracted metadata from {len(records)} images")
        return records

    def _find_images(self, folder: Path) -> List[Path]:
        """
        Find all image files in folder

        Args:
            folder: Folder to search

        Returns:
            List of image file paths
        """
        image_files = []
        extensions = {ext.lower() for ext in self.supported_extensions}

        try:
            if self.recursive:
                pattern = "**/*"
            else:
                pattern = "*"

            for filepath in folder.glob(pattern):
                if filepath.is_file() and filepath.suffix.lower().lstrip('.') in extensions:
                    image_files.append(filepath)

        except Exception as e:
            logger.error(f"Error finding images: {e}")

        return image_files

    def _extract_metadata(self, filepath: Path) -> Optional[Dict]:
        """
        Extract metadata from image

        Args:
            filepath: Path to image file

        Returns:
            Dictionary with image metadata
        """
        try:
            record = {
                'filename': filepath.name,
                'full_path': str(filepath),
                'file_extension': filepath.suffix.lower(),
                'file_size_mb': round(get_file_size_mb(filepath), 2),
                'file_hash': calculate_file_hash(filepath, self.hash_algorithm),
            }

            # Get image dimensions and basic info
            try:
                with Image.open(filepath) as img:
                    record['width'] = img.width
                    record['height'] = img.height
                    record['color_mode'] = img.mode
                    record['megapixels'] = round((img.width * img.height) / 1_000_000, 2)

                    # Try to get DPI
                    if hasattr(img, 'info') and 'dpi' in img.info:
                        record['dpi'] = img.info['dpi']
                    else:
                        record['dpi'] = None

            except Exception as e:
                logger.debug(f"Error getting image dimensions for {filepath}: {e}")
                record['width'] = None
                record['height'] = None
                record['color_mode'] = None
                record['megapixels'] = 0
                record['dpi'] = None

            # Extract EXIF data
            exif_data = self._extract_exif(filepath)
            record.update(exif_data)

            # Detect blur
            blur_info = self.blur_detector.detect_blur(filepath)
            record.update(blur_info)

            # Get file dates
            mod_date = get_file_modification_date(filepath)
            record['file_modified_date'] = format_timestamp(mod_date)

            # Use EXIF date if available, otherwise use file modified date
            if record.get('date_taken'):
                record['sort_date'] = record['date_taken']
            else:
                record['sort_date'] = record['file_modified_date']

            return record

        except Exception as e:
            logger.error(f"Error extracting metadata from {filepath}: {e}")
            return None

    def _extract_exif(self, filepath: Path) -> Dict:
        """
        Extract EXIF metadata from image

        Args:
            filepath: Path to image file

        Returns:
            Dictionary with EXIF data
        """
        exif_data = {
            'camera_make': None,
            'camera_model': None,
            'focal_length': None,
            'aperture': None,
            'iso': None,
            'exposure_time': None,
            'date_taken': None,
            'gps_latitude': None,
            'gps_longitude': None,
        }

        try:
            # Try piexif first
            try:
                exif_dict = piexif.load(str(filepath))

                # Camera make
                if "0th" in exif_dict:
                    if piexif.ImageIFD.Make in exif_dict["0th"]:
                        exif_data['camera_make'] = exif_dict["0th"][piexif.ImageIFD.Make].decode().strip()

                    if piexif.ImageIFD.Model in exif_dict["0th"]:
                        exif_data['camera_model'] = exif_dict["0th"][piexif.ImageIFD.Model].decode().strip()

                    if piexif.ImageIFD.DateTime in exif_dict["0th"]:
                        date_str = exif_dict["0th"][piexif.ImageIFD.DateTime].decode()
                        try:
                            exif_data['date_taken'] = datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S").strftime("%Y-%m-%d %H:%M:%S")
                        except:
                            pass

                # EXIF data
                if "Exif" in exif_dict:
                    exif_ifd = exif_dict["Exif"]

                    if piexif.ExifIFD.FocalLength in exif_ifd:
                        focal = exif_ifd[piexif.ExifIFD.FocalLength]
                        exif_data['focal_length'] = f"{focal[0][0] / focal[0][1]:.1f}mm"

                    if piexif.ExifIFD.FNumber in exif_ifd:
                        fnum = exif_ifd[piexif.ExifIFD.FNumber]
                        exif_data['aperture'] = f"f/{fnum[0][0] / fnum[0][1]:.1f}"

                    if piexif.ExifIFD.ISOSpeedRatings in exif_ifd:
                        exif_data['iso'] = int(exif_ifd[piexif.ExifIFD.ISOSpeedRatings])

                    if piexif.ExifIFD.ExposureTime in exif_ifd:
                        exp = exif_ifd[piexif.ExifIFD.ExposureTime]
                        exif_data['exposure_time'] = f"1/{int(exp[0][1] / exp[0][0])}s"

                # GPS data
                if "GPS" in exif_dict:
                    lat, lon = parse_gps_coordinates(exif_dict["GPS"])
                    exif_data['gps_latitude'] = round(lat, 6) if lat else None
                    exif_data['gps_longitude'] = round(lon, 6) if lon else None

            except Exception as e:
                logger.debug(f"piexif error for {filepath}: {e}")

            # Fallback to PIL
            if not exif_data['date_taken']:
                try:
                    with Image.open(filepath) as img:
                        exif = img._getexif()
                        if exif:
                            for tag_id, value in exif.items():
                                tag_name = TAGS.get(tag_id, tag_id)
                                if tag_name == "DateTime":
                                    try:
                                        exif_data['date_taken'] = datetime.strptime(value, "%Y:%m:%d %H:%M:%S").strftime("%Y-%m-%d %H:%M:%S")
                                    except:
                                        pass
                except:
                    pass

        except Exception as e:
            logger.debug(f"Error extracting EXIF from {filepath}: {e}")

        return exif_data
