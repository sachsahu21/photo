

# ============================================================
# FILE: src/blur_detector.py
# ============================================================
"""Blur Detection - Laplacian variance method."""

import logging

logger = logging.getLogger(__name__)

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


class BlurDetector:
    def __init__(self, threshold=100.0):
        self.threshold = float(threshold)

    def detect_blur(self, filepath):
        if not CV2_AVAILABLE:
            return None, None, "N/A"
        try:
            img = cv2.imread(str(filepath))
            if img is None:
                return None, None, "Error: Cannot read"
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            return self._classify(score)
        except Exception as e:
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
        score = 100.0
        issues = []
        if isinstance(blur_score, (int, float)):
            if blur_score < self.threshold * 0.5:
                score -= 40; issues.append("Very blurry")
            elif blur_score < self.threshold:
                score -= 25; issues.append("Blurry")
            elif blur_score < self.threshold * 1.5:
                score -= 10; issues.append("Slightly soft")
        if width and height:
            mp = (width * height) / 1e6
            if mp < 0.5:
                score -= 30; issues.append("Very low res")
            elif mp < 1.0:
                score -= 20; issues.append("Low res")
            elif mp < 2.0:
                score -= 10; issues.append("Below avg res")
        if not has_exif:
            score -= 5; issues.append("No EXIF")
        return round(max(0, min(100, score)), 1), "; ".join(issues) if issues else "None"

    def set_threshold(self, t):
        self.threshold = float(t)
