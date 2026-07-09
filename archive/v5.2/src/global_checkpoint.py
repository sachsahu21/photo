import json
import os
from pathlib import Path

def load_global_checkpoint(path: str | Path) -> dict:
    """Load global checkpoint JSON from given path.
    Returns dict with keys 'processed' (list) and 'last_index' (int).
    If file does not exist or is invalid, returns empty structure.
    """
    p = Path(path)
    if not p.is_file():
        return {"processed": [], "last_index": -1}
    try:
        with p.open('r', encoding='utf-8') as f:
            data = json.load(f)
        # Ensure expected keys
        processed = data.get('processed', [])
        last_index = data.get('last_index', -1)
        return {"processed": processed, "last_index": last_index}
    except Exception:
        # On error, treat as empty
        return {"processed": [], "last_index": -1}

def save_global_checkpoint(path: str | Path, processed: list, last_index: int) -> None:
    """Save global checkpoint JSON to given path.
    processed: list of processed file paths (strings).
    last_index: index of last processed file (int).
    The function ensures the parent directory exists.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {"processed": processed, "last_index": last_index}
    with p.open('w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
