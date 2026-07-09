"""Metadata JSON persistence for v5.1-style workflows."""

from __future__ import annotations

import json
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .metadata_paths import apply_media_path_to_doc, resolve_absolute_from_doc


def _ensure_json_serializable(obj: Any) -> Any:
    """Deep-convert values so json.dumps never hits datetime/Path/tuple/etc."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, datetime):
        return obj.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, dict):
        return {str(k): _ensure_json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_ensure_json_serializable(x) for x in obj]
    if isinstance(obj, bytes):
        try:
            return obj.decode("utf-8", errors="replace")
        except Exception:
            return ""
    item_fn = getattr(obj, "item", None)
    if callable(item_fn):
        try:
            return _ensure_json_serializable(item_fn())
        except Exception:
            pass
    return str(obj)


def _dateish_to_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, date):
        return v.isoformat()
    return str(v).strip()


def _coalesce(*values: Any, default: Any = None) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return default


def _safe_int(value: Any, default: Any = None) -> Any:
    if value is None or value == "":
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: Any = None) -> Any:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "y", "on")


def _yes_no(value: Any) -> str:
    return "YES" if _truthy(value) else "No"


def _quality_issues(value: Any) -> List[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, (tuple, set)):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value).strip()
    if not text:
        return []
    for sep in (";", "|"):
        if sep in text:
            return [p.strip() for p in text.split(sep) if p.strip()]
    if "," in text and not text.lower().startswith("error:"):
        return [p.strip() for p in text.split(",") if p.strip()]
    return [text]


def _date_parts(value: Any) -> Dict[str, Any]:
    text = _dateish_to_str(value)
    if not text:
        return {"year": None, "month": None, "day": None}
    cleaned = text.replace("Z", "").replace("T", " ")
    try:
        dt = datetime.fromisoformat(cleaned[:19])
        return {"year": dt.year, "month": dt.month, "day": dt.day}
    except (TypeError, ValueError):
        pass
    try:
        y, m, d = text[:10].replace(":", "-").replace("/", "-").split("-")[:3]
        return {"year": int(y), "month": int(m), "day": int(d)}
    except (TypeError, ValueError):
        return {"year": None, "month": None, "day": None}


def _string_list(value: Any) -> List[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, (tuple, set)):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value).strip()
    if not text:
        return []
    return [p.strip() for p in text.split(",") if p.strip()]


def _faces_items_from_record(rec: Dict[str, Any], count: int) -> List[Dict[str, Any]]:
    raw_boxes = rec.get("face_boxes") or []
    items: List[Dict[str, Any]] = []
    if isinstance(raw_boxes, list):
        for idx, raw in enumerate(raw_boxes):
            if isinstance(raw, dict):
                bbox = raw.get("bbox", raw)
                item = {
                    "face_id": raw.get("face_id") or f"FACE-{idx + 1:04d}",
                    "person_id": raw.get("person_id") or f"UNK-{idx + 1:04d}",
                    "person_name": raw.get("person_name"),
                    "confidence": raw.get("confidence"),
                    "bbox": bbox,
                }
            else:
                try:
                    x, y, w, h = raw
                    item = {
                        "face_id": f"FACE-{idx + 1:04d}",
                        "person_id": f"UNK-{idx + 1:04d}",
                        "person_name": None,
                        "confidence": None,
                        "bbox": {"x": int(x), "y": int(y), "w": int(w), "h": int(h)},
                    }
                except Exception:
                    continue
            items.append(item)
    while len(items) < count:
        idx = len(items)
        items.append(
            {
                "face_id": f"FACE-{idx + 1:04d}",
                "person_id": f"UNK-{idx + 1:04d}",
                "person_name": None,
                "confidence": None,
                "bbox": None,
            }
        )
    return items[:count] if count >= 0 else items


class MetadataStore:
    def __init__(self, config: Dict[str, Any]):
        self.config = config or {}
        scan_cfg = (self.config.get("scan") or {})
        meta_cfg = (self.config.get("metadata") or {})

        self.scan_root = Path(scan_cfg.get("folder_path", ".")).expanduser().resolve()
        root_cfg = str(meta_cfg.get("root_folder", "") or "").strip()
        if not root_cfg:
            raise ValueError(
                "metadata.root_folder not set; workspace.root is required in config.yaml"
            )
        self.root = Path(root_cfg).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

        self.strategy = str(meta_cfg.get("update_strategy", "update_missing")).strip().lower()
        self.schema_version = str(meta_cfg.get("schema_version", "2.0"))
        self.tool_version = str(meta_cfg.get("tool_version", "v5.3"))
        self.index_path = self.root / "metadata-index.json"
        # When true, load_records() walks subfolders under root (e.g. legacy nested .../metadata/*.json).
        self.load_recursive = bool(meta_cfg.get("load_recursive", False))

    def _json_path_for_record(self, rec: Dict[str, Any]) -> Path:
        src = str(rec.get("full_path", "")).strip()
        if not src:
            src = str(rec.get("filename", "")).strip()
        key = hashlib.sha1(src.encode("utf-8", errors="ignore")).hexdigest()
        return self.root / f"{key}.json"

    def _media_id_for_record(self, rec: Dict[str, Any], existing: Dict[str, Any] | None = None) -> str:
        if isinstance(existing, dict):
            ef = existing.get("file", {}) if isinstance(existing.get("file", {}), dict) else {}
            if ef.get("media_id"):
                return str(ef.get("media_id"))
        if rec.get("media_id"):
            return str(rec.get("media_id"))
        md5 = str(rec.get("md5_hash", "") or "").strip()
        if md5:
            return md5.lower()
        raw = (
            str(rec.get("full_path", "")).strip() + "|" +
            str(rec.get("filename", "")).strip() + "|" +
            str(rec.get("size_mb", "")).strip()
        )
        return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()

    def _now(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _record_to_doc(self, rec: Dict[str, Any], existing: Dict[str, Any] | None = None) -> Dict[str, Any]:
        base = existing.copy() if isinstance(existing, dict) else {}
        now = self._now()
        generated_at = str(base.get("generated_at") or now)
        media_id = self._media_id_for_record(rec, existing=base)

        manual_date = _dateish_to_str(rec.get("manual_date_override", "") or "")
        date_taken = _dateish_to_str(rec.get("date_taken", "") or "")
        file_modified = _dateish_to_str(rec.get("file_modified", "") or "")
        eff_date = _dateish_to_str(rec.get("effective_organize_date", "") or "")
        eff_src = str(rec.get("effective_date_source", "") or rec.get("date_source", "") or "")
        if not eff_date:
            if manual_date:
                eff_date = manual_date[:10]
                eff_src = "manual"
            elif date_taken:
                eff_date = date_taken[:10]
                eff_src = "exif"
            elif file_modified:
                eff_date = file_modified[:10]
                eff_src = "modified"
            else:
                eff_src = "undated"
        parts = _date_parts(eff_date or date_taken or file_modified)

        existing_sources = base.get("sources") if isinstance(base.get("sources"), dict) else {}
        existing_local = existing_sources.get("local") if isinstance(existing_sources.get("local"), dict) else {}
        cloud = existing_sources.get("cloud") if isinstance(existing_sources.get("cloud"), dict) else {}

        file_section = {
            "media_id": media_id,
            "filename": rec.get("filename", ""),
            "extension": str(rec.get("extension", "") or "").lower().lstrip("."),
            "file_type": rec.get("file_type", ""),
            "mime_type": rec.get("mime_type", ""),
            "full_path": rec.get("full_path", ""),
            "folder": rec.get("folder", ""),
            "parent_folder": rec.get("parent_folder") or Path(str(rec.get("folder", "") or ".")).name,
            "relative_path": rec.get("relative_path", ""),
            "source_root": rec.get("source_root", ""),
            "source_type": rec.get("source_type", "local"),
            "size_bytes": _safe_int(rec.get("size_bytes"), 0),
            "size_mb": rec.get("size_mb", 0),
            "md5_hash": rec.get("md5_hash", ""),
            "sha256_hash": rec.get("sha256_hash", ""),
            "is_hidden": bool(rec.get("is_hidden", False)),
            "is_readonly": bool(rec.get("is_readonly", False)),
            "organized_path": rec.get("organized_path", ""),
        }

        base.update(
            {
                "schema_version": self.schema_version,
                "tool_version": self.tool_version,
                "generated_at": generated_at,
                "updated_at": now,
                "media_id": media_id,
                "file": _ensure_json_serializable(file_section),
                "sources": _ensure_json_serializable(
                    {
                        "primary": rec.get("source_type", "local"),
                        "local": {
                            "source_root": rec.get("source_root") or str(self.scan_root),
                            "relative_path": rec.get("relative_path", ""),
                            "first_seen_at": _coalesce(
                                rec.get("first_seen_at"),
                                existing_local.get("first_seen_at"),
                                generated_at,
                            ),
                            "last_seen_at": _coalesce(rec.get("last_seen_at"), now),
                        },
                        "cloud": {
                            "provider": _coalesce(rec.get("cloud_provider"), cloud.get("provider"), default="none"),
                            "account_id": _coalesce(rec.get("cloud_account_id"), cloud.get("account_id")),
                            "drive_id": _coalesce(rec.get("cloud_drive_id"), cloud.get("drive_id")),
                            "item_id": _coalesce(rec.get("cloud_item_id"), cloud.get("item_id")),
                            "drive_path": _coalesce(rec.get("cloud_drive_path"), cloud.get("drive_path")),
                            "web_url": _coalesce(rec.get("cloud_web_url"), cloud.get("web_url")),
                            "etag": _coalesce(rec.get("cloud_etag"), cloud.get("etag")),
                            "downloaded": bool(_coalesce(rec.get("cloud_downloaded"), cloud.get("downloaded"), default=False)),
                            "local_cache_path": _coalesce(rec.get("cloud_local_cache_path"), cloud.get("local_cache_path")),
                            "provider_raw": _coalesce(rec.get("cloud_provider_raw"), cloud.get("provider_raw"), default={}),
                        },
                    }
                ),
                "filesystem": _ensure_json_serializable(
                    {
                        "created_time": _dateish_to_str(rec.get("created_time", "")),
                        "modified_time": _dateish_to_str(rec.get("modified_time") or file_modified),
                        "accessed_time": _dateish_to_str(rec.get("accessed_time", "")),
                    }
                ),
                "dates": _ensure_json_serializable(
                    {
                        "manual_date_override": manual_date,
                        "date_taken": date_taken,
                        "file_modified": file_modified,
                        "google_photo_taken_time": rec.get("google_photo_taken_time"),
                        "google_creation_time": rec.get("google_creation_time"),
                        "effective_organize_date": eff_date,
                        "effective_date_source": eff_src,
                        "date_source": eff_src,
                        "year": parts["year"],
                        "month": parts["month"],
                        "day": parts["day"],
                    }
                ),
                "hashes": _ensure_json_serializable(
                    {
                        "md5": rec.get("md5_hash", ""),
                        "sha256": rec.get("sha256_hash", ""),
                        "ahash": rec.get("ahash"),
                        "phash": rec.get("phash"),
                        "dhash": rec.get("dhash"),
                    }
                ),
                "image": _ensure_json_serializable(
                    {
                        "width": rec.get("width"),
                        "height": rec.get("height"),
                        "megapixels": rec.get("megapixels"),
                        "aspect_ratio": rec.get("aspect_ratio"),
                        "orientation": rec.get("orientation"),
                        "mode": rec.get("mode"),
                        "dpi": rec.get("dpi"),
                        "has_alpha": rec.get("has_alpha"),
                        "color_space": rec.get("color_space"),
                        "compression": rec.get("compression"),
                    }
                ),
                "video": _ensure_json_serializable(
                    None
                    if rec.get("file_type") != "video"
                    else {
                        "duration_sec": rec.get("video_duration_sec"),
                        "duration_fmt": rec.get("video_duration_fmt"),
                        "width": rec.get("video_width"),
                        "height": rec.get("video_height"),
                        "fps": rec.get("video_fps"),
                        "codec": rec.get("video_codec"),
                        "bitrate_kbps": rec.get("video_bitrate_kbps"),
                        "metadata_source": rec.get("video_meta_source"),
                        "metadata_error": rec.get("video_meta_error"),
                    }
                ),
                "exif": _ensure_json_serializable(
                    {
                        "has_exif": bool(rec.get("has_exif", False)),
                        "camera_make": rec.get("camera_make"),
                        "camera_model": rec.get("camera_model"),
                        "lens_model": rec.get("lens_model"),
                        "iso": rec.get("iso"),
                        "aperture": rec.get("aperture"),
                        "exposure_time": rec.get("exposure_time"),
                        "focal_length": rec.get("focal_length"),
                        "flash": rec.get("flash"),
                        "white_balance": rec.get("white_balance"),
                        "software": rec.get("software"),
                        "orientation": rec.get("exif_orientation"),
                    }
                ),
                "gps": _ensure_json_serializable(
                    {
                        "has_gps": rec.get("gps_lat") is not None and rec.get("gps_lon") is not None,
                        "latitude": rec.get("gps_lat"),
                        "longitude": rec.get("gps_lon"),
                        "altitude": rec.get("gps_altitude"),
                        "location_name": rec.get("location_name"),
                        "city": rec.get("location_city"),
                        "state": rec.get("location_state"),
                        "country": rec.get("location_country"),
                    }
                ),
            }
        )

        face_count = _safe_int(rec.get("face_count"), 0) or 0
        face_items = _faces_items_from_record(rec, face_count)
        base["quality"] = _ensure_json_serializable(
            {
                "blur_score": rec.get("blur_score"),
                "is_blurry": rec.get("is_blurry"),
                "brightness_score": rec.get("brightness_score"),
                "contrast_score": rec.get("contrast_score"),
                "noise_score": rec.get("noise_score"),
                "quality_score": rec.get("quality_score"),
                "quality_rating": rec.get("quality_rating"),
                "quality_issues": _quality_issues(rec.get("quality_issues")),
            }
        )
        base["faces"] = _ensure_json_serializable(
            {
                "face_count": face_count,
                "face_category": rec.get("face_category") or "No People",
                "face_search_ready": bool(face_count > 0),
                "items": face_items,
            }
        )

        person_doc = base.get("person") if isinstance(base.get("person"), dict) else {}
        base["people"] = _ensure_json_serializable(
            {
                "known_names": _string_list(rec.get("people_names")),
                "match_status": person_doc.get("status") or rec.get("person_match_flag", ""),
                "person_id": person_doc.get("person_id") or rec.get("person_label", ""),
                "person_name": person_doc.get("person_name") or rec.get("person_label", ""),
                "similarity": person_doc.get("similarity") or rec.get("person_similarity", ""),
                "source": person_doc.get("source") or rec.get("person_match_source", ""),
            }
        )
        base["tags"] = _ensure_json_serializable(
            {
                "primary_tag": rec.get("primary_tag"),
                "auto_tags": rec.get("auto_tags"),
                "manual_tags": rec.get("manual_tags", []),
                "scene_type": rec.get("scene_type"),
                "event": rec.get("event"),
            }
        )
        base["duplicate"] = _ensure_json_serializable(
            {
                "is_duplicate": _truthy(rec.get("is_duplicate")),
                "duplicate_group": rec.get("duplicate_group") or None,
                "duplicate_type": rec.get("duplicate_type") or ("exact_md5" if _truthy(rec.get("is_duplicate")) else None),
                "master_media_id": rec.get("master_media_id"),
                "duplicate_confidence": rec.get("duplicate_confidence"),
                "is_best_in_group": rec.get("is_best_in_group"),
                "recommendation": rec.get("recommendation"),
            }
        )
        base["similarity"] = _ensure_json_serializable(
            {
                "is_similar": _truthy(rec.get("is_similar")),
                "similar_group": rec.get("similar_group") or None,
                "similarity_score": rec.get("similar_score"),
                "methods": _string_list(rec.get("similar_methods")),
            }
        )
        base["organization"] = _ensure_json_serializable(
            {
                "original_path": rec.get("original_path") or rec.get("full_path", ""),
                "organized_path": rec.get("organized_path", ""),
                "operation": rec.get("organization_operation"),
                "folder_strategy": rec.get("folder_strategy"),
            }
        )
        base["thumbnails"] = _ensure_json_serializable(
            {
                "small": rec.get("thumbnail_path"),
                "medium": rec.get("thumbnail_medium_path"),
            }
        )
        base["processing"] = _ensure_json_serializable(
            {
                "scan_status": "error" if rec.get("error") else "success",
                "metadata_status": rec.get("metadata_status", ""),
                "scan_duration_ms": rec.get("scan_duration_ms"),
                "metadata_engine": rec.get("metadata_engine", "Pillow"),
                "quality_engine": rec.get("quality_engine", "OpenCV"),
                "errors": _quality_issues(rec.get("error")),
                "warnings": _quality_issues(rec.get("warnings")),
            }
        )
        base["ocr"] = _ensure_json_serializable(
            {
                "has_text": bool(rec.get("ocr_text")),
                "text": rec.get("ocr_text"),
                "confidence": rec.get("ocr_confidence"),
            }
        )
        base["ai"] = _ensure_json_serializable(
            {
                "caption": rec.get("ai_caption"),
                "detected_objects": rec.get("detected_objects", []),
                "nsfw_score": rec.get("nsfw_score"),
            }
        )
        base["storage"] = _ensure_json_serializable(
            {
                "archive_recommended": bool(rec.get("archive_recommended", False)),
                "compressible": bool(rec.get("compressible", False)),
                "estimated_savings_mb": rec.get("estimated_savings_mb", 0),
            }
        )
        base["kpi"] = _ensure_json_serializable(
            {
                "metadata_status": rec.get("metadata_status", ""),
                "face_count": face_count,
                "is_duplicate": rec.get("is_duplicate", "No"),
                "is_similar": rec.get("is_similar", "No"),
            }
        )
        # Store the raw record only when explicitly requested (avoids doubling file size).
        if (self.config.get("metadata") or {}).get("store_raw_record", False):
            base["record"] = _ensure_json_serializable(dict(rec))
        fp = str(rec.get("full_path", "") or "").strip()
        if fp:
            try:
                apply_media_path_to_doc(base, Path(fp), self.config)
            except (OSError, ValueError):
                pass
        return base

    def _apply_person_from_doc(self, rec: Dict[str, Any], doc: Dict[str, Any]) -> None:
        """Map top-level doc['person'] into Excel-facing fields (steps 6–8 read JSON via load_records)."""
        p = doc.get("person")
        if not isinstance(p, dict) or not p:
            return
        status = str(p.get("status", "")).strip().lower()
        if status == "known":
            rec["person_match_flag"] = "Yes"
            label = str(p.get("person_name", "") or p.get("person_id", "")).strip()
            rec["person_label"] = label
            sim = p.get("similarity", "")
            if sim is None or sim == "":
                rec["person_similarity"] = ""
            else:
                try:
                    rec["person_similarity"] = float(sim)
                except (TypeError, ValueError):
                    rec["person_similarity"] = str(sim)
            src = str(p.get("source", "") or "seed").strip()
            rec["person_match_source"] = src if src else "seed"
        elif status == "unknown":
            rec["person_match_flag"] = "No"
            rec["person_label"] = str(p.get("person_id", "") or "").strip()
            rec["person_similarity"] = ""
            src = str(p.get("source", "") or "untagged").strip()
            rec["person_match_source"] = src if src else "untagged"

    def _doc_to_record(self, doc: Dict[str, Any], json_path: Path) -> Dict[str, Any]:
        rec = dict(doc.get("record", {}) or {})
        f = doc.get("file", {}) or {}
        d = doc.get("dates", {}) or {}
        q = doc.get("quality", {}) or {}
        img = doc.get("image", {}) or {}
        video = doc.get("video", {}) or {}
        exif = doc.get("exif", {}) or {}
        gps = doc.get("gps", {}) or {}
        hashes = doc.get("hashes", {}) or {}
        sources = doc.get("sources", {}) or {}
        local = sources.get("local", {}) if isinstance(sources.get("local"), dict) else {}
        cloud = sources.get("cloud", {}) if isinstance(sources.get("cloud"), dict) else {}
        dup = doc.get("duplicate", {}) or {}
        sim = doc.get("similarity", {}) or {}
        tags = doc.get("tags", {}) or {}
        processing = doc.get("processing", {}) or {}
        thumbs = doc.get("thumbnails", {}) or {}
        k = doc.get("kpi", {}) or {}
        faces = doc.get("faces", {}) or {}
        if isinstance(faces, list):
            face_count = len(faces)
            face_category = rec.get("face_category", "")
            face_items = faces
            face_search_ready = face_count > 0
        else:
            face_count = _safe_int(_coalesce(faces.get("face_count"), k.get("face_count"), rec.get("face_count")), 0) or 0
            face_category = _coalesce(faces.get("face_category"), rec.get("face_category"), "")
            face_items = _coalesce(faces.get("items"), rec.get("face_boxes"), [])
            face_search_ready = bool(faces.get("face_search_ready", face_count > 0))
        abs_p = resolve_absolute_from_doc(doc, self.config)
        full_path = str(abs_p) if abs_p else _coalesce(f.get("full_path"), rec.get("full_path"), "")
        folder = str(abs_p.parent) if abs_p else _coalesce(f.get("folder"), rec.get("folder"), "")
        file_modified = _coalesce(
            d.get("file_modified"),
            (doc.get("filesystem") or {}).get("modified_time"),
            rec.get("file_modified"),
            "",
        )
        md5_hash = _coalesce(f.get("md5_hash"), hashes.get("md5"), "")
        sha256_hash = _coalesce(f.get("sha256_hash"), hashes.get("sha256"), "")
        size_bytes = _coalesce(f.get("size_bytes"), rec.get("size_bytes"), 0)
        quality_issues = q.get("quality_issues", rec.get("quality_issues", ""))
        if isinstance(quality_issues, list):
            quality_issues = ", ".join(str(v) for v in quality_issues if str(v).strip())
        rec.update({
            "media_id": f.get("media_id") or doc.get("media_id", rec.get("media_id", "")),
            "filename": _coalesce(f.get("filename"), rec.get("filename"), ""),
            "full_path": full_path,
            "folder": folder,
            "relative_path": _coalesce(f.get("relative_path"), rec.get("relative_path"), ""),
            "parent_folder": _coalesce(f.get("parent_folder"), rec.get("parent_folder"), ""),
            "source_root": _coalesce(f.get("source_root"), local.get("source_root"), rec.get("source_root"), ""),
            "source_type": _coalesce(f.get("source_type"), sources.get("primary"), rec.get("source_type"), "local"),
            "file_type": _coalesce(f.get("file_type"), rec.get("file_type"), ""),
            "extension": str(_coalesce(f.get("extension"), rec.get("extension"), "") or "").upper(),
            "mime_type": _coalesce(f.get("mime_type"), rec.get("mime_type"), ""),
            "size_bytes": size_bytes,
            "size_mb": _coalesce(f.get("size_mb"), rec.get("size_mb"), 0),
            "md5_hash": md5_hash,
            "sha256_hash": sha256_hash,
            "first_seen_at": _coalesce(local.get("first_seen_at"), rec.get("first_seen_at"), ""),
            "last_seen_at": _coalesce(local.get("last_seen_at"), rec.get("last_seen_at"), ""),
            "created_time": _coalesce((doc.get("filesystem") or {}).get("created_time"), rec.get("created_time"), ""),
            "modified_time": _coalesce((doc.get("filesystem") or {}).get("modified_time"), rec.get("modified_time"), ""),
            "accessed_time": _coalesce((doc.get("filesystem") or {}).get("accessed_time"), rec.get("accessed_time"), ""),
            "manual_date_override": _coalesce(d.get("manual_date_override"), rec.get("manual_date_override"), ""),
            "date_taken": _coalesce(d.get("date_taken"), rec.get("date_taken"), ""),
            "file_modified": file_modified,
            "google_photo_taken_time": _coalesce(d.get("google_photo_taken_time"), rec.get("google_photo_taken_time")),
            "google_creation_time": _coalesce(d.get("google_creation_time"), rec.get("google_creation_time")),
            "effective_organize_date": _coalesce(d.get("effective_organize_date"), rec.get("effective_organize_date"), ""),
            "effective_date_source": _coalesce(d.get("effective_date_source"), rec.get("effective_date_source"), ""),
            "year": _coalesce(d.get("year"), rec.get("year")),
            "month": _coalesce(d.get("month"), rec.get("month")),
            "day": _coalesce(d.get("day"), rec.get("day")),
            "width": _coalesce(img.get("width"), q.get("width"), rec.get("width")),
            "height": _coalesce(img.get("height"), q.get("height"), rec.get("height")),
            "megapixels": _coalesce(img.get("megapixels"), rec.get("megapixels")),
            "aspect_ratio": _coalesce(img.get("aspect_ratio"), rec.get("aspect_ratio")),
            "orientation": _coalesce(img.get("orientation"), rec.get("orientation")),
            "mode": _coalesce(img.get("mode"), rec.get("mode")),
            "dpi": _coalesce(img.get("dpi"), rec.get("dpi")),
            "has_alpha": _coalesce(img.get("has_alpha"), rec.get("has_alpha")),
            "color_space": _coalesce(img.get("color_space"), rec.get("color_space")),
            "compression": _coalesce(img.get("compression"), rec.get("compression")),
            "has_exif": exif.get("has_exif", rec.get("has_exif", False)),
            "camera_make": _coalesce(exif.get("camera_make"), rec.get("camera_make")),
            "camera_model": _coalesce(exif.get("camera_model"), rec.get("camera_model")),
            "lens_model": _coalesce(exif.get("lens_model"), rec.get("lens_model")),
            "iso": _coalesce(exif.get("iso"), rec.get("iso")),
            "aperture": _coalesce(exif.get("aperture"), rec.get("aperture")),
            "exposure_time": _coalesce(exif.get("exposure_time"), rec.get("exposure_time")),
            "focal_length": _coalesce(exif.get("focal_length"), rec.get("focal_length")),
            "flash": _coalesce(exif.get("flash"), rec.get("flash")),
            "white_balance": _coalesce(exif.get("white_balance"), rec.get("white_balance")),
            "software": _coalesce(exif.get("software"), rec.get("software")),
            "exif_orientation": _coalesce(exif.get("orientation"), rec.get("exif_orientation")),
            "gps_lat": _coalesce(gps.get("latitude"), rec.get("gps_lat")),
            "gps_lon": _coalesce(gps.get("longitude"), rec.get("gps_lon")),
            "gps_altitude": _coalesce(gps.get("altitude"), rec.get("gps_altitude")),
            "location_name": _coalesce(gps.get("location_name"), rec.get("location_name")),
            "location_city": _coalesce(gps.get("city"), rec.get("location_city")),
            "location_state": _coalesce(gps.get("state"), rec.get("location_state")),
            "location_country": _coalesce(gps.get("country"), rec.get("location_country")),
            "blur_score": _coalesce(q.get("blur_score"), rec.get("blur_score")),
            "quality_score": _coalesce(q.get("quality_score"), rec.get("quality_score")),
            "is_blurry": _coalesce(q.get("is_blurry"), rec.get("is_blurry")),
            "brightness_score": _coalesce(q.get("brightness_score"), rec.get("brightness_score")),
            "contrast_score": _coalesce(q.get("contrast_score"), rec.get("contrast_score")),
            "noise_score": _coalesce(q.get("noise_score"), rec.get("noise_score")),
            "quality_rating": _coalesce(q.get("quality_rating"), rec.get("quality_rating"), "Unknown"),
            "quality_issues": quality_issues,
            "video_duration_sec": _coalesce(video.get("duration_sec"), rec.get("video_duration_sec")),
            "video_duration_fmt": _coalesce(video.get("duration_fmt"), rec.get("video_duration_fmt")),
            "video_width": _coalesce(video.get("width"), rec.get("video_width")),
            "video_height": _coalesce(video.get("height"), rec.get("video_height")),
            "video_fps": _coalesce(video.get("fps"), rec.get("video_fps")),
            "video_codec": _coalesce(video.get("codec"), rec.get("video_codec")),
            "video_bitrate_kbps": _coalesce(video.get("bitrate_kbps"), rec.get("video_bitrate_kbps")),
            "video_meta_source": _coalesce(video.get("metadata_source"), rec.get("video_meta_source")),
            "video_meta_error": _coalesce(video.get("metadata_error"), rec.get("video_meta_error")),
            "ahash": _coalesce(hashes.get("ahash"), rec.get("ahash")),
            "phash": _coalesce(hashes.get("phash"), rec.get("phash")),
            "dhash": _coalesce(hashes.get("dhash"), rec.get("dhash")),
            "face_count": face_count,
            "face_category": face_category,
            "face_search_ready": face_search_ready,
            "face_boxes": face_items,
            "is_duplicate": _yes_no(_coalesce(dup.get("is_duplicate"), k.get("is_duplicate"), rec.get("is_duplicate"), "No")),
            "duplicate_group": dup.get("duplicate_group") or rec.get("duplicate_group", ""),
            "duplicate_type": dup.get("duplicate_type") or ("exact_md5" if _truthy(dup.get("is_duplicate")) else rec.get("duplicate_type")),
            "master_media_id": dup.get("master_media_id"),
            "duplicate_confidence": dup.get("duplicate_confidence"),
            "is_best_in_group": dup.get("is_best_in_group") or rec.get("is_best_in_group", ""),
            "recommendation": dup.get("recommendation") or rec.get("recommendation", ""),
            "is_similar": _yes_no(_coalesce(sim.get("is_similar"), k.get("is_similar"), rec.get("is_similar"), "No")),
            "similar_group": sim.get("similar_group") or rec.get("similar_group", ""),
            "similar_score": sim.get("similarity_score") or rec.get("similar_score", ""),
            "similar_methods": ", ".join(sim.get("methods") or []) if isinstance(sim.get("methods"), list) else sim.get("methods", ""),
            "metadata_status": processing.get("metadata_status") or k.get("metadata_status") or rec.get("metadata_status", ""),
            "primary_tag": _coalesce(tags.get("primary_tag"), rec.get("primary_tag")),
            "auto_tags": _coalesce(tags.get("auto_tags"), rec.get("auto_tags")),
            "manual_tags": _coalesce(tags.get("manual_tags"), rec.get("manual_tags"), []),
            "scene_type": _coalesce(tags.get("scene_type"), rec.get("scene_type")),
            "event": _coalesce(tags.get("event"), rec.get("event")),
            "thumbnail_path": _coalesce(thumbs.get("small"), rec.get("thumbnail_path")),
            "thumbnail_medium_path": _coalesce(thumbs.get("medium"), rec.get("thumbnail_medium_path")),
            "cloud_provider": _coalesce(cloud.get("provider"), rec.get("cloud_provider"), "none"),
            "cloud_account_id": _coalesce(cloud.get("account_id"), rec.get("cloud_account_id")),
            "cloud_drive_id": _coalesce(cloud.get("drive_id"), rec.get("cloud_drive_id")),
            "cloud_item_id": _coalesce(cloud.get("item_id"), rec.get("cloud_item_id")),
            "cloud_drive_path": _coalesce(cloud.get("drive_path"), rec.get("cloud_drive_path")),
            "cloud_web_url": _coalesce(cloud.get("web_url"), rec.get("cloud_web_url")),
            "cloud_etag": _coalesce(cloud.get("etag"), rec.get("cloud_etag")),
            "cloud_downloaded": _coalesce(cloud.get("downloaded"), rec.get("cloud_downloaded")),
            "cloud_local_cache_path": _coalesce(cloud.get("local_cache_path"), rec.get("cloud_local_cache_path")),
            "cloud_provider_raw": _coalesce(cloud.get("provider_raw"), rec.get("cloud_provider_raw")),
            "metadata_json_path": str(json_path),
            "schema_version": doc.get("schema_version", self.schema_version),
        })
        self._apply_person_from_doc(rec, doc)
        fp = str(rec.get("full_path") or "").strip()
        if (self.config.get("workflow") or {}).get("excel_include_file_exists_column", True):
            rec["file_exists"] = "Yes" if fp and Path(fp).is_file() else "No"
        else:
            rec["file_exists"] = "Yes"
        return rec

    def rebuild_index(self) -> int:
        from .vault_maintenance import rebuild_vault_index
        return rebuild_vault_index(self.config)

    def load_records(
        self,
        *,
        exclude_missing: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        if exclude_missing is None:
            exclude_missing = bool(
                (self.config.get("workflow") or {}).get("excel_exclude_missing_files", False)
            )
        if not self.root.exists():
            return []
        from .vault_maintenance import iter_vault_json_paths

        paths = list(iter_vault_json_paths(self))
        records = []

        def _load_one(jp: Path):
            try:
                doc = json.loads(jp.read_text(encoding="utf-8"))
                return self._doc_to_record(doc, jp)
            except Exception:
                return None

        threads = max(1, int((self.config.get("processing") or {}).get("threads", 4)))
        with ThreadPoolExecutor(max_workers=threads) as pool:
            for rec in pool.map(_load_one, paths):
                if rec is not None:
                    records.append(rec)

        if exclude_missing:
            records = [r for r in records if str(r.get("file_exists", "")).lower() == "yes"]
        return records

    def upsert_records(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Load existing index so batch flushes accumulate rather than truncate.
        index_by_path: Dict[str, Dict[str, Any]] = {}
        if self.index_path.exists():
            try:
                for entry in json.loads(self.index_path.read_text(encoding="utf-8")):
                    key = str(entry.get("metadata_json_path", ""))
                    if key:
                        index_by_path[key] = entry
            except Exception:
                pass

        out = []
        for rec in records or []:
            jp = self._json_path_for_record(rec)
            existing = None
            if jp.exists():
                try:
                    existing = json.loads(jp.read_text(encoding="utf-8"))
                except Exception:
                    existing = None

            strat = self.strategy
            if strat == "skip_if_present" and existing is not None:
                doc = existing
            elif strat == "update_missing" and existing is not None:
                doc = self._record_to_doc(rec, existing=existing)
                for key, val in (existing or {}).items():
                    if key not in doc:
                        doc[key] = val
            elif strat == "refresh" and existing is not None:
                doc = self._record_to_doc(rec, existing=existing)
            else:
                doc = self._record_to_doc(rec, existing=None)

            doc["schema_version"] = self.schema_version
            doc["tool_version"] = self.tool_version
            # _record_to_doc already serializes every sub-section; no second pass needed.
            jp.write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=True), encoding="utf-8")
            normalized = self._doc_to_record(doc, jp)
            out.append(normalized)
            index_by_path[str(jp)] = {
                "full_path": normalized.get("full_path", ""),
                "metadata_json_path": str(jp),
                "schema_version": doc.get("schema_version", self.schema_version),
                "updated_at": doc.get("updated_at", ""),
            }

        # Write the full accumulated index (compact JSON for smaller file).
        self.index_path.write_text(
            json.dumps(list(index_by_path.values()), separators=(",", ":"), ensure_ascii=True),
            encoding="utf-8",
        )
        return out
