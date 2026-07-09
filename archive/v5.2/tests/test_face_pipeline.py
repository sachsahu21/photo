import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import json

from src.config_manager import ConfigManager
from src.face_indexer import FaceIndexer
from src.people_sync import sync_people_tags


class FacePipelineTests(unittest.TestCase):
    def test_apply_workspace_artifacts_resolves_face_artifact_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = {
                'workspace': {'root': tmp},
                'faces': {
                    'enabled': True,
                    'seed_root': 'seed',
                    'index_db_filename': 'face_index.sqlite',
                    'untagged_subfolder': 'untagged_people',
                },
            }
            from src.workspace_paths import apply_workspace_artifacts

            apply_workspace_artifacts(config)

            self.assertEqual(config['faces']['seed_root'], str(Path(tmp, 'seed')))
            self.assertEqual(config['faces']['data_folder'], str(Path(tmp, 'face_data')))
            self.assertEqual(config['faces']['untagged_root'], str(Path(tmp, 'face_data', 'untagged_people')))
            self.assertEqual(config['faces']['index_db'], str(Path(tmp, 'face_data', 'face_index.sqlite')))

    def test_face_indexer_returns_empty_matches_without_backend(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = {
                'workspace': {'root': tmp},
                'faces': {
                    'enabled': True,
                    'seed_root': str(Path(tmp, 'seed')),
                    'index_db_filename': 'face_index.sqlite',
                    'untagged_subfolder': 'untagged_people',
                },
            }
            from src.workspace_paths import apply_workspace_artifacts

            apply_workspace_artifacts(config)

            with patch.object(FaceIndexer, '_ensure_models', side_effect=RuntimeError('backend unavailable')):
                fi = FaceIndexer(config)
                self.assertEqual(fi.find_person(), [])

    def test_sync_people_tags_creates_unknown_enrichment(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
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

            known, unknown = sync_people_tags(
                [rec],
                [],
                tmp_path / 'untagged',
                export_untagged=True,
                config={'faces': {'untagged_skip_duplicates': True, 'untagged_cleanup_orphans': False}},
            )

            self.assertEqual((known, unknown), (0, 1))
            enriched = json.loads(meta.read_text())
            self.assertEqual(enriched['person']['status'], 'unknown')
            self.assertEqual(enriched['person']['person_id'], 'UNK-SAMPLE')
            self.assertTrue((tmp_path / 'untagged' / 'UNK-SAMPLE').exists())


if __name__ == '__main__':
    unittest.main()
