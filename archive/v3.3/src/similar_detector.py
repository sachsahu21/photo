"""Similar Image Detector v2.5 - Robust hash computation and comparison"""


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


try:
    from scipy.fftpack import dct
    SCIPY_OK = True
except ImportError:
    SCIPY_OK = False




class SimilarDetector:


    def __init__(self, config=None):
        sc = (config or {}).get('similar_detection', {})
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


        if self.enabled:
            methods = []
            if self.ahash_on:
                methods.append('aHash')
            if self.phash_on:
                methods.append('pHash' + (' (scipy)' if SCIPY_OK else ' (basic)'))
            if self.dhash_on:
                methods.append('dHash')
            if self.hist_on:
                methods.append('Histogram')
            if self.sift_on:
                methods.append('SIFT' if CV2_OK else 'SIFT (unavailable)')
            logger.info('Similar detection: %s', ', '.join(methods))


    def compute_hashes(self, records):
        if not self.enabled:
            return records
        if not PIL_OK:
            logger.warning('Pillow not installed, skipping hash computation')
            return records
        if not NP_OK:
            logger.warning('numpy not installed, skipping hash computation')
            return records


        logger.info('Computing image hashes (hash_size=%d)...', self.hash_size)
        computed = 0
        skipped = 0
        errors = 0


        for i, rec in enumerate(records):
            if rec.get('file_type') != 'image':
                continue


            fp = rec.get('full_path', '')
            if not fp or not Path(fp).exists():
                skipped += 1
                continue


            try:
                img = PILImage.open(fp)
                hs = self.hash_size


                gray = img.convert('L').resize((hs, hs), PILImage.LANCZOS)
                pixels = np.array(gray, dtype=float)


                if self.ahash_on:
                    rec['ahash'] = self._compute_ahash(pixels)


                if self.phash_on:
                    rec['phash'] = self._compute_phash(pixels)


                if self.dhash_on:
                    dhash_gray = img.convert('L').resize((hs + 1, hs), PILImage.LANCZOS)
                    dhash_pixels = np.array(dhash_gray, dtype=float)
                    rec['dhash'] = self._compute_dhash(dhash_pixels)


                if self.hist_on:
                    rgb = img.convert('RGB').resize((64, 64), PILImage.LANCZOS)
                    rgb_arr = np.array(rgb)
                    rec['color_hist'] = self._compute_histogram(rgb_arr)


                if self.sift_on and CV2_OK:
                    rec['sift_desc'] = self._compute_sift(fp)


                img.close()
                computed += 1


            except Exception as e:
                errors += 1
                logger.debug('Hash error %s: %s', fp, e)


            if (i + 1) % 500 == 0:
                logger.info('Hashed %d / %d images', computed, i + 1)


        logger.info('Hash computation done: %d computed, %d skipped, %d errors', computed, skipped, errors)
        return records


    def _compute_ahash(self, pixels):
        mean = pixels.mean()
        bits = (pixels >= mean).flatten()
        return self._bits_to_int(bits)


    def _compute_phash(self, pixels):
        if SCIPY_OK:
            dct_result = dct(dct(pixels, axis=0), axis=1)
            half = self.hash_size // 2
            low_freq = dct_result[:half, :half]
            mean = low_freq.mean()
            bits = (low_freq >= mean).flatten()
        else:
            mean = pixels.mean()
            bits = (pixels >= mean).flatten()
        return self._bits_to_int(bits)


    def _compute_dhash(self, pixels):
        diff = pixels[:, 1:] > pixels[:, :-1]
        return self._bits_to_int(diff.flatten())


    def _compute_histogram(self, rgb_arr):
        hist_r = np.histogram(rgb_arr[:, :, 0], bins=32, range=(0, 256))[0]
        hist_g = np.histogram(rgb_arr[:, :, 1], bins=32, range=(0, 256))[0]
        hist_b = np.histogram(rgb_arr[:, :, 2], bins=32, range=(0, 256))[0]
        combined = np.concatenate([hist_r, hist_g, hist_b]).astype(float)
        total = combined.sum()
        if total > 0:
            combined = combined / total
        return combined


    def _compute_sift(self, filepath):
        try:
            img = cv2.imread(str(filepath), cv2.IMREAD_GRAYSCALE)
            if img is None:
                return None


            h, w = img.shape
            if max(h, w) > 800:
                scale = 800.0 / max(h, w)
                img = cv2.resize(img, None, fx=scale, fy=scale)


            try:
                detector = cv2.SIFT_create(nfeatures=100)
            except AttributeError:
                try:
                    detector = cv2.xfeatures2d.SIFT_create(nfeatures=100)
                except Exception:
                    detector = cv2.ORB_create(nfeatures=100)


            keypoints, descriptors = detector.detectAndCompute(img, None)


            if descriptors is not None and len(descriptors) > 0:
                return descriptors
            return None


        except Exception as e:
            logger.debug('SIFT error %s: %s', filepath, e)
            return None


    def _bits_to_int(self, bits):
        result = 0
        for bit in bits:
            result = (result << 1) | int(bit)
        return result


    def _hamming_distance(self, hash1, hash2):
        xor = hash1 ^ hash2
        count = 0
        while xor:
            count += 1
            xor = xor & (xor - 1)
        return count


    def _histogram_similarity(self, hist1, hist2):
        if hist1 is None or hist2 is None:
            return 0.0
        dot = np.dot(hist1, hist2)
        norm1 = np.linalg.norm(hist1)
        norm2 = np.linalg.norm(hist2)
        if norm1 > 0 and norm2 > 0:
            return float(dot / (norm1 * norm2))
        return 0.0


    def _sift_match_count(self, desc1, desc2):
        if desc1 is None or desc2 is None:
            return 0
        try:
            if desc1.dtype != np.float32:
                desc1 = desc1.astype(np.float32)
            if desc2.dtype != np.float32:
                desc2 = desc2.astype(np.float32)


            if len(desc1) < 2 or len(desc2) < 2:
                return 0


            bf = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
            matches = bf.knnMatch(desc1, desc2, k=2)


            good = 0
            for match_pair in matches:
                if len(match_pair) == 2:
                    m, n = match_pair
                    if m.distance < 0.75 * n.distance:
                        good += 1
            return good


        except Exception as e:
            logger.debug('SIFT match error: %s', e)
            return 0


    def find_similar(self, records):
        if not self.enabled:
            return {}


        images = []
        for i, r in enumerate(records):
            if r.get('file_type') != 'image':
                continue
            has_hash = False
            for key in ('ahash', 'phash', 'dhash', 'color_hist', 'sift_desc'):
                if r.get(key) is not None:
                    has_hash = True
                    break
            if has_hash:
                images.append(i)


        if len(images) < 2:
            logger.info('Not enough hashed images for comparison: %d', len(images))
            return {}


        logger.info('Comparing %d images (max %d per image)...', len(images), self.max_cmp)
        pairs = []
        total_comparisons = 0


        for ia in range(len(images)):
            i = images[ia]
            ra = records[i]
            compare_count = 0


            for ib in range(ia + 1, len(images)):
                if compare_count >= self.max_cmp:
                    break


                j = images[ib]
                rb = records[j]
                compare_count += 1
                total_comparisons += 1


                methods = []
                best_sim = 0.0


                if self.ahash_on and ra.get('ahash') is not None and rb.get('ahash') is not None:
                    dist = self._hamming_distance(ra['ahash'], rb['ahash'])
                    max_bits = self.hash_size * self.hash_size
                    sim = 1.0 - (dist / max_bits) if max_bits > 0 else 0.0
                    if dist <= self.ahash_thr:
                        methods.append('ahash:' + str(round(sim * 100, 1)) + '%')
                        best_sim = max(best_sim, sim)


                if self.phash_on and ra.get('phash') is not None and rb.get('phash') is not None:
                    if SCIPY_OK:
                        half = self.hash_size // 2
                        max_bits = half * half
                    else:
                        max_bits = self.hash_size * self.hash_size
                    dist = self._hamming_distance(ra['phash'], rb['phash'])
                    sim = 1.0 - (dist / max_bits) if max_bits > 0 else 0.0
                    if dist <= self.phash_thr:
                        methods.append('phash:' + str(round(sim * 100, 1)) + '%')
                        best_sim = max(best_sim, sim)


                if self.dhash_on and ra.get('dhash') is not None and rb.get('dhash') is not None:
                    max_bits = self.hash_size * self.hash_size
                    dist = self._hamming_distance(ra['dhash'], rb['dhash'])
                    sim = 1.0 - (dist / max_bits) if max_bits > 0 else 0.0
                    if dist <= self.dhash_thr:
                        methods.append('dhash:' + str(round(sim * 100, 1)) + '%')
                        best_sim = max(best_sim, sim)


                if self.hist_on and ra.get('color_hist') is not None and rb.get('color_hist') is not None:
                    sim = self._histogram_similarity(ra['color_hist'], rb['color_hist'])
                    if sim >= self.hist_thr:
                        methods.append('histogram:' + str(round(sim * 100, 1)) + '%')
                        best_sim = max(best_sim, sim)


                if self.sift_on and CV2_OK:
                    if ra.get('sift_desc') is not None and rb.get('sift_desc') is not None:
                        good_matches = self._sift_match_count(ra['sift_desc'], rb['sift_desc'])
                        if good_matches >= self.sift_thr:
                            sift_sim = min(good_matches / 100.0, 1.0)
                            methods.append('sift:' + str(good_matches) + 'pts')
                            best_sim = max(best_sim, sift_sim)


                if methods:
                    pairs.append({
                        'ia': i,
                        'ib': j,
                        'methods': methods,
                        'sim': best_sim,
                    })


            if (ia + 1) % 200 == 0:
                logger.info('Compared %d / %d images (%d pairs found)', ia + 1, len(images), len(pairs))


        logger.info('Comparison done: %d total comparisons, %d similar pairs', total_comparisons, len(pairs))


        groups = self._build_groups(pairs)
        logger.info('Built %d similar groups', len(groups))
        return groups


    def _build_groups(self, pairs):
        if not pairs:
            return {}


        parent = {}


        def find(x):
            path = []
            while parent.get(x, x) != x:
                path.append(x)
                x = parent.get(x, x)
            for p in path:
                parent[p] = x
            return x


        def union(a, b):
            ra = find(a)
            rb = find(b)
            if ra != rb:
                parent[ra] = rb


        for p in pairs:
            union(p['ia'], p['ib'])


        group_members = defaultdict(set)
        for p in pairs:
            root_a = find(p['ia'])
            root_b = find(p['ib'])
            group_members[root_a].add(p['ia'])
            group_members[root_a].add(p['ib'])
            if root_b != root_a:
                group_members[root_a].update(group_members[root_b])
                del group_members[root_b]


        groups = {}
        gid = 1
        for root in sorted(group_members.keys()):
            members = sorted(group_members[root])
            if len(members) >= 2:
                group_pairs = []
                for p in pairs:
                    if p['ia'] in members or p['ib'] in members:
                        group_pairs.append(p)
                groups[gid] = {
                    'members': members,
                    'pairs': group_pairs,
                }
                gid += 1


        return groups


    def mark_similar(self, records, groups):
        if not groups:
            return records


        for rec in records:
            if 'is_similar' not in rec or rec['is_similar'] != 'YES':
                rec['is_similar'] = 'No'
            if 'similar_group' not in rec or not rec['similar_group']:
                rec['similar_group'] = ''
            if 'similar_methods' not in rec:
                rec['similar_methods'] = ''
            if 'similar_score' not in rec:
                rec['similar_score'] = ''


        marked = 0
        for gid, group_data in groups.items():
            label = 'SIM-' + str(gid).zfill(4)


            all_methods = set()
            best_score = 0.0
            for p in group_data['pairs']:
                for m in p['methods']:
                    all_methods.add(m)
                best_score = max(best_score, p['sim'])


            methods_str = ', '.join(sorted(all_methods))
            score_str = str(round(best_score * 100, 1)) + '%'


            for idx in group_data['members']:
                if idx < len(records):
                    records[idx]['is_similar'] = 'YES'
                    records[idx]['similar_group'] = label
                    records[idx]['similar_methods'] = methods_str
                    records[idx]['similar_score'] = score_str
                    marked += 1


        logger.info('Marked %d files as similar in %d groups', marked, len(groups))
        return records


    def get_stats(self, records):
        total_images = sum(1 for r in records if r.get('file_type') == 'image')
        hashed = sum(1 for r in records if r.get('file_type') == 'image' and any(r.get(k) is not None for k in ('ahash', 'phash', 'dhash', 'color_hist', 'sift_desc')))
        similar = sum(1 for r in records if str(r.get('is_similar', '')).upper() == 'YES')
        groups = len(set(r.get('similar_group', '') for r in records if r.get('similar_group') and str(r.get('similar_group', '')).strip()))


        return {
            'total_images': total_images,
            'hashed_images': hashed,
            'similar_files': similar,
            'similar_groups': groups,
        }
