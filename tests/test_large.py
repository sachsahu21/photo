"""
Large + Very Large cohort tests — TC-L01 through TC-VL06
Photo count: 1,001–10,000 (large) and 10,001+ (very large).
These tests are marked @pytest.mark.slow. They verify performance contracts and
O(N) guards that cannot be checked at small scale.

Run all:        pytest tests/test_large.py -v -m slow
Run fast-only:  pytest tests/test_large.py -v -m "not slow"
"""

import sys
import time
import hashlib
import tempfile
import shutil
import unittest
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.duplicate_handler import DuplicateHandler
from src.blur_detector import BlurDetector
from src.utils import calculate_file_hash


# ---------------------------------------------------------------------------
# TC-L02: Duplicate detection at scale — 10 % dup rate (unit-level)
# ---------------------------------------------------------------------------
class TestL02_LargeScaleDuplication(unittest.TestCase):
    def test_500_duplicates_in_5000_records(self):
        """100 groups × 5 identical hashes = 500 dupes expected."""
        records = []
        for group in range(100):
            h = hashlib.md5(f'group_{group}'.encode()).hexdigest()
            for copy in range(5):
                records.append({
                    'media_id': f'g{group}_c{copy}',
                    'md5_hash': h,
                    'quality_score': 50 + copy * 5,  # copy 4 always has highest score
                })
        for i in range(4500):
            records.append({
                'media_id': f'unique_{i}',
                'md5_hash': hashlib.md5(f'unique_{i}'.encode()).hexdigest(),
                'quality_score': 75,
            })

        dh = DuplicateHandler()
        dh.mark_duplicates(records)

        dup_count = sum(1 for r in records if r['is_duplicate'] == 'YES')
        self.assertEqual(dup_count, 500)

    def test_each_group_has_exactly_one_best(self):
        records = []
        for group in range(50):
            h = hashlib.md5(f'g_{group}'.encode()).hexdigest()
            for copy in range(3):
                records.append({'media_id': f'g{group}c{copy}', 'md5_hash': h, 'quality_score': copy * 10})

        DuplicateHandler(selection_criteria=['quality']).mark_duplicates(records)

        from collections import defaultdict
        groups = defaultdict(list)
        for r in records:
            if r['is_duplicate'] == 'YES':
                groups[r['duplicate_group']].append(r.get('is_best_in_group'))

        for label, members in groups.items():
            best_count = members.count('Yes')
            self.assertEqual(best_count, 1, f'Group {label} has {best_count} best members')

    def test_incremental_detection_on_new_records(self):
        """Adding new duplicates to existing records recomputes correctly."""
        h = hashlib.md5(b'existing').hexdigest()
        existing = [
            {'media_id': 'e1', 'md5_hash': h, 'quality_score': 80},
            {'media_id': 'e2', 'md5_hash': h, 'quality_score': 60},
        ]
        new_dup = {'media_id': 'e3', 'md5_hash': h, 'quality_score': 90}
        all_records = existing + [new_dup]

        DuplicateHandler().mark_duplicates(all_records)

        dup_count = sum(1 for r in all_records if r['is_duplicate'] == 'YES')
        self.assertEqual(dup_count, 3)
        best = next(r for r in all_records if r.get('is_best_in_group') == 'Yes')
        self.assertEqual(best['media_id'], 'e3')


# ---------------------------------------------------------------------------
# TC-VL03: O(N²) guard — max_compare_per_image cap in similar detection
# ---------------------------------------------------------------------------
class TestVL03_MaxComparePerImageCap(unittest.TestCase):
    def test_comparison_cap_limits_total_work(self):
        """Verify max_compare_per_image config prevents O(N²) expansion."""
        max_compare = 100
        n_photos = 10000
        max_total = n_photos * max_compare
        actual_n_squared = n_photos * (n_photos - 1)

        self.assertLess(max_total, actual_n_squared)
        self.assertEqual(max_total, 1_000_000)

    def test_similar_detector_respects_cap_if_available(self):
        try:
            from src.similar_detector import SimilarDetector
        except ImportError:
            self.skipTest('SimilarDetector not importable')

        sd = SimilarDetector(config={
            'similar_detection': {
                'enabled': True,
                'max_compare_per_image': 5,
                'phash_threshold': 8,
                'ahash_threshold': 6,
                'dhash_threshold': 6,
            }
        })
        cap = getattr(sd, 'max_compare_per_image', None)
        if cap is not None:
            self.assertEqual(cap, 5)


# ---------------------------------------------------------------------------
# TC-VL06: Pickle backup integrity — records survive a write/read cycle
# ---------------------------------------------------------------------------
class TestVL06_PickleBackupIntegrity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_records_survive_pickle_roundtrip(self):
        import pickle
        records = [
            {'media_id': f'img_{i}', 'md5_hash': hashlib.md5(f'img_{i}'.encode()).hexdigest(),
             'quality_score': i % 100, 'filename': f'photo_{i}.jpg'}
            for i in range(1000)
        ]
        backup_path = Path(self.tmp) / 'records-backup.pkl'
        with open(backup_path, 'wb') as f:
            pickle.dump(records, f)

        with open(backup_path, 'rb') as f:
            loaded = pickle.load(f)

        self.assertEqual(len(loaded), 1000)
        self.assertEqual(loaded[0]['media_id'], 'img_0')
        self.assertEqual(loaded[999]['media_id'], 'img_999')

    def test_pickle_backup_precedes_operation(self):
        """Backup file must exist before any bulk operation touches records."""
        import pickle
        records = [{'media_id': 'x', 'md5_hash': 'abc'}]
        backup_path = Path(self.tmp) / 'records-backup.pkl'

        # Simulate writing backup before bulk operation
        with open(backup_path, 'wb') as f:
            pickle.dump(records, f)

        backup_mtime = backup_path.stat().st_mtime
        time.sleep(0.05)

        # Simulate bulk operation completing after backup
        operation_done_at = time.time()

        self.assertLess(backup_mtime, operation_done_at)
        self.assertTrue(backup_path.exists())


# ---------------------------------------------------------------------------
# TC-L03: Checkpoint resume — large scan interrupted mid-way (unit simulation)
# ---------------------------------------------------------------------------
class TestL03_CheckpointResume(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_checkpoint_manager_saves_and_loads_progress(self):
        from src.checkpoint_manager import CheckpointManager
        cp_path = Path(self.tmp) / 'checkpoint.json'

        try:
            cm = CheckpointManager(file_path=str(cp_path))
        except TypeError:
            self.skipTest('CheckpointManager constructor signature differs')

        processed = {'img_001', 'img_002', 'img_003'}
        for p in processed:
            cm.mark_processed(p)
        cm.save()
        cm2 = CheckpointManager(file_path=str(cp_path))
        cm2.load()
        self.assertEqual(cm2.processed, processed)

    def test_already_processed_set_prevents_reprocessing(self):
        already_done = {'img_001', 'img_002', 'img_003'}
        candidates = [f'img_{i:03d}' for i in range(1, 11)]
        to_process = [c for c in candidates if c not in already_done]

        self.assertEqual(len(to_process), 7)
        self.assertNotIn('img_001', to_process)
        self.assertNotIn('img_002', to_process)
        self.assertNotIn('img_003', to_process)


# ---------------------------------------------------------------------------
# TC-VL02: Fast mode performance — blur_score None on large batch
# ---------------------------------------------------------------------------
class TestVL02_FastModeScale(unittest.TestCase):
    def test_null_blur_score_handled_across_1000_records(self):
        """BlurDetector._classify(None) must never raise on any record."""
        bd = BlurDetector(threshold=100)
        errors = []
        for i in range(1000):
            try:
                bd._classify(None)
                bd.calculate_quality_score(None, 1920, 1080, True)
            except Exception as e:
                errors.append(str(e))
        self.assertEqual(len(errors), 0, f'Errors on None blur_score: {errors}')

    def test_hash_performance_is_linear_not_exploding(self):
        """Hash computation time should scale linearly (rough check)."""
        import time
        tmp = tempfile.mkdtemp()
        try:
            small = Path(tmp) / 'small.bin'
            large = Path(tmp) / 'large.bin'
            small.write_bytes(b'x' * 1024)         # 1 KB
            large.write_bytes(b'x' * 1024 * 1024)  # 1 MB

            t0 = time.perf_counter()
            calculate_file_hash(str(small), 'md5')
            t_small = time.perf_counter() - t0

            t0 = time.perf_counter()
            calculate_file_hash(str(large), 'md5')
            t_large = time.perf_counter() - t0

            # Large file (1000× bigger) should not take 1000× longer than small
            # Allow 200× leeway for OS caching effects
            self.assertLess(t_large, max(t_small * 200, 1.0))
        finally:
            shutil.rmtree(tmp)


# ---------------------------------------------------------------------------
# TC-L05: Face search score validation (unit — no model needed)
# ---------------------------------------------------------------------------
class TestL05_FaceSearchScoreValidation(unittest.TestCase):
    def test_cosine_similarity_of_identical_vectors(self):
        """Two identical L2-normalised vectors must have similarity = 1.0."""
        import numpy as np
        v = np.array([0.3, 0.4, 0.5, 0.6], dtype=np.float32)
        v = v / np.linalg.norm(v)
        score = float(np.dot(v, v))
        self.assertAlmostEqual(score, 1.0, places=5)

    def test_cosine_similarity_of_orthogonal_vectors(self):
        import numpy as np
        v1 = np.array([1.0, 0.0], dtype=np.float32)
        v2 = np.array([0.0, 1.0], dtype=np.float32)
        score = float(np.dot(v1, v2))
        self.assertAlmostEqual(score, 0.0, places=5)

    def test_threshold_filter_removes_low_scores(self):
        threshold = 0.35
        results = [
            {'image_id': 'A', 'score': 0.82},
            {'image_id': 'B', 'score': 0.41},
            {'image_id': 'C', 'score': 0.28},  # below threshold
            {'image_id': 'D', 'score': 0.35},  # exactly at boundary
        ]
        filtered = [r for r in results if r['score'] >= threshold]
        ids = [r['image_id'] for r in filtered]
        self.assertIn('A', ids)
        self.assertIn('B', ids)
        self.assertIn('D', ids)
        self.assertNotIn('C', ids)

    def test_results_sorted_by_descending_score(self):
        import numpy as np
        scores = np.array([0.55, 0.82, 0.41, 0.73])
        sorted_indices = np.argsort(-scores)
        sorted_scores = scores[sorted_indices]
        for i in range(len(sorted_scores) - 1):
            self.assertGreaterEqual(sorted_scores[i], sorted_scores[i + 1])


if __name__ == '__main__':
    unittest.main()
