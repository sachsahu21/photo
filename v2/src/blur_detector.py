import logging
from typing import Tuple, Optional
import cv2

logger = logging.getLogger(__name__)

class BlurDetector:
    def __init__(self, threshold: float = 100):
        self.threshold = threshold

    def detect_blur(self, filepath: str) -> Tuple[Optional[bool], Optional[float], str]:
        try:
            img = cv2.imread(str(filepath))
            if img is None:
                return None, None, "Error: Cannot read image"
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            score = round(cv2.Laplacian(gray, cv2.CV_64F).var(), 2)
            return self._classify(score)
        except Exception as e:
            logger.warning(f"Blur error {filepath}: {e}")
            return None, None, f"Error: {str(e)[:30]}"

    def _classify(self, score: float) -> Tuple[bool, float, str]:
        if score < self.threshold * 0.5:
            return True,  score, "Very Blurry"
        elif score < self.threshold:
            return True,  score, "Blurry"
        elif score < self.threshold * 2:
            return False, score, "Fair"
        else:
            return False, score, "Sharp"
