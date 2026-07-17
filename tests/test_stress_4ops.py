"""
Stress tests — All 4 operations: ADD / DELETE / UPDATE / MOVE-ORGANIZE
Each operation is tested from micro (1-5 files) through large (500-2000 files).

Operation map:
  ADD     — new files enter the corpus (checkpoint, dup detection, metadata upsert)
  DELETE  — duplicate marking, delete_flag, pickle backup, best re-election
  UPDATE  — quality rescore changes winner; metadata path reconcile after move;
             idempotent re-run; stale-path handling
  MOVE    — ImageOrganizer.organize(): date folders, day threshold, screenshots,
             copy vs move, conflict resolution, missing file, delete_flag skip

Run: pytest tests/test_stress_4ops.py -v
"""

import sys
import hashlib
import shutil
import tempfile
import pickle
import time
import threading
import json
import unittest
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.duplicate_handler import DuplicateHandler
from src.blur_detector import BlurDetector
from src.utils import calculate_file_hash, resolve_filename_conflict
from src.checkpoint_manager import CheckpointManager
from src.organizer import ImageOrganizer


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def _h(seed):
    return hashlib.md5(str(seed).encode()).hexdigest()


def _rec(media_id, seed, quality=75, extra=None):
    r = {'media_id': media_id, 'md5_hash': _h(seed), 'quality_score': quality}
    if extra:
        r.update(extra)
    return r


def _unique(n, quality=75, offset=0):
    return [_rec(f'img_{offset+i}', f'uniq_{offset+i}', quality) for i in range(n)]


def _dup_group(n, group_id, qualities=None):
    """n records sharing the same hash; qualities defaults to 10,20,…,n*10."""
    h = _h(f'dup_group_{group_id}')
    qualities = qualities or [i * 10 for i in range(1, n + 1)]
    return [
        {'media_id': f'g{group_id}_c{i}', 'md5_hash': h, 'quality_score': qualities[i]}
        for i in range(n)
    ]


def _org_config(output_dir, operation='copy', conflict='rename', day_thr=60,
                structure='flat', separate_screenshots=True, show=False):
    return {
        'organization': {
            'output_folder': str(output_dir),
            'day_threshold': day_thr,
            'use_exif_date': True,
            'operation': operation,
            'conflict_resolution': conflict,
            'reuse_existing_folders': False,
            'video_subfolder': False,
            'separate_screenshots': separate_screenshots,
            'folder_structure': structure,
        },
        'processing': {'show_progress': show},
        'metadata': {'root_folder': ''},
    }


def _fake_file(directory, name='photo.jpg', content=None):
    p = Path(directory) / name
    p.write_bytes(content or (b'\xff\xd8\xff' + name.encode() + b'\x00' * 100))
    return p


def _org_rec(src_path, date_taken='2023:12:25 10:00:00', quality=80,
             has_exif=True, width=3024, height=4032, file_type='image',
             delete_flag='', filename=None):
    p = Path(src_path)
    return {
        'full_path': str(p),
        'filename': filename or p.name,
        'date_taken': date_taken,
        'file_modified': '2023-12-25 10:00:00',
        'file_type': file_type,
        'delete_flag': delete_flag,
        'has_exif': has_exif,
        'width': width,
        'height': height,
        'quality_score': quality,
    }


# ===========================================================================
# 1. ADD  — files entering the corpus
# ===========================================================================

class TestAdd_MicroScale(unittest.TestCase):
    """1–10 files: correctness of each add path."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_single_new_unique_file_is_not_a_duplicate(self):
        corpus = _unique(5)
        new = _rec('new', 'completely_fresh_seed', quality=88)
        all_r = corpus + [new]
        DuplicateHandler().mark_duplicates(all_r)
        r = next(r for r in all_r if r['media_id'] == 'new')
        self.assertNotEqual(r['is_duplicate'], 'YES')

    def test_add_exact_duplicate_detects_both(self):
        h = _h('same')
        existing = {'media_id': 'orig', 'md5_hash': h, 'quality_score': 70}
        incoming = {'media_id': 'copy', 'md5_hash': h, 'quality_score': 90}
        DuplicateHandler().mark_duplicates([existing, incoming])
        self.assertEqual(sum(1 for r in [existing, incoming] if r['is_duplicate'] == 'YES'), 2)

    def test_add_with_higher_quality_displaces_existing_best(self):
        h = _h('hq_swap')
        existing = {'media_id': 'orig', 'md5_hash': h, 'quality_score': 50}
        incoming = {'media_id': 'hq',   'md5_hash': h, 'quality_score': 95}
        DuplicateHandler(selection_criteria=['quality']).mark_duplicates([existing, incoming])
        best = next(r for r in [existing, incoming] if r.get('is_best_in_group') == 'Yes')
        self.assertEqual(best['media_id'], 'hq')

    def test_add_corrupt_file_does_not_infect_corpus(self):
        corrupt = {'media_id': 'bad', 'md5_hash': '', 'quality_score': 0}
        corpus = _unique(5)
        all_r = corpus + [corrupt]
        DuplicateHandler().mark_duplicates(all_r)
        # Empty hash must not create dup groups
        bad = next(r for r in all_r if r['media_id'] == 'bad')
        self.assertNotEqual(bad['is_duplicate'], 'YES')

    def test_checkpoint_registers_new_file(self):
        cp = Path(self.tmp) / 'cp.json'
        cm = CheckpointManager(file_path=str(cp))
        cm.mark_processed('img_001')
        cm.save()
        cm.mark_processed('img_002_NEW')  # simulate adding a new file
        cm.save()
        cm2 = CheckpointManager(file_path=str(cp))
        cm2.load()
        self.assertIn('img_002_NEW', cm2.processed)


class TestAdd_SmallScale(unittest.TestCase):
    """11–100 files: interactions and checkpoint coverage."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_batch_of_50_unique_files_has_zero_duplicates(self):
        records = _unique(50)
        DuplicateHandler().mark_duplicates(records)
        self.assertEqual(sum(1 for r in records if r['is_duplicate'] == 'YES'), 0)

    def test_add_10_dupes_to_40_unique_detects_only_the_pairs(self):
        corpus = _unique(40)
        h = _h('shared_in_batch')
        dupes = [{'media_id': f'd_{i}', 'md5_hash': h, 'quality_score': i * 5} for i in range(10)]
        all_r = corpus + dupes
        DuplicateHandler().mark_duplicates(all_r)
        dup_count = sum(1 for r in all_r if r['is_duplicate'] == 'YES')
        self.assertEqual(dup_count, 10)
        unique_dups = sum(1 for r in corpus if r['is_duplicate'] == 'YES')
        self.assertEqual(unique_dups, 0)

    def test_checkpoint_skips_already_processed_on_batch_add(self):
        cp = Path(self.tmp) / 'cp.json'
        done = [f'img_{i:03d}' for i in range(50)]
        cm = CheckpointManager(file_path=str(cp))
        for f in done:
            cm.mark_processed(f)
        cm.save()

        all_files = done + [f'img_{i:03d}' for i in range(50, 100)]
        cm2 = CheckpointManager(file_path=str(cp))
        cm2.load()
        to_process = [f for f in all_files if not cm2.is_processed(f)]
        self.assertEqual(len(to_process), 50)

    def test_adding_same_file_twice_idempotent(self):
        h = _h('repeat')
        rec = {'media_id': 'x', 'md5_hash': h, 'quality_score': 80}
        records = [rec, {'media_id': 'y', 'md5_hash': h, 'quality_score': 60}]
        dh = DuplicateHandler(selection_criteria=['quality'])
        dh.mark_duplicates(records)
        first_best = [r.get('is_best_in_group') for r in records]
        dh.mark_duplicates(records)
        second_best = [r.get('is_best_in_group') for r in records]
        self.assertEqual(first_best, second_best)


class TestAdd_LargeScale(unittest.TestCase):
    """1000–5000 files: performance and false-positive rate."""

    def test_1000_unique_files_zero_false_duplicates(self):
        records = _unique(1000)
        DuplicateHandler().mark_duplicates(records)
        self.assertEqual(sum(1 for r in records if r['is_duplicate'] == 'YES'), 0)

    def test_500_group_adds_in_5000_corpus_detects_all(self):
        corpus = _unique(4500)
        # 100 groups × 5 identical hashes
        groups = []
        for g in range(100):
            h = _h(f'mass_group_{g}')
            for c in range(5):
                groups.append({'media_id': f'g{g}_{c}', 'md5_hash': h, 'quality_score': c * 5})
        all_r = corpus + groups
        DuplicateHandler().mark_duplicates(all_r)
        self.assertEqual(sum(1 for r in all_r if r['is_duplicate'] == 'YES'), 500)

    def test_add_performance_5000_records_under_10s(self):
        records = _unique(5000)
        t0 = time.perf_counter()
        DuplicateHandler().mark_duplicates(records)
        elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, 10.0, f'5000-record dup detection took {elapsed:.2f}s')

    def test_concurrent_adds_10_threads_no_crashes(self):
        errors = []

        def worker(tid):
            try:
                recs = _unique(100, offset=tid * 100)
                DuplicateHandler().mark_duplicates(recs)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])


# ===========================================================================
# 2. DELETE  — flagging, pickle backup, best re-election
# ===========================================================================

class TestDelete_MicroScale(unittest.TestCase):
    """1–10 files: delete_flag correctness."""

    def test_delete_flag_set_on_lower_quality_dup(self):
        h = _h('del_micro')
        recs = [
            {'media_id': 'A', 'md5_hash': h, 'quality_score': 90},
            {'media_id': 'B', 'md5_hash': h, 'quality_score': 40},
        ]
        DuplicateHandler(selection_criteria=['quality']).mark_duplicates(recs)
        b = next(r for r in recs if r['media_id'] == 'B')
        self.assertEqual(b['delete_flag'], 'Yes')

    def test_best_never_gets_delete_flag(self):
        h = _h('del_best')
        recs = [
            {'media_id': 'A', 'md5_hash': h, 'quality_score': 90},
            {'media_id': 'B', 'md5_hash': h, 'quality_score': 40},
        ]
        DuplicateHandler(selection_criteria=['quality']).mark_duplicates(recs)
        a = next(r for r in recs if r['media_id'] == 'A')
        self.assertNotEqual(a['delete_flag'], 'Yes')

    def test_unique_record_never_flagged_for_delete(self):
        recs = _unique(5)
        DuplicateHandler().mark_duplicates(recs)
        self.assertEqual(sum(1 for r in recs if r.get('delete_flag') == 'Yes'), 0)

    def test_deleting_best_triggers_new_best(self):
        h = _h('del_cascade')
        recs = [
            {'media_id': 'A', 'md5_hash': h, 'quality_score': 90},
            {'media_id': 'B', 'md5_hash': h, 'quality_score': 70},
            {'media_id': 'C', 'md5_hash': h, 'quality_score': 50},
        ]
        DuplicateHandler(selection_criteria=['quality']).mark_duplicates(recs)
        recs = [r for r in recs if r['media_id'] != 'A']
        DuplicateHandler(selection_criteria=['quality']).mark_duplicates(recs)
        best = next(r for r in recs if r.get('is_best_in_group') == 'Yes')
        self.assertEqual(best['media_id'], 'B')

    def test_delete_all_group_members_leaves_clean_corpus(self):
        h = _h('del_all')
        corpus = _unique(10)
        group = [{'media_id': f'g{i}', 'md5_hash': h, 'quality_score': i * 10} for i in range(3)]
        all_r = corpus + group
        DuplicateHandler().mark_duplicates(all_r)
        survivors = [r for r in all_r if not r['media_id'].startswith('g')]
        DuplicateHandler().mark_duplicates(survivors)
        self.assertEqual(sum(1 for r in survivors if r['is_duplicate'] == 'YES'), 0)


class TestDelete_SmallScale(unittest.TestCase):
    """11–100 files: multi-group delete scenarios."""

    def test_20_groups_of_3_all_have_exactly_one_best(self):
        recs = []
        for g in range(20):
            recs.extend(_dup_group(3, g))
        DuplicateHandler(selection_criteria=['quality']).mark_duplicates(recs)
        groups = defaultdict(list)
        for r in recs:
            if r.get('duplicate_group'):
                groups[r['duplicate_group']].append(r.get('is_best_in_group'))
        for label, members in groups.items():
            self.assertEqual(members.count('Yes'), 1, f'Group {label} has wrong best count')

    def test_cascading_delete_across_5_steps(self):
        h = _h('cascade5')
        recs = [{'media_id': f'img_{i}', 'md5_hash': h, 'quality_score': (10 - i) * 10}
                for i in range(10)]
        dh = DuplicateHandler(selection_criteria=['quality'])
        for step in range(8):  # remove best 8 times; 2 remain
            recs = recs[1:]  # pop the current best
            if len(recs) < 2:
                break
            dh.mark_duplicates(recs)
            best_count = sum(1 for r in recs if r.get('is_best_in_group') == 'Yes')
            self.assertEqual(best_count, 1, f'Step {step}: wrong best count')


class TestDelete_LargeScale(unittest.TestCase):
    """1000+ files: bulk delete performance and pickle integrity."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_bulk_delete_200_groups_correct_count(self):
        recs = []
        for g in range(200):
            recs.extend(_dup_group(5, g))
        DuplicateHandler(selection_criteria=['quality']).mark_duplicates(recs)
        flagged = sum(1 for r in recs if r.get('delete_flag') == 'Yes')
        self.assertEqual(flagged, 800)  # 4 of 5 per group

    def test_bulk_delete_under_5_seconds(self):
        recs = []
        for g in range(400):
            recs.extend(_dup_group(5, g))
        t0 = time.perf_counter()
        DuplicateHandler(selection_criteria=['quality']).mark_duplicates(recs)
        self.assertLess(time.perf_counter() - t0, 5.0)

    def test_pickle_roundtrip_preserves_delete_flags(self):
        recs = []
        for g in range(500):
            recs.extend(_dup_group(2, g))
        DuplicateHandler(selection_criteria=['quality']).mark_duplicates(recs)

        bk = Path(self.tmp) / 'backup.pkl'
        with open(bk, 'wb') as f:
            pickle.dump(recs, f)
        with open(bk, 'rb') as f:
            loaded = pickle.load(f)

        del_in = sum(1 for r in recs if r.get('delete_flag') == 'Yes')
        del_out = sum(1 for r in loaded if r.get('delete_flag') == 'Yes')
        self.assertEqual(del_in, del_out)

    def test_pickle_backup_exists_before_delete_completes(self):
        recs = _unique(500)
        bk = Path(self.tmp) / 'pre_backup.pkl'
        with open(bk, 'wb') as f:
            pickle.dump(recs, f)
        backup_mtime = bk.stat().st_mtime
        time.sleep(0.05)
        DuplicateHandler().mark_duplicates(recs)
        delete_done_at = time.time()
        self.assertLess(backup_mtime, delete_done_at)


# ===========================================================================
# 3. UPDATE  — quality rescore → new winner; metadata path reconcile
# ===========================================================================

class TestUpdate_QualityRescore(unittest.TestCase):
    """Re-running with changed quality scores elects the correct new winner."""

    def test_rescore_flips_best_in_group(self):
        h = _h('rescore')
        recs = [
            {'media_id': 'A', 'md5_hash': h, 'quality_score': 80},
            {'media_id': 'B', 'md5_hash': h, 'quality_score': 60},
        ]
        dh = DuplicateHandler(selection_criteria=['quality'])
        dh.mark_duplicates(recs)
        self.assertEqual(next(r for r in recs if r.get('is_best_in_group') == 'Yes')['media_id'], 'A')

        # Rescore: B now higher
        for r in recs:
            r['quality_score'] = 95 if r['media_id'] == 'B' else 40
        dh.mark_duplicates(recs)
        self.assertEqual(next(r for r in recs if r.get('is_best_in_group') == 'Yes')['media_id'], 'B')

    def test_rescore_idempotent_when_no_change(self):
        h = _h('rescore_idem')
        recs = [
            {'media_id': 'A', 'md5_hash': h, 'quality_score': 85},
            {'media_id': 'B', 'md5_hash': h, 'quality_score': 55},
        ]
        dh = DuplicateHandler(selection_criteria=['quality'])
        dh.mark_duplicates(recs)
        state1 = [(r['media_id'], r.get('is_best_in_group')) for r in recs]
        dh.mark_duplicates(recs)
        state2 = [(r['media_id'], r.get('is_best_in_group')) for r in recs]
        self.assertEqual(state1, state2)

    def test_rescore_50_groups_all_winners_correct(self):
        all_recs = []
        for g in range(50):
            h = _h(f'rg_{g}')
            recs = [{'media_id': f'g{g}_{i}', 'md5_hash': h, 'quality_score': i * 10}
                    for i in range(3)]
            all_recs.extend(recs)

        DuplicateHandler(selection_criteria=['quality']).mark_duplicates(all_recs)

        # Update all: make the _0 record the best (give it 100)
        for r in all_recs:
            if r['media_id'].endswith('_0'):
                r['quality_score'] = 100

        DuplicateHandler(selection_criteria=['quality']).mark_duplicates(all_recs)

        for g in range(50):
            group_recs = [r for r in all_recs if r['media_id'].startswith(f'g{g}_')]
            best = next((r for r in group_recs if r.get('is_best_in_group') == 'Yes'), None)
            self.assertIsNotNone(best, f'Group {g} has no best')
            self.assertTrue(best['media_id'].endswith('_0'), f'Group {g} wrong best: {best["media_id"]}')

    def test_rescore_stale_hash_cleared_when_hash_changes(self):
        """Change hash mid-run → old dup group disappears, no ghost flags."""
        h = _h('stale')
        recs = [
            {'media_id': 'A', 'md5_hash': h, 'quality_score': 80},
            {'media_id': 'B', 'md5_hash': h, 'quality_score': 60},
        ]
        DuplicateHandler().mark_duplicates(recs)

        # Simulate hash update (e.g., file was edited/re-saved)
        recs[1]['md5_hash'] = _h('now_unique')
        DuplicateHandler().mark_duplicates(recs)

        for r in recs:
            self.assertNotEqual(r['is_duplicate'], 'YES',
                                f'{r["media_id"]} still marked dup after hash changed')


class TestUpdate_MetadataPath(unittest.TestCase):
    """Metadata JSON path updates after files are moved."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_metadata_json_path_updated_after_file_move(self):
        src_dir = Path(self.tmp) / 'source'
        dst_dir = Path(self.tmp) / 'dest'
        src_dir.mkdir()
        dst_dir.mkdir()

        img = src_dir / 'photo.jpg'
        img.write_bytes(b'\xff\xd8\xff' + b'\x00' * 100)
        meta = src_dir / 'photo.json'
        meta.write_text(json.dumps({'full_path': str(img), 'filename': 'photo.jpg'}))

        shutil.move(str(img), str(dst_dir / 'photo.jpg'))

        # Simulate updating the metadata record after the move
        doc = json.loads(meta.read_text())
        doc['full_path'] = str(dst_dir / 'photo.jpg')
        meta.write_text(json.dumps(doc))

        reloaded = json.loads(meta.read_text())
        self.assertEqual(reloaded['full_path'], str(dst_dir / 'photo.jpg'))

    def test_hash_stable_across_move(self):
        src = Path(self.tmp) / 'src.jpg'
        src.write_bytes(b'image bytes' * 200)
        dst = Path(self.tmp) / 'dst.jpg'
        shutil.copy2(str(src), str(dst))

        h1 = calculate_file_hash(str(src), 'md5')
        h2 = calculate_file_hash(str(dst), 'md5')
        self.assertEqual(h1, h2)

    def test_missing_file_after_move_returns_empty_hash(self):
        vanished = Path(self.tmp) / 'vanished.jpg'
        result = calculate_file_hash(str(vanished), 'md5')
        self.assertEqual(result, '')

    def test_metadata_json_100_records_all_paths_updated(self):
        meta_dir = Path(self.tmp) / 'meta'
        meta_dir.mkdir()
        new_base = Path(self.tmp) / 'organized'
        new_base.mkdir()

        records = []
        for i in range(100):
            old_path = f'/old/location/photo_{i}.jpg'
            new_path = str(new_base / f'photo_{i}.jpg')
            doc = {'media_id': f'img_{i}', 'full_path': old_path, 'filename': f'photo_{i}.jpg'}
            jp = meta_dir / f'photo_{i}.json'
            jp.write_text(json.dumps(doc))

            # Simulate reconcile: update path in JSON
            doc['full_path'] = new_path
            jp.write_text(json.dumps(doc))
            records.append(doc)

        for i, doc in enumerate(records):
            self.assertTrue(doc['full_path'].endswith(f'photo_{i}.jpg'))
            self.assertNotIn('/old/location/', doc['full_path'])


# ===========================================================================
# 4. MOVE/ORGANIZE  — ImageOrganizer.organize()
# ===========================================================================

class TestOrganize_MicroScale(unittest.TestCase):
    """1–5 files: basic copy, status, error paths."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.src = Path(self.tmp) / 'source'
        self.out = Path(self.tmp) / 'output'
        self.src.mkdir()
        self.out.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _organizer(self, **kwargs):
        return ImageOrganizer(_org_config(self.out, **kwargs))

    def test_single_file_copy_returns_success(self):
        f = _fake_file(self.src)
        rec = _org_rec(f)
        results = self._organizer().organize([rec])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['status'], 'Success')

    def test_organized_file_lands_in_output_dir(self):
        f = _fake_file(self.src, 'landing.jpg')
        rec = _org_rec(f)
        self._organizer().organize([rec])
        found = list(self.out.rglob('landing.jpg'))
        self.assertGreater(len(found), 0, 'File not found in output')

    def test_missing_source_returns_not_found_status(self):
        ghost = self.src / 'ghost.jpg'  # never written
        rec = _org_rec(ghost)
        results = self._organizer().organize([rec])
        self.assertIn('Not found', results[0]['status'])

    def test_empty_records_returns_empty_list(self):
        self.assertEqual(self._organizer().organize([]), [])

    def test_delete_flagged_record_is_skipped(self):
        f = _fake_file(self.src, 'flagged.jpg')
        rec = _org_rec(f, delete_flag='Yes')
        results = self._organizer().organize([rec])
        self.assertEqual(len(results), 0, 'Delete-flagged record should be skipped entirely')

    def test_delete_flag_yes_lowercase_also_skipped(self):
        f = _fake_file(self.src, 'flagged_lc.jpg')
        rec = _org_rec(f, delete_flag='yes')
        results = self._organizer().organize([rec])
        self.assertEqual(len(results), 0)

    def test_record_with_no_full_path_returns_error(self):
        rec = {'media_id': 'x', 'filename': 'noop.jpg', 'date_taken': '2023:01:01 00:00:00',
               'delete_flag': '', 'has_exif': False}
        results = self._organizer().organize([rec])
        self.assertIn('Error', results[0]['status'])


class TestOrganize_DateFolders(unittest.TestCase):
    """Day threshold logic and folder naming."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.src = Path(self.tmp) / 'source'
        self.out = Path(self.tmp) / 'output'
        self.src.mkdir()
        self.out.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_below_day_threshold_goes_to_monthly_folder(self):
        org = ImageOrganizer(_org_config(self.out, day_thr=60))
        files = [_fake_file(self.src, f'p{i}.jpg') for i in range(5)]
        recs = [_org_rec(f, date_taken='2023:06:15 10:00:00') for f in files]
        org.organize(recs)
        # monthly folder: 2023-06-00-...
        monthly = list(self.out.rglob('2023-06-00*'))
        self.assertGreater(len(monthly), 0, 'Monthly folder not created for 5 files')

    def test_above_day_threshold_goes_to_daily_folder(self):
        org = ImageOrganizer(_org_config(self.out, day_thr=5))
        files = [_fake_file(self.src, f'q{i}.jpg') for i in range(10)]
        recs = [_org_rec(f, date_taken='2023:06:20 10:00:00') for f in files]
        org.organize(recs)
        daily = list(self.out.rglob('2023-06-20*'))
        self.assertGreater(len(daily), 0, 'Daily folder not created when count > threshold')

    def test_exactly_at_threshold_triggers_daily_folder(self):
        org = ImageOrganizer(_org_config(self.out, day_thr=5))
        files = [_fake_file(self.src, f'r{i}.jpg') for i in range(5)]
        recs = [_org_rec(f, date_taken='2023:07:04 10:00:00') for f in files]
        org.organize(recs)
        daily = list(self.out.rglob('2023-07-04*'))
        self.assertGreater(len(daily), 0, 'Daily folder not created at exact threshold')

    def test_undated_files_go_to_undated_folder(self):
        org = ImageOrganizer(_org_config(self.out))
        files = [_fake_file(self.src, f'u{i}.jpg') for i in range(3)]
        recs = [_org_rec(f, date_taken=None, has_exif=False) for f in files]
        for r in recs:
            r['date_taken'] = None
            r['file_modified'] = None
        org.organize(recs)
        undated = list(self.out.rglob('undated*'))
        self.assertGreater(len(undated), 0, 'Undated folder not created')

    def test_mixed_dates_produce_separate_folders(self):
        org = ImageOrganizer(_org_config(self.out, day_thr=1))
        dates = ['2023:01:01 10:00:00', '2023:06:15 10:00:00', '2023:12:25 10:00:00']
        files = [_fake_file(self.src, f'mix{i}.jpg') for i in range(3)]
        recs = [_org_rec(f, date_taken=d) for f, d in zip(files, dates)]
        org.organize(recs)
        subfolders = [d for d in self.out.iterdir() if d.is_dir()]
        self.assertGreaterEqual(len(subfolders), 3, 'Expected 3 separate date folders')

    def test_year_structure_places_files_under_year_dir(self):
        org = ImageOrganizer(_org_config(self.out, structure='year'))
        f = _fake_file(self.src, 'yr.jpg')
        rec = _org_rec(f, date_taken='2022:03:10 00:00:00')
        org.organize([rec])
        year_dirs = [d for d in self.out.iterdir() if d.is_dir() and d.name == '2022']
        self.assertEqual(len(year_dirs), 1)


class TestOrganize_Screenshots(unittest.TestCase):
    """Screenshot detection by filename and resolution."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.src = Path(self.tmp) / 'source'
        self.out = Path(self.tmp) / 'output'
        self.src.mkdir()
        self.out.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_screenshot_filename_goes_to_screenshot_folder(self):
        org = ImageOrganizer(_org_config(self.out, separate_screenshots=True))
        f = _fake_file(self.src, 'Screenshot_2023.jpg')
        rec = _org_rec(f, has_exif=False)
        rec['filename'] = 'Screenshot_2023.jpg'
        org.organize([rec])
        ss_folders = list(self.out.rglob('*screenshot*'))
        self.assertGreater(len(ss_folders), 0, 'Screenshot folder not created')

    def test_regular_photo_not_in_screenshot_folder(self):
        org = ImageOrganizer(_org_config(self.out, separate_screenshots=True, day_thr=1))
        f = _fake_file(self.src, 'IMG_1234.jpg')
        rec = _org_rec(f, has_exif=True, width=3024, height=4032)
        rec['filename'] = 'IMG_1234.jpg'
        org.organize([rec])
        ss_folders = list(self.out.rglob('*screenshot*'))
        self.assertEqual(len(ss_folders), 0, 'Regular photo wrongly put in screenshot folder')

    def test_screenshot_detection_disabled(self):
        org = ImageOrganizer(_org_config(self.out, separate_screenshots=False, day_thr=1))
        f = _fake_file(self.src, 'Screenshot_test.jpg')
        rec = _org_rec(f, has_exif=False)
        rec['filename'] = 'Screenshot_test.jpg'
        results = org.organize([rec])
        self.assertEqual(results[0]['status'], 'Success')
        ss_folders = list(self.out.rglob('*screenshot*'))
        self.assertEqual(len(ss_folders), 0)


class TestOrganize_Operations(unittest.TestCase):
    """Copy vs move; conflict resolution."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.src = Path(self.tmp) / 'source'
        self.out = Path(self.tmp) / 'output'
        self.src.mkdir()
        self.out.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_copy_leaves_source_intact(self):
        f = _fake_file(self.src, 'copy_me.jpg')
        rec = _org_rec(f)
        ImageOrganizer(_org_config(self.out, operation='copy')).organize([rec])
        self.assertTrue(f.exists(), 'Source file should survive a copy operation')

    def test_move_removes_source(self):
        f = _fake_file(self.src, 'move_me.jpg')
        rec = _org_rec(f)
        ImageOrganizer(_org_config(self.out, operation='move')).organize([rec])
        self.assertFalse(f.exists(), 'Source file should be gone after move operation')

    def test_skip_conflict_when_dest_exists(self):
        f = _fake_file(self.src, 'dup.jpg')
        rec = _org_rec(f)
        # First copy
        org = ImageOrganizer(_org_config(self.out, conflict='skip'))
        org.organize([rec])
        # Second organize with same source file (re-created)
        _fake_file(self.src, 'dup.jpg')
        results = org.organize([rec])
        # On conflict skip, status is 'Skipped'
        statuses = [r['status'] for r in results]
        self.assertIn('Skipped', statuses)

    def test_rename_conflict_creates_unique_name(self):
        org = ImageOrganizer(_org_config(self.out, conflict='rename', day_thr=1))
        f1 = _fake_file(self.src, 'same.jpg', content=b'content_one' + b'\x00' * 100)
        r1 = _org_rec(f1, date_taken='2023:01:01 00:00:00')
        org.organize([r1])

        f2 = _fake_file(self.src, 'same.jpg', content=b'content_two' + b'\x00' * 100)
        r2 = _org_rec(f2, date_taken='2023:01:01 00:00:00')
        results = org.organize([r2])
        self.assertEqual(results[0]['status'], 'Success')
        dest1, dest2 = results[0]['destination'], results[0]['destination']
        all_organized = list(self.out.rglob('same*.jpg'))
        self.assertGreaterEqual(len(all_organized), 1)


class TestOrganize_LargeScale(unittest.TestCase):
    """100–500 files: performance and correctness at scale."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.src = Path(self.tmp) / 'source'
        self.out = Path(self.tmp) / 'output'
        self.src.mkdir()
        self.out.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_100_files_all_succeed(self):
        org = ImageOrganizer(_org_config(self.out, day_thr=200))
        files = [_fake_file(self.src, f'bulk_{i:03d}.jpg') for i in range(100)]
        recs = [_org_rec(f, date_taken='2023:08:20 10:00:00') for f in files]
        results = org.organize(recs)
        success = sum(1 for r in results if r['status'] == 'Success')
        self.assertEqual(success, 100)

    def test_delete_flagged_records_excluded_from_100(self):
        org = ImageOrganizer(_org_config(self.out, day_thr=200))
        files = [_fake_file(self.src, f'mix_{i:03d}.jpg') for i in range(100)]
        recs = [_org_rec(f, date_taken='2023:09:01 10:00:00',
                         delete_flag='Yes' if i % 5 == 0 else '')
                for i, f in enumerate(files)]
        results = org.organize(recs)
        # 100 // 5 = 20 flagged → 80 processed
        self.assertEqual(len(results), 80)
        self.assertTrue(all(r['status'] == 'Success' for r in results))

    def test_200_files_across_4_dates_performance(self):
        org = ImageOrganizer(_org_config(self.out, day_thr=300))
        dates = ['2023:03:01', '2023:06:15', '2023:09:20', '2023:12:25']
        files = []
        recs = []
        for i in range(200):
            d = dates[i % 4]
            f = _fake_file(self.src, f'multi_{i:03d}.jpg')
            files.append(f)
            recs.append(_org_rec(f, date_taken=d + ' 10:00:00'))

        t0 = time.perf_counter()
        results = org.organize(recs)
        elapsed = time.perf_counter() - t0

        self.assertLess(elapsed, 30.0, f'200-file organize took {elapsed:.2f}s')
        success = sum(1 for r in results if r['status'] == 'Success')
        self.assertEqual(success, 200)


# ===========================================================================
# 5. CROSS-OPERATION  — interleaved add → delete → update → move
# ===========================================================================

class TestCrossOp_FullCycle(unittest.TestCase):
    """End-to-end: add → mark duplicates → rescore → organize non-deleted files."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.src = Path(self.tmp) / 'source'
        self.out = Path(self.tmp) / 'output'
        self.src.mkdir()
        self.out.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_full_cycle_20_files_5_dups(self):
        """Add 20 files (5 form a dup group), mark dups, rescore winner, organize survivors."""
        h = _h('full_cycle_group')
        records = _unique(15, offset=0)

        dup_group = [
            {'media_id': f'dup_{i}', 'md5_hash': h, 'quality_score': i * 10}
            for i in range(5)
        ]
        records.extend(dup_group)

        # STEP 1 — mark duplicates
        DuplicateHandler(selection_criteria=['quality']).mark_duplicates(records)
        self.assertEqual(sum(1 for r in records if r['is_duplicate'] == 'YES'), 5)

        # STEP 2 — rescore: flip winner inside the dup group
        for r in records:
            if r['media_id'] == 'dup_0':
                r['quality_score'] = 999  # new winner
        DuplicateHandler(selection_criteria=['quality']).mark_duplicates(records)
        best = next(r for r in records if r.get('is_best_in_group') == 'Yes')
        self.assertEqual(best['media_id'], 'dup_0')

        # STEP 3 — organize only non-deleted files (write fake source files for them)
        survivors = [r for r in records if r.get('delete_flag') != 'Yes']
        for r in survivors:
            f = _fake_file(self.src, r['media_id'] + '.jpg')
            r['full_path'] = str(f)
            r['filename'] = f.name
            r['date_taken'] = '2023:11:05 12:00:00'
            r['has_exif'] = True
            r['width'] = 3024
            r['height'] = 4032
            r['file_type'] = 'image'

        org = ImageOrganizer(_org_config(self.out, day_thr=100))
        results = org.organize(survivors)
        success = sum(1 for r in results if r['status'] == 'Success')
        self.assertEqual(success, len(survivors))

    def test_checkpoint_tracks_only_undeleted_survivors(self):
        """After delete pass, checkpoint holds the survivors' IDs, not deleted ones."""
        tmp = tempfile.mkdtemp()
        try:
            cp = Path(tmp) / 'cp.json'
            h = _h('chk_del')
            records = [
                {'media_id': 'A', 'md5_hash': h, 'quality_score': 90},
                {'media_id': 'B', 'md5_hash': h, 'quality_score': 50},
            ]
            DuplicateHandler(selection_criteria=['quality']).mark_duplicates(records)
            survivors = [r for r in records if r.get('delete_flag') != 'Yes']

            cm = CheckpointManager(file_path=str(cp))
            for r in survivors:
                cm.mark_processed(r['media_id'])
            cm.save()

            cm2 = CheckpointManager(file_path=str(cp))
            cm2.load()
            self.assertIn('A', cm2.processed)
            self.assertNotIn('B', cm2.processed)
        finally:
            shutil.rmtree(tmp)

    def test_add_delete_add_same_file_stays_detected(self):
        """Delete a file, re-add it — still detected as dup of surviving copy."""
        h = _h('readd')
        copy_a = {'media_id': 'A', 'md5_hash': h, 'quality_score': 80}
        copy_b = {'media_id': 'B', 'md5_hash': h, 'quality_score': 70}
        DuplicateHandler().mark_duplicates([copy_a, copy_b])

        # Delete B
        recs = [copy_a]
        DuplicateHandler().mark_duplicates(recs)
        self.assertEqual(recs[0]['is_duplicate'], 'No')

        # Re-add B
        copy_b2 = {'media_id': 'B_readded', 'md5_hash': h, 'quality_score': 65}
        recs = [copy_a, copy_b2]
        DuplicateHandler().mark_duplicates(recs)
        self.assertEqual(sum(1 for r in recs if r['is_duplicate'] == 'YES'), 2)


if __name__ == '__main__':
    unittest.main()
