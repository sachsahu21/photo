# Image Scanner v5.4 — Developer Reference

---

## Project Structure

```
v5.4/
├── main.py                     Entry point and task orchestration
├── config.yaml                 Runtime configuration
├── src/
│   ├── config_manager.py       YAML config loader with dot-notation access
│   ├── scanner.py              Core file scanner and EXIF extractor
│   ├── metadata_store.py       JSON vault read/write/upsert
│   ├── duplicate_handler.py    MD5-based duplicate detection and scoring
│   ├── organizer.py            File copy/move into date-based folder tree
│   ├── excel_writer.py         openpyxl multi-sheet Excel workbook generator
│   ├── face_indexer.py         Face embedding extraction + SQLite index
│   ├── face_detector.py        OpenCV face detection (Haar cascade / DNN)
│   ├── people_sync.py          Match faces to seeds, tag metadata records
│   ├── metadata_reconcile.py   Path reconciliation across vault records
│   ├── vault_maintenance.py    Dedupe, quarantine, cleanup helpers
│   ├── generate_report.py      Scan progress CSV + XLSX report generator
│   ├── analytics.py            Storage and date analytics aggregator
│   ├── similar_detector.py     Perceptual hash + histogram similarity
│   ├── blur_detector.py        Laplacian variance blur scorer
│   ├── auto_tagger.py          MobileNet image classification (optional)
│   ├── geocoder.py             Offline GPS → place name resolution
│   ├── image_clusterer.py      Color-histogram clustering
│   ├── comparison_generator.py HTML side-by-side duplicate viewer
│   ├── thumbnail_generator.py  JPEG thumbnail creation
│   ├── parallel_processor.py   Thread-pool task runner
│   ├── video_metadata.py       Video duration/codec metadata extractor
│   ├── checkpoint_manager.py   Per-scan checkpoint (resume on crash)
│   ├── global_checkpoint.py    Global processed-file checkpoint
│   ├── metadata_paths.py       Path helpers for vault JSON layout
│   ├── workspace_paths.py      Resolve workspace sub-path constants
│   ├── utils.py                Shared utilities (date parsing, etc.)
│   └── cloud_scanner.py        Cloud scan stub (not yet implemented)
├── web/
│   └── streamlit_app.py        Streamlit dashboard skeleton (in progress)
├── USER_GUIDE.md
├── DEVELOPER_REFERENCE.md
├── README.md
└── CHANGELOG.md
```

---

## Architecture Overview

```
config.yaml
    │
    ▼
ConfigManager          ← dot-notation access to all settings
    │
    ├── ImageScanner   ← walks scan folder, extracts EXIF / video metadata,
    │       │             runs blur/face/similar detection per file
    │       └── batch_callback → MetadataStore.upsert_records (every N files)
    │
    ├── DuplicateHandler  ← groups records by md5_hash, scores and marks best
    │
    ├── MetadataStore     ← JSON vault: one .json per media file
    │       └── metadata-index.json  ← in-memory rebuild index
    │
    ├── ExcelWriter       ← reads vault records → openpyxl workbook
    │
    ├── ImageOrganizer    ← copies/moves files into date-tree output folder
    │
    └── FaceIndexer       ← face_recognition embeddings → SQLite DB
            └── PeopleSync  ← seed matching → metadata tag updates
```

### Data flow (standard first-run)

```
scan folder
    → ImageScanner.scan()
    → MetadataStore.upsert_records()      ← vault JSON written per batch
    → DuplicateHandler.mark_duplicates()  ← MD5 groups + best selection
    → MetadataStore.upsert_records()      ← vault updated with dup flags
    → ExcelWriter.write()                 ← Excel workbook
    → [user reviews Excel]
    → quarantine_media_cascade()          ← moves flagged files + JSON
    → ImageOrganizer.organize()           ← copies to date tree
```

---

## Task Function Reference (main.py)

### Menu-driven tasks

| Function | Menu Option | Description |
|----------|-------------|-------------|
| `task_analyze_folders(config, logger)` | 11 | Walks scan folder, gathers per-folder stats (size, image count, video count). Writes Summary + Details + Hierarchy + MaxFolder sheets to `workspace/folder_analysis/*.xlsx`. |
| `task_1b(config, logger)` | 31 | Loads vault records, optionally dedupes, runs `StorageAnalytics`, writes Excel workbook via `ExcelWriter`. Returns the Excel path. Saves it to `last_excel_path` for reuse. |
| `task_1(config, logger)` | 21 | Full scan: `ImageScanner.scan()` → duplicate detection → optional similar detection → `MetadataStore.upsert_records()` → post-scan dedupe → missing metadata check. Returns metadata root path. |
| `task_enrich_metadata(config, logger)` | 22 | Re-scans files already in vault. Uses `_merge_missing_record()` to fill only empty fields. Shows `Progress: X / N enriched` every batch. |
| `task_reconcile_paths(config, logger)` | 23 | Calls `reconcile_vault_paths()` to fix stale `full_path` entries after file moves. |
| `task_dedupe_vault(config, logger)` | 24 | Calls `dedupe_vault()` to remove duplicate vault JSON entries. |
| `task_fresh_restart_metadata(config, logger)` | 25 | Validates quarantine targets, moves metadata + checkpoints + backup to `workspace/quarantine/`, creates manifest, then calls `task_1()`. Requires user to type `DELETE METADATA`. |
| `task_2(ep, config, logger)` | 32 | Reads Excel workbook, collects rows where DELETE? = YES, calls `quarantine_media_cascade()`, then recomputes duplicates + reconcile. |
| `task_3(ep, config, logger)` | 41 | Reads Excel, shows source directories for selective filtering, calls `ImageOrganizer.organize()`. After organize: `auto_reconcile_if_enabled()` + `dedupe_vault()`. |
| `task_convert_structure(config, logger)` | 42 | Calls `ImageOrganizer.convert_structure()` to re-layout organized tree. |
| `task_merge_dates(config, logger)` | 43 | Auto-detects or accepts structure override, calls `ImageOrganizer.merge_duplicate_dates()`. |
| `task_update_counts(config, logger)` | 44 | Calls `ImageOrganizer.update_all_pic_counts()`. |
| `task_5(config, logger)` | 51 | Calls `FaceIndexer.build_or_update_index(recursive=True)`. Reports files processed and faces indexed. |
| `task_6(config, logger)` | 52 | `FaceIndexer.find_person()` → `sync_people_tags()` with untagged export enabled. |
| `task_7(config, logger)` | 53 | Same as task_6 but `seed_only_refresh=True` and `export_untagged=False` — only re-tags known matches. |
| `task_cleanup_untagged(config, logger)` | 54 | `cleanup_untagged_orphans()` — removes empty folders from `untagged_people/`. |
| `task_8(config, logger)` | (internal alias) | Alias for `task_1b`. Used by some legacy call sites. |

---

### Internal Helper Functions

| Function | Purpose |
|----------|---------|
| `setup_log(config)` | Configures `logging` with file handler (`workspace/logs/`) and optional console handler. Level from `logging.level`. |
| `save_bk(records, config)` | Pickle-serialises the full record list to `workspace/records-backup.pkl`. Fallback if scan crashes. |
| `load_bk(config)` | Deserialises records from the backup file. Returns `None` if file does not exist. |
| `_norm_path(value)` | Lowercases and resolves a path string for case-insensitive set membership. |
| `_record_path_set(records)` | Returns a set of normalised `full_path` values from a record list. |
| `_with_scan_defaults(records)` | Ensures `delete_flag`, `is_duplicate`, `duplicate_group`, `is_best_in_group`, `recommendation`, `is_similar`, `similar_group`, `similar_score`, `similar_methods` are present on every record. |
| `_recompute_duplicate_metadata(config)` | Loads full vault, runs `DuplicateHandler.mark_duplicates()`, upserts result. Used after quarantine to re-rank remaining files. |
| `_make_batch_writer(config)` | Returns `(on_record, flush)` closures. `on_record` accumulates records and flushes every `metadata_flush_interval` files. Used as `batch_callback` in scanner. |
| `_export_missing_metadata_report(config, missing_paths)` | Writes a CSV of paths with no vault JSON to `workspace/reports/missing-metadata-*.csv`. |
| `_missing_metadata_paths(records, config)` | Compares scanned record paths against vault; returns paths that have no JSON entry. |
| `_handle_missing_metadata(missing_paths, config, logger)` | Interactive menu: rescan missing files only / export report / ignore. |
| `_merge_missing_record(existing, fresh)` | Merges two record dicts, preferring existing non-empty values. Updates `last_seen_at` from fresh. Used by Enrich. |
| `_missing_value(value)` | Returns True for None, `''`, `'unknown'`, `'none'`, `'no exif'`. |
| `_path_under(path, root)` | Returns True if `path` is inside `root` (safe path check for quarantine). |
| `_generated_quarantine_target(path, workspace_root, protected_roots)` | Returns resolved path only if it is inside workspace and NOT inside scan/organized folders. Prevents accidental data loss. |
| `_vault_line(config)` | Returns the workspace / metadata vault / library root summary lines shown in the menu header. |

---

## Source Module Descriptions

### `src/config_manager.py`
Loads and validates `config.yaml`. Provides dot-notation access via `config.get('section.key', default)`. Resolves all subfolders relative to `workspace.root` so no other module does path math. Exposes `artifact_summary()` for menu display.

Key methods:
- `ConfigManager()` — loads config, resolves workspace subpaths
- `config.get(key, default)` — dot-notation accessor
- `config.to_dict()` — returns raw dict for passing to constructors
- `config.validate()` — checks required keys exist and paths are valid
- `config.artifact_summary()` — returns dict with workspace, metadata, etc.

---

### `src/scanner.py` — `ImageScanner`
Core file scanner. Walks the scan folder using `pathlib.rglob`, reads EXIF via `Pillow`, video metadata via `ffprobe`/`src/video_metadata.py`, computes MD5 hash, runs `BlurDetector`, `FaceDetector`, `AutoTagger`, `Geocoder` per file.

Key methods:
- `scan(folder_path, batch_callback=None)` — full folder scan, returns list of records
- `scan_files(file_list, batch_callback=None)` — scan a specific list of paths
- `analyze_folders(base_path)` — returns per-folder stats dict (used by option 11)

Each record is a dict with keys including:
`media_id`, `filename`, `full_path`, `relative_path`, `extension`, `file_type`, `size_mb`, `width`, `height`, `date_taken`, `file_modified`, `md5_hash`, `quality_score`, `is_blurry`, `blur_score`, `face_count`, `has_exif`, `exif_make`, `exif_model`, `gps_lat`, `gps_lon`, `location`, `file_exists`, `last_seen_at`, `metadata_json_path`

---

### `src/metadata_store.py` — `MetadataStore`
Manages the JSON vault. Each media file has one corresponding `.json` file under `workspace/metadata/`. Also maintains `metadata-index.json` as a fast lookup index.

Key methods:
- `load_records(exclude_missing=True)` — loads all vault JSONs, optionally skipping records where file no longer exists
- `upsert_records(records)` — insert or update records (matched by `media_id` or `full_path`)
- `rebuild_index()` — regenerates `metadata-index.json`
- `root` — Path to the metadata subfolder

---

### `src/duplicate_handler.py` — `DuplicateHandler`
Groups records by `md5_hash`, selects the best copy using a configurable scoring function, marks all others for deletion.

Key methods:
- `find_duplicates(records)` → `{group_label: [indices]}`
- `select_best(records, indices)` → index of best record
- `mark_duplicates(records)` → mutates records with `is_duplicate`, `duplicate_group`, `duplicate_type`, `master_media_id`, `is_best_in_group`, `recommendation`, `delete_flag`
- `_score(record)` → numeric score used for selection (quality × 100 + resolution/1M × 10 + timestamp/1e8 + size_mb)

---

### `src/organizer.py` — `ImageOrganizer`
Copies or moves files into a date-based output tree. Date source priority: `manual_date_override` → `effective_organize_date` → `date_taken` → `file_modified`.

Key methods:
- `organize(records)` → list of move results with `status`
- `convert_structure(source, target_structure, output_folder)` — re-layouts existing tree (class method)
- `merge_duplicate_dates(source, structure)` — merges same-date folders (class method)
- `update_all_pic_counts(source)` — writes `_count.txt` files per folder (class method)
- `detect_structure(source)` — detects current layout type (class method)

Configuration keys used: `organization.output_folder`, `organization.operation`, `organization.folder_structure`, `organization.conflict_resolution`, `organization.day_threshold`, `organization.use_exif_date`, `organization.video_subfolder`, `organization.separate_screenshots`

---

### `src/excel_writer.py` — `ExcelWriter`
Writes the multi-sheet Excel workbook from a list of metadata records.

Sheets written (controlled by `output.sheets.*`):
- **All Images** — full record list
- **Duplicates** — `is_duplicate == 'YES'` rows
- **Similar Images** — `is_similar == 'YES'` rows
- **Blurry Images** — `is_blurry == True` rows
- **Summary** — high-level statistics block
- **Quality Report** — quality scores breakdown
- **Analytics** — storage / date analytics (from `StorageAnalytics`)
- **Clusters** — clustering results (if enabled)

Key methods:
- `write(records, scan_folder, analytics_data=None)` → path to saved Excel file

---

### `src/face_indexer.py` — `FaceIndexer`
Extracts 128-dimension face embeddings using the `face_recognition` library (dlib under the hood). Stores embeddings + metadata in a SQLite database (`face_index.sqlite`).

Key methods:
- `build_or_update_index(recursive=True)` → `(files_processed, faces_indexed)`
- `find_person(seed_folder=None)` → list of `{path, person, distance}` matches
- `index_db` → Path to SQLite file

Config keys: `faces.data_subfolder`, `faces.index_db_filename`, `faces.seed_root`, `faces.similarity_threshold`, `faces.max_results`, `faces.library_source`

---

### `src/people_sync.py` — `sync_people_tags`
Matches `FaceIndexer.find_person()` results back to metadata records and writes `people_tags` into the vault. Optionally exports untagged face samples to `untagged_people/` for manual review.

Signature:
```python
sync_people_tags(
    records, matches, untagged_root,
    export_untagged=True,
    seed_only_refresh=False,
    untagged_max_samples=1,
    untagged_pick_best_quality=True,
    untagged_export_mode='full',
    config=None,
) -> (known_count, unknown_count)
```

---

### `src/metadata_reconcile.py`
Fixes stale `full_path` values in vault records after files are moved. Searches both `scan.folder_path` and `organization.output_folder`.

Key functions:
- `reconcile_vault_paths(cfg)` → stats dict with counts of updated/removed records
- `auto_reconcile_if_enabled(cfg, context)` — calls reconcile only if `metadata.auto_reconcile_paths: true`

---

### `src/vault_maintenance.py`
Collection of vault housekeeping functions.

Key functions:
- `dedupe_vault(cfg, quiet=False)` — removes duplicate JSON files from the vault
- `quarantine_media_cascade(cfg, targets)` — moves photo files + vault JSONs to quarantine, removes face index rows, writes manifest
- `quarantine_generated_targets(cfg, safe_targets, action, manifest_prefix)` — generic quarantine mover for task_25 (fresh restart)
- `cleanup_untagged_orphans(cfg)` — deletes empty `untagged_people/` subdirectories
- `save_last_excel_path(config, path)` / `load_last_excel_path(config)` — persist last Excel path between sessions
- `rebuild_vault_index(cfg)` — regenerates `metadata-index.json`

---

### `src/generate_report.py`
Produces the scan progress report (option 12).

Reads:
- All files matching extensions in `scan.folder_path`
- `workspace/global_checkpoint.json` to get the processed set

Writes:
- `workspace/folder_analysis/scanned_pending_report_<ts>.csv` — flat status list (backward-compatible)
- `workspace/folder_analysis/scanned_pending_report_<ts>.xlsx` — multi-sheet workbook:
  - **Summary** — total/scanned/pending counts + sizes + directory counts
  - **By Directory** — per-folder breakdown with % done
  - **Pending Files** — directory, filename, full path, size
  - **Scanned Files** — directory, filename, full path
  - **All Files** — combined status list

---

### `src/similar_detector.py` — `SimilarDetector`
Computes perceptual hashes (ahash, phash, dhash) and optionally color histogram + SIFT features. Groups images where hash distance falls below configured thresholds.

Key methods:
- `compute_hashes(records)` → records with hash fields added
- `find_similar(records)` → `{group_id: [indices]}`
- `mark_similar(records, groups)` → mutates records with `is_similar`, `similar_group`, `similar_score`, `similar_methods`

---

### `src/analytics.py` — `StorageAnalytics`
Aggregates vault records into summary statistics for the Excel Analytics sheet.

Key method:
- `analyze(records)` → dict with keys: `total_size_gb`, `by_year`, `by_type`, `by_camera`, `duplicate_waste_gb`, etc.

---

### `src/workspace_paths.py`
Single source of truth for derived workspace paths.

Key function:
- `records_backup_path(config)` → `workspace/records-backup.pkl`

---

## Config Key Reference

All keys accessed via `config.get('section.key', default)`.

### `workspace`
| Key | Type | Description |
|-----|------|-------------|
| `workspace.root` | str | **Required.** Absolute path to workspace folder. All artifacts are stored here. |

### `scan`
| Key | Type | Description |
|-----|------|-------------|
| `scan.folder_path` | str | **Required.** Source folder to scan. |
| `scan.recursive` | bool | Scan subfolders. Default: `true` |
| `scan.extensions.images` | list | Image extensions to include. |
| `scan.extensions.videos` | list | Video extensions to include. |

### `organization`
| Key | Type | Description |
|-----|------|-------------|
| `organization.output_folder` | str | **Required.** Destination for organized files. |
| `organization.folder_structure` | str | `flat` / `year` / `year-month-date` |
| `organization.operation` | str | `copy` or `move` |
| `organization.conflict_resolution` | str | `rename` / `skip` / `overwrite` |
| `organization.day_threshold` | int | Files/day above this get a daily folder, else monthly. |
| `organization.use_exif_date` | bool | Prefer EXIF date over file modified date. |
| `organization.video_subfolder` | bool | Put videos in a `video/` subfolder. |
| `organization.separate_screenshots` | bool | Move screenshots to `screenshots/` subfolder. |

### `metadata`
| Key | Type | Description |
|-----|------|-------------|
| `metadata.subfolder` | str | Subfolder under workspace for vault JSONs. Default: `metadata` |
| `metadata.library_root` | str | Optional: parent of multiple scan locations for relative paths. |
| `metadata.store_relative_paths` | bool | Store paths relative to `library_root`. |
| `metadata.reconcile_prefer` | str | `organized` or `scan` — which path wins on reconcile. |
| `metadata.auto_reconcile_paths` | bool | Auto-reconcile after organize/quarantine/convert. |
| `metadata.reconcile_remove_missing` | bool | Delete vault entry if file is missing everywhere. |
| `metadata.dedupe_before_excel` | bool | Dedupe vault before writing Excel. |
| `metadata.dedupe_after_scan` | bool | Dedupe vault after scan completes. |
| `metadata.update_strategy` | str | `skip_if_present` / `update_missing` / `refresh` / `full_overwrite` |

### `faces`
| Key | Type | Description |
|-----|------|-------------|
| `faces.enabled` | bool | Enable face detection and indexing. |
| `faces.data_subfolder` | str | Subfolder for face index SQLite. Default: `face_data` |
| `faces.seed_root` | str | Subfolder under workspace for seed photos. |
| `faces.target_person` | str | If set, `find_person()` searches for this person only. |
| `faces.library_source` | str | `scan` or `organized` — which folder the face index searches. |
| `faces.similarity_threshold` | float | Face match distance threshold (0–1). Lower = stricter. |
| `faces.max_results` | int | Max matches returned per search. |
| `faces.export_untagged` | bool | Export unknown face samples. |
| `faces.untagged_max_samples` | int | Max sample photos per unknown person to export. |
| `faces.untagged_pick_best_quality` | bool | Prefer highest quality sample when exporting. |
| `faces.untagged_export_mode` | str | `full` = full image, `crop` = face crop only. |

### `output`
| Key | Type | Description |
|-----|------|-------------|
| `output.subfolder` | str | Subfolder for Excel reports. Default: `reports` |
| `output.filename_prefix` | str | Prefix for Excel filenames. |
| `output.sheets.*` | bool | Toggle individual Excel sheets on/off. |

### `processing`
| Key | Type | Description |
|-----|------|-------------|
| `processing.threads` | int | Worker threads for parallel scanning. |
| `processing.fast_mode` | bool | Skip slower analysis (similar, clustering). |
| `processing.checkpoint_enabled` | bool | Write scan checkpoint for resume. |
| `processing.checkpoint_interval` | int | Files between checkpoint writes. |
| `processing.metadata_flush_interval` | int | Records per vault batch write. |
| `processing.skip_video_hash` | bool | Skip MD5 hashing for video files (faster). |

### `duplicates`
| Key | Type | Description |
|-----|------|-------------|
| `duplicates.enabled` | bool | Run duplicate detection. |
| `duplicates.hash_algorithm` | str | `md5` (only supported value currently). |
| `duplicates.selection_criteria` | list | Scoring dimensions: `quality`, `resolution`, `date`, `size`. |

### `similar_detection`
| Key | Type | Description |
|-----|------|-------------|
| `similar_detection.enabled` | bool | Run perceptual hash similarity. Slow. |
| `similar_detection.ahash` / `phash` / `dhash` | bool | Which hashes to compute. |
| `similar_detection.ahash_threshold` etc. | int | Max hamming distance to count as similar. |

### `blur_detection`
| Key | Type | Description |
|-----|------|-------------|
| `blur_detection.enabled` | bool | Compute Laplacian blur score. |
| `blur_detection.threshold` | int | Score below this → marked blurry. |

### `workflow`
| Key | Type | Description |
|-----|------|-------------|
| `workflow.reset_dup_sim_for_excel` | bool | Clear duplicate/similar flags before Excel write. |
| `workflow.excel_exclude_missing_files` | bool | Omit records where file no longer exists from Excel. |
| `workflow.excel_include_file_exists_column` | bool | Add a File Exists? column to the Excel. |

### `quarantine`
| Key | Type | Description |
|-----|------|-------------|
| `quarantine.subfolder` | str | Subfolder under workspace for quarantined files. |
| `quarantine.preserve_relative_paths` | bool | Replicate folder structure inside quarantine. |
| `quarantine.manifest_prefix` | str | Prefix for manifest JSON filenames. |

---

## Adding a New Menu Option

1. Write a `task_<name>(config, logger)` function in `main.py`.
2. Add a print line in the menu display block (the `while True:` loop).
3. Add an `elif ch == 'NN':` branch calling your function.
4. If it needs new config keys, add them to `config.yaml` with sensible defaults and document them above.

---

## Selective Directory Organize (Option 41)

Option 41 now shows source directories from the Excel and allows filtering before organizing.

**Implementation location:** `task_3()` in `main.py`, lines after record loading.

**How it works:**
1. After loading records from Excel, builds a `dir_map` (directory → file count).
2. Displays numbered list of directories.
3. User enters comma-separated numbers (e.g. `1,3,5`) or presses Enter for all.
4. Records are filtered to only selected directories before calling `ImageOrganizer.organize()`.

**To extend:** The filter could be pre-applied at the config level by adding an `organization.include_dirs` list config key and reading it in `task_3` before displaying the menu.

---

## Scan Progress Report (Option 12 / generate_report.py)

The XLSX report produces five sheets. The `scanned` set is computed as `all_files ∩ processed` (intersection with actual filesystem files) rather than using the raw checkpoint set. This prevents ghost entries from inflating scanned counts when files were deleted after scanning.

**By Directory sheet:** Per-parent-directory breakdown. The `% Done` column = `scanned / total × 100`. Useful for targeting specific folders in a large partial scan.

---

## Known Limitations

- `src/cloud_scanner.py` is a stub — `scan()` returns `[]`. Microsoft Graph API integration is the planned implementation.
- `web/streamlit_app.py` is a skeleton with placeholder metrics.
- `similar_detection` is slow at scale (O(n²) hash comparison capped by `max_compare_per_image`).
- Face recognition requires the `dlib` wheel, which on Windows needs Visual C++ build tools or a pre-built wheel.

---

*Developer Reference for Image Scanner v5.4. For user-facing documentation see [USER_GUIDE.md](USER_GUIDE.md).*
