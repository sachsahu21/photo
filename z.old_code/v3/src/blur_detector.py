
# ============================================================================
# FILE: src/blur_detector.py
# ============================================================================
"""
Blur Detection Module - Detects blurry images using Laplacian variance
"""

import cv2
import logging
import numpy as np
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class BlurDetector:
    """Detects blur in images using Laplacian variance method"""

    def __init__(self, threshold: int = 100, quality_thresholds: Optional[Dict] = None):
        """
        Initialize blur detector

        Args:
            threshold: Blur threshold (default 100)
            quality_thresholds: Quality classification thresholds
        """
        self.threshold = threshold
        self.quality_thresholds = quality_thresholds or {
            'very_blurry': 50,
            'blurry': 100,
            'fair': 200
        }

    def detect_blur(self, image_path: Path) -> Dict[str, any]:
        """
        Detect blur in image

        Args:
            image_path: Path to image file

        Returns:
            Dictionary with blur metrics
        """
        try:
            image = cv2.imread(str(image_path))

            if image is None:
                logger.warning(f"Could not read image: {image_path}")
                return {
                    'blur_score': 0,
                    'is_blurry': False,
                    'quality_class': 'Unknown',
                    'quality_score': 0
                }

            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()

            is_blurry = laplacian_var < self.threshold
            quality_class = self._classify_quality(laplacian_var)
            quality_score = self._calculate_quality_score(laplacian_var)

            return {
                'blur_score': round(laplacian_var, 2),
                'is_blurry': is_blurry,
                'quality_class': quality_class,
                'quality_score': quality_score
            }

        except Exception as e:
            logger.error(f"Error detecting blur for {image_path}: {e}")
            return {
                'blur_score': 0,
                'is_blurry': False,
                'quality_class': 'Error',
                'quality_score': 0
            }

    def _classify_quality(self, blur_score: float) -> str:
        """Classify image quality based on blur score"""
        if blur_score < self.quality_thresholds['very_blurry']:
            return 'Very Blurry'
        elif blur_score < self.quality_thresholds['blurry']:
            return 'Blurry'
        elif blur_score < self.quality_thresholds['fair']:
            return 'Fair'
        else:
            return 'Sharp'

    def _calculate_quality_score(self, blur_score: float) -> int:
        """
        Calculate quality score (0-100%)

        Args:
            blur_score: Laplacian variance blur score

        Returns:
            Quality score 0-100
        """
        max_score = 500
        quality = min(100, int((blur_score / max_score) * 100))
        return max(0, quality)