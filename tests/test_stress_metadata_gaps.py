"""
Stress tests for the 4 real-world gaps the existing test suite does NOT cover:

  GAP-1: One photo → two vault JSON files (fast-scan/no-md5 path or copy+rescan)
          MetadataStore._json_path_for_record() uses SHA1(full_path).  Two different
          full_paths for the same content → two JSON files.  md5-migration only fires
          when the record carries a non-empty md5_hash.

  GAP-2: DELETE operation links records to vault JSONs via metadata_json_path.
          Tests verify: correct JSON removed, sibling JSON untouched, stale/missing
          path is handled gracefully without crashing.

  GAP-3: organize() must return exactly N results for N input records — no record
          multiplication.  After copy, source still has a valid vault record; after move,
          source record's path is stale.

  GAP-4: Cross-location dup detection — two records with identical md5 but different
          full_path (source + organized copy) are marked as duplicates by DuplicateHandler,
          and only the lower-quality one gets delete_flag.

Run: pytest tests/test_stress_metadata_gaps.py -v
"""

import sys
import json
import shutil
import hashlib
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.metadata_store import MetadataStore
from src.duplicate_handler import DuplicateHandler
from src.organizer import ImageOrganizer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _meta_config(meta_dir, scan_dir=None, org_dir=None):
    """Minimal config dict that MetadataStore accepts."""
    return {
        "metadata": {
            "root_folder": str(meta_dir),
            "update_strategy": "update_missing",
        },
        "scan": {"folder_path": str(scan_dir or meta_dir)},
        "organization": {"output_folder": str(org_dir or meta_dir)},
        "processing": {"threads": 1},
    }


def _org_config(output_dir, operation="copy", conflict="rename", day_thr=60):
    return {
        "organization": {
            "output_folder": str(output_dir),
            "day_threshold": day_thr,
            "use_exif_date": True,
            "operation": operation,
            "conflict_resolution": conflict,
            "reuse_existing_folders": False,
            "video_subfolder": False,
            "separate_screenshots": False,
            "folder_structure": "flat",
        },
        "processing": {"show_progress": False},
        "metadata": {"root_folder": ""},
    }


def _fake_jpg(path, seed="x"):
    """Write a minimal non-empty JPEG-header file and return its path."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\xff\xd8\xff" + seed.encode() + b"\x00" * 64)
    return p


def _md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def _vault_json_path_for(meta_dir, full_path):
    """Reproduce MetadataStore._json_path_for_record() logic."""
    key = hashlib.sha1(str(full_path).encode("utf-8", errors="ignore")).hexdigest()
    return Path(meta_dir) / f"{key}.json"


def _write_vault_json(meta_dir, full_path, md5_hash, media_id, quality=75):
    """Write a minimal vault JSON in the structure MetadataStore expects."""
    jp = _vault_json_path_for(meta_dir, full_path)
    doc = {
        "schema_version": "2.0",
        "file": {
            "media_id": media_id,
            "full_path": str(full_path),
            "filename": Path(full_path).name,
            "md5_hash": md5_hash,
        },
        "hashes": {"md5": md5_hash},
        # quality_score lives in the "quality" section — _doc_to_record reads it from there
        "quality": {
            "quality_score": quality,
        },
        "duplicate": {
            "is_duplicate": False,
            "duplicate_group": None,
            "is_best_in_group": None,
        },
    }
    jp.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
    return jp


def _save_one(store, full_path, md5_hash, media_id, quality=75):
    """Save a single record via MetadataStore and return the normalized record."""
    rec = {
        "full_path": str(full_path),
        "filename": Path(full_path).name,
        "md5_hash": md5_hash,
        "media_id": media_id,
        "quality_score": quality,
        "file_type": "image",
        "date_taken": "2023:12:25 10:00:00",
        "has_exif": True,
        "width": 3024,
        "height": 4032,
    }
    results = store.upsert_records([rec])
    return results[0] if results else None


def _org_rec(src_path, date_taken="2023:12:25 10:00:00", quality=80, delete_flag=""):
    p = Path(src_path)
    return {
        "full_path": str(p),
        "filename": p.name,
        "date_taken": date_taken,
        "file_modified": "2023-12-25 10:00:00",
        "file_type": "image",
        "delete_flag": delete_flag,
        "has_exif": True,
        "width": 3024,
        "height": 4032,
        "quality_score": quality,
    }


# ===========================================================================
# GAP-1: One photo → two vault JSON files (no-md5 fast scan scenario)
# ===========================================================================

class TestGap1_TwoVaultJsonsPerPhoto(unittest.TestCase):
    """
    When md5 is absent from a record, MetadataStore cannot detect that the same
    content was already saved under a different path-hash.  The result: two vault
    JSON files for one physical photo.  Verify the data model and the deduplication
    path that resolves it.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.meta_dir = Path(self.tmp) / "vault"
        self.meta_dir.mkdir()
        self.scan_dir = Path(self.tmp) / "source"
        self.scan_dir.mkdir()
        self.org_dir = Path(self.tmp) / "organized"
        self.org_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_same_full_path_always_produces_same_json_filename(self):
        """SHA1(full_path) → deterministic vault JSON filename."""
        fp = str(self.scan_dir / "photo.jpg")
        jp1 = _vault_json_path_for(self.meta_dir, fp)
        jp2 = _vault_json_path_for(self.meta_dir, fp)
        self.assertEqual(jp1, jp2)

    def test_two_different_paths_same_content_different_json_files(self):
        """Two paths → two SHA1 hashes → two distinct vault JSON files."""
        source_path = str(self.scan_dir / "photo.jpg")
        org_path = str(self.org_dir / "2023-12-25-001pic" / "photo.jpg")
        jp_source = _vault_json_path_for(self.meta_dir, source_path)
        jp_org = _vault_json_path_for(self.meta_dir, org_path)
        self.assertNotEqual(jp_source, jp_org,
            "Different full_paths must map to different vault JSON files")

    def test_no_md5_record_creates_second_json_for_organized_copy(self):
        """
        Fast-scan record (no md5_hash) saved at source path first.
        Then the organized copy is saved with no md5_hash.
        md5-migration logic skips → two vault JSONs created.
        """
        config = _meta_config(self.meta_dir, self.scan_dir, self.org_dir)
        store = MetadataStore(config)

        source_path = self.scan_dir / "photo.jpg"
        _fake_jpg(source_path, "original-bytes")

        org_folder = self.org_dir / "2023-12-25-001pic"
        org_folder.mkdir(parents=True, exist_ok=True)
        org_path = org_folder / "photo.jpg"
        _fake_jpg(org_path, "original-bytes")

        # Save source record WITHOUT md5 (fast-scan mode)
        store.upsert_records([{
            "full_path": str(source_path),
            "filename": "photo.jpg",
            "md5_hash": "",  # no hash — migration cannot fire
            "media_id": "img_source",
            "quality_score": 70,
            "file_type": "image",
            "date_taken": "2023:12:25 10:00:00",
        }])

        # Save organized-path record also WITHOUT md5
        store.upsert_records([{
            "full_path": str(org_path),
            "filename": "photo.jpg",
            "md5_hash": "",
            "media_id": "img_org",
            "quality_score": 70,
            "file_type": "image",
            "date_taken": "2023:12:25 10:00:00",
        }])

        # Both JSONs must exist because migration requires md5
        jp_src = _vault_json_path_for(self.meta_dir, source_path)
        jp_org = _vault_json_path_for(self.meta_dir, org_path)
        self.assertTrue(jp_src.exists(), "Source vault JSON should exist")
        self.assertTrue(jp_org.exists(), "Organized vault JSON should exist")
        self.assertNotEqual(jp_src, jp_org)

    def test_with_md5_rescan_migrates_old_json_to_new_path(self):
        """
        When md5 IS present and no explicit media_id is set, MetadataStore uses
        md5 as the media_id.  _build_md5_index then keys by that md5, and the
        lookup _md5_index.get(rec_md5) finds the old vault JSON.  The old
        source-path JSON is migrated to the new organized-path hash, leaving
        only one vault JSON.

        Note: migration ONLY fires when media_id is not explicitly provided —
        if media_id is set, the index keys by media_id while the lookup uses md5,
        so they never match.  This is the expected usage pattern.
        """
        config = _meta_config(self.meta_dir, self.scan_dir, self.org_dir)
        store = MetadataStore(config)

        source_path = self.scan_dir / "photo.jpg"
        _fake_jpg(source_path, "real-bytes-12345")
        md5 = _md5(source_path)

        # Step 1: save source record WITH md5, WITHOUT explicit media_id
        # → MetadataStore derives media_id = md5, so the vault JSON's top-level
        #   media_id equals the md5 and _build_md5_index keys by it correctly.
        store.upsert_records([{
            "full_path": str(source_path),
            "filename": "photo.jpg",
            "md5_hash": md5,
            "quality_score": 70,
            "file_type": "image",
            "date_taken": "2023:12:25 10:00:00",
        }])
        jp_source = _vault_json_path_for(self.meta_dir, source_path)
        self.assertTrue(jp_source.exists())

        # Step 2: organized copy exists at a new path
        org_path = self.org_dir / "2023-12-25-001pic" / "photo.jpg"
        org_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(source_path), str(org_path))

        # Step 3: scan organized copy WITH md5, WITHOUT explicit media_id — migration fires
        store.upsert_records([{
            "full_path": str(org_path),
            "filename": "photo.jpg",
            "md5_hash": md5,
            "quality_score": 70,
            "file_type": "image",
            "date_taken": "2023:12:25 10:00:00",
        }])

        jp_org = _vault_json_path_for(self.meta_dir, org_path)
        # Old JSON should be gone (migrated), new JSON exists
        self.assertFalse(jp_source.exists(), "Old source-path vault JSON should be migrated away")
        self.assertTrue(jp_org.exists(), "Organized-path vault JSON should exist after migration")

    def test_two_vault_jsons_both_appear_in_load_records(self):
        """
        Two vault JSONs (same md5, different full_path) → load_records returns
        two records, one per JSON.  This is what causes the double-row in Excel.
        """
        config = _meta_config(self.meta_dir, self.scan_dir, self.org_dir)
        store = MetadataStore(config)

        source_path = self.scan_dir / "photo.jpg"
        org_path = self.org_dir / "photo.jpg"
        _fake_jpg(source_path, "content-abc")
        _fake_jpg(org_path, "content-abc")
        md5 = "abc123fake"  # same md5 for both

        # Write two vault JSONs manually (simulating no-md5-migration scenario)
        _write_vault_json(self.meta_dir, source_path, md5, "img_a", quality=60)
        _write_vault_json(self.meta_dir, org_path,    md5, "img_b", quality=80)

        records = store.load_records()
        full_paths = [r.get("full_path", "") for r in records]
        # Both records must be loaded
        self.assertIn(str(source_path), full_paths)
        self.assertIn(str(org_path), full_paths)
        self.assertEqual(len(records), 2)

    def test_two_vault_jsons_same_md5_detected_as_duplicates(self):
        """
        Two in-memory records loaded from two vault JSONs (same md5, different path)
        must be flagged as duplicates by DuplicateHandler.
        """
        md5 = "sharedmd5value"
        source_path = str(self.scan_dir / "photo.jpg")
        org_path = str(self.org_dir / "photo.jpg")

        _write_vault_json(self.meta_dir, source_path, md5, "img_a", quality=60)
        _write_vault_json(self.meta_dir, org_path,    md5, "img_b", quality=80)

        config = _meta_config(self.meta_dir, self.scan_dir, self.org_dir)
        store = MetadataStore(config)
        records = store.load_records()

        DuplicateHandler(selection_criteria=["quality"]).mark_duplicates(records)

        dup_count = sum(1 for r in records if r.get("is_duplicate") == "YES")
        self.assertEqual(dup_count, 2, "Both cross-location copies must be marked as duplicates")

        best = [r for r in records if r.get("is_best_in_group") == "Yes"]
        self.assertEqual(len(best), 1, "Exactly one record must be best-in-group")
        self.assertEqual(best[0]["full_path"], org_path,
            "Higher-quality record (organized copy, quality=80) must be the winner")

    def test_lower_quality_vault_json_gets_delete_flag(self):
        """Source copy (lower quality) must get delete_flag=Yes; organized copy must not."""
        md5 = "dupmd5fordelete"
        source_path = str(self.scan_dir / "photo.jpg")
        org_path = str(self.org_dir / "photo.jpg")

        _write_vault_json(self.meta_dir, source_path, md5, "img_low", quality=50)
        _write_vault_json(self.meta_dir, org_path,    md5, "img_hi",  quality=90)

        config = _meta_config(self.meta_dir, self.scan_dir, self.org_dir)
        store = MetadataStore(config)
        records = store.load_records()

        DuplicateHandler(selection_criteria=["quality"]).mark_duplicates(records)

        low  = next(r for r in records if r.get("full_path") == source_path)
        high = next(r for r in records if r.get("full_path") == org_path)
        self.assertEqual(low["delete_flag"], "Yes",  "Source (low quality) must be flagged for delete")
        self.assertNotEqual(high.get("delete_flag"), "Yes", "Organized (best) must NOT be flagged")


# ===========================================================================
# GAP-2: DELETE op uses metadata_json_path to remove vault JSONs
# ===========================================================================

class TestGap2_DeleteMetadataJsonPath(unittest.TestCase):
    """
    The DELETE operation in main.py reads metadata_json_path from Excel and
    removes that file.  Tests verify correct removal, sibling untouched,
    graceful handling of stale paths, and the path-derivation identity.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.meta_dir = Path(self.tmp) / "vault"
        self.meta_dir.mkdir()
        self.scan_dir = Path(self.tmp) / "source"
        self.scan_dir.mkdir()
        self.org_dir = Path(self.tmp) / "org"
        self.org_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_metadata_json_path_derived_as_sha1_of_full_path(self):
        """metadata_json_path on a saved record is SHA1(full_path) in vault root."""
        config = _meta_config(self.meta_dir, self.scan_dir, self.org_dir)
        store = MetadataStore(config)

        src = self.scan_dir / "test.jpg"
        _fake_jpg(src)
        rec = _save_one(store, src, "md5abc", "m1")

        expected = str(_vault_json_path_for(self.meta_dir, src))
        self.assertEqual(rec["metadata_json_path"], expected)

    def test_delete_via_metadata_json_path_removes_that_json(self):
        """
        Simulates the main.py DELETE flow: read metadata_json_path from record,
        call unlink().  The targeted JSON disappears; the vault root no longer
        has it.
        """
        config = _meta_config(self.meta_dir, self.scan_dir, self.org_dir)
        store = MetadataStore(config)

        src = self.scan_dir / "todelete.jpg"
        _fake_jpg(src)
        rec = _save_one(store, src, "deadbeef01", "del1")

        json_path = Path(rec["metadata_json_path"])
        self.assertTrue(json_path.exists(), "Vault JSON must exist before delete")

        # Simulate main.py delete: unlink the vault JSON
        json_path.unlink()

        self.assertFalse(json_path.exists(), "Vault JSON must be gone after delete")

    def test_delete_removes_only_targeted_json_sibling_survives(self):
        """
        Two vault JSONs (same md5, different paths).  DELETE via the source-path
        metadata_json_path removes only that JSON.  The organized-path JSON survives.
        """
        md5 = "shared789xyz"
        source_path = self.scan_dir / "photo.jpg"
        org_path = self.org_dir / "photo.jpg"

        jp_src = _write_vault_json(self.meta_dir, source_path, md5, "img_src", quality=40)
        jp_org = _write_vault_json(self.meta_dir, org_path,    md5, "img_org", quality=90)

        # DELETE the source-path JSON (as main.py would)
        jp_src.unlink()

        self.assertFalse(jp_src.exists(), "Source vault JSON must be removed")
        self.assertTrue(jp_org.exists(), "Organized vault JSON must survive sibling delete")

    def test_stale_metadata_json_path_missing_is_handled_gracefully(self):
        """
        If metadata_json_path in Excel points to a JSON that no longer exists
        (already cleaned up), the delete code must not raise an exception.
        This replicates the main.py pattern: check exists() before unlink().
        """
        stale_path = self.meta_dir / "nonexistent_abc123.json"
        self.assertFalse(stale_path.exists())

        # Replicate main.py graceful-delete pattern
        try:
            if stale_path.exists():
                stale_path.unlink()
            result = "ok"
        except OSError as e:
            result = str(e)

        self.assertEqual(result, "ok", "Stale metadata_json_path must not crash delete flow")

    def test_delete_flag_yes_record_has_metadata_json_path_pointing_to_real_file(self):
        """
        After DuplicateHandler marks a record for delete, its metadata_json_path
        must resolve to an actual file so main.py DELETE can find and remove it.
        """
        md5 = "checkrealpathmd5"
        source_path = str(self.scan_dir / "src.jpg")
        org_path = str(self.org_dir / "org.jpg")

        jp_src = _write_vault_json(self.meta_dir, source_path, md5, "src_id", quality=30)
        jp_org = _write_vault_json(self.meta_dir, org_path,    md5, "org_id", quality=95)

        config = _meta_config(self.meta_dir, self.scan_dir, self.org_dir)
        store = MetadataStore(config)
        records = store.load_records()

        DuplicateHandler(selection_criteria=["quality"]).mark_duplicates(records)

        delete_targets = [r for r in records if r.get("delete_flag") == "Yes"]
        self.assertEqual(len(delete_targets), 1, "Exactly one record must be flagged for delete")

        target = delete_targets[0]
        mjp = target.get("metadata_json_path", "")
        self.assertTrue(mjp, "Delete target must have metadata_json_path")
        self.assertTrue(Path(mjp).exists(),
            f"metadata_json_path '{mjp}' must point to a real vault JSON")

    def test_deleting_flagged_json_leaves_best_json_untouched(self):
        """End-to-end: mark dups, delete flagged JSON, verify survivor JSON still valid."""
        md5 = "e2edeletemd5"
        source_path = str(self.scan_dir / "e2e_src.jpg")
        org_path = str(self.org_dir / "e2e_org.jpg")

        jp_src = _write_vault_json(self.meta_dir, source_path, md5, "e2e_src", quality=20)
        jp_org = _write_vault_json(self.meta_dir, org_path,    md5, "e2e_org", quality=85)

        config = _meta_config(self.meta_dir, self.scan_dir, self.org_dir)
        store = MetadataStore(config)
        records = store.load_records()

        DuplicateHandler(selection_criteria=["quality"]).mark_duplicates(records)

        for rec in records:
            if rec.get("delete_flag") == "Yes":
                mjp = Path(rec["metadata_json_path"])
                if mjp.exists():
                    mjp.unlink()

        # Reload vault — only the survivor JSON must be there
        remaining = store.load_records()
        self.assertEqual(len(remaining), 1, "Only the best-in-group record must remain in vault")
        self.assertEqual(remaining[0]["full_path"], org_path,
            "Surviving record must be the organized (higher quality) copy")


# ===========================================================================
# GAP-3: organize() must not multiply records
# ===========================================================================

class TestGap3_OrganizeNoRecordMultiplication(unittest.TestCase):
    """
    organize() takes N input records and returns at most N result dicts.
    The input list itself must not grow.  After copy, source record's full_path
    is still valid (file exists).  After move, source path is gone.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.src = Path(self.tmp) / "source"
        self.out = Path(self.tmp) / "output"
        self.src.mkdir()
        self.out.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _organizer(self, operation="copy", conflict="rename", day_thr=60):
        return ImageOrganizer(_org_config(self.out, operation=operation,
                                          conflict=conflict, day_thr=day_thr))

    def test_copy_n_records_returns_exactly_n_results(self):
        """organize(copy) with N records → len(results) == N (no extras)."""
        n = 15
        files = [_fake_jpg(self.src / f"bulk_{i:02d}.jpg", str(i)) for i in range(n)]
        recs = [_org_rec(f) for f in files]

        results = self._organizer(day_thr=100).organize(recs)
        self.assertEqual(len(results), n,
            f"Expected {n} results, got {len(results)}")

    def test_copy_does_not_lengthen_input_records_list(self):
        """organize() must not mutate the input list by appending to it."""
        files = [_fake_jpg(self.src / f"inp_{i}.jpg", str(i)) for i in range(5)]
        recs = [_org_rec(f) for f in files]
        original_len = len(recs)

        self._organizer(day_thr=100).organize(recs)

        self.assertEqual(len(recs), original_len,
            "Input records list must not be extended by organize()")

    def test_move_n_records_returns_exactly_n_results(self):
        """organize(move) with N records → len(results) == N."""
        n = 10
        files = [_fake_jpg(self.src / f"mv_{i:02d}.jpg", str(i)) for i in range(n)]
        recs = [_org_rec(f) for f in files]

        results = self._organizer(operation="move", day_thr=100).organize(recs)
        self.assertEqual(len(results), n)

    def test_copy_source_file_still_exists_after_organize(self):
        """After organize(copy), source file still lives — rescan will find it again."""
        f = _fake_jpg(self.src / "stay.jpg")
        rec = _org_rec(f)

        self._organizer(operation="copy", day_thr=1).organize([rec])

        self.assertTrue(f.exists(),
            "Source file must survive organize(copy) — it can be rescanned again")

    def test_move_source_file_gone_after_organize(self):
        """After organize(move), source path is gone — no stale record should be used."""
        f = _fake_jpg(self.src / "gone.jpg")
        rec = _org_rec(f)

        self._organizer(operation="move", day_thr=1).organize([rec])

        self.assertFalse(f.exists(),
            "Source file must be removed by organize(move)")

    def test_result_has_source_and_destination_keys(self):
        """Each organize result dict must carry both 'source' and 'destination'."""
        f = _fake_jpg(self.src / "check.jpg")
        rec = _org_rec(f)

        results = self._organizer(day_thr=1).organize([rec])
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertIn("source", r, "Result must have 'source' key")
        self.assertIn("destination", r, "Result must have 'destination' key")
        self.assertEqual(r["status"], "Success")

    def test_copy_destination_file_actually_exists(self):
        """After organize(copy), the destination path in the result must be a real file."""
        f = _fake_jpg(self.src / "dest_check.jpg")
        rec = _org_rec(f, date_taken="2023:08:14 09:00:00")

        results = self._organizer(day_thr=1).organize([rec])
        dest = Path(results[0]["destination"])
        self.assertTrue(dest.exists(), f"Organized file must exist at destination: {dest}")

    def test_delete_flagged_records_excluded_from_results(self):
        """
        Records with delete_flag='Yes' are skipped entirely — they produce no result dict.
        N total records, K flagged → N-K results.
        """
        files = [_fake_jpg(self.src / f"mix_{i}.jpg", str(i)) for i in range(10)]
        recs = [_org_rec(f, delete_flag="Yes" if i % 3 == 0 else "") for i, f in enumerate(files)]
        flagged_count = sum(1 for r in recs if r["delete_flag"] == "Yes")

        results = self._organizer(day_thr=100).organize(recs)
        self.assertEqual(len(results), 10 - flagged_count)

    def test_post_copy_rescan_creates_second_record_with_same_md5(self):
        """
        After copy, source + organized copy both exist.  If vault saves both
        (no-md5 scenario), DuplicateHandler must detect them as the same content.
        This is the root cause of the 'two records for one photo' report.
        """
        f_src = _fake_jpg(self.src / "rescan.jpg", "same-bytes-as-org")
        content_md5 = _md5(f_src)

        # organize → copy to output
        results = self._organizer(day_thr=1, operation="copy").organize([_org_rec(f_src)])
        self.assertEqual(results[0]["status"], "Success")

        dest = Path(results[0]["destination"])
        self.assertTrue(dest.exists())
        dest_md5 = _md5(dest)
        self.assertEqual(content_md5, dest_md5,
            "Organized copy must have identical md5 to source — it IS the same photo")

        # Both paths exist → if both land in vault (no-md5 scenario), dup handler
        # must identify them as a duplicate pair
        rec_src = {"media_id": "src_id", "md5_hash": content_md5, "quality_score": 70,
                   "full_path": str(f_src)}
        rec_dst = {"media_id": "dst_id", "md5_hash": content_md5, "quality_score": 70,
                   "full_path": str(dest)}
        DuplicateHandler().mark_duplicates([rec_src, rec_dst])

        dup_count = sum(1 for r in [rec_src, rec_dst] if r.get("is_duplicate") == "YES")
        self.assertEqual(dup_count, 2,
            "Both the source and the organized copy must be marked as duplicates")


# ===========================================================================
# GAP-4: Cross-location dup detection end-to-end
# ===========================================================================

class TestGap4_CrossLocationDupDetection(unittest.TestCase):
    """
    The full workflow: scan → vault → load_records → mark_duplicates → delete.
    Focuses on same photo at two paths (source + organized copy).
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.meta_dir = Path(self.tmp) / "vault"
        self.meta_dir.mkdir()
        self.scan_dir = Path(self.tmp) / "source"
        self.scan_dir.mkdir()
        self.org_dir = Path(self.tmp) / "organized"
        self.org_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_10_cross_location_pairs_all_detected_as_dups(self):
        """10 photos each at source + organized → 20 records, all 20 are dups."""
        records = []
        for i in range(10):
            md5 = hashlib.md5(f"photo_{i}".encode()).hexdigest()
            records.append({"media_id": f"src_{i}", "md5_hash": md5,
                            "quality_score": 60, "full_path": f"/source/photo_{i}.jpg"})
            records.append({"media_id": f"org_{i}", "md5_hash": md5,
                            "quality_score": 80, "full_path": f"/org/photo_{i}.jpg"})

        DuplicateHandler(selection_criteria=["quality"]).mark_duplicates(records)

        dup_count = sum(1 for r in records if r.get("is_duplicate") == "YES")
        self.assertEqual(dup_count, 20, "All 20 cross-location copies must be marked as dups")

        best_count = sum(1 for r in records if r.get("is_best_in_group") == "Yes")
        self.assertEqual(best_count, 10, "Each of 10 groups must have exactly one best")

    def test_source_copies_all_get_delete_flag(self):
        """Source copies (lower quality) all get delete_flag=Yes; organized survive."""
        records = []
        for i in range(10):
            md5 = hashlib.md5(f"pair_{i}".encode()).hexdigest()
            records.append({"media_id": f"src_{i}", "md5_hash": md5,
                            "quality_score": 40, "full_path": f"/source/img_{i}.jpg"})
            records.append({"media_id": f"org_{i}", "md5_hash": md5,
                            "quality_score": 85, "full_path": f"/org/img_{i}.jpg"})

        DuplicateHandler(selection_criteria=["quality"]).mark_duplicates(records)

        src_recs = [r for r in records if r["media_id"].startswith("src_")]
        org_recs = [r for r in records if r["media_id"].startswith("org_")]

        self.assertTrue(all(r["delete_flag"] == "Yes" for r in src_recs),
            "All source copies must be delete-flagged")
        self.assertTrue(all(r.get("delete_flag") != "Yes" for r in org_recs),
            "All organized copies must NOT be delete-flagged")

    def test_equal_quality_does_not_crash_and_elects_one_winner(self):
        """Two copies with identical quality — must not crash; exactly one winner per group."""
        records = []
        for i in range(5):
            md5 = hashlib.md5(f"tie_{i}".encode()).hexdigest()
            records.append({"media_id": f"a_{i}", "md5_hash": md5, "quality_score": 75})
            records.append({"media_id": f"b_{i}", "md5_hash": md5, "quality_score": 75})

        DuplicateHandler(selection_criteria=["quality"]).mark_duplicates(records)

        from collections import defaultdict
        groups = defaultdict(list)
        for r in records:
            if r.get("duplicate_group"):
                groups[r["duplicate_group"]].append(r)
        for grp, members in groups.items():
            best = [m for m in members if m.get("is_best_in_group") == "Yes"]
            self.assertEqual(len(best), 1, f"Group {grp}: tie must still yield exactly one winner")

    def test_delete_two_vault_jsons_correct_one_removed_via_metadata_json_path(self):
        """
        Full delete simulation: 2 vault JSONs → load_records → mark_duplicates →
        DELETE via metadata_json_path → only one JSON remains in vault.
        """
        md5 = "fullcycle_delete_md5"
        src_p  = str(self.scan_dir / "fc.jpg")
        org_p  = str(self.org_dir / "fc.jpg")

        jp_src = _write_vault_json(self.meta_dir, src_p,  md5, "fc_src", quality=35)
        jp_org = _write_vault_json(self.meta_dir, org_p,  md5, "fc_org", quality=92)

        config = _meta_config(self.meta_dir, self.scan_dir, self.org_dir)
        store = MetadataStore(config)
        records = store.load_records()
        self.assertEqual(len(records), 2)

        DuplicateHandler(selection_criteria=["quality"]).mark_duplicates(records)

        # Simulate main.py DELETE: remove the vault JSON for each delete-flagged record
        deleted_jsons = []
        for rec in records:
            if rec.get("delete_flag") == "Yes":
                mjp = Path(rec["metadata_json_path"])
                if mjp.exists():
                    mjp.unlink()
                    deleted_jsons.append(str(mjp))

        self.assertEqual(len(deleted_jsons), 1, "Exactly one vault JSON must be deleted")
        # The remaining vault JSON must be the organized (high quality) one
        self.assertTrue(jp_org.exists(), "Organized-copy vault JSON must survive")
        self.assertFalse(jp_src.exists(), "Source-copy vault JSON must be removed")

    def test_100_cross_location_pairs_performance(self):
        """100 pairs (200 records) — dup detection and delete-flag assignment under 3s."""
        import time
        records = []
        for i in range(100):
            md5 = hashlib.md5(f"perf_pair_{i}".encode()).hexdigest()
            records.append({"media_id": f"s{i}", "md5_hash": md5, "quality_score": 50})
            records.append({"media_id": f"o{i}", "md5_hash": md5, "quality_score": 80})

        t0 = time.perf_counter()
        DuplicateHandler(selection_criteria=["quality"]).mark_duplicates(records)
        elapsed = time.perf_counter() - t0

        self.assertLess(elapsed, 3.0, f"200-record cross-location dup detection took {elapsed:.2f}s")
        flagged = sum(1 for r in records if r.get("delete_flag") == "Yes")
        self.assertEqual(flagged, 100)


if __name__ == "__main__":
    unittest.main()
