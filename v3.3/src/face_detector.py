"""Face Detector v2.5 - Multiple methods with fallbacks"""


import logging
from pathlib import Path


logger = logging.getLogger(__name__)


try:
    import cv2
    CV2_OK = True
except ImportError:
    CV2_OK = False


try:
    import numpy as np
    NP_OK = True
except ImportError:
    NP_OK = False




class FaceDetector:


    def __init__(self, method='opencv', min_face_size=30, scale_factor=1.1, min_neighbors=5):
        self.method = method
        self.min_face_size = min_face_size
        self.scale_factor = scale_factor
        self.min_neighbors = min_neighbors
        self._cascade_front = None
        self._cascade_profile = None
        self._max_dim = 1200


        if CV2_OK:
            self._init_cascades()


    def _init_cascades(self):
        try:
            front_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            self._cascade_front = cv2.CascadeClassifier(front_path)
            if self._cascade_front.empty():
                self._cascade_front = None
                logger.warning('Frontal face cascade empty')
        except Exception as e:
            logger.warning('Frontal cascade init: %s', e)
            self._cascade_front = None


        try:
            alt_path = cv2.data.haarcascades + 'haarcascade_frontalface_alt2.xml'
            self._cascade_alt = cv2.CascadeClassifier(alt_path)
            if self._cascade_alt.empty():
                self._cascade_alt = None
        except Exception:
            self._cascade_alt = None


        try:
            profile_path = cv2.data.haarcascades + 'haarcascade_profileface.xml'
            self._cascade_profile = cv2.CascadeClassifier(profile_path)
            if self._cascade_profile.empty():
                self._cascade_profile = None
        except Exception:
            self._cascade_profile = None


    def detect(self, filepath):
        if not CV2_OK:
            return 0, 'No People', []


        try:
            img = cv2.imread(str(filepath))
            if img is None:
                return 0, 'No People', []
            return self.detect_from_image(img)
        except Exception as e:
            logger.debug('Face detect error %s: %s', filepath, e)
            return 0, 'No People', []


    def detect_from_image(self, img):
        if not CV2_OK or img is None:
            return 0, 'No People', []


        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        except Exception:
            return 0, 'No People', []


        h, w = gray.shape
        scale = 1.0
        if max(h, w) > self._max_dim:
            scale = self._max_dim / max(h, w)
            gray = cv2.resize(gray, None, fx=scale, fy=scale)


        gray = cv2.equalizeHist(gray)


        all_faces = []


        if self._cascade_front is not None:
            faces = self._detect_with_cascade(gray, self._cascade_front)
            all_faces.extend(faces)


        if len(all_faces) == 0 and self._cascade_alt is not None:
            faces = self._detect_with_cascade(gray, self._cascade_alt)
            all_faces.extend(faces)


        if self._cascade_profile is not None:
            profiles = self._detect_with_cascade(gray, self._cascade_profile)
            for pf in profiles:
                if not self._overlaps_any(pf, all_faces):
                    all_faces.append(pf)


            flipped = cv2.flip(gray, 1)
            profiles_r = self._detect_with_cascade(flipped, self._cascade_profile)
            fw = gray.shape[1]
            for pf in profiles_r:
                corrected = (fw - pf[0] - pf[2], pf[1], pf[2], pf[3])
                if not self._overlaps_any(corrected, all_faces):
                    all_faces.append(corrected)


        if scale != 1.0:
            all_faces = [
                (int(x / scale), int(y / scale), int(wf / scale), int(hf / scale))
                for x, y, wf, hf in all_faces
            ]


        count = len(all_faces)
        category = self._categorize(count)


        return count, category, all_faces


    def _detect_with_cascade(self, gray, cascade):
        try:
            faces = cascade.detectMultiScale(
                gray,
                scaleFactor=self.scale_factor,
                minNeighbors=self.min_neighbors,
                minSize=(self.min_face_size, self.min_face_size),
                flags=cv2.CASCADE_SCALE_IMAGE
            )
            if faces is None or len(faces) == 0:
                return []
            return [(int(x), int(y), int(w), int(h)) for x, y, w, h in faces]
        except Exception:
            return []


    def _overlaps_any(self, face, face_list, threshold=0.3):
        if not face_list:
            return False
        fx, fy, fw, fh = face
        for ex, ey, ew, eh in face_list:
            ix1 = max(fx, ex)
            iy1 = max(fy, ey)
            ix2 = min(fx + fw, ex + ew)
            iy2 = min(fy + fh, ey + eh)
            if ix2 > ix1 and iy2 > iy1:
                intersection = (ix2 - ix1) * (iy2 - iy1)
                area1 = fw * fh
                area2 = ew * eh
                min_area = min(area1, area2)
                if min_area > 0 and intersection / min_area > threshold:
                    return True
        return False


    def _categorize(self, count):
        if count == 0:
            return 'No People'
        elif count == 1:
            return 'Portrait'
        elif count == 2:
            return 'Couple'
        elif count <= 4:
            return 'Small Group'
        elif count <= 10:
            return 'Group'
        else:
            return 'Large Group'


    def detect_batch(self, filepaths):
        results = []
        for fp in filepaths:
            count, category, faces = self.detect(fp)
            results.append({
                'face_count': count,
                'face_category': category,
            })
        return results
