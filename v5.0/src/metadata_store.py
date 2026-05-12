"""Metadata JSON persistence for v5.1-style workflows."""

from __future__ import annotations

import json
import hashlib
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List


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


class MetadataStore:
    def __init__(self, config: Dict[str, Any]):
        self.config = config or {}
        scan_cfg = (self.config.get("scan") or {})
        meta_cfg = (self.config.get("metadata") or {})

        self.scan_root = Path(scan_cfg.get("folder_path", ".")).expanduser().resolve()
        root_cfg = str(meta_cfg.get("root_folder", "") or "").strip()
        self.root = Path(root_cfg).expanduser().resolve() if root_cfg else (self.scan_root / "metadata")
        self.root.mkdir(parents=True, exist_ok=True)

        self.strategy = str(meta_cfg.get("update_strategy", "update_missing")).strip().lower()
        self.schema_version = str(meta_cfg.get("schema_version", "1.0"))
        self.tool_version = str(meta_cfg.get("tool_version", "v5.1"))
        self.index_path = self.root / "metadata-index.json"

    def _json_path_for_record(self, rec: Dict[str, Any]) -> Path:
        src = str(rec.get("full_path", "")).strip()
        if not src:
            src = str(rec.get("filename", "")).strip()
        key = hashlib.sha1(src.encode("utf-8", errors="ignore")).hexdigest()
        return self.root / f"{key}.json"

    def _now(self) -> str:
        return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    def _record_to_doc(self, rec: Dict[str, Any], existing: Dict[str, Any] | None = None) -> Dict[str, Any]:
        base = existing.copy() if isinstance(existing, dict) else {}
        now = self._now()
        base.setdefault("schema_version", self.schema_version)
        base.setdefault("tool_version", self.tool_version)
        base.setdefault("generated_at", now)
        base["updated_at"] = now

        base["file"] = {
            "filename": rec.get("filename", ""),
            "full_path": rec.get("full_path", ""),
            "folder": rec.get("folder", ""),
            "file_type": rec.get("file_type", ""),
            "extension": rec.get("extension", ""),
            "size_mb": rec.get("size_mb", 0),
            "md5_hash": rec.get("md5_hash", ""),
        }
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

        base["dates"] = {
            "manual_date_override": manual_date,
            "date_taken": date_taken,
            "file_modified": file_modified,
            "effective_organize_date": eff_date,
            "effective_date_source": eff_src,
        }
        base["quality"] = _ensure_json_serializable(
            {
                "width": rec.get("width"),
                "height": rec.get("height"),
                "blur_score": rec.get("blur_score"),
                "quality_score": rec.get("quality_score"),
                "is_blurry": rec.get("is_blurry"),
            }
        )
        face_count = int(rec.get("face_count", 0) or 0)
        existing_faces = base.get("faces", [])
        if not isinstance(existing_faces, list):
            existing_faces = []
        if not existing_faces and face_count > 0:
            existing_faces = [
                {"face_idx": i, "person_id": f"UNK-{i+1:04d}", "person_name": None, "label_source": "unknown"}
                for i in range(face_count)
            ]
        base["faces"] = _ensure_json_serializable(existing_faces)
        base["tags"] = _ensure_json_serializable(
            {
                "primary_tag": rec.get("primary_tag"),
                "auto_tags": rec.get("auto_tags"),
                "manual_tags": rec.get("manual_tags", []),
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
        base["record"] = _ensure_json_serializable(dict(rec))
        return base

    def _doc_to_record(self, doc: Dict[str, Any], json_path: Path) -> Dict[str, Any]:
        rec = dict(doc.get("record", {}) or {})
        f = doc.get("file", {}) or {}
        d = doc.get("dates", {}) or {}
        q = doc.get("quality", {}) or {}
        k = doc.get("kpi", {}) or {}
        rec.update({
            "filename": f.get("filename", ""),
            "full_path": f.get("full_path", ""),
            "folder": f.get("folder", ""),
            "file_type": f.get("file_type", ""),
            "extension": f.get("extension", ""),
            "size_mb": f.get("size_mb", 0),
            "md5_hash": f.get("md5_hash", ""),
            "manual_date_override": d.get("manual_date_override", ""),
            "date_taken": d.get("date_taken", ""),
            "file_modified": d.get("file_modified", ""),
            "effective_organize_date": d.get("effective_organize_date", ""),
            "effective_date_source": d.get("effective_date_source", ""),
            "width": q.get("width"),
            "height": q.get("height"),
            "blur_score": q.get("blur_score"),
            "quality_score": q.get("quality_score"),
            "is_blurry": q.get("is_blurry"),
            "face_count": k.get("face_count", 0),
            "is_duplicate": k.get("is_duplicate", "No"),
            "is_similar": k.get("is_similar", "No"),
            "metadata_status": k.get("metadata_status", ""),
            "primary_tag": (doc.get("tags", {}) or {}).get("primary_tag"),
            "auto_tags": (doc.get("tags", {}) or {}).get("auto_tags"),
            "metadata_json_path": str(json_path),
            "schema_version": doc.get("schema_version", self.schema_version),
        })
        return rec

    def upsert_records(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out = []
        index = []
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
            doc = _ensure_json_serializable(doc)
            jp.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
            normalized = self._doc_to_record(doc, jp)
            out.append(normalized)
            index.append(
                {
                    "full_path": normalized.get("full_path", ""),
                    "metadata_json_path": str(jp),
                    "schema_version": doc.get("schema_version", self.schema_version),
                    "updated_at": doc.get("updated_at", ""),
                }
            )

        self.index_path.write_text(json.dumps(index, indent=2, ensure_ascii=True), encoding="utf-8")
        return out

    def load_records(self) -> List[Dict[str, Any]]:
        if not self.root.exists():
            return []
        records = []
        for jp in sorted(self.root.glob("*.json")):
            if jp.name == self.index_path.name:
                continue
            try:
                doc = json.loads(jp.read_text(encoding="utf-8"))
                records.append(self._doc_to_record(doc, jp))
            except Exception:
                continue
        return records
