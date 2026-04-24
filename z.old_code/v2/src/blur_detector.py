"""
Blur Detection Module
Detects blurry images using Laplacian variance
"""

import logging
from typing import Tuple, Optional
import cv2
import numpy as np

logger = logging.getLogger(__name__)


class BlurDetector:
    """Detect and rate image blur"""

    def __init__(self, threshold: float = 100):
        """
        Initialize blur detector

        Args:
            threshold: Laplacian variance threshold (lower = more sensitive)
        """
        self.threshold = threshold

    def detect_blur(self, filepath: str) -> Tuple[Optional[bool], Optional[float], str]:
        """
        Detect if image is blurry

        Args:
            filepath: Path to image file

        Returns:
            Tuple of (is_blurry, blur_score, quality_rating)
            - is_blurry: True if blurry, False if sharp, None if error
            - blur_score: Laplacian variance score
            - quality_rating: String rating (Very Blurry, Blurry, Fair, Sharp, Error)
        """
        try:
            img = cv2.imread(str(filepath))
            if img is None:
                return None, None, "Error: Cannot read image"

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()

            return self._classify_blur(laplacian_var)

        except Exception as e:
            logger.warning(f"Error detecting blur in {filepath}: {e}")
            return None, None, f"Error: {str(e)[:30]}"

    def _classify_blur(self, blur_score: float) -> Tuple[bool, float, str]:
        """Classify blur score into categories"""
        blur_score = round(blur_score, 2)

        if blur_score < self.threshold * 0.5:
            return True, blur_score, "Very Blurry"
        elif blur_score < self.threshold:
            return True, blur_score, "Blurry"
        elif blur_score < self.threshold * 2:
            return False, blur_score, "Fair"
        else:
            return False, blur_score, "Sharp"

    def set_threshold(self, threshold: float):
        """Update blur threshold"""
        self.threshold = threshold
        logger.info(f"Blur threshold updated to {threshold}")