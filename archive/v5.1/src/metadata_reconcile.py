"""Fast metadata path reconcile for vault JSON (no full rescan)."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .metadata_paths import (
    apply_media_path_to_doc,
    get_organized_root,
    get_scan_root,
    reconcile_prefer,
    resolve_absolute_from_doc,
)
from .metadata_store import MetadataStore, _ensure_json_serializable

logger = logging.getLogger(__name__)


def _media_extensions(config: Dict[str, Any]) -> Set[str]:
    scan = (config.get("scan") or {}).get("extensions") or {}
    exts: Set[str] = set()
    for group in ("images", "videos"):
        for e in scan.get(group) or []:
            s = str(e).lower().lstrip(".")
            if s:
                exts.add("." + s)
    if not exts:
        exts = {
            ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".heic", ".heif",
            ".mp4", ".mov", ".avi", ".mkv", ".m4v",
        }
    return exts


def _search_roots(config: Dict[str, Any]) -> List[Path]:
    roots: List[Path] = []
    org = get_organized_root(config)
    scan = get_scan_root(config)
    if org:
        roots.append(org)
    if scan and scan not in roots:
        roots.append(scan)
    return roots


def _build_file_index(
    roots: List[Path],
    exts: Set[str],
) -> Tuple[Dict[str, List[Path]], Dict[Tuple[str, int], List[Path]]]:
    by_name: Dict[str, List[Path]] = defaultdict(list)
    by_name_size: Dict[Tuple[str, int], List[Path]] = defaultdict(list)
    for root in roots:
        try:
            for p in root.rglob("*"):
                if not p.is_file():
                    continue
                if p.suffix.lower() not in exts:
                    continue
                key = p.name.lower()
                by_name[key].append(p)
                try:
                    by_name_size[(key, p.stat().st_size)].append(p)
                except OSError:
                    pass
        except OSError as e:
            logger.warning("Reconcile index skip %s: %s", root, e)
    return by_name, by_name_size


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False
    except OSError:
        return False


def _pick_preferred(
    candidates: List[Path],
    prefer: str,
    org_root: Optional[Path],
    scan_root: Optional[Path],
) -> Optional[Path]:
    if not candidates:
        return None
    seen: Dict[str, Path] = {}
    for c in candidates:
        try:
            seen[str(c.resolve())] = c
        except OSError:
            seen[str(c)] = c
    uniq = list(seen.values())
    under_org = [c for c in uniq if org_root and _is_under(c, org_root)]
    under_scan = [c for c in uniq if scan_root and _is_under(c, scan_root)]
    if prefer == "scan":
        if under_scan:
            return sorted(under_scan, key=lambda x: str(x))[0]
        if under_org:
            return sorted(under_org, key=lambda x: str(x))[0]
    else:
        if under_org:
            return sorted(under_org, key=lambda x: str(x))[0]
        if under_scan:
            return sorted(under_scan, key=lambda x: str(x))[0]
    return sorted(uniq, key=lambda x: str(x))[0]


def _filename_from_doc(doc: Dict[str, Any]) -> str:
    f = doc.get("file", {}) if isinstance(doc.get("file"), dict) else {}
    rec = doc.get("record", {}) if isinstance(doc.get("record"), dict) else {}
    fn = str(f.get("filename") or rec.get("filename") or "").strip()
    if not fn:
        fp = str(f.get("full_path") or rec.get("full_path") or "")
        if fp:
            fn = Path(fp).name
    return fn


def _resolve_path(
    doc: Dict[str, Any],
    by_name: Dict[str, List[Path]],
    by_name_size: Dict[Tuple[str, int], List[Path]],
    config: Dict[str, Any],
) -> Optional[Path]:
    prefer = reconcile_prefer(config)
    org_root = get_organized_root(config)
    scan_root = get_scan_root(config)

    candidates: List[Path] = []
    current = resolve_absolute_from_doc(doc, config)
    if current is not None:
        candidates.append(current)

    fn = _filename_from_doc(doc)
    if fn:
        key = fn.lower()
        f = doc.get("file", {}) if isinstance(doc.get("file"), dict) else {}
        rec = doc.get("record", {}) if isinstance(doc.get("record"), dict) else {}
        size_mb = f.get("size_mb") or rec.get("size_mb")
        named = list(by_name.get(key, []))
        if size_mb is not None:
            try:
                target_bytes = int(float(size_mb) * 1024 * 1024)
                sized = list(by_name_size.get((key, target_bytes), []))
                if sized:
                    named = sized + named
                else:
                    for (k, sz), paths in by_name_size.items():
                        if k == key and abs(sz - target_bytes) <= 65536:
                            named.extend(paths)
            except (TypeError, ValueError):
                pass
        candidates.extend(named)

    picked = _pick_preferred(candidates, prefer, org_root, scan_root)
    return picked


def reconcile_vault_paths(
    config: Dict[str, Any],
    *,
    remove_missing: Optional[bool] = None,
    quiet: bool = False,
) -> Dict[str, int]:
    store = MetadataStore(config)
    meta_cfg = config.get("metadata") or {}
    if remove_missing is None:
        remove_missing = bool(meta_cfg.get("reconcile_remove_missing", False))

    roots = _search_roots(config)
    if not roots:
        if not quiet:
            print("  Reconcile: no search roots (set scan.folder_path and/or organization.output_folder)")
        return {"updated": 0, "unchanged": 0, "missing": 0, "removed": 0}

    if not quiet:
        print("  Vault: " + str(store.root))
        print("  Searching: " + ", ".join(str(r) for r in roots))
        print("  Prefer paths under: " + reconcile_prefer(config))
        from .metadata_paths import get_library_root, store_relative_paths

        lib = get_library_root(config)
        if lib and store_relative_paths(config):
            print("  Library root (relative paths): " + str(lib))

    exts = _media_extensions(config)
    by_name, by_name_size = _build_file_index(roots, exts)

    stats = {"updated": 0, "unchanged": 0, "missing": 0, "removed": 0}
    if store.load_recursive:
        json_paths = sorted(
            p for p in store.root.rglob("*.json") if p.name != store.index_path.name
        )
    else:
        json_paths = sorted(store.root.glob("*.json"))

    for jp in json_paths:
        if jp.name == store.index_path.name:
            continue
        try:
            doc = json.loads(jp.read_text(encoding="utf-8"))
        except Exception:
            stats["missing"] += 1
            continue
        if not isinstance(doc, dict):
            continue

        resolved = _resolve_path(doc, by_name, by_name_size, config)
        if resolved is None:
            stats["missing"] += 1
            if remove_missing:
                try:
                    jp.unlink()
                    stats["removed"] += 1
                except OSError:
                    pass
            continue

        if apply_media_path_to_doc(doc, resolved, config, jp):
            doc["updated_at"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
            doc = _ensure_json_serializable(doc)
            jp.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
            stats["updated"] += 1
        else:
            stats["unchanged"] += 1

    if not quiet:
        msg = (
            "  Path reconcile: "
            + str(stats["updated"]) + " updated, "
            + str(stats["unchanged"]) + " ok, "
            + str(stats["missing"]) + " not found"
        )
        if stats["removed"]:
            msg += ", " + str(stats["removed"]) + " json removed"
        print(msg)

    from .vault_maintenance import dedupe_vault, rebuild_vault_index

    if bool(meta_cfg.get("dedupe_on_reconcile", True)):
        dedupe_stats = dedupe_vault(config, quiet=quiet)
        stats["dedupe_removed"] = dedupe_stats.get("removed", 0)
    else:
        rebuild_vault_index(config)
    return stats


def auto_reconcile_if_enabled(config: Dict[str, Any], reason: str = "") -> Dict[str, int]:
    meta = config.get("metadata") or {}
    if not meta.get("auto_reconcile_paths", True):
        return {"updated": 0, "unchanged": 0, "missing": 0, "removed": 0}
    if reason:
        print("  Auto path reconcile (" + reason + ")...")
    return reconcile_vault_paths(config, quiet=not bool(reason))
