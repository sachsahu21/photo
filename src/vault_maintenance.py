"""Vault dedupe, quarantine flows, index rebuild, untagged/face cleanup."""

from __future__ import annotations

import json
import csv
import logging
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .metadata_paths import get_organized_root, get_scan_root, resolve_absolute_from_doc
from .metadata_reconcile import _build_file_index, _media_extensions, _resolve_path, _search_roots
from .metadata_store import MetadataStore, _ensure_json_serializable
from .workspace_paths import resolve_workspace_root

logger = logging.getLogger(__name__)


def _path_key(p: Path) -> str:
    try:
        return str(p.resolve()).lower()
    except OSError:
        return str(p).lower()


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _quarantine_base(config: Dict[str, Any]) -> Path:
    q = config.get("quarantine") or {}
    raw = str(q.get("root_folder") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    sub = str(q.get("subfolder") or "quarantine").strip() or "quarantine"
    return (resolve_workspace_root(config) / Path(sub.replace("\\", "/")).name).resolve()


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    for i in range(1, 100000):
        candidate = parent / (stem + "-" + str(i) + suffix)
        if not candidate.exists():
            return candidate
    return parent / (stem + "-" + _timestamp() + suffix)


def _quarantine_relative_path(config: Dict[str, Any], src: Path) -> Path:
    q = config.get("quarantine") or {}
    if not q.get("preserve_relative_paths", True):
        return Path(src.name)
    roots = [get_scan_root(config), get_organized_root(config)]
    for root in roots:
        if not root:
            continue
        try:
            return src.resolve().relative_to(root.resolve())
        except (OSError, ValueError):
            continue
    return Path(src.name)


def _manifest_path(run_root: Path, prefix: str) -> Path:
    return run_root / (prefix + "-" + _timestamp() + ".csv")


def _write_manifest(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "timestamp",
        "action",
        "sheet",
        "label",
        "media_id",
        "original_path",
        "quarantine_path",
        "metadata_json_path",
        "quarantined_metadata_path",
        "md5_hash",
        "duplicate_group",
        "status",
        "error",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _doc_updated_at(doc: Dict[str, Any]) -> str:
    return str(doc.get("updated_at") or doc.get("generated_at") or "")


def _doc_media_id(doc: Dict[str, Any]) -> str:
    f = doc.get("file") if isinstance(doc.get("file"), dict) else {}
    return str(f.get("media_id") or "").strip()


def _doc_md5(doc: Dict[str, Any]) -> str:
    f = doc.get("file") if isinstance(doc.get("file"), dict) else {}
    return str(f.get("md5_hash") or "").strip().lower()


def _is_under(path: Path, root: Optional[Path]) -> bool:
    if not root:
        return False
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False
    except OSError:
        return False


def _score_keeper(doc: Dict[str, Any], jp: Path, resolved: Optional[Path], config: Dict[str, Any]) -> Tuple:
    """Higher = prefer keeping this JSON when deduping."""
    org = get_organized_root(config)
    scan = get_scan_root(config)
    under_org = 1 if resolved and _is_under(resolved, org) else 0
    under_scan = 1 if resolved and _is_under(resolved, scan) else 0
    prefer = str((config.get("metadata") or {}).get("dedupe_prefer", "organized")).lower()
    if prefer == "scan":
        loc_score = under_scan * 10 + under_org
    else:
        loc_score = under_org * 10 + under_scan
    return (loc_score, _doc_updated_at(doc), str(jp))


def iter_vault_json_paths(store: MetadataStore) -> List[Path]:
    if store.load_recursive:
        return sorted(
            p for p in store.root.rglob("*.json") if p.name != store.index_path.name
        )
    return sorted(p for p in store.root.glob("*.json") if p.name != store.index_path.name)


def _read_vault_json_parallel(
    paths: List[Path],
    workers: int = 8,
) -> List[Tuple[Path, Dict[str, Any]]]:
    """Read vault JSON files in parallel. Returns (path, doc) pairs for valid docs."""
    results: List[Tuple[Path, Dict[str, Any]]] = []

    def _read(jp: Path):
        try:
            doc = json.loads(jp.read_text(encoding="utf-8"))
            if isinstance(doc, dict):
                return jp, doc
        except Exception:
            pass
        return None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for item in as_completed({pool.submit(_read, jp): jp for jp in paths}):
            result = item.result()
            if result is not None:
                results.append(result)
    return results


def rebuild_vault_index(
    config: Dict[str, Any],
    parsed: Optional[List[Tuple[Path, Dict[str, Any]]]] = None,
) -> int:
    """Write metadata-index.json. Pass `parsed` to reuse already-read docs and skip disk re-read."""
    store = MetadataStore(config)
    if parsed is None:
        paths = iter_vault_json_paths(store)
        parsed = _read_vault_json_parallel(paths)
    index: List[Dict[str, str]] = []
    for jp, doc in parsed:
        f = doc.get("file") if isinstance(doc.get("file"), dict) else {}
        index.append(
            {
                "full_path": str(f.get("full_path") or ""),
                "media_id": _doc_media_id(doc),
                "metadata_json_path": str(jp),
                "schema_version": str(doc.get("schema_version", "")),
                "updated_at": _doc_updated_at(doc),
            }
        )
    store.index_path.write_text(
        json.dumps(index, indent=2, ensure_ascii=True), encoding="utf-8"
    )
    return len(index)


def dedupe_vault(config: Dict[str, Any], *, quiet: bool = False) -> Dict[str, int]:
    """
    Remove duplicate vault JSON files and rebuild the index.

    Groups by stored full_path. Two JSONs with the same full_path key are
    collapsed into one (true vault redundancy). Exception: if both paths exist
    on disk and share the same MD5, they are cross-location duplicates — both
    vault records are preserved so duplicate detection can flag them correctly.

    Reads all vault JSONs once in parallel, then reuses the parsed docs
    when rebuilding the index — no second read pass.
    """
    store = MetadataStore(config)

    # --- read all vault JSONs in parallel ---
    all_paths = iter_vault_json_paths(store)
    parsed = _read_vault_json_parallel(all_paths)

    groups: Dict[str, List[Tuple[Path, Dict[str, Any], Optional[Path]]]] = {}
    orphan_md5: Dict[str, List[Tuple[Path, Dict[str, Any]]]] = {}

    for jp, doc in parsed:
        f = doc.get("file") if isinstance(doc.get("file"), dict) else {}
        stored_fp = str(f.get("full_path") or "").strip()
        if stored_fp:
            fp_path = Path(stored_fp)
            md5 = _doc_md5(doc)
            # Two vault JSONs with the same full_path key but BOTH existing on disk
            # with the same MD5 are cross-location duplicates — keep both records so
            # duplicate detection can flag them correctly. Only collapse when the
            # path does not exist (stale/redundant vault entry) or has no MD5.
            key = stored_fp.lower()
            existing_group = groups.get(key)
            if existing_group and md5 and fp_path.is_file():
                # Check if the existing group entry also points to a real file with the same MD5
                ex_jp, ex_doc, ex_res = existing_group[0]
                ex_md5 = _doc_md5(ex_doc)
                if ex_md5 == md5 and ex_res is not None and ex_res.is_file() and ex_res != fp_path:
                    # Genuine cross-location duplicate — use unique key so both records survive
                    key = stored_fp.lower() + "|" + str(jp)
            groups.setdefault(key, []).append((jp, doc, fp_path))
        else:
            md5 = _doc_md5(doc)
            if md5:
                orphan_md5.setdefault(md5, []).append((jp, doc))

    q_base = _quarantine_base(config)
    q_run: Optional[Path] = None
    manifest_rows: List[Dict[str, Any]] = []

    def _quarantine_json(jp: Path, doc: Dict[str, Any], reason: str) -> bool:
        nonlocal q_run
        if q_run is None:
            q_run = _unique_path(q_base / ("dedupe-" + _timestamp()))
            q_run.mkdir(parents=True, exist_ok=True)
        dest = _unique_path(q_run / ("dedupe_" + jp.name))
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(jp), str(dest))
            f = doc.get("file") if isinstance(doc.get("file"), dict) else {}
            manifest_rows.append({
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                "action": "dedupe",
                "reason": reason,
                "original_json_path": str(jp),
                "quarantine_path": str(dest),
                "full_path": str(f.get("full_path") or ""),
                "md5": _doc_md5(doc),
            })
            return True
        except OSError as e:
            logger.debug("Dedupe quarantine %s: %s", jp, e)
            return False

    removed = 0
    group_count = 0
    quarantined_paths: Set[str] = set()

    for _key, items in groups.items():
        if len(items) < 2:
            continue
        group_count += 1
        items.sort(key=lambda t: _score_keeper(t[1], t[0], t[2], config), reverse=True)
        keeper_jp, keeper_doc, keeper_res = items[0]
        for jp, doc, _res in items[1:]:
            if _quarantine_json(jp, doc, "duplicate-full-path"):
                removed += 1
                quarantined_paths.add(str(jp))
        if keeper_res is not None:
            try:
                from .metadata_paths import apply_media_path_to_doc
                apply_media_path_to_doc(keeper_doc, keeper_res, config, keeper_jp)
                keeper_doc["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                keeper_jp.write_text(
                    json.dumps(_ensure_json_serializable(keeper_doc), indent=2, ensure_ascii=True),
                    encoding="utf-8",
                )
            except Exception:
                pass

    for _md5, items in orphan_md5.items():
        if len(items) < 2:
            continue
        group_count += 1
        items.sort(key=lambda t: _doc_updated_at(t[1]), reverse=True)
        for jp, doc in items[1:]:
            if _quarantine_json(jp, doc, "duplicate-md5-no-path"):
                removed += 1
                quarantined_paths.add(str(jp))

    if q_run and manifest_rows:
        manifest = _manifest_path(q_run, "quarantine-dedupe-manifest")
        import csv as _csv
        fields = ["timestamp", "action", "reason", "original_json_path", "quarantine_path", "full_path", "md5"]
        with open(manifest, "w", newline="", encoding="utf-8") as fh:
            w = _csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(manifest_rows)

    # reuse already-parsed docs — skip second read pass
    surviving = [(jp, doc) for jp, doc in parsed if str(jp) not in quarantined_paths]
    rebuild_vault_index(config, parsed=surviving)

    stats = {"groups": group_count, "removed": removed, "kept": len(groups) + len(orphan_md5) - removed}
    if not quiet:
        print(
            "  Vault dedupe: "
            + str(group_count)
            + " duplicate groups, "
            + str(removed)
            + " json quarantined"
            + (" → " + str(q_run) if q_run else "")
        )
    return stats


def find_json_path(
    store: MetadataStore,
    *,
    metadata_json_path: str = "",
    media_id: str = "",
    full_path: str = "",
) -> Optional[Path]:
    if metadata_json_path:
        p = Path(metadata_json_path)
        if p.is_file():
            return p
    # Try path-hash lookup first (O(1)) — avoids scanning vault when full_path is known
    fp = (full_path or "").strip()
    if fp:
        candidate = store._json_path_for_record({"full_path": fp})
        if candidate.exists():
            return candidate
    # Fall back to media_id scan only when path-hash misses
    mid = (media_id or "").strip().lower()
    if mid:
        for jp in iter_vault_json_paths(store):
            try:
                doc = json.loads(jp.read_text(encoding="utf-8"))
                if _doc_media_id(doc).lower() == mid:
                    return jp
            except Exception:
                continue
    return None


def remove_untagged_folder(config: Dict[str, Any], person_id: str) -> bool:
    pid = (person_id or "").strip()
    if not pid:
        return False
    faces = config.get("faces") or {}
    root = Path(str(faces.get("untagged_root") or ""))
    if not root:
        return False
    dest = root / pid
    if not dest.is_dir():
        return False
    try:
        shutil.rmtree(dest)
        return True
    except OSError as e:
        logger.debug("Untagged rmtree %s: %s", dest, e)
        return False


def cleanup_untagged_orphans(config: Dict[str, Any], *, quiet: bool = False) -> Dict[str, int]:
    """Remove untagged sample folders when source file is gone or person is known."""
    store = MetadataStore(config)
    faces = config.get("faces") or {}
    untagged_root = Path(str(faces.get("untagged_root") or ""))
    if not untagged_root.is_dir():
        return {"removed_dirs": 0, "kept": 0}

    known_ids: Set[str] = set()
    missing_ids: Set[str] = set()
    for jp in iter_vault_json_paths(store):
        try:
            doc = json.loads(jp.read_text(encoding="utf-8"))
        except Exception:
            continue
        p = doc.get("person") if isinstance(doc.get("person"), dict) else {}
        status = str(p.get("status", "")).lower()
        pid = str(p.get("person_id") or "").strip()
        if status == "known" and pid:
            known_ids.add(pid)
        if status == "unknown" and pid:
            resolved = resolve_absolute_from_doc(doc, config)
            if resolved is None:
                missing_ids.add(pid)

    removed = 0
    kept = 0
    for child in untagged_root.iterdir():
        if not child.is_dir() or child.name.startswith("."):
            continue
        if child.name in known_ids or child.name in missing_ids:
            try:
                shutil.rmtree(child)
                removed += 1
            except OSError:
                pass
        else:
            kept += 1

    if not quiet:
        print("  Untagged cleanup: " + str(removed) + " folders removed, " + str(kept) + " kept")
    return {"removed_dirs": removed, "kept": kept}


def remove_face_index_paths(config: Dict[str, Any], paths: List[str]) -> int:
    paths_norm = {_path_key(Path(p)) for p in paths if p}
    if not paths_norm:
        return 0
    try:
        from .face_indexer import FaceIndexer

        fi = FaceIndexer(config)
        if not fi.index_db.is_file():
            return 0
        import sqlite3

        con = sqlite3.connect(str(fi.index_db))
        n = 0
        try:
            # Build normalised key → stored path map in one pass, then batch delete.
            stored_map = {}
            for (stored,) in con.execute("SELECT path FROM files").fetchall():
                try:
                    stored_map[_path_key(Path(stored))] = stored
                except OSError:
                    pass
            to_delete = [stored_map[pk] for pk in paths_norm if pk in stored_map]
            for stored in to_delete:
                con.execute("DELETE FROM faces WHERE file_path = ?", (stored,))
                con.execute("DELETE FROM files WHERE path = ?", (stored,))
                n += 1
        finally:
            con.commit()
            con.close()
        return n
    except Exception as e:
        logger.debug("Face index cleanup: %s", e)
        return 0


def quarantine_generated_targets(
    config: Dict[str, Any],
    targets: List[Tuple[str, Path]],
    *,
    action: str = "fresh-restart",
    manifest_prefix: str = "fresh-restart-manifest",
) -> Dict[str, Any]:
    run_root = _unique_path(_quarantine_base(config) / (action + "-" + _timestamp()))
    run_root.mkdir(parents=True, exist_ok=True)
    rows: List[Dict[str, Any]] = []
    moved = 0
    missing = 0

    for label, raw_path in targets:
        src = Path(raw_path)
        dest = _unique_path(run_root / src.name)
        row = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "action": action,
            "label": label,
            "original_path": str(src),
            "quarantine_path": str(dest),
            "status": "",
            "error": "",
        }
        try:
            if src.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dest))
                row["status"] = "moved"
                moved += 1
            else:
                row["status"] = "missing"
                missing += 1
        except Exception as e:
            row["status"] = "error"
            row["error"] = str(e)
        rows.append(row)

    manifest = _manifest_path(run_root, manifest_prefix)
    _write_manifest(manifest, rows)
    return {
        "run_root": str(run_root),
        "manifest_path": str(manifest),
        "moved": moved,
        "missing": missing,
        "rows": len(rows),
    }


def quarantine_media_cascade(
    config: Dict[str, Any],
    targets: List[Dict[str, str]],
    *,
    action: str = "delete-actions",
) -> Dict[str, Any]:
    store = MetadataStore(config)
    q_cfg = config.get("quarantine") or {}
    manifest_prefix = str(q_cfg.get("manifest_prefix") or "quarantine-manifest").strip()
    run_root = _unique_path(_quarantine_base(config) / (action + "-" + _timestamp()))
    media_root = run_root / "media"
    metadata_root = run_root / "metadata"
    run_root.mkdir(parents=True, exist_ok=True)

    stats: Dict[str, Any] = {
        "files_moved": 0,
        "files_missing": 0,
        "json_moved": 0,
        "json_missing": 0,
        "face_rows_removed": 0,
        "manifest_path": "",
        "quarantine_root": str(run_root),
    }
    seen_json: Set[str] = set()
    paths_for_face: List[str] = []
    rows: List[Dict[str, Any]] = []

    for t in targets:
        fp = str(t.get("full_path") or "").strip()
        mp = str(t.get("metadata_json_path") or "").strip()
        mid = str(t.get("media_id") or "").strip()
        sheet = str(t.get("sheet") or "").strip()
        md5 = str(t.get("md5_hash") or "").strip()
        dup_group = str(t.get("duplicate_group") or "").strip()
        quarantine_path = ""
        quarantined_metadata_path = ""
        status = []
        error = ""

        if fp:
            paths_for_face.append(fp)
            try:
                src = Path(fp)
                if src.is_file():
                    rel = _quarantine_relative_path(config, src)
                    dest = _unique_path(media_root / rel)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src), str(dest))
                    quarantine_path = str(dest)
                    stats["files_moved"] += 1
                    status.append("file_moved")
                else:
                    stats["files_missing"] += 1
                    status.append("file_missing")
            except Exception as e:
                stats["files_missing"] += 1
                status.append("file_error")
                error = str(e)

        jp = find_json_path(store, metadata_json_path=mp, media_id=mid, full_path=fp)
        if jp is None:
            stats["json_missing"] += 1
            status.append("json_missing")
        else:
            jkey = str(jp.resolve())
            if jkey not in seen_json:
                seen_json.add(jkey)
                try:
                    doc = json.loads(jp.read_text(encoding="utf-8"))
                    if not md5:
                        f = doc.get("file") if isinstance(doc.get("file"), dict) else {}
                        h = doc.get("hashes") if isinstance(doc.get("hashes"), dict) else {}
                        md5 = str(f.get("md5_hash") or h.get("md5") or "").strip()
                    if not dup_group:
                        d = doc.get("duplicate") if isinstance(doc.get("duplicate"), dict) else {}
                        dup_group = str(d.get("duplicate_group") or "").strip()
                except Exception:
                    pass
                try:
                    dest = _unique_path(metadata_root / jp.name)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(jp), str(dest))
                    quarantined_metadata_path = str(dest)
                    stats["json_moved"] += 1
                    status.append("json_moved")
                except Exception as e:
                    stats["json_missing"] += 1
                    status.append("json_error")
                    error = (error + "; " if error else "") + str(e)

        rows.append(
            {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "action": action,
                "sheet": sheet,
                "media_id": mid,
                "original_path": fp,
                "quarantine_path": quarantine_path,
                "metadata_json_path": mp,
                "quarantined_metadata_path": quarantined_metadata_path,
                "md5_hash": md5,
                "duplicate_group": dup_group,
                "status": ", ".join(status),
                "error": error,
            }
        )

    if paths_for_face:
        stats["face_rows_removed"] = remove_face_index_paths(config, paths_for_face)

    manifest = _manifest_path(run_root, manifest_prefix)
    _write_manifest(manifest, rows)
    stats["manifest_path"] = str(manifest)
    rebuild_vault_index(config)
    return stats


def quarantine_files_fast(
    config: Dict[str, Any],
    targets: List[Dict[str, str]],
    *,
    action: str = "delete-actions",
) -> Dict[str, Any]:
    """Move media files to quarantine only — no vault scan, no index rebuild.

    JSON metadata files are relocated using the O(1) path-hash lookup when
    possible. Skips the full vault walk and index rebuild so the operation
    completes in seconds regardless of library size. Call option 24 (Dedupe
    Vault) afterwards to purge any orphaned metadata JSON files.
    """
    store = MetadataStore(config)
    q_cfg = config.get("quarantine") or {}
    manifest_prefix = str(q_cfg.get("manifest_prefix") or "quarantine-manifest").strip()
    run_root = _unique_path(_quarantine_base(config) / (action + "-" + _timestamp()))
    media_root = run_root / "media"
    metadata_root = run_root / "metadata"
    run_root.mkdir(parents=True, exist_ok=True)

    stats: Dict[str, Any] = {
        "files_moved": 0,
        "files_missing": 0,
        "json_moved": 0,
        "json_missing": 0,
        "face_rows_removed": 0,
        "manifest_path": "",
        "quarantine_root": str(run_root),
    }
    seen_json: Set[str] = set()
    paths_for_face: List[str] = []
    rows: List[Dict[str, Any]] = []

    for t in targets:
        fp = str(t.get("full_path") or "").strip()
        mp = str(t.get("metadata_json_path") or "").strip()
        mid = str(t.get("media_id") or "").strip()
        sheet = str(t.get("sheet") or "").strip()
        md5 = str(t.get("md5_hash") or "").strip()
        dup_group = str(t.get("duplicate_group") or "").strip()
        quarantine_path = ""
        quarantined_metadata_path = ""
        status = []
        error = ""

        # --- move media file ---
        if fp:
            paths_for_face.append(fp)
            try:
                src = Path(fp)
                if src.is_file():
                    rel = _quarantine_relative_path(config, src)
                    dest = _unique_path(media_root / rel)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src), str(dest))
                    quarantine_path = str(dest)
                    stats["files_moved"] += 1
                    status.append("file_moved")
                else:
                    stats["files_missing"] += 1
                    status.append("file_missing")
            except Exception as e:
                stats["files_missing"] += 1
                status.append("file_error")
                error = str(e)

        # --- O(1) JSON lookup: explicit path → path-hash only (no vault scan) ---
        jp: Optional[Path] = None
        if mp:
            p = Path(mp)
            if p.is_file():
                jp = p
        if jp is None and fp:
            candidate = store._json_path_for_record({"full_path": fp})
            if candidate.exists():
                jp = candidate

        if jp is None:
            stats["json_missing"] += 1
            status.append("json_missing")
        else:
            jkey = str(jp.resolve())
            if jkey not in seen_json:
                seen_json.add(jkey)
                try:
                    dest = _unique_path(metadata_root / jp.name)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(jp), str(dest))
                    quarantined_metadata_path = str(dest)
                    stats["json_moved"] += 1
                    status.append("json_moved")
                except Exception as e:
                    stats["json_missing"] += 1
                    status.append("json_error")
                    error = (error + "; " if error else "") + str(e)

        rows.append(
            {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "action": action,
                "sheet": sheet,
                "media_id": mid,
                "original_path": fp,
                "quarantine_path": quarantine_path,
                "metadata_json_path": mp,
                "quarantined_metadata_path": quarantined_metadata_path,
                "md5_hash": md5,
                "duplicate_group": dup_group,
                "status": ", ".join(status),
                "error": error,
            }
        )

    if paths_for_face:
        stats["face_rows_removed"] = remove_face_index_paths(config, paths_for_face)

    manifest = _manifest_path(run_root, manifest_prefix)
    _write_manifest(manifest, rows)
    stats["manifest_path"] = str(manifest)
    # intentionally skip rebuild_vault_index — user runs option 24 for that
    return stats


def enrich_records_file_exists(
    records: List[Dict[str, Any]],
    config: Dict[str, Any],
) -> List[Dict[str, Any]]:
    for rec in records:
        fp = str(rec.get("full_path") or "").strip()
        exists = False
        if fp:
            try:
                exists = Path(fp).is_file()
            except OSError:
                exists = False
        rec["file_exists"] = "Yes" if exists else "No"
    return records


def filter_records_for_excel(
    records: List[Dict[str, Any]],
    config: Dict[str, Any],
) -> List[Dict[str, Any]]:
    wf = config.get("workflow") or {}
    if not wf.get("excel_exclude_missing_files", False):
        return records
    return [r for r in records if str(r.get("file_exists", "Yes")).lower() == "yes"]


def save_last_excel_path(config: Dict[str, Any], path: str) -> None:
    try:
        from .workspace_paths import resolve_workspace_root

        p = resolve_workspace_root(config) / "last-excel.txt"
        p.write_text(str(path).strip(), encoding="utf-8")
    except Exception:
        pass


def load_last_excel_path(config: Dict[str, Any]) -> Optional[str]:
    try:
        from .workspace_paths import resolve_workspace_root

        p = resolve_workspace_root(config) / "last-excel.txt"
        if p.is_file():
            s = p.read_text(encoding="utf-8").strip()
            return s if s else None
    except Exception:
        pass
    return None


def retire_scan_json_for_organized_file(
    config: Dict[str, Any],
    organized_path: Path,
    keeper_json: Path,
    md5_hash: str = "",
) -> int:
    """After organize, remove other vault JSON for same md5 that only point at scan tree."""
    if not bool((config.get("organization") or {}).get("retire_scan_path_json_on_organize", True)):
        return 0
    org = get_organized_root(config)
    scan = get_scan_root(config)
    if not org or not scan:
        return 0
    try:
        if not _is_under(organized_path, org):
            return 0
    except OSError:
        return 0

    store = MetadataStore(config)
    md5 = (md5_hash or "").strip().lower()
    removed = 0
    keeper_key = str(keeper_json.resolve())

    for jp in iter_vault_json_paths(store):
        if str(jp.resolve()) == keeper_key:
            continue
        try:
            doc = json.loads(jp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if md5 and _doc_md5(doc) != md5:
            continue
        resolved = resolve_absolute_from_doc(doc, config)
        if resolved is None:
            fp = str((doc.get("file") or {}).get("full_path") or "")
            if fp:
                try:
                    resolved = Path(fp)
                except Exception:
                    resolved = None
        if resolved is None:
            continue
        if _is_under(resolved, scan) and not _is_under(resolved, org):
            try:
                jp.unlink()
                removed += 1
            except OSError:
                pass
    if removed:
        rebuild_vault_index(config)
    return removed
