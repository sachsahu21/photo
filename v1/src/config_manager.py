
# ============================================================
# FILE: src/config_manager.py
# ============================================================
"""
Configuration Manager - YAML config loading with dot-notation access
"""

import yaml
import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manages application configuration from YAML file."""

    def __init__(self, config_path='config.yaml'):
        self.config_path = self._resolve_path(config_path)
        self.config = {}
        self._load_config()

    def _resolve_path(self, config_path):
        candidates = [
            Path(config_path),
            Path(__file__).parent.parent / config_path,
            Path.cwd() / config_path,
            Path.cwd() / 'config' / config_path,
        ]
        for p in candidates:
            if p.exists():
                return p
        return candidates[0]

    def _load_config(self):
        if not self.config_path.exists():
            logger.warning(f"Config not found: {self.config_path}, using defaults")
            self.config = self._defaults()
            return

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                loaded = yaml.safe_load(f)

            if not isinstance(loaded, dict):
                logger.warning("Config is not a valid YAML mapping, using defaults")
                self.config = self._defaults()
                return

            self.config = loaded
            logger.info(f"Config loaded from {self.config_path}")

        except yaml.YAMLError as e:
            logger.error(f"YAML parse error: {e}")
            self.config = self._defaults()
        except Exception as e:
            logger.error(f"Config load error: {e}")
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
            'blur_detection': {
                'enabled': True,
                'threshold': 100,
            },
            'duplicates': {
                'enabled': True,
                'hash_algorithm': 'md5',
                'match_mode': 'exact',
                'similarity_threshold': 90,
                'auto_select_best': True,
                'selection_criteria': ['quality', 'resolution', 'date', 'size'],
            },
            'organization': {
                'output_folder': './organized_images',
                'day_threshold': 60,
                'use_exif_date': True,
                'operation': 'copy',
                'conflict_resolution': 'rename',
            },
            'output': {
                'output_folder': './reports',
                'filename_prefix': 'image_scan',
                'sheets': {
                    'all_images': True,
                    'blurry_images': True,
                    'duplicates': True,
                    'summary': True,
                    'quality_report': True,
                },
            },
            'processing': {
                'threads': 0,
                'show_progress': True,
                'verbose': False,
            },
            'logging': {
                'level': 'INFO',
                'file': './logs/image_scanner.log',
                'console': True,
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

        scan_path = self.get('scan.folder_path')
        if not scan_path:
            errors.append("scan.folder_path is required")
        elif not Path(scan_path).exists():
            errors.append(f"scan.folder_path does not exist: {scan_path}")

        threshold = self.get('blur_detection.threshold')
        if threshold is not None and not isinstance(threshold, (int, float)):
            errors.append("blur_detection.threshold must be a number")

        output = self.get('organization.output_folder')
        if not output:
            errors.append("organization.output_folder is required")

        for err in errors:
            logger.error(f"Config validation: {err}")

        if errors:
            print("\n  ⚠ Configuration issues:")
            for err in errors:
                print(f"    - {err}")

        return len(errors) == 0
