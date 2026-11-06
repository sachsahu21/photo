import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict

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

def prune_global_checkpoint(checkpoint_path: str | Path, config: Dict[str, Any]) -> int:
    """Remove global checkpoint entries whose vault JSON no longer exists.

    This keeps the checkpoint in sync after vault JSONs are deleted, quarantined,
    or lost due to a crashed scan — so the next scan re-processes those files.
    Returns the number of stale entries removed.
    """
    cp_path = Path(checkpoint_path)
    if not cp_path.is_file():
        return 0

    proc_cfg = config.get("processing") or {}
    ws = (config.get("workspace") or {}).get("root", "")
    md_cfg = config.get("metadata") or {}
    subfolder = str(md_cfg.get("subfolder") or "metadata").strip() or "metadata"
    vault_dir = Path(ws) / subfolder if ws else None
    if not vault_dir or not vault_dir.exists():
        return 0

    data = load_global_checkpoint(cp_path)
    before = data["processed"]
    if not before:
        return 0

    surviving = []
    removed = 0
    for fp in before:
        sha1 = hashlib.sha1(fp.encode("utf-8")).hexdigest()
        if (vault_dir / (sha1 + ".json")).exists():
            surviving.append(fp)
        else:
            removed += 1

    if removed:
        save_global_checkpoint(cp_path, surviving, len(surviving) - 1)
    return removed


def rebuild_checkpoint_from_vault(checkpoint_path: str | Path, config: Dict[str, Any]) -> int:
    """Rebuild the global checkpoint by reading file paths from existing vault JSONs.

    Used when the checkpoint is empty but vault JSONs already exist — avoids a
    full re-scan of files whose metadata is already on disk.
    Returns the number of entries written.
    """
    ws = (config.get("workspace") or {}).get("root", "")
    md_cfg = config.get("metadata") or {}
    subfolder = str(md_cfg.get("subfolder") or "metadata").strip() or "metadata"
    vault_dir = Path(ws) / subfolder if ws else None
    if not vault_dir or not vault_dir.exists():
        return 0

    index_name = "metadata-index.json"
    processed = []
    for jf in vault_dir.glob("*.json"):
        if jf.name == index_name:
            continue
        try:
            doc = json.loads(jf.read_text(encoding="utf-8"))
            file_section = doc.get("file") or {}
            fp = str(file_section.get("full_path") or "").strip()
            if fp:
                processed.append(fp)
        except Exception:
            pass

    if processed:
        save_global_checkpoint(checkpoint_path, processed, len(processed) - 1)
    return len(processed)


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
