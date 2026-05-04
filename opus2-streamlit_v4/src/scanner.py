# ============================================================
# FILE: src/scanner.py
# ============================================================
"""Scanner v2.4"""
import os, logging
from pathlib import Path
from datetime import datetime
from tqdm import tqdm
from .blur_detector import BlurDetector
from .video_metadata import VideoMetadataExtractor
from .utils import (calculate_file_hash, safe_string, parse_exif_date, parse_gps_coordinates, get_file_modification_date, get_record_defaults, determine_metadata_status, determine_date_source)
logger = logging.getLogger(__name__)
try:
    from PIL import Image as PILImage; from PIL.ExifTags import TAGS; PIL_OK = True
except ImportError: PIL_OK = False
try:
    import cv2; CV2_OK = True
except ImportError: CV2_OK = False

class ImageScanner:
    def __init__(self, config):
        self.config = config
        bc = config.get('blur_detection', {}); self.blur_on = bc.get('enabled', True)
        self.blur_det = BlurDetector(threshold=bc.get('threshold', 100))
        self.vid_ext = VideoMetadataExtractor()
        dc = config.get('duplicates', {}); self.hash_algo = dc.get('hash_algorithm', 'md5'); self.dup_on = dc.get('enabled', True)
        sc = config.get('scan', {}); ec = sc.get('extensions', {})
        if isinstance(ec, dict):
            self.img_ext = set('.' + e.lower().lstrip('.') for e in (ec.get('images', []) or []) if e)
            self.vid_exts = set('.' + e.lower().lstrip('.') for e in (ec.get('videos', []) or []) if e)
        else:
            self.img_ext = {'.jpg','.jpeg','.png','.gif','.bmp','.tiff','.webp','.heic','.raw','.cr2','.nef','.arw','.dng'}
            self.vid_exts = {'.mp4','.mov','.avi','.mkv','.3gp','.m4v','.mpg','.mpeg','.wmv','.flv','.webm','.mts'}
        self.all_ext = self.img_ext | self.vid_exts; self.recursive = sc.get('recursive', True)
        pc = config.get('processing', {}); self.show = pc.get('show_progress', True)
        self.fast = pc.get('fast_mode', False); self.skip_vh = pc.get('skip_video_hash', True)
        self.cp_on = pc.get('checkpoint_enabled', False); self.cp_int = pc.get('checkpoint_interval', 100)
        if self.fast: self.face_on = self.thumb_on = self.tag_on = self.blur_on = False; self.geo_on = config.get('geocoding',{}).get('enabled',False)
        else:
            self.face_on = config.get('face_detection',{}).get('enabled',False); self.thumb_on = config.get('thumbnails',{}).get('enabled',False)
            self.tag_on = config.get('auto_tagging',{}).get('enabled',False); self.geo_on = config.get('geocoding',{}).get('enabled',False)
        self._face = self._thumb = self._tag = self._geo = None

    def _init_feat(self):
        if self.face_on and not self._face:
            try:
                from .face_detector import FaceDetector; self._face = FaceDetector()
            except: self.face_on = False
        if self.thumb_on and not self._thumb:
            try:
                from .thumbnail_generator import ThumbnailGenerator; tc = self.config.get('thumbnails',{})
                self._thumb = ThumbnailGenerator(output_folder=tc.get('output_folder','./thumbnails'), size=tc.get('size',[150,100]))
            except: self.thumb_on = False
        if self.tag_on and not self._tag:
            try:
                from .auto_tagger import AutoTagger; tc = self.config.get('auto_tagging',{})
                self._tag = AutoTagger(top_k=tc.get('top_k',5))
            except: self.tag_on = False
        if self.geo_on and not self._geo:
            try:
                from .geocoder import Geocoder; self._geo = Geocoder()
            except: self.geo_on = False

    def scan(self, folder_path):
        folder = Path(folder_path).expanduser().resolve()
        if not folder.exists(): raise FileNotFoundError('Not found: ' + str(folder))
        self._init_feat()
        files = sorted(f for dp, _, fns in (os.walk(folder) if self.recursive else [(str(folder), [], [i.name for i in folder.iterdir()])]) for fn in fns for f in [Path(dp) / fn] if f.suffix.lower() in self.all_ext and f.is_file())
        if not files: return []
        logger.info('Found %d files', len(files))
        cp = None
        if self.cp_on:
            from .checkpoint_manager import CheckpointManager; cp = CheckpointManager(interval=self.cp_int)
            if cp.load(): files = [f for f in files if not cp.is_processed(str(f))]
        records = []
        for fp in tqdm(files, desc='Scanning', unit='file', disable=not self.show):
            try:
                records.append(self._extract(fp))
                if cp: cp.mark_processed(str(fp))
            except Exception as e: records.append(self._err(fp, str(e)))
        if self.geo_on and self._geo:
            coords, indices = [], []
            for i, r in enumerate(records):
                if r.get('gps_lat') is not None and r.get('gps_lon') is not None: coords.append((r['gps_lat'], r['gps_lon'])); indices.append(i)
            if coords:
                try:
                    for i, geo in zip(indices, self._geo.geocode_batch(coords)): records[i].update(geo)
                except: pass
        for rec in records: rec['metadata_status'] = determine_metadata_status(rec); rec['date_source'] = determine_date_source(rec)
        if cp: cp.save(); cp.clear()
        return records

    def _type(self, ext):
        if ext in self.img_ext: return 'image'
        if ext in self.vid_exts: return 'video'
        return 'other'

    def _extract(self, fp):
        d = get_record_defaults(); st = fp.stat(); ext = fp.suffix.lower(); ft = self._type(ext)
        md = get_file_modification_date(fp)
        fh = '' if (ft == 'video' and self.skip_vh) else (calculate_file_hash(fp, self.hash_algo) if self.dup_on else '')
        d.update({'filename': fp.name, 'folder': str(fp.parent), 'full_path': str(fp), 'extension': ext.lstrip('.').upper(), 'file_type': ft, 'size_mb': round(st.st_size / (1024*1024), 2), 'file_modified': md.strftime('%Y-%m-%d %H:%M:%S') if md else '', 'md5_hash': fh})
        if ft == 'image':
            pi = ci = None
            if PIL_OK:
                try: pi = PILImage.open(fp)
                except Exception as e: d['error'] = str(e)[:120]
            if CV2_OK and (self.blur_on or self.face_on):
                try: ci = cv2.imread(str(fp))
                except: pass
            if pi: d.update(self._img_meta(fp, pi))
            if self.blur_on and ci is not None:
                try:
                    score = float(cv2.Laplacian(cv2.cvtColor(ci, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())
                    d['is_blurry'], d['blur_score'], d['quality_rating'] = self.blur_det._classify(score)
                except: pass
            try: d['quality_score'], d['quality_issues'] = self.blur_det.calculate_quality_score(d.get('blur_score'), d.get('width'), d.get('height'), d.get('has_exif', False))
            except: pass
            if self.face_on and self._face and ci is not None:
                try:
                    gf = cv2.cvtColor(ci, cv2.COLOR_BGR2GRAY); h, w = gf.shape
                    if max(h,w) > 1200: gf = cv2.resize(gf, None, fx=1200.0/max(h,w), fy=1200.0/max(h,w))
                    if self._face._cascade:
                        faces = self._face._cascade.detectMultiScale(gf, scaleFactor=1.1, minNeighbors=5, minSize=(30,30))
                        c = len(faces) if faces is not None else 0; d['face_count'] = c
                        d['face_category'] = 'No People' if c == 0 else ('Portrait' if c == 1 else ('Small Group' if c <= 4 else 'Large Group'))
                except: pass
            if self.thumb_on and self._thumb and pi:
                try:
                    tp = Path(self._thumb.output_folder) / ('thumb-' + fp.stem + '-' + str(st.st_size) + '.jpg')
                    if not tp.exists(): ic = pi.copy().convert('RGB'); ic.thumbnail(self._thumb.size, PILImage.LANCZOS); ic.save(tp, 'JPEG', quality=75)
                    d['thumbnail_path'] = str(tp)
                except: pass
            if self.tag_on and self._tag and pi:
                try: d.update(self._tag.tag(fp))
                except: pass
            if pi:
                try: pi.close()
                except: pass
        elif ft == 'video':
            try:
                vm = self.vid_ext.extract(fp); d.update(vm)
                if d.get('video_width'): d['width'] = d['video_width']
                if d.get('video_height'): d['height'] = d['video_height']
            except Exception as e: d['error'] = str(e)[:120]
        return d

    def _img_meta(self, fp, pi):
        m = {}
        try:
            m['width'], m['height'], m['mode'] = pi.width, pi.height, pi.mode
            try:
                dpi = pi.info.get('dpi')
                if dpi and isinstance(dpi, tuple) and len(dpi) >= 2: m['dpi'] = str(int(dpi[0])) + 'x' + str(int(dpi[1]))
            except: pass
            try:
                er = pi.getexif() if hasattr(pi, 'getexif') else None
                if er and len(er) > 0:
                    m['has_exif'] = True; exif = {TAGS.get(tid, str(tid)): v for tid, v in er.items()}
                    m['camera_make'] = safe_string(exif.get('Make', '')); m['camera_model'] = safe_string(exif.get('Model', ''))
                    m['date_taken'] = parse_exif_date(exif)
                    fl = exif.get('FocalLength')
                    if fl:
                        try:
                            if isinstance(fl, tuple) and len(fl)==2 and fl[1]: m['focal_length'] = str(round(fl[0]/fl[1],1)) + 'mm'
                            elif isinstance(fl, (int,float)): m['focal_length'] = str(round(float(fl),1)) + 'mm'
                        except: pass
                    fn = exif.get('FNumber')
                    if fn:
                        try:
                            if isinstance(fn, tuple) and len(fn)==2 and fn[1]: m['aperture'] = 'f/' + str(round(fn[0]/fn[1],1))
                            elif isinstance(fn, (int,float)): m['aperture'] = 'f/' + str(round(float(fn),1))
                        except: pass
                    iso = exif.get('ISOSpeedRatings') or exif.get('PhotographicSensitivity')
                    if iso: m['iso'] = str(iso)
                    et = exif.get('ExposureTime')
                    if et:
                        try:
                            if isinstance(et, tuple) and len(et)==2 and et[1]:
                                ev = et[0]/et[1]; m['exposure_time'] = ('1/' + str(int(1/ev)) + 's') if ev < 1 else str(round(ev,1)) + 's'
                            elif isinstance(et, (int,float)): m['exposure_time'] = str(float(et)) + 's'
                        except: pass
                    gl, gn = parse_gps_coordinates(exif.get('GPSInfo'))
                    if gl is not None: m['gps_lat'] = round(gl, 6)
                    if gn is not None: m['gps_lon'] = round(gn, 6)
            except: pass
        except Exception as e: m['error'] = str(e)[:120]
        return m

    def _err(self, fp, msg):
        r = get_record_defaults()
        try: st = fp.stat(); r['size_mb'] = round(st.st_size/(1024*1024),2); r['file_modified'] = datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
        except: pass
        r.update({'filename': fp.name, 'folder': str(fp.parent), 'full_path': str(fp), 'extension': fp.suffix.lstrip('.').upper(), 'file_type': self._type(fp.suffix.lower()), 'error': msg[:120], 'metadata_status': 'Error', 'date_source': 'None'})
        return r
