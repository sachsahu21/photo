# ============================================================
# FILE: src/checkpoint_manager.py
# ============================================================
"""Checkpoint Manager v2.4"""
import json, logging
from pathlib import Path
logger = logging.getLogger(__name__)

class CheckpointManager:
    def __init__(self, interval=100):
        self.interval = interval
        self.processed = set()
        self.count = 0
        self._file = '.scan_checkpoint.json'
    def load(self):
        try:
            p = Path(self._file)
            if p.exists():
                with open(p, 'r') as f:
                    self.processed = set(json.load(f).get('processed', []))
                return True
        except Exception: pass
        return False
    def save(self):
        try:
            with open(self._file, 'w') as f:
                json.dump({'processed': list(self.processed)}, f)
        except Exception: pass
    def mark_processed(self, fp):
        self.processed.add(fp)
        self.count += 1
        if self.count % self.interval == 0: self.save()
    def is_processed(self, fp):
        return fp in self.processed
    def clear(self):
        try:
            p = Path(self._file)
            if p.exists(): p.unlink()
        except Exception: pass
