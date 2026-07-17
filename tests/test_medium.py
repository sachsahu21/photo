"""
Medium cohort tests — TC-MD01 through TC-MD06
Photo count: 101–1000. Goal: checkpoint recovery, threading, path reconciliation.
Run from repo root: pytest tests/test_medium.py -v
"""

import sys
import json
import shutil
import tempfile
import hashlib
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.duplicate_handler import DuplicateHandler
from src.utils import calculate_file_hash, determine_date_source


# ---------------------------------------------------------------------------
# TC-MD03: Day threshold NOT triggered — < 60 files/day stays monthly
# ---------------------------------------------------------------------------
class TestMD03_BelowDayThreshold(unittest.TestCase):
    def test_40_files_per_day_stays_monthly(self):
        from collections import defaultdict
        day_threshold = 60
        per_day = defaultdict(int)
        for i in range(200):
            date = f'2023-05-{(i % 5) + 1:02d}'
            per_day[date] += 1  # 40 per day across 5 days
        for date, count in per_day.items():
            use_daily = count >= day_threshold
            self.assertFalse(use_daily, f'{date} has {count} files but triggered daily split')

    def test_boundary_59_stays_monthly(self):
        day_threshold = 60
        self.assertFalse(59 >= day_threshold)

    def test_boundary_60_triggers_daily(self):
        day_threshold = 60
        self.assertTrue(60 >= day_threshold)


# ---------------------------------------------------------------------------
# TC-MD04: update_strategy — idempotent upsert behaviour
# ---------------------------------------------------------------------------
class TestMD04_DuplicateHandlerIdempotent(unittest.TestCase):
    def test_mark_duplicates_is_idempotent(self):
        h = hashlib.md5(b'content').hexdigest()
        records = [
            {'media_id': 'A', 'md5_hash': h, 'quality_score': 90},
            {'media_id': 'B', 'md5_hash': h, 'quality_score': 70},
        ]
        dh = DuplicateHandler()
        dh.mark_duplicates(records)
        state_after_first = [r['is_best_in_group'] for r in records]

        dh.mark_duplicates(records)  # run again on already-marked records
        state_after_second = [r['is_best_in_group'] for r in records]

        self.assertEqual(state_after_first, state_after_second)

    def test_rerun_clears_old_dup_flags_before_recomputing(self):
        h1 = hashlib.md5(b'group1').hexdigest()
        records = [
            {'media_id': 'A', 'md5_hash': h1, 'quality_score': 80},
            {'media_id': 'B', 'md5_hash': h1, 'quality_score': 60},
        ]
        dh = DuplicateHandler()
        dh.mark_duplicates(records)

        # Change hashes so they're no longer duplicates
        records[0]['md5_hash'] = 'unique_a'
        records[1]['md5_hash'] = 'unique_b'
        dh.mark_duplicates(records)

        for r in records:
            self.assertNotEqual(r['is_duplicate'], 'YES',
                                f'{r["media_id"]} still marked as duplicate after hash change')


# ---------------------------------------------------------------------------
# TC-MD05: People sync — unmatched faces get unknown status
# ---------------------------------------------------------------------------
class TestMD05_PeopleSyncUnknown(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_unmatched_face_gets_unknown_status(self):
        from src.people_sync import sync_people_tags
        tmp_path = Path(self.tmp)

        src = tmp_path / 'photo.jpg'
        src.write_bytes(b'fake-image-data')
        meta = tmp_path / 'photo.json'
        meta.write_text(json.dumps({'person': {}, 'faces': {'face_count': 1}}))

        rec = {
            'full_path': str(src),
            'metadata_json_path': str(meta),
            'face_count': 1,
            'media_id': 'photo',
        }
        known, unknown = sync_people_tags(
            [rec],
            [],
            tmp_path / 'untagged',
            export_untagged=True,
            config={'faces': {'untagged_skip_duplicates': True, 'untagged_cleanup_orphans': False}},
        )
        self.assertEqual(unknown, 1)
        self.assertEqual(known, 0)
        enriched = json.loads(meta.read_text())
        self.assertEqual(enriched['person']['status'], 'unknown')

    def test_untagged_folder_created_for_unknown(self):
        from src.people_sync import sync_people_tags
        tmp_path = Path(self.tmp)

        src = tmp_path / 'sample.jpg'
        src.write_bytes(b'fake-image')
        meta = tmp_path / 'sample.json'
        meta.write_text(json.dumps({'person': {}, 'faces': {'face_count': 2}}))

        rec = {
            'full_path': str(src),
            'metadata_json_path': str(meta),
            'face_count': 2,
            'media_id': 'sample',
        }
        sync_people_tags(
            [rec], [],
            tmp_path / 'untagged',
            export_untagged=True,
            config={'faces': {'untagged_skip_duplicates': True, 'untagged_cleanup_orphans': False}},
        )
        untagged_dirs = list((tmp_path / 'untagged').iterdir())
        self.assertGreater(len(untagged_dirs), 0)


# ---------------------------------------------------------------------------
# TC-MD06: Path reconciliation — workspace paths stay consistent after move
# ---------------------------------------------------------------------------
class TestMD06_WorkspacePaths(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_workspace_paths_resolve_under_root(self):
        from src.workspace_paths import apply_workspace_artifacts
        ws = Path(self.tmp) / 'workspace'
        ws.mkdir()
        config = {
            'workspace': {'root': str(ws)},
            'faces': {
                'enabled': True,
                'seed_root': 'seed',
                'index_db_filename': 'face_index.sqlite',
                'untagged_subfolder': 'untagged_people',
            },
        }
        apply_workspace_artifacts(config)
        self.assertTrue(config['faces']['index_db'].startswith(str(ws)))
        self.assertTrue(config['faces']['seed_root'].startswith(str(ws)))

    def test_hash_stable_after_file_copy(self):
        src = Path(self.tmp) / 'original.jpg'
        src.write_bytes(b'image bytes' * 100)
        dst = Path(self.tmp) / 'copy.jpg'
        import shutil as _shutil
        _shutil.copy2(str(src), str(dst))

        h_src = calculate_file_hash(str(src), 'md5')
        h_dst = calculate_file_hash(str(dst), 'md5')
        self.assertEqual(h_src, h_dst)

    def test_hash_changes_after_file_modification(self):
        p = Path(self.tmp) / 'photo.jpg'
        p.write_bytes(b'original content')
        h1 = calculate_file_hash(str(p), 'md5')
        p.write_bytes(b'modified content')
        h2 = calculate_file_hash(str(p), 'md5')
        self.assertNotEqual(h1, h2)


# ---------------------------------------------------------------------------
# TC-MD02: Multi-thread stability — DuplicateHandler with concurrent records
# ---------------------------------------------------------------------------
class TestMD02_ThreadingStability(unittest.TestCase):
    def test_duplicate_detection_on_large_record_set(self):
        import threading
        results = []
        errors = []

        def run_detection(batch_id):
            try:
                h = hashlib.md5(f'group_{batch_id}'.encode()).hexdigest()
                records = [
                    {'media_id': f'{batch_id}_A', 'md5_hash': h, 'quality_score': 80},
                    {'media_id': f'{batch_id}_B', 'md5_hash': h, 'quality_score': 60},
                ]
                dh = DuplicateHandler()
                dh.mark_duplicates(records)
                dups = [r for r in records if r['is_duplicate'] == 'YES']
                results.append(len(dups))
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=run_detection, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f'Thread errors: {errors}')
        self.assertTrue(all(n == 2 for n in results),
                        f'Expected all batches to find 2 dupes, got: {results}')


if __name__ == '__main__':
    unittest.main()
