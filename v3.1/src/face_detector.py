

# ============================================================
# FILE: src/face_detector.py  (#1 - NEW)
# ============================================================
"""
Face Detection - Detect and count faces in images.
Uses OpenCV Haar cascades (no extra dependencies).
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import cv2
    CV2_OK = True
except ImportError:
    CV2_OK = False


class FaceDetector:
    """Detect faces using OpenCV Haar cascades."""

    def __init__(self, method='opencv'):
        self.method = method
        self._cascade = None
        if CV2_OK:
            try:
                cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
                self._cascade = cv2.CascadeClassifier(cascade_path)
                if self._cascade.empty():
                    logger.warning("Haar cascade failed to load")
                    self._cascade = None
            except Exception as e:
                logger.warning(f"Face detector init error: {e}")

    def detect(self, filepath):
        """
        Detect faces in image.

        Returns:
            dict with 'face_count' (int) and 'face_category' (str)
        """
        result = {'face_count': 0, 'face_category': 'No People'}

        if not CV2_OK or self._cascade is None:
            return result

        try:
            img = cv2.imread(str(filepath))
            if img is None:
                return result

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # Resize for speed if image is large
            h, w = gray.shape
            scale = 1.0
            if max(h, w) > 1200:
                scale = 1200.0 / max(h, w)
                gray = cv2.resize(gray, None, fx=scale, fy=scale)

            faces = self._cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)
            )

            count = len(faces) if faces is not None else 0
            result['face_count'] = count

            if count == 0:
                result['face_category'] = 'No People'
            elif count == 1:
                result['face_category'] = 'Portrait'
            elif count <= 4:
                result['face_category'] = 'Small Group'
            else:
                result['face_category'] = 'Large Group'

            return result

        except Exception as e:
            logger.debug(f"Face detection error {filepath}: {e}")
            return result
