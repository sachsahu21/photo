

# ============================================================
# FILE: src/thumbnail_generator.py  (#2 - NEW)
# ============================================================
"""
Thumbnail Generator - Create small preview images.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from PIL import Image
    PIL_OK = True
except ImportError:
    PIL_OK = False


class ThumbnailGenerator:
    """Generate thumbnails for images."""

    def __init__(self, output_folder='./thumbnails', size=(150, 100)):
        self.output_folder = Path(output_folder)
        self.output_folder.mkdir(parents=True, exist_ok=True)
        self.size = tuple(size) if isinstance(size, (list, tuple)) else (150, 100)

    def generate(self, filepath):
        """
        Generate thumbnail for an image.

        Returns:
            Path to thumbnail or None
        """
        if not PIL_OK:
            return None

        try:
            filepath = Path(filepath)
            thumb_name = f"thumb_{filepath.stem}_{filepath.stat().st_size}.jpg"
            thumb_path = self.output_folder / thumb_name

            if thumb_path.exists():
                return str(thumb_path)

            with Image.open(filepath) as img:
                img = img.convert('RGB')
                img.thumbnail(self.size, Image.LANCZOS)
                img.save(thumb_path, 'JPEG', quality=75)

            return str(thumb_path)

        except Exception as e:
            logger.debug(f"Thumbnail error {filepath}: {e}")
            return None

    def generate_for_video(self, filepath):
        """Extract first frame as thumbnail."""
        try:
            import cv2
            cap = cv2.VideoCapture(str(filepath))
            if not cap.isOpened():
                return None

            ret, frame = cap.read()
            cap.release()

            if not ret or frame is None:
                return None

            filepath = Path(filepath)
            thumb_name = f"thumb_{filepath.stem}_{filepath.stat().st_size}.jpg"
            thumb_path = self.output_folder / thumb_name

            if thumb_path.exists():
                return str(thumb_path)

            # Resize
            h, w = frame.shape[:2]
            scale = min(self.size[0] / w, self.size[1] / h)
            if scale < 1:
                frame = cv2.resize(frame, None, fx=scale, fy=scale)

            cv2.imwrite(str(thumb_path), frame)
            return str(thumb_path)

        except Exception as e:
            logger.debug(f"Video thumbnail error {filepath}: {e}")
            return None
