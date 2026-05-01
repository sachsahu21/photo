# ============================================================
# FILE: src/similar_detector.py
# ============================================================
"""Similar Image Detector v1.0"""

import logging
from pathlib import Path
from collections import defaultdict
logger = logging.getLogger(__name__)

try:
    from PIL import Image as PILImage
    PIL_OK = True
except ImportError:
    PIL_OK = False
try:
    import numpy as np
    NP_OK = True
except ImportError:
    NP_OK = False
try:
    import cv2
    CV2_OK = True
except ImportError:
    CV2_OK = False


class SimilarDetector:
    def __init__(self, config=None):
        if config is None:
            config = {}
        sc = config.get('similar_detection', {})
        self.enabled = sc.get('enabled', False)
        self.ahash_on = sc.get('ahash', True)
        self.phash_on = sc.get('phash', True)
        self.dhash_on = sc.get('dhash', True)
        self.hist_on = sc.get('color_histogram', False)
        self.sift_on = sc.get('sift', False)
        self.ahash_thr = sc.get('ahash_threshold', 10)
        self.phash_thr = sc.get('phash_threshold', 10)
        self.dhash_thr = sc.get('dhash_threshold', 10)
        self.hist_thr = sc.get('histogram_threshold', 0.85)
        self.sift_thr = sc.get('sift_threshold', 30)
        self.hash_size = sc.get('hash_size', 8)
        self.max_cmp = sc.get('max_compare_per_image', 200)

    def compute_hashes(self, records):
        if not self.enabled or not PIL_OK or not NP_OK:
            return records
        logger.info('Computing image hashes...')
        computed = 0
        for i, rec in enumerate(records):
            if rec.get('file_type') != 'image':
                continue
            fp = rec.get('full_path', '')
            if not fp or not Path(fp).exists():
                continue
            try:
                img = PILImage.open(fp)
                hs = self.hash_size
                gray = img.convert('L')
                resized = gray.resize((hs, hs), PILImage.LANCZOS)
                pixels = np.array(resized, dtype=float)
                if self.ahash_on:
                    rec['ahash'] = self._ahash(pixels)
                if self.phash_on:
                    rec['phash'] = self._phash(pixels)
                if self.dhash_on:
                    gd = img.convert('L').resize((hs + 1, hs), PILImage.LANCZOS)
                    rec['dhash'] = self._dhash(np.array(gd, dtype=float))
                if self.hist_on:
                    rgb = img.convert('RGB').resize((64, 64), PILImage.LANCZOS)
                    rec['color_hist'] = self._histogram(np.array(rgb))
                if self.sift_on and CV2_OK:
                    rec['sift_desc'] = self._sift(fp)
                img.close()
                computed += 1
            except Exception:
                pass
            if (i + 1) % 500 == 0:
                logger.info('Hashed %d / %d', i + 1, len(records))
        logger.info('Hashes computed: %d', computed)
        return records

    def _ahash(self, px):
        return self._to_int((px >= px.mean()).flatten())

    def _phash(self, px):
        try:
            from scipy.fftpack import dct
            d = dct(dct(px, axis=0), axis=1)
            h = self.hash_size // 2
            lf = d[:h, :h]
            return self._to_int((lf >= lf.mean()).flatten())
        except ImportError:
            return self._to_int((px - px.mean() >= 0).flatten())

    def _dhash(self, px):
        return self._to_int((px[:, 1:] > px[:, :-1]).flatten())

    def _histogram(self, rgb):
        hr = np.histogram(rgb[:, :, 0], bins=32, range=(0, 256))[0]
        hg = np.histogram(rgb[:, :, 1], bins=32, range=(0, 256))[0]
        hb = np.histogram(rgb[:, :, 2], bins=32, range=(0, 256))[0]
        h = np.concatenate([hr, hg, hb]).astype(float)
        t = h.sum()
        return h / t if t > 0 else h

    def _sift(self, fp):
        try:
            img = cv2.imread(str(fp), cv2.IMREAD_GRAYSCALE)
            if img is None:
                return None
            h, w = img.shape
            if max(h, w) > 800:
                s = 800.0 / max(h, w)
                img = cv2.resize(img, None, fx=s, fy=s)
            try:
                det = cv2.SIFT_create(nfeatures=100)
            except AttributeError:
                det = cv2.ORB_create(nfeatures=100)
            _, desc = det.detectAndCompute(img, None)
            return desc if desc is not None and len(desc) > 0 else None
        except Exception:
            return None

    def _to_int(self, bits):
        r = 0
        for b in bits:
            r = (r << 1) | int(b)
        return r

    def _hamming(self, h1, h2):
        x = h1 ^ h2
        c = 0
        while x:
            c += 1
            x = x & (x - 1)
        return c

    def _hist_sim(self, h1, h2):
        if h1 is None or h2 is None:
            return 0.0
        d = np.dot(h1, h2)
        n1, n2 = np.linalg.norm(h1), np.linalg.norm(h2)
        return float(d / (n1 * n2)) if n1 > 0 and n2 > 0 else 0.0

    def _sift_match(self, d1, d2):
        if d1 is None or d2 is None:
            return 0
        try:
            if d1.dtype != np.float32:
                d1 = d1.astype(np.float32)
            if d2.dtype != np.float32:
                d2 = d2.astype(np.float32)
            bf = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
            matches = bf.knnMatch(d1, d2, k=2)
            good = 0
            for mp in matches:
                if len(mp) == 2 and mp[0].distance < 0.75 * mp[1].distance:
                    good += 1
            return good
        except Exception:
            return 0

    def find_similar(self, records):
        if not self.enabled:
            return {}
        images = [i for i, r in enumerate(records) if r.get('file_type') == 'image' and
                  (r.get('ahash') is not None or r.get('phash') is not None or r.get('dhash') is not None
                   or r.get('color_hist') is not None or r.get('sift_desc') is not None)]
        if len(images) < 2:
            return {}
        logger.info('Comparing %d images...', len(images))
        pairs = []
        for ia in range(len(images)):
            i = images[ia]
            ra = records[i]
            cc = 0
            for ib in range(ia + 1, len(images)):
                if cc >= self.max_cmp:
                    break
                j = images[ib]
                rb = records[j]
                cc += 1
                methods, best = [], 0.0
                if self.ahash_on and ra.get('ahash') is not None and rb.get('ahash') is not None:
                    dist = self._hamming(ra['ahash'], rb['ahash'])
                    mb = self.hash_size * self.hash_size
                    sim = 1.0 - (dist / mb)
                    if dist <= self.ahash_thr:
                        methods.append('ahash:' + str(round(sim * 100, 1)) + '%')
                        best = max(best, sim)
                if self.phash_on and ra.get('phash') is not None and rb.get('phash') is not None:
                    half = self.hash_size // 2
                    dist = self._hamming(ra['phash'], rb['phash'])
                    sim = 1.0 - (dist / (half * half))
                    if dist <= self.phash_thr:
                        methods.append('phash:' + str(round(sim * 100, 1)) + '%')
                        best = max(best, sim)
                if self.dhash_on and ra.get('dhash') is not None and rb.get('dhash') is not None:
                    dist = self._hamming(ra['dhash'], rb['dhash'])
                    mb = self.hash_size * self.hash_size
                    sim = 1.0 - (dist / mb)
                    if dist <= self.dhash_thr:
                        methods.append('dhash:' + str(round(sim * 100, 1)) + '%')
                        best = max(best, sim)
                if self.hist_on and ra.get('color_hist') is not None and rb.get('color_hist') is not None:
                    sim = self._hist_sim(ra['color_hist'], rb['color_hist'])
                    if sim >= self.hist_thr:
                        methods.append('histogram:' + str(round(sim * 100, 1)) + '%')
                        best = max(best, sim)
                if self.sift_on and CV2_OK and ra.get('sift_desc') is not None and rb.get('sift_desc') is not None:
                    gm = self._sift_match(ra['sift_desc'], rb['sift_desc'])
                    if gm >= self.sift_thr:
                        methods.append('sift:' + str(gm) + 'pts')
                        best = max(best, min(gm / 100.0, 1.0))
                if methods:
                    pairs.append({'ia': i, 'ib': j, 'methods': methods, 'sim': best})
            if (ia + 1) % 200 == 0:
                logger.info('Compared %d / %d', ia + 1, len(images))
        groups = self._group(pairs)
        logger.info('Similar: %d pairs, %d groups', len(pairs), len(groups))
        return groups

    def _group(self, pairs):
        if not pairs:
            return {}
        parent = {}
        def find(x):
            while parent.get(x, x) != x:
                parent[x] = parent.get(parent[x], parent[x])
                x = parent[x]
            return x
        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
        for p in pairs:
            union(p['ia'], p['ib'])
        gm = defaultdict(list)
        for p in pairs:
            for idx in (p['ia'], p['ib']):
                gm[find(idx)].append(idx)
        groups = {}
        gid = 1
        for root in sorted(gm.keys()):
            members = sorted(set(gm[root]))
            if len(members) >= 2:
                groups[gid] = {'members': members, 'pairs': [p for p in pairs if p['ia'] in members or p['ib'] in members]}
                gid += 1
        return groups

    def mark_similar(self, records, groups):
        if not groups:
            return records
        for rec in records:
            rec.setdefault('is_similar', 'No')
            rec.setdefault('similar_group', '')
            rec.setdefault('similar_methods', '')
            rec.setdefault('similar_score', '')
        for gid, gd in groups.items():
            label = 'SIM-' + str(gid).zfill(4)
            ms = set()
            bs = 0.0
            for p in gd['pairs']:
                for m in p['methods']:
                    ms.add(m)
                bs = max(bs, p['sim'])
            mstr = ', '.join(sorted(ms))
            sstr = str(round(bs * 100, 1)) + '%'
            for idx in gd['members']:
                if idx < len(records):
                    records[idx]['is_similar'] = 'YES'
                    records[idx]['similar_group'] = label
                    records[idx]['similar_methods'] = mstr
                    records[idx]['similar_score'] = sstr
        return records

