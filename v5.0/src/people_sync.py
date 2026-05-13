"""People tagging sync from face matches into metadata JSON."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _path_aliases(p: str) -> List[str]:
    """Keys to match index paths vs record paths (Windows casing, resolve)."""
    keys: List[str] = []
    s = (p or "").strip()
    if not s:
        return keys
    keys.append(s)
    try:
        rp = str(Path(s).resolve())
        keys.append(rp)
        keys.append(rp.lower())
    except Exception:
        pass
    out: List[str] = []
    seen = set()
    for k in keys:
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


def _build_match_index(matches: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Map every path alias -> best match row for that file."""
    best: Dict[str, Dict[str, Any]] = {}
    for m in matches or []:
        fp = str(m.get("file_path", "")).strip()
        if not fp:
            continue
        for alias in _path_aliases(fp):
            cur = best.get(alias)
            if cur is None or float(m.get("similarity", 0.0)) > float(cur.get("similarity", 0.0)):
                best[alias] = m
    return best


def _lookup_match(best: Dict[str, Dict[str, Any]], fp: str) -> Dict[str, Any] | None:
    for alias in _path_aliases(fp):
        if alias in best:
            return best[alias]
    return None


def sync_people_tags(
    records: List[Dict[str, Any]],
    matches: List[Dict[str, Any]],
    untagged_root: Path,
    *,
    export_untagged: bool = True,
    seed_only_refresh: bool = False,
) -> Tuple[int, int]:
    """
    Update metadata JSON with seed person matches.

    export_untagged: copy up to 5 sample images per unknown person id.
    seed_only_refresh: only apply rows that match a seed person; do not create/update unknowns.
    """
    best_by_alias = _build_match_index(matches)
    if export_untagged:
        untagged_root.mkdir(parents=True, exist_ok=True)
    known_updates = 0
    unknown_updates = 0

    for rec in records or []:
        meta_path = str(rec.get("metadata_json_path", "")).strip()
        if not meta_path:
            continue
        jp = Path(meta_path)
        if not jp.exists():
            continue

        try:
            doc = json.loads(jp.read_text(encoding="utf-8"))
        except Exception:
            continue

        fp = str(rec.get("full_path", "")).strip()
        media_id = str(rec.get("media_id", "")).strip() or Path(meta_path).stem[:8]
        match = _lookup_match(best_by_alias, fp)

        person_info = doc.get("person", {}) if isinstance(doc.get("person", {}), dict) else {}

        if match:
            person_info["status"] = "known"
            person_info["person_id"] = str(match.get("person_label", "")).strip()
            person_info["person_name"] = str(match.get("person_label", "")).strip()
            person_info["similarity"] = float(match.get("similarity", 0.0))
            person_info["source"] = "seed"
            doc["person"] = person_info
            known_updates += 1
        else:
            if seed_only_refresh:
                continue
            face_count = int(rec.get("face_count", 0) or 0)
            if face_count > 0:
                unk_id = str(person_info.get("person_id", "")).strip() or ("UNK-" + media_id[:8].upper())
                person_info["status"] = "unknown"
                person_info["person_id"] = unk_id
                person_info["person_name"] = ""
                person_info["source"] = "untagged"
                doc["person"] = person_info
                unknown_updates += 1

                if export_untagged:
                    src = Path(fp)
                    if src.exists():
                        dest_dir = untagged_root / unk_id
                        dest_dir.mkdir(parents=True, exist_ok=True)
                        if len([p for p in dest_dir.iterdir() if p.is_file()]) < 5:
                            dest = dest_dir / src.name
                            if not dest.exists():
                                try:
                                    shutil.copy2(str(src), str(dest))
                                except Exception:
                                    pass

        if str(person_info.get("status", "")).strip().lower() == "known":
            rec["person_match_flag"] = "Yes"
            rec["person_label"] = person_info.get("person_name", "")
            rec["person_similarity"] = person_info.get("similarity", "")
            rec["person_match_source"] = "seed"
        else:
            rec["person_match_flag"] = "No"
            rec["person_label"] = person_info.get("person_id", "")
            rec["person_similarity"] = ""
            rec["person_match_source"] = "" if seed_only_refresh else "untagged"

        try:
            jp.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
        except Exception:
            pass

    return known_updates, unknown_updates
