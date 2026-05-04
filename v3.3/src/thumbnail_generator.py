# ============================================================
# FILE: src/thumbnail_generator.py
# ============================================================
"""Thumbnail Generator v2.4"""
import logging; from pathlib import Path; logger=logging.getLogger(__name__)
try: from PIL import Image as PILImage; PIL_OK=True
except ImportError: PIL_OK=False
try: import cv2; CV2_OK=True
except ImportError: CV2_OK=False
class ThumbnailGenerator:
    def __init__(self, output_folder='./thumbnails', size=None):
        self.output_folder=Path(output_folder); self.output_folder.mkdir(parents=True,exist_ok=True); self.size=tuple(size) if size else (150,100)
    def generate_for_video(self, filepath):
        if not CV2_OK: return None
        try:
            fp=Path(filepath); tp=self.output_folder/('vthumb-'+fp.stem+'.jpg')
            if tp.exists(): return str(tp)
            cap=cv2.VideoCapture(str(fp))
            if not cap.isOpened(): return None
            cap.set(cv2.CAP_PROP_POS_FRAMES, min(int(cap.get(cv2.CAP_PROP_FRAME_COUNT))//4,30))
            ret,frame=cap.read(); cap.release()
            if not ret: return None
            h,w=frame.shape[:2]; s=min(self.size[0]/w,self.size[1]/h)
            cv2.imwrite(str(tp),cv2.resize(frame,(int(w*s),int(h*s)))); return str(tp)
        except: return None
