# ============================================================
# FILE: src/face_detector.py
# ============================================================
"""Face Detector v2.4"""
import logging; logger=logging.getLogger(__name__)
try: import cv2; CV2_OK=True
except ImportError: CV2_OK=False
class FaceDetector:
    def __init__(self, method='opencv'):
        self._cascade=None
        if CV2_OK:
            try:
                self._cascade=cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_frontalface_default.xml')
                if self._cascade.empty(): self._cascade=None
            except: pass
