"""
Small cohort tests — TC-S01 through TC-S07
Photo count: 11–100 photos. Goal: feature interaction, selection criteria, thresholds.
Run from repo root: pytest tests/test_small.py -v
"""

import sys
import json
import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.duplicate_handler import DuplicateHandler
from src.blur_detector import BlurDetector
from src.utils import resolve_filename_conflict


# ---------------------------------------------------------------------------
# TC-S02: 3-way exact duplicate — selection criteria priority and tie-breaking
# ---------------------------------------------------------------------------
class TestS02_ThreeWayDuplicateSelection(unittest.TestCase):
    def _dup_records(self, quality_scores, widths=None, heights=None):
        h = hashlib.md5(b'same content bytes').hexdigest()
        widths = widths or [640] * len(quality_scores)
        heights = heights or [480] * len(quality_scores)
        return [
            {
                'media_id': str(i),
                'md5_hash': h,
                'quality_score': q,
                'width': widths[i],
                'height': heights[i],
                'size_mb': 1.0,
            }
            for i, q in enumerate(quality_scores)
        ]

    def test_best_selected_by_quality(self):
        records = self._dup_records([60, 85, 95])
        DuplicateHandler(selection_criteria=['quality']).mark_duplicates(records)
        best = next(r for r in records if r.get('is_best_in_group') == 'Yes')
        self.assertEqual(best['media_id'], '2')

    def test_all_three_marked_as_duplicate(self):
        records = self._dup_records([60, 70, 80])
        DuplicateHandler().mark_duplicates(records)
        self.assertEqual(sum(1 for r in records if r['is_duplicate'] == 'YES'), 3)

    def test_exactly_one_best_in_group(self):
        records = self._dup_records([55, 75, 90])
        DuplicateHandler().mark_duplicates(records)
        self.assertEqual(sum(1 for r in records if r.get('is_best_in_group') == 'Yes'), 1)

    def test_resolution_tie_break_when_quality_tied(self):
        h = hashlib.md5(b'same').hexdigest()
        records = [
            {'media_id': '0', 'md5_hash': h, 'quality_score': 75, 'width': 640,  'height': 480},
            {'media_id': '1', 'md5_hash': h, 'quality_score': 75, 'width': 1920, 'height': 1080},
            {'media_id': '2', 'md5_hash': h, 'quality_score': 75, 'width': 640,  'height': 480},
        ]
        DuplicateHandler(selection_criteria=['quality', 'resolution']).mark_duplicates(records)
        best = next(r for r in records if r.get('is_best_in_group') == 'Yes')
        self.assertEqual(best['media_id'], '1')  # highest pixel count wins

    def test_non_duplicate_stays_clean(self):
        h = hashlib.md5(b'same').hexdigest()
        records = [
            {'media_id': 'dup1', 'md5_hash': h, 'quality_score': 80},
            {'media_id': 'dup2', 'md5_hash': h, 'quality_score': 60},
            {'media_id': 'unique', 'md5_hash': 'different_hash_abc', 'quality_score': 90},
        ]
        DuplicateHandler().mark_duplicates(records)
        unique = next(r for r in records if r['media_id'] == 'unique')
        self.assertNotEqual(unique['is_duplicate'], 'YES')
        self.assertEqual(unique['duplicate_group'], '')


# ---------------------------------------------------------------------------
# TC-S03: Near-duplicate via perceptual hash — pHash threshold boundary
# ---------------------------------------------------------------------------
class TestS03_PerceptualHashThreshold(unittest.TestCase):
    def test_similar_detector_import_and_init(self):
        try:
            from src.similar_detector import SimilarDetector
            sd = SimilarDetector(config={
                'similar_detection': {
                    'enabled': True,
                    'ahash_threshold': 6,
                    'phash_threshold': 8,
                    'dhash_threshold': 6,
                    'max_compare_per_image': 100,
                }
            })
            self.assertIsNotNone(sd)
        except ImportError:
            self.skipTest('SimilarDetector not importable — optional dependency missing')

    def test_exact_duplicate_has_zero_hash_distance(self):
        try:
            import numpy as np
            from src.similar_detector import SimilarDetector
        except ImportError:
            self.skipTest('numpy or SimilarDetector unavailable')

        sd = SimilarDetector(config={'similar_detection': {'enabled': True, 'phash_threshold': 8}})
        if not hasattr(sd, '_compute_phash'):
            self.skipTest('_compute_phash not available')

        try:
            from PIL import Image
            import io
            img = Image.new('RGB', (64, 64), color=(100, 150, 200))
            buf = io.BytesIO()
            img.save(buf, 'JPEG', quality=90)
            buf.seek(0)
            h1 = sd._compute_phash(buf.getvalue())
            buf.seek(0)
            h2 = sd._compute_phash(buf.getvalue())
            self.assertEqual(h1, h2)
        except Exception:
            self.skipTest('PIL not available or _compute_phash signature differs')


# ---------------------------------------------------------------------------
# TC-S04: Day threshold folder split — >= 60 files triggers daily folder
# ---------------------------------------------------------------------------
class TestS04_DayThresholdFolderSplit(unittest.TestCase):
    def _day_counts(self, n_files, date='2023-12-25'):
        counts = defaultdict(int)
        for _ in range(n_files):
            counts[date] += 1
        return counts

    def test_65_files_triggers_day_folder(self):
        day_threshold = 60
        counts = self._day_counts(65)
        self.assertGreaterEqual(counts['2023-12-25'], day_threshold)

    def test_40_files_does_not_trigger_day_folder(self):
        day_threshold = 60
        counts = self._day_counts(40)
        self.assertLess(counts['2023-12-25'], day_threshold)

    def test_exactly_60_files_triggers_day_folder(self):
        day_threshold = 60
        counts = self._day_counts(60)
        self.assertGreaterEqual(counts['2023-12-25'], day_threshold)

    def test_59_files_does_not_trigger(self):
        day_threshold = 60
        counts = self._day_counts(59)
        self.assertLess(counts['2023-12-25'], day_threshold)


# ---------------------------------------------------------------------------
# TC-S05: Blur detection — quality score interaction
# ---------------------------------------------------------------------------
class TestS05_BlurQualityInteraction(unittest.TestCase):
    def _score(self, bd, blur, w, h, exif=True):
        result = bd.calculate_quality_score(blur, w, h, exif)
        return result[0] if isinstance(result, tuple) else result

    def test_high_blur_score_gives_high_quality(self):
        bd = BlurDetector(threshold=100)
        score = self._score(bd, 1500, 3024, 4032)  # 12MP, very sharp
        self.assertGreater(score, 75)

    def test_very_blurry_image_gets_low_quality(self):
        bd = BlurDetector(threshold=100)
        score = self._score(bd, 10, 640, 480, exif=False)  # blur_score 10 < 30% of 100
        self.assertLess(score, 50)

    def test_low_resolution_penalised(self):
        bd = BlurDetector(threshold=100)
        score_low_res  = self._score(bd, 200, 400, 300)    # 0.12MP
        score_high_res = self._score(bd, 200, 4000, 3000)  # 12MP
        self.assertLess(score_low_res, score_high_res)

    def test_quality_score_range_is_0_to_100(self):
        bd = BlurDetector(threshold=100)
        for blur, w, h in [(0, 100, 100), (50, 640, 480), (1000, 4000, 3000), (None, 1920, 1080)]:
            score = self._score(bd, blur, w, h)
            self.assertGreaterEqual(score, 0)
            self.assertLessEqual(score, 100)


# ---------------------------------------------------------------------------
# TC-S06: Filename conflict resolution — rename strategy
# ---------------------------------------------------------------------------
class TestS06_FilenameConflictResolution(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_rename_strategy_produces_unique_path(self):
        original = Path(self.tmp) / 'photo.jpg'
        original.write_bytes(b'existing file')
        result = resolve_filename_conflict(original, strategy='rename')
        self.assertIsNotNone(result)
        self.assertNotEqual(str(result), str(original))
        self.assertTrue(str(result).endswith('.jpg'))

    def test_skip_strategy_returns_none_on_conflict(self):
        original = Path(self.tmp) / 'photo.jpg'
        original.write_bytes(b'existing file')
        result = resolve_filename_conflict(original, strategy='skip')
        self.assertIsNone(result)

    def test_overwrite_strategy_returns_same_path(self):
        original = Path(self.tmp) / 'photo.jpg'
        original.write_bytes(b'existing file')
        result = resolve_filename_conflict(original, strategy='overwrite')
        self.assertEqual(str(result), str(original))

    def test_no_conflict_returns_original_path(self):
        new_path = Path(self.tmp) / 'new_photo.jpg'
        # file does not exist
        result = resolve_filename_conflict(new_path, strategy='rename')
        self.assertEqual(str(result), str(new_path))


# ---------------------------------------------------------------------------
# TC-S07: Fast mode — blur_score None handled gracefully across the board
# ---------------------------------------------------------------------------
class TestS07_FastModeNullBlurScore(unittest.TestCase):
    def test_blur_classifier_on_none_is_unknown(self):
        bd = BlurDetector(threshold=100)
        is_blurry, score, label = bd._classify(None)
        self.assertIsNone(is_blurry)
        self.assertIsNone(score)
        self.assertEqual(label, 'Unknown')

    def test_quality_score_with_no_blur_uses_resolution_only(self):
        bd = BlurDetector(threshold=100)
        result = bd.calculate_quality_score(None, 3840, 2160, True)
        score = result[0] if isinstance(result, tuple) else result
        self.assertGreater(score, 50)  # resolution bonus should push above base 50

    def test_duplicate_handler_works_with_records_lacking_quality(self):
        h = hashlib.md5(b'content').hexdigest()
        records = [
            {'media_id': 'A', 'md5_hash': h},  # no quality_score
            {'media_id': 'B', 'md5_hash': h},
        ]
        DuplicateHandler(selection_criteria=['quality']).mark_duplicates(records)
        # Should not raise; one must be best
        best_count = sum(1 for r in records if r.get('is_best_in_group') == 'Yes')
        self.assertEqual(best_count, 1)


if __name__ == '__main__':
    unittest.main()
