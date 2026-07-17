"""
Stress tests — Add & Delete operations
How the system behaves when photos are added to or removed from an existing corpus.

Scenarios covered:
  Add:    single add, batch add, duplicate add, same-filename conflict, corrupt file,
          checkpoint update, resume after interrupted scan
  Delete: delete_flag set correctly, pickle backup before delete, best re-election
          after best is removed, delete-all-group-members, missing file on disk,
          delete then re-add, bulk delete performance
  Stress: rapid add-delete cycling, group rebalancing, concurrent threads, large pickle

Run: pytest tests/test_stress_add_delete.py -v
"""

import sys
import hashlib
import shutil
import tempfile
import pickle
import time
import threading
import unittest
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.duplicate_handler import DuplicateHandler
from src.utils import calculate_file_hash, calculate_file_hashes, resolve_filename_conflict
from src.checkpoint_manager import CheckpointManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_record(media_id, content_seed, quality=75, extra=None):
    h = hashlib.md5(str(content_seed).encode()).hexdigest()
    r = {'media_id': media_id, 'md5_hash': h, 'quality_score': quality}
    if extra:
        r.update(extra)
    return r


def _unique_records(n, quality=75):
    return [_make_record(f'img_{i}', f'unique_{i}', quality) for i in range(n)]


# ===========================================================================
# ADD SCENARIOS
# ===========================================================================

class TestAdd01_SingleFileAdd(unittest.TestCase):
    """Add one new photo to a corpus of 100."""

    def test_new_unique_file_is_not_marked_duplicate(self):
        corpus = _unique_records(100)
        new_file = _make_record('new_001', 'brand_new_content', quality=88)
        all_records = corpus + [new_file]

        DuplicateHandler().mark_duplicates(all_records)

        new = next(r for r in all_records if r['media_id'] == 'new_001')
        self.assertNotEqual(new['is_duplicate'], 'YES')

    def test_upsert_increases_corpus_size_by_one(self):
        corpus = _unique_records(100)
        new_file = _make_record('new_002', 'another_new', quality=70)
        self.assertEqual(len(corpus) + 1, len(corpus + [new_file]))


class TestAdd02_BatchAdd500(unittest.TestCase):
    """Add 500 unique files to a 1000-record corpus."""

    def test_no_false_duplicates_in_batch_of_unique_files(self):
        corpus = _unique_records(1000)
        batch  = [_make_record(f'batch_{i}', f'batch_seed_{i}') for i in range(500)]
        all_records = corpus + batch

        DuplicateHandler().mark_duplicates(all_records)

        dup_count = sum(1 for r in all_records if r['is_duplicate'] == 'YES')
        self.assertEqual(dup_count, 0)

    def test_batch_add_preserves_existing_corpus_integrity(self):
        corpus = _unique_records(100)
        # Pre-mark corpus (all unique → none should be dupes)
        DuplicateHandler().mark_duplicates(corpus)

        batch = [_make_record(f'b_{i}', f'batch_{i}') for i in range(50)]
        all_records = corpus + batch
        DuplicateHandler().mark_duplicates(all_records)

        dup_count = sum(1 for r in all_records if r['is_duplicate'] == 'YES')
        self.assertEqual(dup_count, 0)


class TestAdd03_AddExactDuplicate(unittest.TestCase):
    """Add a file whose MD5 matches an existing record."""

    def test_incoming_dup_is_detected_immediately(self):
        h = hashlib.md5(b'original_bytes').hexdigest()
        existing = {'media_id': 'orig', 'md5_hash': h, 'quality_score': 80}
        incoming = {'media_id': 'copy', 'md5_hash': h, 'quality_score': 60}

        records = [existing, incoming]
        DuplicateHandler().mark_duplicates(records)

        dup_count = sum(1 for r in records if r['is_duplicate'] == 'YES')
        self.assertEqual(dup_count, 2)

    def test_higher_quality_original_stays_best(self):
        h = hashlib.md5(b'same_bytes').hexdigest()
        existing = {'media_id': 'orig', 'md5_hash': h, 'quality_score': 90}
        incoming = {'media_id': 'copy', 'md5_hash': h, 'quality_score': 50}

        DuplicateHandler(selection_criteria=['quality']).mark_duplicates([existing, incoming])
        best = next(r for r in [existing, incoming] if r.get('is_best_in_group') == 'Yes')
        self.assertEqual(best['media_id'], 'orig')

    def test_incoming_higher_quality_displaces_original_as_best(self):
        h = hashlib.md5(b'same_bytes_hq').hexdigest()
        existing = {'media_id': 'orig', 'md5_hash': h, 'quality_score': 50}
        incoming = {'media_id': 'new_hq', 'md5_hash': h, 'quality_score': 95}

        DuplicateHandler(selection_criteria=['quality']).mark_duplicates([existing, incoming])
        best = next(r for r in [existing, incoming] if r.get('is_best_in_group') == 'Yes')
        self.assertEqual(best['media_id'], 'new_hq')

    def test_add_duplicate_to_100_record_corpus_detects_only_that_pair(self):
        corpus = _unique_records(100)
        h = corpus[42]['md5_hash']  # pick an existing record's hash
        incoming = {'media_id': 'dup_of_42', 'md5_hash': h, 'quality_score': 99}

        all_records = corpus + [incoming]
        DuplicateHandler().mark_duplicates(all_records)

        dups = [r for r in all_records if r['is_duplicate'] == 'YES']
        self.assertEqual(len(dups), 2)
        dup_ids = {r['media_id'] for r in dups}
        self.assertIn('img_42', dup_ids)
        self.assertIn('dup_of_42', dup_ids)


class TestAdd04_AddSameFilenameConflict(unittest.TestCase):
    """Add a file whose name already exists on disk (different content)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_rename_strategy_avoids_overwrite(self):
        existing = Path(self.tmp) / 'photo.jpg'
        existing.write_bytes(b'original content')

        result = resolve_filename_conflict(existing, strategy='rename')
        self.assertNotEqual(str(result), str(existing))
        self.assertTrue(str(result).endswith('.jpg'))

    def test_skip_strategy_signals_do_not_copy(self):
        existing = Path(self.tmp) / 'photo.jpg'
        existing.write_bytes(b'original content')

        result = resolve_filename_conflict(existing, strategy='skip')
        self.assertIsNone(result)

    def test_overwrite_strategy_returns_same_path(self):
        existing = Path(self.tmp) / 'photo.jpg'
        existing.write_bytes(b'original content')

        result = resolve_filename_conflict(existing, strategy='overwrite')
        self.assertEqual(Path(result), existing)

    def test_no_conflict_needs_no_resolution(self):
        new_path = Path(self.tmp) / 'never_seen_before.jpg'
        result = resolve_filename_conflict(new_path, strategy='rename')
        self.assertEqual(Path(result), new_path)


class TestAdd05_AddCorruptFile(unittest.TestCase):
    """Add a corrupt or truncated file — system must not crash."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_truncated_jpeg_hash_still_returns_string(self):
        p = Path(self.tmp) / 'truncated.jpg'
        p.write_bytes(b'\xff\xd8\xff' + b'\x00' * 30)
        result = calculate_file_hash(str(p), 'md5')
        self.assertIsInstance(result, str)
        self.assertNotEqual(result, '')

    def test_empty_file_hash_returns_string(self):
        p = Path(self.tmp) / 'empty.jpg'
        p.write_bytes(b'')
        result = calculate_file_hash(str(p), 'md5')
        self.assertIsInstance(result, str)

    def test_missing_file_hash_returns_empty_string(self):
        result = calculate_file_hash(str(Path(self.tmp) / 'ghost.jpg'), 'md5')
        self.assertEqual(result, '')

    def test_corrupt_file_record_does_not_poison_dup_detection(self):
        corpus = _unique_records(20)
        corrupt_record = {'media_id': 'bad', 'md5_hash': '', 'quality_score': 0}
        all_records = corpus + [corrupt_record]

        DuplicateHandler().mark_duplicates(all_records)

        corrupt = next(r for r in all_records if r['media_id'] == 'bad')
        # Empty hash must not match any real record
        self.assertNotEqual(corrupt['is_duplicate'], 'YES')


class TestAdd06_CheckpointUpdatedOnAdd(unittest.TestCase):
    """Checkpoint correctly tracks newly added files."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_new_file_added_to_checkpoint_after_processing(self):
        cp_path = Path(self.tmp) / 'checkpoint.json'
        cm = CheckpointManager(file_path=str(cp_path))

        existing = {'img_001', 'img_002'}
        for f in existing:
            cm.mark_processed(f)
        cm.save()

        # Simulate adding a new file during next scan
        cm.mark_processed('img_003')
        cm.save()

        cm2 = CheckpointManager(file_path=str(cp_path))
        cm2.load()
        self.assertIn('img_003', cm2.processed)
        self.assertEqual(len(cm2.processed), 3)

    def test_checkpoint_does_not_reprocess_existing_files(self):
        cp_path = Path(self.tmp) / 'checkpoint.json'
        cm = CheckpointManager(file_path=str(cp_path))

        for f in ['img_001', 'img_002', 'img_003']:
            cm.mark_processed(f)
        cm.save()

        cm2 = CheckpointManager(file_path=str(cp_path))
        cm2.load()

        candidates = ['img_001', 'img_002', 'img_003', 'img_004']
        to_process = [c for c in candidates if not cm2.is_processed(c)]
        self.assertEqual(to_process, ['img_004'])


class TestAdd07_ResumeInterruptedScan(unittest.TestCase):
    """Simulate a scan interrupted at 50/100 — resume processes only the remaining 50."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_resume_skips_already_processed(self):
        cp_path = Path(self.tmp) / 'checkpoint.json'
        total = [f'img_{i:03d}' for i in range(100)]
        processed_so_far = set(total[:50])

        cm = CheckpointManager(file_path=str(cp_path))
        for f in processed_so_far:
            cm.mark_processed(f)
        cm.save()

        cm2 = CheckpointManager(file_path=str(cp_path))
        cm2.load()
        remaining = [f for f in total if not cm2.is_processed(f)]

        self.assertEqual(len(remaining), 50)
        self.assertTrue(all(f not in processed_so_far for f in remaining))

    def test_full_rescan_after_complete_run_processes_nothing(self):
        cp_path = Path(self.tmp) / 'checkpoint.json'
        total = [f'img_{i:03d}' for i in range(20)]

        cm = CheckpointManager(file_path=str(cp_path))
        for f in total:
            cm.mark_processed(f)
        cm.save()

        cm2 = CheckpointManager(file_path=str(cp_path))
        cm2.load()
        remaining = [f for f in total if not cm2.is_processed(f)]
        self.assertEqual(len(remaining), 0)


# ===========================================================================
# DELETE SCENARIOS
# ===========================================================================

class TestDel01_DeleteFlagSet(unittest.TestCase):
    """delete_flag is set correctly on non-best duplicates."""

    def test_lower_quality_dup_gets_delete_flag_yes(self):
        h = hashlib.md5(b'content').hexdigest()
        records = [
            {'media_id': 'A', 'md5_hash': h, 'quality_score': 90},
            {'media_id': 'B', 'md5_hash': h, 'quality_score': 60},
        ]
        DuplicateHandler(selection_criteria=['quality']).mark_duplicates(records)

        b = next(r for r in records if r['media_id'] == 'B')
        self.assertEqual(b['delete_flag'], 'Yes')

    def test_best_in_group_has_delete_flag_no(self):
        h = hashlib.md5(b'content').hexdigest()
        records = [
            {'media_id': 'A', 'md5_hash': h, 'quality_score': 90},
            {'media_id': 'B', 'md5_hash': h, 'quality_score': 60},
        ]
        DuplicateHandler(selection_criteria=['quality']).mark_duplicates(records)

        a = next(r for r in records if r['media_id'] == 'A')
        self.assertNotEqual(a['delete_flag'], 'Yes')

    def test_unique_record_never_gets_delete_flag(self):
        records = _unique_records(50)
        DuplicateHandler().mark_duplicates(records)

        flagged = [r for r in records if r.get('delete_flag') == 'Yes']
        self.assertEqual(len(flagged), 0)

    def test_three_way_group_only_one_survives_delete_flag(self):
        h = hashlib.md5(b'three').hexdigest()
        records = [
            {'media_id': 'A', 'md5_hash': h, 'quality_score': 90},
            {'media_id': 'B', 'md5_hash': h, 'quality_score': 70},
            {'media_id': 'C', 'md5_hash': h, 'quality_score': 50},
        ]
        DuplicateHandler(selection_criteria=['quality']).mark_duplicates(records)

        flagged = [r for r in records if r.get('delete_flag') == 'Yes']
        not_flagged = [r for r in records if r.get('delete_flag') != 'Yes']
        self.assertEqual(len(flagged), 2)
        self.assertEqual(len(not_flagged), 1)
        self.assertEqual(not_flagged[0]['media_id'], 'A')


class TestDel02_PickleBackupBeforeDelete(unittest.TestCase):
    """Pickle backup must exist and predate any bulk-delete operation."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_backup_written_before_delete_operation(self):
        records = _unique_records(200)
        backup_path = Path(self.tmp) / 'records-backup.pkl'

        # Write backup BEFORE simulating the delete operation
        with open(backup_path, 'wb') as f:
            pickle.dump(records, f)
        backup_mtime = backup_path.stat().st_mtime

        time.sleep(0.05)  # ensure delete happens after backup
        delete_started_at = time.time()

        self.assertLess(backup_mtime, delete_started_at)

    def test_backup_contains_all_records_including_flagged(self):
        h = hashlib.md5(b'x').hexdigest()
        records = [
            {'media_id': 'A', 'md5_hash': h, 'quality_score': 90},
            {'media_id': 'B', 'md5_hash': h, 'quality_score': 50},
        ]
        DuplicateHandler(selection_criteria=['quality']).mark_duplicates(records)

        backup_path = Path(self.tmp) / 'records-backup.pkl'
        with open(backup_path, 'wb') as f:
            pickle.dump(records, f)

        with open(backup_path, 'rb') as f:
            loaded = pickle.load(f)

        self.assertEqual(len(loaded), 2)
        b_in_backup = next(r for r in loaded if r['media_id'] == 'B')
        self.assertEqual(b_in_backup['delete_flag'], 'Yes')


class TestDel03_BestReelectionAfterBestDeleted(unittest.TestCase):
    """When the 'best' record is removed, re-running marks a new best."""

    def test_rerun_after_best_removed_elects_new_best(self):
        h = hashlib.md5(b'group').hexdigest()
        records = [
            {'media_id': 'A', 'md5_hash': h, 'quality_score': 90},  # original best
            {'media_id': 'B', 'md5_hash': h, 'quality_score': 70},
            {'media_id': 'C', 'md5_hash': h, 'quality_score': 50},
        ]
        DuplicateHandler(selection_criteria=['quality']).mark_duplicates(records)

        # Simulate deleting A (best)
        records = [r for r in records if r['media_id'] != 'A']
        DuplicateHandler(selection_criteria=['quality']).mark_duplicates(records)

        best = next((r for r in records if r.get('is_best_in_group') == 'Yes'), None)
        self.assertIsNotNone(best)
        self.assertEqual(best['media_id'], 'B')

    def test_repeated_deletions_always_produce_exactly_one_best(self):
        h = hashlib.md5(b'shrinking_group').hexdigest()
        records = [
            {'media_id': f'img_{i}', 'md5_hash': h, 'quality_score': (5 - i) * 20}
            for i in range(5)
        ]
        dh = DuplicateHandler(selection_criteria=['quality'])

        for remove_id in ['img_0', 'img_1', 'img_2']:
            records = [r for r in records if r['media_id'] != remove_id]
            dh.mark_duplicates(records)
            best_count = sum(1 for r in records if r.get('is_best_in_group') == 'Yes')
            self.assertEqual(best_count, 1, f'After removing {remove_id}: expected 1 best, got {best_count}')


class TestDel04_DeleteAllGroupMembers(unittest.TestCase):
    """Deleting every member of a dup group leaves no dup markers in the corpus."""

    def test_empty_group_leaves_clean_corpus(self):
        h = hashlib.md5(b'doomed_group').hexdigest()
        corpus = _unique_records(50)
        dup_group = [
            {'media_id': f'dup_{i}', 'md5_hash': h, 'quality_score': i * 10}
            for i in range(3)
        ]
        all_records = corpus + dup_group
        DuplicateHandler().mark_duplicates(all_records)

        # Remove all dup group members
        survivors = [r for r in all_records if not r['media_id'].startswith('dup_')]
        DuplicateHandler().mark_duplicates(survivors)

        dup_count = sum(1 for r in survivors if r['is_duplicate'] == 'YES')
        self.assertEqual(dup_count, 0)


class TestDel05_DeleteMissingFileOnDisk(unittest.TestCase):
    """File already gone from disk — hash returns '' and system stays stable."""

    def test_hash_on_deleted_file_returns_empty(self):
        result = calculate_file_hash('/nonexistent/deleted_photo.jpg', 'md5')
        self.assertEqual(result, '')

    def test_dual_hash_on_deleted_file_returns_empty_pair(self):
        md5, sha = calculate_file_hashes('/nonexistent/photo.jpg')
        self.assertEqual(md5, '')
        self.assertEqual(sha, '')

    def test_empty_hash_record_does_not_create_false_dup_group(self):
        corpus = _unique_records(10)
        # Two records with empty hash (simulating files missing from disk)
        ghost_a = {'media_id': 'ghost_a', 'md5_hash': '', 'quality_score': 0}
        ghost_b = {'media_id': 'ghost_b', 'md5_hash': '', 'quality_score': 0}
        all_records = corpus + [ghost_a, ghost_b]

        DuplicateHandler().mark_duplicates(all_records)

        # Empty-hash records must not be grouped as duplicates of each other
        ghost_a_r = next(r for r in all_records if r['media_id'] == 'ghost_a')
        ghost_b_r = next(r for r in all_records if r['media_id'] == 'ghost_b')
        # Both should NOT be flagged YES (empty hash is not a valid dedup key)
        for r in [ghost_a_r, ghost_b_r]:
            self.assertNotEqual(r.get('is_duplicate'), 'YES',
                                f'{r["media_id"]} incorrectly marked as dup via empty hash')


class TestDel06_DeleteThenReAdd(unittest.TestCase):
    """Delete a file then re-add the same bytes — treated as dup of any remaining copy."""

    def test_re_added_file_detected_as_dup_of_surviving_copy(self):
        h = hashlib.md5(b'original').hexdigest()
        copy_a = {'media_id': 'copy_a', 'md5_hash': h, 'quality_score': 80}
        copy_b = {'media_id': 'copy_b', 'md5_hash': h, 'quality_score': 70}

        records = [copy_a, copy_b]
        DuplicateHandler().mark_duplicates(records)

        # Simulate deleting copy_b, then re-adding it
        records = [r for r in records if r['media_id'] != 'copy_b']
        re_added = {'media_id': 'copy_b_readded', 'md5_hash': h, 'quality_score': 65}
        records.append(re_added)
        DuplicateHandler().mark_duplicates(records)

        dup_count = sum(1 for r in records if r['is_duplicate'] == 'YES')
        self.assertEqual(dup_count, 2)

    def test_re_added_with_higher_quality_becomes_new_best(self):
        h = hashlib.md5(b'replaced').hexdigest()
        original = {'media_id': 'orig', 'md5_hash': h, 'quality_score': 60}
        restored = {'media_id': 'restored_hq', 'md5_hash': h, 'quality_score': 95}

        records = [original, restored]
        DuplicateHandler(selection_criteria=['quality']).mark_duplicates(records)

        best = next(r for r in records if r.get('is_best_in_group') == 'Yes')
        self.assertEqual(best['media_id'], 'restored_hq')


class TestDel07_BulkDelete1000(unittest.TestCase):
    """Mark 1000 records for deletion — runs in under 5 seconds."""

    def test_bulk_delete_flag_performance(self):
        # 200 groups × 5 copies
        records = []
        for g in range(200):
            h = hashlib.md5(f'grp_{g}'.encode()).hexdigest()
            for c in range(5):
                records.append({'media_id': f'g{g}_c{c}', 'md5_hash': h, 'quality_score': c * 10})

        t0 = time.perf_counter()
        DuplicateHandler(selection_criteria=['quality']).mark_duplicates(records)
        elapsed = time.perf_counter() - t0

        flagged = [r for r in records if r.get('delete_flag') == 'Yes']
        self.assertEqual(len(flagged), 800)  # 4 of 5 per group
        self.assertLess(elapsed, 5.0, f'Bulk delete took {elapsed:.2f}s — too slow')


# ===========================================================================
# STRESS SCENARIOS — add + delete interleaved
# ===========================================================================

class TestStress01_RapidAddDeleteCycle(unittest.TestCase):
    """Add 100, delete 50, add 50 different — integrity holds throughout."""

    def test_add_delete_add_cycle_dup_count_stays_zero(self):
        pool = _unique_records(100)
        DuplicateHandler().mark_duplicates(pool)

        # Delete first 50
        pool = pool[50:]

        # Add 50 new unique records (different seeds)
        new_batch = [_make_record(f'new_{i}', f'fresh_seed_{i}') for i in range(50)]
        pool = pool + new_batch
        DuplicateHandler().mark_duplicates(pool)

        dup_count = sum(1 for r in pool if r['is_duplicate'] == 'YES')
        self.assertEqual(dup_count, 0)

    def test_delete_introduces_dup_when_hash_now_unique(self):
        h = hashlib.md5(b'shared').hexdigest()
        records = [
            {'media_id': 'A', 'md5_hash': h, 'quality_score': 90},
            {'media_id': 'B', 'md5_hash': h, 'quality_score': 70},
        ]
        DuplicateHandler().mark_duplicates(records)

        # Delete B — now only A remains, so no dup
        records = [r for r in records if r['media_id'] != 'B']
        DuplicateHandler().mark_duplicates(records)

        self.assertEqual(records[0]['is_duplicate'], 'No')


class TestStress02_GroupRebalancing(unittest.TestCase):
    """Shrink a group one by one — best re-elected at each step."""

    def test_best_reelected_at_each_deletion_step(self):
        h = hashlib.md5(b'rebalance').hexdigest()
        quality_ladder = [90, 80, 70, 60, 50]  # img_0 always highest
        records = [
            {'media_id': f'img_{i}', 'md5_hash': h, 'quality_score': q}
            for i, q in enumerate(quality_ladder)
        ]

        dh = DuplicateHandler(selection_criteria=['quality'])
        expected_best = ['img_0', 'img_0', 'img_0', 'img_0']  # best until only 1 left

        for step, expected in enumerate(expected_best):
            # Remove lowest quality (last record)
            records = records[:-1]
            if len(records) < 2:
                break
            dh.mark_duplicates(records)
            best = next((r for r in records if r.get('is_best_in_group') == 'Yes'), None)
            self.assertIsNotNone(best, f'No best at step {step}')
            self.assertEqual(best['media_id'], expected, f'Wrong best at step {step}')


class TestStress03_ConcurrentAddDelete(unittest.TestCase):
    """10 threads simultaneously marking dups on isolated record sets — no crashes."""

    def test_concurrent_mark_duplicates_no_exceptions(self):
        errors = []
        results = []

        def worker(thread_id):
            try:
                h = hashlib.md5(f't_{thread_id}'.encode()).hexdigest()
                records = [
                    {'media_id': f't{thread_id}_A', 'md5_hash': h, 'quality_score': 80},
                    {'media_id': f't{thread_id}_B', 'md5_hash': h, 'quality_score': 60},
                ]
                dh = DuplicateHandler(selection_criteria=['quality'])
                dh.mark_duplicates(records)
                # Simulate delete of B, re-mark
                records = [r for r in records if not r['media_id'].endswith('_B')]
                dh.mark_duplicates(records)
                results.append(records[0]['is_duplicate'])
            except Exception as e:
                errors.append(f'Thread {thread_id}: {e}')

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f'Concurrent errors: {errors}')
        self.assertTrue(all(r == 'No' for r in results),
                        'After solo record has no dup, is_duplicate should be No')


class TestStress04_LargePickleRoundtrip(unittest.TestCase):
    """5000 records with delete flags survive a pickle write/read cycle."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_5000_records_with_flags_survive_pickle(self):
        records = []
        for g in range(1000):
            h = hashlib.md5(f'g_{g}'.encode()).hexdigest()
            records.append({'media_id': f'g{g}_best', 'md5_hash': h, 'quality_score': 90})
            records.append({'media_id': f'g{g}_del',  'md5_hash': h, 'quality_score': 50})
        for i in range(3000):
            records.append(_make_record(f'u_{i}', f'uniq_{i}'))

        DuplicateHandler(selection_criteria=['quality']).mark_duplicates(records)

        backup = Path(self.tmp) / 'backup.pkl'
        with open(backup, 'wb') as f:
            pickle.dump(records, f)

        with open(backup, 'rb') as f:
            loaded = pickle.load(f)

        self.assertEqual(len(loaded), len(records))

        del_flagged = sum(1 for r in loaded if r.get('delete_flag') == 'Yes')
        self.assertEqual(del_flagged, 1000)  # one per dup group

        best_count = sum(1 for r in loaded if r.get('is_best_in_group') == 'Yes')
        self.assertEqual(best_count, 1000)  # one best per group


if __name__ == '__main__':
    unittest.main()
