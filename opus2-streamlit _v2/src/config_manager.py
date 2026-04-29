# ============================================================
# FILE: src/config_manager.py
# ============================================================
"""Configuration Manager v2.2"""

import yaml
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class ConfigManager:

    def __init__(self, config_path='config.yaml'):
        self.config_path = self._resolve_path(config_path)
        self.config = {}
        self._load_config()

    def _resolve_path(self, config_path):
        for p in [Path(config_path), Path(__file__).parent.parent / config_path,
                   Path.cwd() / config_path]:
            if p.exists():
                return p
        return Path(config_path)

    def _load_config(self):
        if not self.config_path.exists():
            logger.warning(f"Config not found: {self.config_path}, using defaults")
            self.config = self._defaults()
            return
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                loaded = yaml.safe_load(f)
            if isinstance(loaded, dict):
                self.config = loaded
                logger.info(f"Config loaded: {self.config_path}")
            else:
                self.config = self._defaults()
        except Exception as e:
            logger.error(f"Config error: {e}")
            self.config = self._defaults()

    def _defaults(self):
        return {
            'scan': {
                'folder_path': './sample_images',
                'recursive': True,
                'extensions': {
                    'images': ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'tif',
                               'webp', 'heic', 'heif', 'raw', 'cr2', 'nef', 'arw', 'dng'],
                    'videos': ['mp4', 'mov', 'avi', 'mkv', '3gp', 'm4v', 'mpg', 'mpeg',
                               'wmv', 'flv', 'webm', 'mts'],
                },
            },
            'blur_detection': {'enabled': True, 'threshold': 100},
            'duplicates': {
                'enabled': True, 'hash_algorithm': 'md5', 'match_mode': 'exact',
                'similarity_threshold': 90, 'auto_select_best': True,
                'selection_criteria': ['quality', 'resolution', 'date', 'size'],
            },
            'organization': {
                'output_folder': './organized_images',
                'day_threshold': 60,
                'use_exif_date': True,
                'operation': 'copy',
                'conflict_resolution': 'rename',
                'reuse_existing_folders': True,
                'video_subfolder': True,
                'folder_structure': 'flat',
                'separate_screenshots': True,
            },
            'output': {
                'output_folder': './reports',
                'filename_prefix': 'image-scan',
                'sheets': {
                    'all_images': True, 'blurry_images': True, 'duplicates': True,
                    'summary': True, 'quality_report': True, 'analytics': True,
                    'clusters': True,
                },
            },
            'processing': {
                'threads': 0,
                'show_progress': True,
                'verbose': False,
                'checkpoint_enabled': True,
                'checkpoint_interval': 100,
                'fast_mode': False,
                'skip_video_hash': True,
            },
            'face_detection': {'enabled': False, 'method': 'opencv'},
            'thumbnails': {
                'enabled': True, 'size': [150, 100],
                'output_folder': './thumbnails', 'embed_in_excel': True,
            },
            'clustering': {
                'enabled': False, 'method': 'color_histogram',
                'n_clusters': 10, 'min_cluster_size': 3,
            },
            'geocoding': {'enabled': False, 'method': 'offline'},
            'auto_tagging': {
                'enabled': False, 'model': 'mobilenet',
                'top_k': 5, 'confidence_threshold': 0.3,
            },
            'comparison': {'enabled': True, 'output_folder': './comparisons'},
            'analytics': {'enabled': True},
            'cloud': {
                'enabled': False, 'provider': 'none',
                'bucket': '', 'prefix': '', 'credentials_path': '',
            },
            'streamlit': {'enabled': True, 'port': 8501},
            'logging': {'level': 'INFO', 'file': './logs/image-scanner.log', 'console': True},
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
            errors.append("scan.folder_path required")
        elif not Path(sp).exists():
            errors.append(f"scan.folder_path not found: {sp}")
        if not self.get('organization.output_folder'):
            errors.append("organization.output_folder required")

        # Validate folder_structure
        fs = self.get('organization.folder_structure', 'flat')
        if fs not in ('flat', 'year-month', 'year-month-day'):
            errors.append(f"Invalid folder_structure: {fs}. Use: flat, year-month, year-month-day")

        for e in errors:
            logger.error(f"Config: {e}")
        if errors:
            print("\n  ⚠ Config issues:")
            for e in errors:
                print(f"    - {e}")
        return len(errors) == 0
