# ============================================================
# FILE: src/blur_detector.py
# ============================================================
"""Blur Detector v2.4"""
import logging
logger = logging.getLogger(__name__)
try:
    import cv2
    CV2_OK = True
except ImportError:
    CV2_OK = False

class BlurDetector:
    def __init__(self, threshold=100):
        self.threshold = threshold
    def _classify(self, score):
        if score is None:
            return None, None, 'Unknown'
        score = round(score, 2)
        if score < self.threshold * 0.3:
            return True, score, 'Very Blurry'
        elif score < self.threshold:
            return True, score, 'Blurry'
        elif score < self.threshold * 3:
            return False, score, 'Acceptable'
        elif score < self.threshold * 10:
            return False, score, 'Sharp'
        return False, score, 'Very Sharp'
    def calculate_quality_score(self, blur_score, width, height, has_exif):
        issues, score = [], 50.0
        if blur_score is not None:
            if blur_score >= self.threshold * 10:
                score += 25
            elif blur_score >= self.threshold * 3:
                score += 15
            elif blur_score >= self.threshold:
                score += 5
            elif blur_score >= self.threshold * 0.3:
                score -= 10; issues.append('Blurry')
            else:
                score -= 25; issues.append('Very Blurry')
        if width and height:
            try:
                px = int(width) * int(height)
                if px >= 12000000: score += 15
                elif px >= 8000000: score += 10
                elif px >= 2000000: score += 5
                elif px < 500000: score -= 10; issues.append('Low Res')
            except (ValueError, TypeError): pass
        if has_exif: score += 10
        else: issues.append('No EXIF')
        return round(max(0, min(100, score)), 1), ', '.join(issues) if issues else 'Good'
