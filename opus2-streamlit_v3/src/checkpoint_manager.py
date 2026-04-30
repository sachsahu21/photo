

# ============================================================
# FILE: src/checkpoint_manager.py  (#4 - NEW)
# ============================================================
"""
Checkpoint Manager - Save/resume scan progress.
"""

import json
import logging
from pathlib import Path
from typing import Set, Optional

logger = logging.getLogger(__name__)

CHECKPOINT_FILE = '.scan_checkpoint.json'


class CheckpointManager:
    """Manage scan checkpoints for resume capability."""

    def __init__(self, checkpoint_dir='.', interval=100):
        self.checkpoint_path = Path(checkpoint_dir) / CHECKPOINT_FILE
        self.interval = interval
        self.processed_files: Set[str] = set()
        self.counter = 0

    def load(self):
        """Load existing checkpoint."""
        try:
            if self.checkpoint_path.exists():
                with open(self.checkpoint_path, 'r') as f:
                    data = json.load(f)
                self.processed_files = set(data.get('processed', []))
                logger.info(f"Checkpoint loaded: {len(self.processed_files)} files already processed")
                return True
        except Exception as e:
            logger.warning(f"Checkpoint load error: {e}")
        return False

    def is_processed(self, filepath):
        """Check if file was already processed."""
        return str(filepath) in self.processed_files

    def mark_processed(self, filepath):
        """Mark file as processed, auto-save at interval."""
        self.processed_files.add(str(filepath))
        self.counter += 1
        if self.counter % self.interval == 0:
            self.save()

    def save(self):
        """Save checkpoint to disk."""
        try:
            with open(self.checkpoint_path, 'w') as f:
                json.dump({'processed': list(self.processed_files)}, f)
        except Exception as e:
            logger.warning(f"Checkpoint save error: {e}")

    def clear(self):
        """Clear checkpoint."""
        self.processed_files.clear()
        self.counter = 0
        try:
            if self.checkpoint_path.exists():
                self.checkpoint_path.unlink()
        except Exception:
            pass

