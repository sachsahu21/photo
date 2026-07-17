"""Resolve and store media paths (absolute + optional library-relative)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple


def get_library_root(config: Dict[str, Any]) -> Optional[Path]:
    """Configurable root for relative_path (e.g. parent of folder2/folder3)."""
    meta = config.get("metadata") or {}
    lr = str(meta.get("library_root", "") or "").strip()
    if not lr:
        return None
    try:
        p = Path(lr).expanduser().resolve()
        return p if p.exists() else p
    except OSError:
        return Path(lr).expanduser()


def store_relative_paths(config: Dict[str, Any]) -> bool:
    meta = config.get("metadata") or {}
    if not meta.get("store_relative_paths", True):
        return False
    return get_library_root(config) is not None


def get_organized_root(config: Dict[str, Any]) -> Optional[Path]:
    org = (config.get("organization") or {}).get("output_folder", "")
    if not org:
        return None
    try:
        return Path(org).expanduser().resolve()
    except OSError:
        return Path(org).expanduser()


def get_scan_root(config: Dict[str, Any]) -> Optional[Path]:
    scan = (config.get("scan") or {}).get("folder_path", "")
    if not scan:
        return None
    try:
        return Path(scan).expanduser().resolve()
    except OSError:
        return Path(scan).expanduser()


def reconcile_prefer(config: Dict[str, Any]) -> str:
    return str((config.get("metadata") or {}).get("reconcile_prefer", "organized")).strip().lower()


def to_relative_path(abs_path: Path | str, library_root: Path) -> str:
    p = Path(abs_path).resolve()
    root = library_root.resolve()
    rel = p.relative_to(root)
    return rel.as_posix()


def resolve_absolute_from_doc(doc: Dict[str, Any], config: Dict[str, Any]) -> Optional[Path]:
    """Best absolute path for a metadata document."""
    f = doc.get("file", {}) if isinstance(doc.get("file"), dict) else {}
    rec = doc.get("record", {}) if isinstance(doc.get("record"), dict) else {}

    lib = get_library_root(config)
    rel = str(f.get("relative_path", "") or "").strip()
    if lib and rel:
        try:
            cand = (lib.resolve() / rel).resolve()
            if cand.is_file():
                return cand
        except (ValueError, OSError):
            pass

    for raw in (
        f.get("full_path"),
        f.get("organized_path"),
        rec.get("full_path"),
    ):
        s = str(raw or "").strip()
        if not s:
            continue
        p = Path(s)
        if p.is_file():
            try:
                return p.resolve()
            except OSError:
                return p
    return None


def paths_equal(a: Path | str, b: Path | str) -> bool:
    try:
        return Path(a).resolve() == Path(b).resolve()
    except OSError:
        return str(a) == str(b)


def apply_media_path_to_doc(
    doc: Dict[str, Any],
    media: Path,
    config: Dict[str, Any],
    json_path: Optional[Path] = None,
) -> bool:
    """
    Write canonical paths into doc['file'] and doc['record'].
    Stores relative_path when metadata.library_root is set.
    Returns True if anything changed.
    """
    media = media.resolve()
    folder = str(media.parent)
    abs_str = str(media)

    f = doc.get("file", {}) if isinstance(doc.get("file"), dict) else {}
    rec = doc.get("record", {}) if isinstance(doc.get("record"), dict) else {}

    lib = get_library_root(config)
    rel_str = ""
    if lib and store_relative_paths(config):
        try:
            rel_str = to_relative_path(media, lib)
        except ValueError:
            rel_str = ""

    # When library_root is not set, recompute relative_path from scan_root so
    # stale paths (from a previous scan with a different scan_root) get corrected.
    if not rel_str:
        scan_root = get_scan_root(config)
        if scan_root:
            try:
                rel_str = media.relative_to(scan_root.resolve()).as_posix()
            except ValueError:
                rel_str = ""

    old_abs = str(f.get("full_path", "") or "")
    old_rel = str(f.get("relative_path", "") or "")
    old_folder = str(f.get("folder", "") or "")
    old_org = str(f.get("organized_path", "") or "")

    changed = (
        not paths_equal(old_abs, media)
        or old_folder != folder
        or old_org != abs_str
        or (rel_str and old_rel != rel_str)
        or (rel_str and not old_rel)
        or (not rel_str and old_rel)  # stale relative_path that now resolves to nothing
    )
    if not changed:
        return False

    if not isinstance(doc.get("file"), dict):
        doc["file"] = {}
    doc["file"]["full_path"] = abs_str
    doc["file"]["organized_path"] = abs_str
    doc["file"]["folder"] = folder
    if not doc["file"].get("filename"):
        doc["file"]["filename"] = media.name
    if rel_str:
        doc["file"]["relative_path"] = rel_str
    elif old_rel:
        # Clear stale relative_path — file is no longer under any known root
        doc["file"]["relative_path"] = ""

    if isinstance(rec, dict):
        rec["full_path"] = abs_str
        rec["folder"] = folder
        if rel_str:
            rec["relative_path"] = rel_str
        elif old_rel:
            rec["relative_path"] = ""
        doc["record"] = rec

    if json_path is not None:
        doc["metadata_path"] = str(json_path.resolve())
    return True


def enrich_record_resolved_paths(rec: Dict[str, Any], config: Dict[str, Any]) -> None:
    """Fill full_path/folder on a flat record from relative_path + library_root."""
    lib = get_library_root(config)
    rel = str(rec.get("relative_path", "") or "").strip()
    if not rel:
        f_rel = ""
        # may only be in nested doc when loading
    else:
        f_rel = rel
    if lib and f_rel:
        try:
            p = (lib.resolve() / f_rel).resolve()
            if p.is_file():
                rec["full_path"] = str(p)
                rec["folder"] = str(p.parent)
        except (ValueError, OSError):
            pass
