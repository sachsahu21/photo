
# ============================================================================
# FILE: src/config_manager.py
# ============================================================================
"""
Configuration Manager - Handles YAML configuration loading and access
"""

import yaml
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manages application configuration with dot notation access"""

    def __init__(self, config_path: str = "config.yaml"):
        """
        Initialize configuration manager

        Args:
            config_path: Path to YAML configuration file
        """
        self.config_path = Path(config_path)
        self.config: Dict[str, Any] = {}
        self._load_config() 

    def _load_config(self) -> None:
        """Load configuration from YAML file"""
        try:
            if not self.config_path.exists():
                logger.warning(f"Config file not found: {self.config_path}")
                self.config = self._get_default_config()
                return

            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f) or {}
                logger.info(f"Configuration loaded from {self.config_path}")

        except yaml.YAMLError as e:
            logger.error(f"YAML parsing error: {e}")
            self.config = self._get_default_config()
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            self.config = self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration"""
        return {
            'scan': {
                'folder_path': './sample_images',
                'recursive': True,
                'supported_extensions': ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'webp', 'heic', 'raw', 'cr2', 'nef', 'arw', 'dng']
            },
            'blur_detection': {
                'threshold': 100,
                'method': 'laplacian',
                'quality_thresholds': {'very_blurry': 50, 'blurry': 100, 'fair': 200}
            },
            'duplicates': {
                'hash_algorithm': 'md5',
                'selection_criteria': ['quality', 'resolution', 'date', 'size']
            },
            'organization': {
                'output_folder': './organized_images',
                'operation_type': 'copy',
                'folder_structure': 'date_based',
                'date_format': 'yyyymmdd',
                'threshold_for_daily_folders': 60,
                'handle_conflicts': 'rename'
            },
            'excel': {
                'output_folder': './reports',
                'filename_pattern': 'image_scan_{timestamp}.xlsx',
                'freeze_rows': 1,
                'auto_filter': True
            },
            'logging': {
                'level': 'INFO',
                'file': './logs/image_scanner.log'
            },
            'processing': {
                'thread_count': 4,
                'batch_size': 100,
                'timeout_seconds': 3600
            }
        }

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value using dot notation

        Args:
            key: Configuration key (e.g., 'scan.folder_path')
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        keys = key.split('.')
        value = self.config

        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default

    def set(self, key: str, value: Any) -> None:
        """
        Set configuration value using dot notation

        Args:
            key: Configuration key (e.g., 'scan.folder_path')
            value: Value to set
        """
        keys = key.split('.')
        config = self.config

        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]

        config[keys[-1]] = value
        logger.debug(f"Config set: {key} = {value}")

    def to_dict(self) -> Dict[str, Any]:
        """Get entire configuration as dictionary"""
        return self.config.copy()

    def validate(self) -> bool:
        """Validate configuration"""
        required_keys = [
            'scan.folder_path',
            'blur_detection.threshold',
            'organization.output_folder'
        ]

        for key in required_keys:
            if self.get(key) is None:
                logger.error(f"Missing required config: {key}")
                return False

        return True
