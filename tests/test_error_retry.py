"""
Regression tests — files that error during a scan must be retried next scan.

Previously, error records were written into the global checkpoint alongside
successful ones, so a file that failed once (locked, transient read error,
corrupt) was permanently skipped on every future scan — a silent vault gap.

Run: pytest tests/test_error_retry.py -v
"""

import json
import sys
import shutil
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.scanner import ImageScanner

try:
    from PIL import Image
    PIL_OK = True
except ImportError:
    PIL_OK = False


def _write_jpg(path, color):
    Image.new('RGB', (32, 32), color).save(path, 'JPEG')


@unittest.skipUnless(PIL_OK, 'Pillow required')
class TestErroredFilesRetried(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.scan_dir = self.tmp / 'pics'
        self.scan_dir.mkdir()
        self.ck = self.tmp / 'global_checkpoint.json'
        self.good1 = self.scan_dir / 'good1.jpg'
        self.good2 = self.scan_dir / 'good2.jpg'
        self.bad = self.scan_dir / 'bad.jpg'
        _write_jpg(self.good1, 'red')
        _write_jpg(self.good2, 'green')
        _write_jpg(self.bad, 'blue')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _scanner(self):
        return ImageScanner({
            'scan': {
                'folder_path': str(self.scan_dir),
                'extensions': {'images': ['jpg'], 'videos': []},
            },
            'processing': {
                'threads': 1,
                'show_progress': False,
                'global_checkpoint_file': str(self.ck),
            },
            'blur_detection': {'enabled': False},
        })

    def _checkpoint_paths(self):
        data = json.loads(self.ck.read_text(encoding='utf-8'))
        return set(data.get('processed', []))

    def _scan_with_failure_on_bad(self, scanner):
        orig = scanner._extract
        bad_key = str(self.bad).lower()

        def failing_extract(fp, fields_needed=None):
            if str(fp).lower() == bad_key:
                raise OSError('simulated read failure')
            return orig(fp, fields_needed=fields_needed)

        scanner._extract = failing_extract
        return scanner.scan(str(self.scan_dir))

    def test_errored_file_excluded_from_global_checkpoint(self):
        records = self._scan_with_failure_on_bad(self._scanner())

        errored = [r for r in records if r.get('error')]
        self.assertEqual(len(errored), 1)
        self.assertEqual(errored[0]['full_path'], str(self.bad))

        processed = self._checkpoint_paths()
        self.assertNotIn(str(self.bad), processed)
        self.assertEqual(processed, {str(self.good1), str(self.good2)})

    def test_errored_file_is_retried_and_recorded_on_next_scan(self):
        self._scan_with_failure_on_bad(self._scanner())

        # Second scan without the failure: only the errored file is rescanned.
        records = self._scanner().scan(str(self.scan_dir))
        self.assertEqual([r['full_path'] for r in records], [str(self.bad)])
        self.assertFalse(records[0].get('error'))
        self.assertIn(str(self.bad), self._checkpoint_paths())

    def test_successful_files_are_not_rescanned(self):
        self._scan_with_failure_on_bad(self._scanner())
        records = self._scanner().scan(str(self.scan_dir))
        scanned = {r['full_path'] for r in records}
        self.assertNotIn(str(self.good1), scanned)
        self.assertNotIn(str(self.good2), scanned)


@unittest.skipUnless(PIL_OK, 'Pillow required')
class TestDecodeFailureNotRetriedForever(unittest.TestCase):
    """A file that reads fine but cannot be decoded (e.g. RAW without a backend)
    must be checkpointed, not re-hashed on every scan — the opposite of a hard
    read failure. Discriminator: a hashed record carries an md5; an unreadable
    one does not.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.scan_dir = self.tmp / 'pics'
        self.scan_dir.mkdir()
        self.ck = self.tmp / 'global_checkpoint.json'
        self.good = self.scan_dir / 'photo.jpg'
        self.rawish = self.scan_dir / 'shot.cr2'   # undecodable content
        _write_jpg(self.good, 'red')
        self.rawish.write_bytes(b'\x00\x01\x02RAWGARBAGE' * 64)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _scanner(self):
        return ImageScanner({
            'scan': {
                'folder_path': str(self.scan_dir),
                'extensions': {'images': ['jpg', 'cr2'], 'videos': []},
            },
            'processing': {
                'threads': 1,
                'show_progress': False,
                'global_checkpoint_file': str(self.ck),
                'fast_mode': True,
            },
            'blur_detection': {'enabled': False},
        })

    def _checkpoint_paths(self):
        data = json.loads(self.ck.read_text(encoding='utf-8'))
        return set(data.get('processed', []))

    def test_undecodable_file_is_error_but_hashed(self):
        records = self._scanner().scan(str(self.scan_dir))
        rec = next(r for r in records if r['full_path'] == str(self.rawish))
        self.assertTrue(rec.get('error'))          # decode failed
        self.assertTrue(rec.get('md5_hash'))       # but it WAS read/hashed

    def test_undecodable_file_is_checkpointed_and_not_rescanned(self):
        self._scanner().scan(str(self.scan_dir))
        # It read successfully (has md5), so it should be checkpointed despite the error.
        self.assertIn(str(self.rawish), self._checkpoint_paths())
        # Next scan must NOT re-process it (no infinite re-hashing of large RAW files).
        records2 = self._scanner().scan(str(self.scan_dir))
        self.assertEqual(records2, [])
