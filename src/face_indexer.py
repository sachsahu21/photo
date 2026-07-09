"""
Face Indexer v4.1

Builds a local face embedding index (SQLite) and searches it using seed photos.
Requires optional deps: facenet-pytorch + torch + torchvision.
"""

from __future__ import annotations

import sqlite3
import logging
from pathlib import Path
from typing import Iterable, Optional, Dict, Any, List, Tuple

import numpy as np

logger = logging.getLogger(__name__)


def _try_import_facenet():
    try:
        import torch
        from PIL import Image
        from facenet_pytorch import MTCNN, InceptionResnetV1
        return torch, Image, MTCNN, InceptionResnetV1
    except Exception:
        return None, None, None, None


def _iter_images(root: Path, exts: Iterable[str], recursive: bool = True) -> Iterable[Path]:
    exts = {("." + e.lower().lstrip(".")) for e in (exts or [])}
    if not exts:
        exts = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
    if not root.exists():
        return []

    it = root.rglob("*") if recursive else root.iterdir()
    for p in it:
        if p.is_file() and p.suffix.lower() in exts:
            yield p


def _cosine_sim_matrix(query_vec: np.ndarray, mat: np.ndarray) -> np.ndarray:
    q = query_vec.astype(np.float32, copy=False)
    m = mat.astype(np.float32, copy=False)
    qn = np.linalg.norm(q) + 1e-12
    mn = np.linalg.norm(m, axis=1) + 1e-12
    return (m @ q) / (mn * qn)


class FaceIndexer:
    def __init__(self, config: Dict[str, Any]):
        self.config = config or {}
        self.faces_cfg = (self.config or {}).get("faces", {}) or {}

        scan_cfg = (self.config or {}).get("scan", {}) or {}
        exts_cfg = (scan_cfg.get("extensions", {}) or {}).get("images", []) or []
        self.image_exts = [str(e).lower() for e in exts_cfg]

        self.enabled = bool(self.faces_cfg.get("enabled", False))
        self.seed_root = Path(self.faces_cfg.get("seed_root", "") or "")
        self.target_person = str(self.faces_cfg.get("target_person", "")).strip()
        self.library_source = str(self.faces_cfg.get("library_source", "scan")).lower()
        self.sim_thr = self._resolve_similarity_threshold(self.faces_cfg)
        self.max_results = int(self.faces_cfg.get("max_results", 50000))
        if self.max_results < 0:
            self.max_results = 0
        index_db = str(self.faces_cfg.get("index_db") or "").strip()
        if not index_db:
            index_db = str(self.faces_cfg.get("index_db_filename") or "face_index.sqlite").strip() or "face_index.sqlite"
        self.index_db = Path(index_db).expanduser()
        if not str(self.index_db):
            raise ValueError("faces.index_db not resolved; set workspace.root in config.yaml")

        self._torch, self._PILImage, self._MTCNN, self._Resnet = _try_import_facenet()
        self._mtcnn = None
        self._resnet = None

    @staticmethod
    def _resolve_similarity_threshold(faces_cfg: Dict[str, Any]) -> float:
        """
        Cosine similarity in [0, 1]. Higher = stricter (fewer matches).
        If similarity_threshold_percent is set (0-100), it overrides similarity_threshold.
        """
        pct = faces_cfg.get("similarity_threshold_percent")
        if pct is not None:
            if not (isinstance(pct, str) and not str(pct).strip()):
                try:
                    v = float(pct)
                    return max(0.0, min(1.0, v / 100.0))
                except (TypeError, ValueError):
                    pass
        try:
            return max(0.0, min(1.0, float(faces_cfg.get("similarity_threshold", 0.35))))
        except (TypeError, ValueError):
            return 0.35

    def _require_enabled(self):
        if not self.enabled:
            raise RuntimeError("faces.enabled is false in config.yaml")

    def _require_backend(self):
        if self._MTCNN is None or self._Resnet is None or self._PILImage is None:
            raise RuntimeError(
                "Face backend unavailable. Install:\n"
                "  pip install facenet-pytorch torch torchvision"
            )

    def _get_library_root(self) -> Path:
        if self.library_source == "organized":
            org = (self.config.get("organization") or {})
            return Path(org.get("output_folder", "./organized_images"))
        scan = (self.config.get("scan") or {})
        return Path(scan.get("folder_path", "./sample_images"))

    def _open_db(self) -> sqlite3.Connection:
        self.index_db.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(str(self.index_db))
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
              path TEXT PRIMARY KEY,
              mtime REAL NOT NULL,
              size INTEGER NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS faces (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              file_path TEXT NOT NULL,
              face_idx INTEGER NOT NULL,
              x1 INTEGER, y1 INTEGER, x2 INTEGER, y2 INTEGER,
              det_score REAL,
              embedding BLOB NOT NULL,
              FOREIGN KEY(file_path) REFERENCES files(path)
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_faces_file ON faces(file_path);")
        return con

    def _ensure_models(self):
        if self._mtcnn is not None and self._resnet is not None:
            return
        self._require_backend()
        device = "cpu"
        self._mtcnn = self._MTCNN(keep_all=True, device=device)
        self._resnet = self._Resnet(pretrained="vggface2").eval().to(device)

    def _extract_face_embeddings(self, image_path: str) -> List[Tuple[np.ndarray, Optional[List[int]], float]]:
        pil = self._PILImage.open(image_path).convert("RGB")
        try:
            boxes, probs = self._mtcnn.detect(pil)
            if boxes is None:
                return []

            face_tensors = self._mtcnn(pil)
            if face_tensors is None:
                return []
            if len(face_tensors.shape) == 3:
                face_tensors = face_tensors.unsqueeze(0)

            with self._torch.no_grad():
                emb_batch = self._resnet(face_tensors).cpu().numpy()

            out = []
            for i, emb in enumerate(emb_batch):
                box = boxes[i] if i < len(boxes) else None
                bbox = None
                if box is not None:
                    bbox = [int(v) for v in box[:4]]
                det_score = float(probs[i]) if probs is not None and i < len(probs) and probs[i] is not None else 0.0
                out.append((emb.astype(np.float32), bbox, det_score))
            return out
        finally:
            pil.close()

    def build_or_update_index(self, recursive: bool = True) -> Tuple[int, int]:
        self._require_enabled()
        try:
            self._ensure_models()
        except RuntimeError as exc:
            logger.warning("Face indexing skipped: %s", exc)
            return 0, 0

        root = self._get_library_root()
        con = self._open_db()
        indexed_files = 0
        indexed_faces = 0

        try:
            for fp in _iter_images(root, self.image_exts, recursive=recursive):
                try:
                    st = fp.stat()
                except Exception:
                    continue

                rel = str(fp)
                mtime = float(st.st_mtime)
                size = int(st.st_size)

                row = con.execute("SELECT mtime, size FROM files WHERE path=?", (rel,)).fetchone()
                if row and float(row[0]) == mtime and int(row[1]) == size:
                    continue

                con.execute("INSERT OR REPLACE INTO files(path, mtime, size) VALUES(?,?,?)", (rel, mtime, size))
                con.execute("DELETE FROM faces WHERE file_path=?", (rel,))

                try:
                    entries = self._extract_face_embeddings(rel)
                except Exception:
                    entries = []

                for i, (emb, bbox, det_score) in enumerate(entries):
                    x1 = y1 = x2 = y2 = None
                    if bbox is not None and len(bbox) >= 4:
                        x1, y1, x2, y2 = bbox[:4]
                    con.execute(
                        "INSERT INTO faces(file_path, face_idx, x1, y1, x2, y2, det_score, embedding) VALUES(?,?,?,?,?,?,?,?)",
                        (rel, i, x1, y1, x2, y2, float(det_score), emb.tobytes()),
                    )
                    indexed_faces += 1

                indexed_files += 1
                if indexed_files % 200 == 0:
                    con.commit()
                    logger.info("Face index updated: %d files", indexed_files)

            con.commit()
            return indexed_files, indexed_faces
        finally:
            con.close()

    def _seed_person_dirs(self) -> List[Tuple[str, Path]]:
        try:
            self.seed_root.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        if not self.seed_root.exists():
            return []
        if self.target_person:
            d = self.seed_root / self.target_person
            return [(self.target_person, d)] if d.exists() and d.is_dir() else []
        out = []
        for d in sorted(self.seed_root.iterdir()):
            if d.is_dir():
                out.append((d.name, d))
        return out

    def _embed_seed_person(self, person_dir: Path) -> Optional[np.ndarray]:
        embs: List[np.ndarray] = []
        for fp in _iter_images(person_dir, self.image_exts, recursive=True):
            try:
                entries = self._extract_face_embeddings(str(fp))
                if not entries:
                    continue
                best = max(entries, key=lambda x: float(x[2]))
                embs.append(best[0])
            except Exception:
                continue
        if not embs:
            return None
        return np.mean(np.stack(embs, axis=0), axis=0).astype(np.float32)

    def find_person(self) -> List[Dict[str, Any]]:
        self._require_enabled()
        try:
            self._ensure_models()
        except RuntimeError as exc:
            logger.warning("Known person matching skipped: %s", exc)
            return []

        person_dirs = self._seed_person_dirs()
        if not person_dirs:
            logger.warning("No seed person folders found under: %s; skipping known matches.", self.seed_root)
            return []

        con = self._open_db()
        try:
            rows = con.execute("SELECT file_path, embedding FROM faces").fetchall()
            if not rows:
                logger.warning("Face index is empty. Run 'Build/Update Face Index' first.")
                return []

            paths: List[str] = []
            embs: List[np.ndarray] = []
            for p, blob in rows:
                if blob is None:
                    continue
                v = np.frombuffer(blob, dtype=np.float32)
                if v.size:
                    paths.append(str(p))
                    embs.append(v)

            if not embs:
                raise RuntimeError("No valid embeddings in index.")

            mat = np.stack(embs, axis=0)

            # Build seed matrix: compute all person embeddings first, then do a
            # single matrix–matrix multiply instead of one query per person.
            seed_labels: List[str] = []
            seed_vecs: List[np.ndarray] = []
            for person_label, person_dir in person_dirs:
                sv = self._embed_seed_person(person_dir)
                if sv is not None:
                    seed_labels.append(person_label)
                    seed_vecs.append(sv)

            merged: Dict[Tuple[str, str], float] = {}

            if seed_vecs:
                seed_mat = np.stack(seed_vecs, axis=0).astype(np.float32)  # (P, D)
                lib_mat = mat.astype(np.float32)                            # (N, D)
                # Normalise rows for cosine similarity.
                seed_norms = np.linalg.norm(seed_mat, axis=1, keepdims=True) + 1e-12
                lib_norms = np.linalg.norm(lib_mat, axis=1, keepdims=True) + 1e-12
                sim_matrix = (lib_mat / lib_norms) @ (seed_mat / seed_norms).T  # (N, P)

                for pi, person_label in enumerate(seed_labels):
                    col = sim_matrix[:, pi]
                    for path_str, s in zip(paths, col.tolist()):
                        if s >= self.sim_thr:
                            key = (person_label, path_str)
                            if key not in merged or s > merged[key]:
                                merged[key] = float(s)

            ranked = sorted(merged.items(), key=lambda x: x[1], reverse=True)
            if self.max_results > 0:
                ranked = ranked[: self.max_results]
            return [
                {"person_label": person, "file_path": fp, "similarity": round(sim, 4)}
                for (person, fp), sim in ranked
            ]
        finally:
            con.close()