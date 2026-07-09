"""
Configuration Manager
Handles loading and validating configuration
"""

import yaml
from pathlib import Path
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class ConfigManager:
    """Load and manage configuration from YAML file"""

    DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

    def __init__(self, config_path: str = None):
        """
        Initialize configuration manager

        Args:
            config_path: Path to config.yaml file
        """
        self.config_path = Path(config_path) if config_path else self.DEFAULT_CONFIG_PATH
        self.config = self._load_config()
        self._validate_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        if not self.config_path.exists():
            logger.error(f"Config file not found: {self.config_path}")
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            logger.info(f"Configuration loaded from {self.config_path}")
            return config
        except yaml.YAMLError as e:
            logger.error(f"Error parsing YAML: {e}")
            raise

    def _validate_config(self):
        """Validate required configuration fields"""
        required_fields = ['scan', 'blur_detection', 'organization', 'output']

        for field in required_fields:
            if field not in self.config:
                raise ValueError(f"Missing required config section: {field}")

        # Validate scan folder
        scan_folder = Path(self.config['scan']['folder_path'])
        if not scan_folder.exists():
            raise ValueError(f"Scan folder does not exist: {scan_folder}")

        logger.info("Configuration validation passed")

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by dot notation (e.g., 'blur_detection.threshold')"""
        keys = key.split('.')
        value = self.config

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default

        return value if value is not None else default

    def set(self, key: str, value: Any):
        """Set configuration value"""
        keys = key.split('.')
        config = self.config

        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]

        config[keys[-1]] = value

    def to_dict(self) -> Dict[str, Any]:
        """Return full configuration as dictionary"""
        return self.config