import yaml
import logging
from pathlib import Path

from .workspace_paths import apply_workspace_artifacts, resolve_workspace_root

logger = logging.getLogger(__name__)


class ConfigManager:
    def __init__(self, config_path='config.yaml'):
        self.config_path = self._resolve(config_path)
        self.config = {}
        self._load()

    def _resolve(self, cp):
        for p in [Path(cp), Path(__file__).parent.parent / cp, Path.cwd() / cp]:
            if p.exists():
                return p
        return Path(cp)

    def _load(self):
        if not self.config_path.exists():
            self.config = self._defaults()
        else:
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    loaded = yaml.safe_load(f)
                self.config = loaded if isinstance(loaded, dict) else self._defaults()
            except Exception:
                self.config = self._defaults()
        self._apply_workspace_root()

    def _apply_workspace_root(self):
        """Require workspace.root and resolve all artifact paths under it."""
        try:
            apply_workspace_artifacts(self.config)
        except ValueError as e:
            logger.error(str(e))

    def workspace_root(self) -> Path:
        return resolve_workspace_root(self.config)

    def _defaults(self):
        return {
            'workspace': {'root': ''},
            'scan': {
                'folder_path': './sample_images',
                'recursive': True,
                'extensions': {
                    'images': [
                        'jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'tif', 'webp',
                        'heic', 'heif', 'raw', 'cr2', 'nef', 'arw', 'dng'
                    ],
                    'videos': [
                        'mp4', 'mov', 'avi', 'mkv', '3gp', 'm4v', 'mpg',
                        'mpeg', 'wmv', 'flv', 'webm', 'mts'
                    ],
                },
            },
            'blur_detection': {'enabled': True, 'threshold': 100},
            'duplicates': {
                'enabled': True,
                'hash_algorithm': 'md5',
                'match_mode': 'exact',
                'similarity_threshold': 90,
                'selection_criteria': ['quality', 'resolution', 'date', 'size'],
            },
            'similar_detection': {
                'enabled': False,
                'ahash': True,
                'phash': True,
                'dhash': True,
                'color_histogram': False,
                'sift': False,
                'ahash_threshold': 10,
                'phash_threshold': 10,
                'dhash_threshold': 10,
                'histogram_threshold': 0.85,
                'sift_threshold': 30,
                'hash_size': 8,
                'max_compare_per_image': 200,
            },
            'organization': {
                'output_folder': './organized_images',
                'retire_scan_path_json_on_organize': True,
                'day_threshold': 60,
                'use_exif_date': True,
                'operation': 'copy',
                'conflict_resolution': 'rename',
                'reuse_existing_folders': True,
                'video_subfolder': True,
                'folder_structure': 'year',
                'separate_screenshots': True,
                'screenshot_keywords': [
                    'screenshot', 'screen_shot', 'screen-shot',
                    'capture', 'snip', 'snipaste', 'sharex',
                    'screen recording', 'screenrecording', 'printscreen',
                ],
                'screenshot_detect_by_resolution': True,
                'screenshot_custom_resolutions': [],
            },
            'output': {
                'subfolder': 'reports',
                'filename_prefix': 'image-scan',
                'sheets': {
                    'all_images': True,
                    'blurry_images': True,
                    'duplicates': True,
                    'similar_images': True,
                    'summary': True,
                    'quality_report': True,
                    'analytics': True,
                    'clusters': True,
                },
            },
            'metadata': {
                'subfolder': 'metadata',
                'library_root': '',
                'store_relative_paths': True,
                'reconcile_prefer': 'organized',
                'load_recursive': False,
                'auto_reconcile_paths': True,
                'reconcile_remove_missing': False,
                'dedupe_on_reconcile': True,
                'dedupe_before_excel': False,
                'dedupe_after_scan': True,
                'dedupe_prefer': 'organized',
                'update_strategy': 'update_missing',
                'schema_version': '2.0',
                'tool_version': 'v5.3',
            },
            'workflow': {
                'reset_dup_sim_for_excel': False,
                'excel_exclude_missing_files': False,
                'excel_include_file_exists_column': True,
            },
            'faces': {
                'enabled': False,
                'seed_root': 'seed',
                'target_person': '',
                'library_source': 'scan',
                'data_subfolder': 'face_data',
                'index_db_filename': 'face_index.sqlite',
                'similarity_threshold': 0.8,
                'similarity_threshold_percent': None,
                'max_results': 50000,
                'export_untagged': True,
                'untagged_skip_duplicates': True,
                'untagged_cleanup_orphans': True,
                'untagged_subfolder': 'untagged_people',
                'untagged_max_samples': 1,
                'untagged_pick_best_quality': True,
                'untagged_export_mode': 'full',
            },
            'processing': {
                'threads': 0,
                'show_progress': True,
                'verbose': False,
                'checkpoint_enabled': True,
                'checkpoint_interval': 100,
                'checkpoint_subfolder': 'checkpoints',
                'scan_checkpoint_filename': '.scan_checkpoint.json',
                'global_checkpoint_filename': 'global_checkpoint.json',
                'metadata_flush_interval': 100,
                'fast_mode': False,
                'skip_video_hash': True,
            },
            'face_detection': {
                'enabled': False,
                'method': 'opencv',
                'min_face_size': 24,
                'min_neighbors': 4,
                'scale_factor': 1.08,
            },
            'thumbnails': {
                'enabled': True,
                'subfolder': 'thumbnails',
                'size': [150, 100],
                'embed_in_excel': False,
            },
            'clustering': {
                'enabled': False,
                'method': 'color_histogram',
                'n_clusters': 10,
                'min_cluster_size': 3,
            },
            'geocoding': {'enabled': False, 'method': 'offline'},
            'auto_tagging': {
                'enabled': False,
                'model': 'mobilenet',
                'top_k': 5,
                'confidence_threshold': 0.3,
            },
            'comparison': {'enabled': True, 'subfolder': 'comparisons', 'generate_after_excel': False},
            'analytics': {'enabled': True},
            'cloud': {'enabled': False, 'provider': 'none'},
            'quarantine': {
                'subfolder': 'quarantine',
                'preserve_relative_paths': True,
                'manifest_prefix': 'quarantine-manifest',
            },
            'streamlit': {'enabled': True, 'port': 8501},
            'logging': {
                'level': 'INFO',
                'subfolder': 'logs',
                'log_filename': 'image-scanner.log',
                'console': True
            },
        }

    def get(self, key, default=None):
        keys = key.split('.')
        value = self.config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value

    def set(self, key, value):
        keys = key.split('.')
        cfg = self.config
        for k in keys[:-1]:
            if k not in cfg or not isinstance(cfg[k], dict):
                cfg[k] = {}
            cfg = cfg[k]
        cfg[keys[-1]] = value

    def to_dict(self):
        return self.config.copy()

    def artifact_summary(self):
        """Resolved artifact paths for display."""
        return {
            'workspace': str(self.get('workspace._resolved_root') or self.get('workspace.root', '')),
            'metadata': self.get('metadata.root_folder', ''),
            'face_data': self.get('faces.data_folder', ''),
            'face_index': self.get('faces.index_db', ''),
            'untagged': self.get('faces.untagged_root', ''),
            'reports': self.get('output.output_folder', ''),
            'comparisons': self.get('comparison.output_folder', ''),
            'thumbnails': self.get('thumbnails.output_folder', ''),
            'quarantine': self.get('quarantine.root_folder', ''),
            'log': self.get('logging.file', ''),
            'checkpoint': self.get('processing.checkpoint_file', ''),
            'backup': str(self.workspace_root() / 'records-backup.pkl'),
        }

    def validate(self):
        errors = []
        ws = str(self.get('workspace.root', '') or '').strip()
        if not ws:
            errors.append('workspace.root is required (all tool artifacts live under this folder)')
        else:
            try:
                apply_workspace_artifacts(self.config)
            except ValueError as e:
                errors.append(str(e))
            except OSError as e:
                errors.append('workspace.root not usable: ' + str(e))

        rf = str(self.get('metadata.root_folder', '') or '').strip()
        if ws and not rf:
            errors.append('metadata vault not resolved (check workspace.root)')

        sp = self.get('scan.folder_path')
        if not sp:
            errors.append('scan.folder_path required')
        elif not Path(sp).exists():
            errors.append('scan.folder_path not found: ' + str(sp))

        fs = self.get('organization.folder_structure', 'year')
        if fs not in ('flat', 'year', 'year-month-date'):
            errors.append(
                'Invalid folder_structure: ' + str(fs) +
                ' (use flat, year, or year-month-date)'
            )

        us = str(self.get('metadata.update_strategy', 'update_missing') or '').lower()
        if us not in ('skip_if_present', 'update_missing', 'refresh', 'full_overwrite'):
            errors.append('Invalid metadata.update_strategy: ' + us)

        if errors:
            print('\n  Config issues:')
            for e in errors:
                print('    - ' + e)
        return len(errors) == 0
