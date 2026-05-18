import yaml
import logging
from pathlib import Path

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
            self._apply_workspace_root()
            return
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                loaded = yaml.safe_load(f)
            self.config = loaded if isinstance(loaded, dict) else self._defaults()
        except Exception:
            self.config = self._defaults()
        self._apply_workspace_root()

    @staticmethod
    def _is_absolute_path(s: str) -> bool:
        s = (s or '').strip().replace('/', '\\')
        if not s:
            return False
        if len(s) >= 2 and s[0] == '\\' and s[1] == '\\':
            return True
        if len(s) >= 3 and s[1] == ':' and s[2] in ('\\', '/'):
            return True
        return False

    def _apply_workspace_root(self):
        """
        When workspace.root is set, resolve tool artifact paths under that folder
        (metadata, faces, reports, comparisons, thumbnails, logs, scan checkpoint, backup).
        Absolute paths in YAML are left unchanged.
        """
        ws_cfg = self.config.get('workspace') or {}
        root = str(ws_cfg.get('root', '') or '').strip()
        if not root:
            return
        try:
            W = Path(root).expanduser().resolve()
            W.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.warning('workspace.root mkdir failed %s: %s', root, e)
            try:
                W = Path(root).expanduser().resolve()
            except OSError:
                return

        def get(keys):
            d = self.config
            for k in keys:
                if not isinstance(d, dict):
                    return ''
                d = d.get(k)
            return d

        def setv(keys, value: str):
            d = self.config
            for k in keys[:-1]:
                if k not in d or not isinstance(d[k], dict):
                    d[k] = {}
                d = d[k]
            d[keys[-1]] = value

        def join_if_not_abs(keys, subdir: str):
            cur = get(keys)
            cur_s = str(cur if cur is not None else '').strip()
            if self._is_absolute_path(cur_s):
                return
            if not cur_s or cur_s.startswith('./') or not Path(cur_s).is_absolute():
                setv(keys, str(W / subdir))

        join_if_not_abs(['metadata', 'root_folder'], 'metadata')

        join_if_not_abs(['faces', 'data_folder'], 'face_data')

        idx = str(get(['faces', 'index_db']) or '').strip()
        if not self._is_absolute_path(idx):
            data = str(get(['faces', 'data_folder']) or str(W / 'face_data'))
            name = Path(idx).name if idx else 'face_index.sqlite'
            if not name.endswith('.sqlite') and not name.endswith('.db'):
                name = 'face_index.sqlite'
            setv(['faces', 'index_db'], str(Path(data) / name))

        join_if_not_abs(['faces', 'untagged_root'], 'untagged_people')

        join_if_not_abs(['output', 'output_folder'], 'reports')

        join_if_not_abs(['comparison', 'output_folder'], 'comparisons')

        join_if_not_abs(['thumbnails', 'output_folder'], 'thumbnails')

        lf = str(get(['logging', 'file']) if get(['logging', 'file']) is not None else '').strip()
        if not self._is_absolute_path(lf):
            setv(['logging', 'file'], str(W / 'logs' / 'image-scanner.log'))

        ck = str(get(['processing', 'checkpoint_file']) if get(['processing', 'checkpoint_file']) is not None else '').strip()
        if not self._is_absolute_path(ck):
            setv(['processing', 'checkpoint_file'], str(W / '.scan_checkpoint.json'))

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
                'output_folder': './reports',
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
                'root_folder': '',
                'library_root': '',
                'store_relative_paths': True,
                'reconcile_prefer': 'organized',
                'load_recursive': False,
                'auto_reconcile_paths': True,
                'reconcile_remove_missing': False,
                'update_strategy': 'update_missing',
                'schema_version': '1.0',
                'tool_version': 'v5.1',
            },
            'workflow': {
                'reset_dup_sim_for_excel': False,
            },
            'faces': {
                'enabled': False,
                'seed_root': './seed',
                'target_person': '',
                'library_source': 'scan',
                'data_folder': './face_data',
                'index_db': './face_index.sqlite',
                'similarity_threshold': 0.8,
                'similarity_threshold_percent': None,
                'max_results': 200,
                'untagged_root': './untagged_people',
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
                'checkpoint_file': '',
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
                'size': [150, 100],
                'output_folder': './thumbnails',
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
            'comparison': {'enabled': True, 'output_folder': './comparisons'},
            'analytics': {'enabled': True},
            'cloud': {'enabled': False, 'provider': 'none'},
            'streamlit': {'enabled': True, 'port': 8501},
            'logging': {
                'level': 'INFO',
                'file': './logs/image-scanner.log',
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

    def validate(self):
        errors = []
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

        if errors:
            print('\n  Config issues:')
            for e in errors:
                print('    - ' + e)
        return len(errors) == 0

