import yaml, logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)

class ConfigManager:
    DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

    def __init__(self, config_path: str = None):
        self.config_path = Path(config_path) if config_path else self.DEFAULT_CONFIG_PATH
        self.config = self._load()
        self._validate()

    def _load(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config not found: {self.config_path}")
        with open(self.config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        logger.info(f"Config loaded from {self.config_path}")
        return config

    def _validate(self):
        for field in ['scan', 'blur_detection', 'organization', 'output']:
            if field not in self.config:
                raise ValueError(f"Missing config section: {field}")
        scan_folder = Path(self.config['scan']['folder_path'])
        if not scan_folder.exists():
            raise ValueError(f"Scan folder does not exist: {scan_folder}")
        logger.info("Config validation passed")

    def get(self, key: str, default: Any = None) -> Any:
        keys = key.split('.')
        value = self.config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default

    def set(self, key: str, value: Any):
        keys = key.split('.')
        config = self.config
        for k in keys[:-1]:
            config = config.setdefault(k, {})
        config[keys[-1]] = value

    def to_dict(self) -> Dict[str, Any]:
        return self.config
