# Image Scanner v5.0 (Metadata-First Workflow)

This version uses a metadata-first flow:

- generate per-file metadata JSON first,
- generate Excel from metadata,
- apply manual actions from Excel,
- organize images and move linked metadata,
- sync people tags using seed folders.

## Setup

1. Create environment and install dependencies:

```bash
py -3.11 -m venv .venv311
.venv311\Scripts\activate
python -m pip install --upgrade pip setuptools wheel
pip install -r v5.0/requirements.txt
```

2. Run from `v5.0` folder:

```bash
cd v5.0
python main.py
```

## Workspace root (single folder for artifacts)

Set `workspace.root` in `config.yaml` to one directory (for example a folder on an external drive). When non-empty, the loader resolves these **relative** paths under that root: `metadata.root_folder`, `faces.data_folder` / `faces.index_db` / `faces.untagged_root`, `output.output_folder`, `comparison.output_folder`, `thumbnails.output_folder`, `logging.file`, `processing.checkpoint_file`, and the pickle backup `records-backup.pkl` used by the app lives at `<workspace>/records-backup.pkl`. Paths that are already **absolute** in YAML are left as-is; clear or shorten them if you want everything to follow `workspace.root`. Photo sources (`scan.folder_path`, `organization.output_folder`, `faces.seed_root`) are not moved automatically.

## Menu

- **1. Metadata & Excel** — scan metadata, Excel, deletes, refresh Excel, **Update vault full paths** (fast reconcile; always available).
- **2. Organize library** — organize from Excel, convert structure, merge same-date folders.
- **3. Faces** — face index, people sync, seed refresh.

## Run sequence (menu steps)

1. `Generate / Refresh Metadata`  
   Scans `scan.folder_path` and writes JSON files under `<scan.folder_path>/metadata` (or `metadata.root_folder`).  
   When `duplicates.enabled` / `similar_detection.enabled` are on, duplicate and similar flags are computed during this step.

2. `Generate Excel from Metadata`  
   Reads JSON from `metadata.root_folder` (or `<scan.folder_path>/metadata` if `root_folder` is empty) and builds Excel. Use `metadata.load_recursive: true` only if JSON lives in subfolders under that root.  
   If `workflow.reset_dup_sim_for_excel` is `true`, `Duplicate?` / `Similar?` are reset to `No` in the workbook source before generation (use when you want a clean sheet from metadata).

3. `Apply Excel Delete Actions`  
   Deletes rows marked in Excel (`DELETE?`, `Duplicate?`, `Similar?`) and deletes linked metadata JSON.

4. `Organize Images + Metadata`  
   Organizes files by config. If `metadata.root_folder` is **set** (vault), JSON **stays** in that folder and `file.full_path` / `organized_path` in JSON are updated to the organized image path. If `root_folder` is **empty**, JSON is moved/copied next to the organized media under `.../metadata/`.

5. `Build/Update Face Index`  
   Builds face embedding DB from library source (`faces.library_source`).

6. `People Tag Sync + Untagged Samples`  
   Applies seed matches into metadata. Unknown persons get IDs; optional samples go to `faces.untagged_root` (see `faces.untagged_max_samples`, `faces.untagged_pick_best_quality`, `faces.untagged_export_mode`). Seed matches use `faces.similarity_threshold` or `faces.similarity_threshold_percent` (0–100, overrides the float).

7. `Seed Feedback Refresh`  
   After you rename unknown person folders and move them into seed root, run again to refresh metadata person labels.

8. `Refresh Final Excel`  
   Regenerate final Excel from updated metadata.

9. `Convert Folder Structure`  
   Re-layout an existing organized tree (e.g. flat → year); uses `ImageOrganizer` with current `organization.folder_structure`.

10. `Merge Same-Date Folders`  
    Combine duplicate date/month folders under the organized root when configured.

## Config Checklist (`v5.0/config.yaml`)

Set these before running:

- `scan.folder_path`: source photo/video folder.
- `organization.output_folder`: target organized folder.
- `organization.folder_structure`: `flat` / `year` / `year-month-date`.
- `organization.operation`: `copy` or `move`.
- `workspace.root`: optional single root for tool artifacts (metadata vault, face data, reports, comparisons, thumbnails, logs, checkpoint, `records-backup.pkl`). Empty = use each path in YAML as given.
- `metadata.root_folder`: optional absolute path = single shared metadata vault (good for multiple partial scans, one Excel). Empty = `<scan.folder_path>/metadata`.
- `metadata.load_recursive`: `true` to load all `*.json` under `root_folder` recursively.
- `metadata.library_root`: parent folder for partial scans (e.g. `folder1` with `folder2` + `folder3`). When set, JSON stores **`relative_path`** so you can move the tree to another disk by changing only this path.
- `metadata.store_relative_paths`: `true` (default when `library_root` is set) writes `file.relative_path` in vault JSON.
- `metadata.reconcile_prefer`: `organized` or `scan` — when both copies exist, reconcile updates to the preferred location.
- `metadata.auto_reconcile_paths`: `true` = auto-fix vault paths after delete, organize, convert, merge; `false` = off (menu **Update vault full paths** still runs).
- `metadata.reconcile_remove_missing`: `true` = delete vault JSON when the image file is gone everywhere.
- `metadata.update_strategy`: `skip_if_present` / `update_missing` / `refresh` / `full_overwrite`.
- `workflow.reset_dup_sim_for_excel`: if `true`, step 2 clears duplicate/similar columns before writing Excel.
- `duplicates.enabled` / `similar_detection.enabled`: control whether step 1 fills those signals.
- `faces.data_folder`: ensured on disk before face index build; you can point `faces.index_db` under this folder to keep face artifacts in one place.
- `faces.seed_root`: person seed folders (one person per subfolder).
- `faces.library_source`: `scan` or `organized` (should match where paths in metadata/index should resolve after organize).
- `faces.index_db`: SQLite file path for face index.
- `faces.similarity_threshold`: cosine 0.0–1.0; higher = stricter seed matches (e.g. `0.8`).
- `faces.similarity_threshold_percent`: optional 0–100; when set, overrides `similarity_threshold`.
- `faces.untagged_root`: output folder for unknown-person samples.
- `faces.untagged_max_samples`: max files per unknown id (default `1`).
- `faces.untagged_pick_best_quality`: when max is 1, replace export if a sharper / higher-quality image is seen later.
- `faces.untagged_export_mode`: `full` (copy file) or `face_crop` (largest OpenCV face JPEG; falls back to full).

## Notes

- `Media ID` is written in metadata/Excel to keep image-metadata linkage stable.
- **Person columns in Excel** (`Person Match?`, `Person Label`, etc.) are filled when you run step **2** or **8** by reading each file’s metadata JSON `person` object (written in step **6** / refreshed in step **7**). Steps **5** and **6** stay independent: the index (step 5) does not need to be rebuilt when you only regenerate Excel.
- Re-run step 5 after large organize/move operations if you want face index paths aligned to organized library.
- Use `organization.operation: copy` for first validation run.
