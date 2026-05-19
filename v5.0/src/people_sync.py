"""People tagging sync from face matches into metadata JSON."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_UNTAGGED_STATE = "_untagged_best.json"
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


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


def _score_tuple(rec: Dict[str, Any]) -> Tuple[float, float, int]:
    """Higher tuple = sharper / better for picking one representative (blur_score: higher = sharper)."""
    b = rec.get("blur_score")
    q = rec.get("quality_score")
    w, h = rec.get("width"), rec.get("height")
    try:
        bf = float(b) if b is not None else -1.0
    except (TypeError, ValueError):
        bf = -1.0
    try:
        qf = float(q) if q is not None else -1.0
    except (TypeError, ValueError):
        qf = -1.0
    try:
        px = int(w or 0) * int(h or 0)
    except (TypeError, ValueError):
        px = 0
    return (bf, qf, px)


def _list_exported_images(dest_dir: Path) -> List[Path]:
    out: List[Path] = []
    if not dest_dir.is_dir():
        return out
    for p in dest_dir.iterdir():
        if not p.is_file():
            continue
        n = p.name
        if n.startswith("_") or n.startswith("."):
            continue
        if p.suffix.lower() in _IMAGE_EXTS:
            out.append(p)
    return out


def _read_untagged_state(dest_dir: Path) -> Optional[Dict[str, Any]]:
    sp = dest_dir / _UNTAGGED_STATE
    if not sp.is_file():
        return None
    try:
        return json.loads(sp.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_untagged_state(dest_dir: Path, tup: Tuple[float, float, int], filename: str) -> None:
    sp = dest_dir / _UNTAGGED_STATE
    doc = {
        "blur_score": tup[0],
        "quality_score": tup[1],
        "pixels": tup[2],
        "filename": filename,
    }
    try:
        sp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    except OSError:
        pass


def _tuple_from_state(st: Dict[str, Any]) -> Tuple[float, float, int]:
    try:
        b = float(st.get("blur_score", -1.0))
    except (TypeError, ValueError):
        b = -1.0
    try:
        q = float(st.get("quality_score", -1.0))
    except (TypeError, ValueError):
        q = -1.0
    try:
        px = int(st.get("pixels", 0))
    except (TypeError, ValueError):
        px = 0
    return (b, q, px)


def _write_face_crop(src: Path, dest: Path, *, padding: float = 0.22) -> bool:
    """Largest OpenCV Haar face crop; returns False if no face or read failure."""
    try:
        import cv2
    except ImportError:
        return False

    try:
        from .face_detector import FaceDetector
    except Exception:
        return False

    det = FaceDetector()
    count, _cat, boxes = det.detect(str(src))
    if count < 1 or not boxes:
        return False

    img = cv2.imread(str(src))
    if img is None:
        return False

    ih, iw = img.shape[:2]
    x, y, bw, bh = max(boxes, key=lambda b: int(b[2]) * int(b[3]))
    pad_x = int(bw * padding)
    pad_y = int(bh * padding)
    x1 = max(0, x - pad_x)
    y1 = max(0, y - pad_y)
    x2 = min(iw, x + bw + pad_x)
    y2 = min(ih, y + bh + pad_y)
    if x2 <= x1 or y2 <= y1:
        return False

    crop = img[y1:y2, x1:x2]
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(dest), crop, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        return dest.is_file()
    except Exception:
        return False


def _export_untagged_file(
    src: Path,
    dest_dir: Path,
    rec: Dict[str, Any],
    *,
    use_crop: bool,
    crop_dest_name: Optional[str] = None,
) -> Optional[str]:
    """Copy full image or write a single face crop. Returns written filename or None."""
    if use_crop:
        cname = crop_dest_name or f"{src.stem}_face.jpg"
        dest = dest_dir / cname
        if _write_face_crop(src, dest):
            return dest.name
        logger.debug("Face crop failed for %s, falling back to full image", src)

    dest = dest_dir / src.name
    try:
        shutil.copy2(str(src), str(dest))
        return dest.name
    except OSError as e:
        logger.debug("Untagged export copy failed %s -> %s: %s", src, dest, e)
        return None


def _maybe_export_untagged_sample(
    src: Path,
    dest_dir: Path,
    rec: Dict[str, Any],
    *,
    max_samples: int,
    pick_best: bool,
    export_mode: str,
) -> None:
    if not src.is_file():
        return

    max_samples = max(1, min(20, int(max_samples)))
    mode = (export_mode or "full").strip().lower()
    use_crop = mode == "face_crop"
    dest_dir.mkdir(parents=True, exist_ok=True)

    imgs = _list_exported_images(dest_dir)
    new_tup = _score_tuple(rec)

    mid = str(rec.get("media_id", "") or "").strip()[:8] or "id"

    if pick_best and max_samples == 1:
        st = _read_untagged_state(dest_dir)
        old_tup = _tuple_from_state(st) if st else (-1.0, -1.0, -1)
        if imgs and new_tup <= old_tup:
            return
        for p in imgs:
            try:
                p.unlink()
            except OSError:
                pass
        try:
            (dest_dir / _UNTAGGED_STATE).unlink()
        except OSError:
            pass
        crop_name = f"{src.stem}_{mid}_face.jpg" if use_crop else None
        name = _export_untagged_file(
            src, dest_dir, rec, use_crop=use_crop, crop_dest_name=crop_name
        )
        if name:
            _write_untagged_state(dest_dir, new_tup, name)
        return

    if len(imgs) >= max_samples:
        return

    if use_crop:
        dest_name = f"{src.stem}_{mid}_face.jpg"
    else:
        dest_name = src.name
    if (dest_dir / dest_name).exists():
        return

    _export_untagged_file(
        src,
        dest_dir,
        rec,
        use_crop=use_crop,
        crop_dest_name=dest_name if use_crop else None,
    )


def _should_skip_untagged_export(rec: Dict[str, Any], config: Dict[str, Any]) -> bool:
    faces = config.get("faces") or {}
    if not faces.get("untagged_skip_duplicates", True):
        return False
    if str(rec.get("is_duplicate", "")).upper() != "YES":
        return False
    best = str(rec.get("is_best_in_group", "")).strip().lower()
    return best not in ("yes", "y", "1", "true")


def sync_people_tags(
    records: List[Dict[str, Any]],
    matches: List[Dict[str, Any]],
    untagged_root: Path,
    *,
    export_untagged: bool = True,
    seed_only_refresh: bool = False,
    untagged_max_samples: int = 1,
    untagged_pick_best_quality: bool = True,
    untagged_export_mode: str = "full",
    config: Optional[Dict[str, Any]] = None,
) -> Tuple[int, int]:
    """
    Update metadata JSON with seed person matches.

    export_untagged: export sample images for unknown ids (see untagged_* options).
    seed_only_refresh: only apply rows that match a seed person; do not create/update unknowns.

    untagged_max_samples: max image files per unknown folder (default 1).
    untagged_pick_best_quality: when max_samples is 1, replace the export if a sharper/higher-quality
        candidate appears (blur_score, quality_score, then resolution).
    untagged_export_mode: "full" copies the file; "face_crop" writes largest Haar face JPEG
        (falls back to full if no face or OpenCV missing).
    """
    config = config or {}
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

                if export_untagged and not _should_skip_untagged_export(rec, config):
                    src = Path(fp)
                    if src.exists():
                        dest_dir = untagged_root / unk_id
                        _maybe_export_untagged_sample(
                            src,
                            dest_dir,
                            rec,
                            max_samples=untagged_max_samples,
                            pick_best=untagged_pick_best_quality,
                            export_mode=untagged_export_mode,
                        )

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

    faces_cfg = config.get("faces") or {}
    if faces_cfg.get("untagged_cleanup_orphans", True) and export_untagged:
        try:
            from .vault_maintenance import cleanup_untagged_orphans

            cleanup_untagged_orphans(config, quiet=True)
        except Exception:
            pass

    return known_updates, unknown_updates
