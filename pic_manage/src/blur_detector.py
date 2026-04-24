

# ============================================================
# FILE: src/blur_detector.py
# ============================================================
"""
Blur Detection - Laplacian variance method
"""

import logging

logger = logging.getLogger(__name__)

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    logger.warning("OpenCV not available - blur detection disabled")


class BlurDetector:
    """Detect image blur using Laplacian variance."""

    def __init__(self, threshold=100.0):
        self.threshold = float(threshold)

    def detect_blur(self, filepath):
        """
        Returns:
            Tuple of (is_blurry, blur_score, quality_rating)
        """
        if not CV2_AVAILABLE:
            return None, None, "N/A (OpenCV missing)"

        try:
            img = cv2.imread(str(filepath))
            if img is None:
                return None, None, "Error: Cannot read"

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())

            return self._classify(laplacian_var)

        except Exception as e:
            logger.debug(f"Blur detection error for {filepath}: {e}")
            return None, None, f"Error: {str(e)[:40]}"

    def _classify(self, score):
        score = round(score, 2)
        if score < self.threshold * 0.5:
            return True, score, "Very Blurry"
        elif score < self.threshold:
            return True, score, "Blurry"
        elif score < self.threshold * 2:
            return False, score, "Fair"
        else:
            return False, score, "Sharp"

    def calculate_quality_score(self, blur_score=None, width=None, height=None, has_exif=False):
        """Calculate quality score 0-100."""
        score = 100.0
        issues = []

        if blur_score is not None and isinstance(blur_score, (int, float)):
            if blur_score < self.threshold * 0.5:
                score -= 40
                issues.append("Very blurry")
            elif blur_score < self.threshold:
                score -= 25
                issues.append("Blurry")
            elif blur_score < self.threshold * 1.5:
                score -= 10
                issues.append("Slightly soft")

        if width and height:
            mp = (width * height) / 1_000_000
            if mp < 0.5:
                score -= 30
                issues.append("Very low resolution")
            elif mp < 1.0:
                score -= 20
                issues.append("Low resolution")
            elif mp < 2.0:
                score -= 10
                issues.append("Below average resolution")

        if not has_exif:
            score -= 5
            issues.append("No EXIF data")

        return round(max(0.0, min(100.0, score)), 1), "; ".join(issues) if issues else "None"

    def set_threshold(self, threshold):
        self.threshold = float(threshold)

