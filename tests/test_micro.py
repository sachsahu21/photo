"""
Micro cohort tests — TC-M01 through TC-M06
Photo count: 1–10 photos. Goal: core correctness, one assumption per test.
Run from repo root: pytest tests/test_micro.py -v
"""

import sys
import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils import (
    calculate_file_hash,
    calculate_file_hashes,
    determine_date_source,
    parse_exif_date,
)
from src.duplicate_handler import DuplicateHandler
from src.blur_detector import BlurDetector


# ---------------------------------------------------------------------------
# TC-M01: Single JPEG with valid EXIF — date_source priority
# ---------------------------------------------------------------------------
class TestM01_ExifDateSource(unittest.TestCase):
    def test_exif_date_takes_priority(self):
        record = {
            'date_taken': '2023:05:14 12:30:00',
            'file_modified': '2024-01-10 09:00:00',
            'has_exif': True,
        }
        self.assertEqual(determine_date_source(record), 'EXIF')

    def test_file_modified_used_when_no_exif_date(self):
        record = {
            'date_taken': None,
            'file_modified': '2024-01-10 09:00:00',
            'has_exif': False,
        }
        self.assertEqual(determine_date_source(record), 'File Modified')

    def test_none_returned_when_both_absent(self):
        record = {'date_taken': None, 'file_modified': None, 'has_exif': False}
        self.assertEqual(determine_date_source(record), 'None')

    def test_parse_exif_date_priority_order(self):
        # DateTimeOriginal wins over DateTime
        exif = {
            'DateTimeOriginal': '2023:05:14 12:30:00',
            'DateTime': '2022:01:01 00:00:00',
        }
        result = parse_exif_date(exif)
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2023)
        self.assertEqual(result.month, 5)
        self.assertEqual(result.day, 14)

    def test_parse_exif_date_returns_none_for_empty(self):
        self.assertIsNone(parse_exif_date({}))
        self.assertIsNone(parse_exif_date({'DateTimeOriginal': ''}))


# ---------------------------------------------------------------------------
# TC-M02: PNG without EXIF — fallback to file_modified
# ---------------------------------------------------------------------------
class TestM02_NoExifFallback(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_file_with_no_exif_date_falls_back(self):
        record = {
            'date_taken': '',
            'file_modified': '2024-06-15 08:00:00',
            'has_exif': False,
        }
        source = determine_date_source(record)
        self.assertEqual(source, 'File Modified')

    def test_calculate_hash_works_on_plain_png_bytes(self):
        # Minimal 1×1 white PNG (89 bytes, no EXIF)
        png_bytes = (
            b'\x89PNG\r\n\x1a\n'
            b'\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx'
            b'\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00'
            b'\x00\x00IEND\xaeB`\x82'
        )
        p = Path(self.tmp) / 'pixel.png'
        p.write_bytes(png_bytes)
        h = calculate_file_hash(str(p), 'md5')
        self.assertNotEqual(h, '')
        self.assertEqual(len(h), 32)


# ---------------------------------------------------------------------------
# TC-M03: Corrupt file — hash does not crash, scan should not fail hard
# ---------------------------------------------------------------------------
class TestM03_CorruptFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_hash_on_truncated_jpeg_header_returns_string(self):
        p = Path(self.tmp) / 'corrupt.jpg'
        p.write_bytes(b'\xff\xd8\xff' + b'\x00' * 50)  # partial JPEG header
        result = calculate_file_hash(str(p), 'md5')
        self.assertIsInstance(result, str)
        self.assertNotEqual(result, '')  # partial bytes still hashable

    def test_hash_of_garbage_bytes_returns_string(self):
        p = Path(self.tmp) / 'garbage.jpg'
        p.write_bytes(b'\x00\x01\x02' * 100)
        result = calculate_file_hash(str(p), 'sha256')
        self.assertIsInstance(result, str)
        self.assertEqual(len(result), 64)

    def test_hash_of_nonexistent_file_returns_empty(self):
        result = calculate_file_hash('/no/such/file.jpg', 'md5')
        self.assertEqual(result, '')


# ---------------------------------------------------------------------------
# TC-M04: Exact duplicate pair — MD5 match, best-selection logic
# ---------------------------------------------------------------------------
class TestM04_ExactDuplicates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._content = b'fake image payload ' * 50

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _make_file(self, name, content=None):
        p = Path(self.tmp) / name
        p.write_bytes(content or self._content)
        return str(p)

    def test_identical_files_produce_same_md5(self):
        p1 = self._make_file('img1.jpg')
        p2 = self._make_file('img2.jpg')
        self.assertEqual(
            calculate_file_hash(p1, 'md5'),
            calculate_file_hash(p2, 'md5'),
        )

    def test_different_files_produce_different_md5(self):
        p1 = self._make_file('img1.jpg', b'content_A' * 30)
        p2 = self._make_file('img2.jpg', b'content_B' * 30)
        self.assertNotEqual(
            calculate_file_hash(p1, 'md5'),
            calculate_file_hash(p2, 'md5'),
        )

    def test_duplicate_pair_both_marked_YES(self):
        h = hashlib.md5(self._content).hexdigest()
        records = [
            {'media_id': 'A', 'md5_hash': h, 'quality_score': 80, 'width': 640, 'height': 480},
            {'media_id': 'B', 'md5_hash': h, 'quality_score': 60, 'width': 640, 'height': 480},
            {'media_id': 'C', 'md5_hash': 'unique_hash_xyz', 'quality_score': 90},
        ]
        DuplicateHandler(hash_algorithm='md5', selection_criteria=['quality']).mark_duplicates(records)

        dups = [r for r in records if r['is_duplicate'] == 'YES']
        self.assertEqual(len(dups), 2)

    def test_higher_quality_score_wins_best_in_group(self):
        h = hashlib.md5(self._content).hexdigest()
        records = [
            {'media_id': 'A', 'md5_hash': h, 'quality_score': 80},
            {'media_id': 'B', 'md5_hash': h, 'quality_score': 60},
        ]
        DuplicateHandler(selection_criteria=['quality']).mark_duplicates(records)

        best = next(r for r in records if r.get('is_best_in_group') == 'Yes')
        self.assertEqual(best['media_id'], 'A')
        other = next(r for r in records if r['media_id'] == 'B')
        self.assertEqual(other['delete_flag'], 'Yes')

    def test_unique_file_not_marked_as_duplicate(self):
        h = hashlib.md5(self._content).hexdigest()
        records = [
            {'media_id': 'A', 'md5_hash': h, 'quality_score': 80},
            {'media_id': 'B', 'md5_hash': h, 'quality_score': 60},
            {'media_id': 'C', 'md5_hash': 'other', 'quality_score': 90},
        ]
        DuplicateHandler().mark_duplicates(records)
        unique = next(r for r in records if r['media_id'] == 'C')
        self.assertNotEqual(unique['is_duplicate'], 'YES')

    def test_group_label_format_is_MD5_prefix(self):
        h = hashlib.md5(self._content).hexdigest()
        records = [{'media_id': 'X', 'md5_hash': h}, {'media_id': 'Y', 'md5_hash': h}]
        groups = DuplicateHandler().find_duplicates(records)
        label = list(groups.keys())[0]
        self.assertTrue(label.startswith('MD5-'))
        self.assertEqual(len(label), 16)  # 'MD5-' + 12 hex chars


# ---------------------------------------------------------------------------
# TC-M05: Face size threshold (via BlurDetector as proxy for threshold gating)
# ---------------------------------------------------------------------------
class TestM05_ThresholdBoundaries(unittest.TestCase):
    def test_blur_score_below_30pct_threshold_is_very_blurry(self):
        bd = BlurDetector(threshold=100)
        is_blurry, _, label = bd._classify(29)
        self.assertTrue(is_blurry)
        self.assertEqual(label, 'Very Blurry')

    def test_blur_score_between_30_and_100pct_is_blurry(self):
        bd = BlurDetector(threshold=100)
        is_blurry, _, label = bd._classify(55)
        self.assertTrue(is_blurry)
        self.assertEqual(label, 'Blurry')

    def test_blur_score_at_threshold_is_not_blurry(self):
        bd = BlurDetector(threshold=100)
        is_blurry, _, _ = bd._classify(100)
        self.assertFalse(is_blurry)

    def test_none_input_returns_unknown(self):
        bd = BlurDetector(threshold=100)
        is_blurry, score, label = bd._classify(None)
        self.assertIsNone(is_blurry)
        self.assertIsNone(score)
        self.assertEqual(label, 'Unknown')

    def test_quality_score_handles_none_blur(self):
        bd = BlurDetector(threshold=100)
        result = bd.calculate_quality_score(None, 1920, 1080, True)
        score = result[0] if isinstance(result, tuple) else result
        self.assertIsNotNone(score)
        self.assertIsInstance(score, float)


# ---------------------------------------------------------------------------
# TC-M06: Invalid / non-existent config paths — no crash, workspace paths
# ---------------------------------------------------------------------------
class TestM06_InvalidConfigPath(unittest.TestCase):
    def test_workspace_path_construction_on_missing_root(self):
        from src.workspace_paths import apply_workspace_artifacts
        config = {
            'workspace': {'root': '/totally/fake/path/xyz'},
            'faces': {
                'enabled': False,
                'seed_root': 'seed',
                'index_db_filename': 'face_index.sqlite',
                'untagged_subfolder': 'untagged_people',
            },
        }
        try:
            apply_workspace_artifacts(config)
        except Exception as e:
            self.fail(f'apply_workspace_artifacts raised unexpectedly: {e}')

    def test_calculate_hash_on_nonexistent_path_returns_empty(self):
        # Scanner's hash call on missing file must return '' not raise
        result = calculate_file_hash('C:\\Does\\Not\\Exist\\photo.jpg', 'md5')
        self.assertEqual(result, '')

    def test_dual_hash_on_nonexistent_path_returns_empty_pair(self):
        md5, sha = calculate_file_hashes('C:\\Does\\Not\\Exist\\photo.jpg')
        self.assertEqual(md5, '')
        self.assertEqual(sha, '')


if __name__ == '__main__':
    unittest.main()
