
# ============================================================
# FILE: src/checkpoint_manager.py
# ============================================================
"""Checkpoint Manager v2.3"""

import json
import logging
from pathlib import Path
logger = logging.getLogger(__name__)
CHECKPOINT_FILE = '.scan_checkpoint.json'


class CheckpointManager:
    def __init__(self, interval=100):
        self.interval = interval
        self.processed = set()
        self.count = 0

    def load(self):
        try:
            p = Path(CHECKPOINT_FILE)
            if p.exists():
                with open(p, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.processed = set(data.get('processed', []))
                return True
        except Exception:
            pass
        return False

    def save(self):
        try:
            with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
                json.dump({'processed': list(self.processed)}, f)
        except Exception:
            pass

    def mark_processed(self, filepath):
        self.processed.add(filepath)
        self.count += 1
        if self.count % self.interval == 0:
            self.save()

    def is_processed(self, filepath):
        return filepath in self.processed

    def clear(self):
        try:
            p = Path(CHECKPOINT_FILE)
            if p.exists():
                p.unlink()
        except Exception:
            pass
