"""Resolve mandatory workspace.root artifact paths."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional


BACKUP_FILENAME = "records-backup.pkl"
CHECKPOINT_FILENAME = ".scan_checkpoint.json"
LOG_FILENAME = "image-scanner.log"
GLOBAL_CHECKPOINT_FILENAME = "global_checkpoint.json"

# Default subfolder names under workspace.root
DEFAULTS = {
    "metadata": "metadata",
    "face_data": "face_data",
    "untagged_people": "untagged_people",
    "reports": "reports",
    "comparisons": "comparisons",
    "thumbnails": "thumbnails",
    "logs": "logs",
    "checkpoints": "checkpoints",
    "quarantine": "quarantine",
}


def is_absolute_path(s: str) -> bool:
    s = (s or "").strip().replace("/", "\\")
    if not s:
        return False
    if len(s) >= 2 and s[0] == "\\" and s[1] == "\\":
        return True
    if len(s) >= 3 and s[1] == ":" and s[2] in ("\\", "/"):
        return True
    return False


def _basename_subdir(value: str) -> str:
    """Turn a subfolder name or relative path into a single folder component."""
    s = (value or "").strip().replace("\\", "/").strip("./")
    if not s:
        return ""
    parts = [p for p in s.split("/") if p and p not in (".", "..")]
    return parts[-1] if parts else ""


def subdir_from_section(
    section: Optional[Dict[str, Any]],
    legacy_key: str,
    default: str,
    alt_keys: tuple = (),
) -> str:
    """
    Read optional ``subfolder``, legacy key, or alt_keys as a subfolder name only.
    Absolute values are ignored (default used).
    """
    if not isinstance(section, dict):
        return default
    sf = str(section.get("subfolder", "") or "").strip()
    if sf:
        name = _basename_subdir(sf)
        return name or default
    for key in (legacy_key,) + tuple(alt_keys):
        legacy = str(section.get(key, "") or "").strip()
        if legacy:
            if is_absolute_path(legacy):
                return default
            name = _basename_subdir(legacy)
            return name or default
    return default


def resolve_workspace_root(config: Dict[str, Any]) -> Path:
    ws = (config.get("workspace") or {})
    root = str(ws.get("root", "") or "").strip()
    if not root:
        raise ValueError("workspace.root is required in config.yaml")
    return Path(root).expanduser().resolve()


def records_backup_path(config) -> Path:
    if hasattr(config, "workspace_root"):
        return config.workspace_root() / BACKUP_FILENAME
    if hasattr(config, "to_dict"):
        config = config.to_dict()
    return resolve_workspace_root(config) / BACKUP_FILENAME


def apply_workspace_artifacts(config: Dict[str, Any]) -> None:
    """
    Force all tool artifact paths under workspace.root. Mutates *config* in place.
    Photo libraries (scan, organize, seed) are not modified.
    """
    W = resolve_workspace_root(config)
    W.mkdir(parents=True, exist_ok=True)

    meta = config.setdefault("metadata", {})
    meta_sub = subdir_from_section(meta, "root_folder", DEFAULTS["metadata"])
    meta["root_folder"] = str(W / meta_sub)

    faces = config.setdefault("faces", {})
    data_sub = subdir_from_section(
        faces, "data_folder", DEFAULTS["face_data"], alt_keys=("data_subfolder",)
    )
    faces["data_folder"] = str(W / data_sub)

    seed_sub = subdir_from_section(faces, "seed_root", "seed")
    faces["seed_root"] = str(W / seed_sub) if not is_absolute_path(seed_sub) else seed_sub

    db_name = str(faces.get("index_db_filename") or "face_index.sqlite").strip()
    if not db_name:
        db_name = "face_index.sqlite"
    faces["index_db"] = str(W / Path(db_name).name)

    untagged_sub = subdir_from_section(
        faces, "untagged_root", DEFAULTS["untagged_people"], alt_keys=("untagged_subfolder",)
    )
    untagged_value = str(faces.get("untagged_root") or "").strip()
    if untagged_value and is_absolute_path(untagged_value):
        faces["untagged_root"] = untagged_value
    else:
        faces["untagged_root"] = str(W / untagged_sub)

    out = config.setdefault("output", {})
    out_sub = subdir_from_section(out, "output_folder", DEFAULTS["reports"])
    out["output_folder"] = str(W / out_sub)

    cmp_cfg = config.setdefault("comparison", {})
    cmp_sub = subdir_from_section(cmp_cfg, "output_folder", DEFAULTS["comparisons"])
    cmp_cfg["output_folder"] = str(W / cmp_sub)

    thumb = config.setdefault("thumbnails", {})
    thumb_sub = subdir_from_section(thumb, "output_folder", DEFAULTS["thumbnails"])
    thumb["output_folder"] = str(W / thumb_sub)

    log_cfg = config.setdefault("logging", {})
    log_sub = subdir_from_section(log_cfg, "file", DEFAULTS["logs"])
    log_name = str(log_cfg.get("log_filename") or LOG_FILENAME).strip() or LOG_FILENAME
    log_name = Path(log_name.replace("\\", "/")).name or LOG_FILENAME
    log_cfg["file"] = str(W / log_sub / log_name)

    proc = config.setdefault("processing", {})
    checkpoint_sub = subdir_from_section(
        proc, "checkpoint_subfolder", DEFAULTS["checkpoints"]
    )
    checkpoint_root = W / checkpoint_sub

    scan_ck_name = str(
        proc.get("scan_checkpoint_filename")
        or proc.get("checkpoint_filename")
        or proc.get("checkpoint_file")
        or ""
    ).strip()
    if scan_ck_name:
        scan_ck_name = Path(scan_ck_name.replace("\\", "/")).name
    else:
        scan_ck_name = CHECKPOINT_FILENAME

    global_ck_name = str(proc.get("global_checkpoint_filename") or "").strip()
    if global_ck_name:
        global_ck_name = Path(global_ck_name.replace("\\", "/")).name
    else:
        global_ck_name = GLOBAL_CHECKPOINT_FILENAME

    proc["checkpoint_file"] = str(checkpoint_root / scan_ck_name)
    proc["global_checkpoint_file"] = str(checkpoint_root / global_ck_name)

    quarantine = config.setdefault("quarantine", {})
    quarantine_sub = subdir_from_section(
        quarantine, "root_folder", DEFAULTS["quarantine"]
    )
    quarantine["root_folder"] = str(W / quarantine_sub)
    quarantine.setdefault("preserve_relative_paths", True)
    quarantine.setdefault("manifest_prefix", "quarantine-manifest")

    config.setdefault("workspace", {})["_resolved_root"] = str(W)
