"""Checkpoint Manager v2.4"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class CheckpointManager:
    def __init__(self, interval=100, file_path=None):
        if not file_path:
            raise ValueError('checkpoint file_path required (set workspace.root in config.yaml)')
        self.interval = interval
        self.processed = set()
        self.count = 0
        self._file = str(file_path)

    def load(self):
        try:
            p = Path(self._file)
            if p.exists():
                with open(p, 'r', encoding='utf-8') as f:
                    self.processed = set(json.load(f).get('processed', []))
                return True
        except Exception:
            pass
        return False

    def save(self):
        try:
            p = Path(self._file)
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, 'w', encoding='utf-8') as f:
                json.dump({'processed': list(self.processed)}, f)
        except Exception:
            pass

    def mark_processed(self, fp):
        self.processed.add(fp)
        self.count += 1
        if self.count % self.interval == 0:
            self.save()

    def is_processed(self, fp):
        return fp in self.processed

    def clear(self):
        try:
            p = Path(self._file)
            if p.exists():
                p.unlink()
        except Exception:
            pass

