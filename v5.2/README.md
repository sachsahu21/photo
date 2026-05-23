# Image Scanner v5.2 – Documentation

## Overview
This repository provides a command‑line tool for scanning, analysing, organising, and tagging large photo & video collections. The workflow is driven by a **menu** (displayed in `main.py`) that invokes a set of **task functions**.  Each task performs a clearly defined step – from scanning the source folder, generating reports, to building a face index.

---
## Menu Options (what you see when you run `python main.py`)

| # | Menu entry | What it does | Implementation |
|---|------------|--------------|----------------|
| **11** | `Analyze scan folder and file counts` | Walks the scan folder, gathers per‑folder statistics (size, image/video counts) and writes an optional Excel/JSON report. | [task_analyze_folders](file:///C:/Users/ISSUser/Desktop/Sachin/git/photo/v5.2/main.py#L690-L693) |
| **12** | `Build / Refresh Metadata Vault` | Scans every file, detects duplicates/similar images, stores rich metadata JSON records in the vault. | [task_1](file:///C:/Users/ISSUser/Desktop/Sachin/git/photo/v5.2/main.py#L692-L694) |
| **13** | `Reconcile & Dedupe Vault Paths` | Updates each record’s `full_path` to reflect the current filesystem layout **and** removes duplicate vault rows. | [task_reconcile_paths](file:///C:/Users/ISSUser/Desktop/Sachin/git/photo/v5.2/main.py#L694-L696) |
| **14** | `Delete duplicate metadata` | Traverses the metadata vault and deletes any JSON entries that refer to the same file (hash‑based). | [task_dedupe_vault](file:///C:/Users/ISSUser/Desktop/Sachin/git/photo/v5.2/main.py#L696-L698) |
| **15** | `Remove untagged sample folders` | Deletes empty *untagged* sample directories created by the people‑tag workflow. | [task_cleanup_untagged](file:///C:/Users/ISSUser/Desktop/Sachin/git/photo/v5.2/main.py#L698-L700) |
| **16** | `Export Scanned‑Pending CSV` | Runs the custom script `src/generate_report.py` to produce `reports/scanned_pending_report.csv`, a flat view of all scanned files and their pending status. | [generate_report.main](file:///C:/Users/ISSUser/Desktop/Sachin/git/photo/v5.2/src/generate_report.py) |
| **21** | `Export Excel from Vault` | Loads the metadata vault and writes a multi‑sheet Excel workbook (`reports/global_scan_stats.xlsx`). | [task_1b](file:///C:/Users/ISSUser/Desktop/Sachin/git/photo/v5.2/main.py#L704-L706) |
| **22** | `Execute deletions from Excel` | Reads the Excel workbook, finds rows marked for deletion, removes the corresponding files and vault entries, then reconciles the vault. | [task_2](file:///C:/Users/ISSUser/Desktop/Sachin/git/photo/v5.2/main.py#L706-L712) |
| **31** | `Organise library (Excel‑driven)` | Uses the Excel workbook to move/rename files into the organised output folder and updates the vault. | [task_3](file:///C:/Users/ISSUser/Desktop/Sachin/git/photo/v5.2/main.py#L714-L718) |
| **32** | `Convert folder layout` | Re‑structures the organised tree (`flat`, `year`, or `year‑month‑date`). | [task_convert_structure](file:///C:/Users/ISSUser/Desktop/Sachin/git/photo/v5.2/main.py#L720-L724) |
| **33** | `Merge duplicate date folders` | Detects multiple folders that share the same date and merges their contents. | [task_merge_dates](file:///C:/Users/ISSUser/Desktop/Sachin/git/photo/v5.2/main.py#L576-L584) |
| **34** | `Refresh folder image counts` | Walks the organised output and writes a count file so UI tools can display number of images per folder. | [task_update_counts](file:///C:/Users/ISSUser/Desktop/Sachin/git/photo/v5.2/main.py#L601-L608) |
| **41** | `Build / Update Face Index` | Extracts facial embeddings for every image and stores them in a SQLite DB (`workspace.root/face_data`). | [task_5](file:///C:/Users/ISSUser/Desktop/Sachin/git/photo/v5.2/main.py#L464-L477) |
| **42** | `Sync people tags & export untagged samples` | Matches faces against known people, tags metadata, and optionally exports a configurable number of untagged sample images for manual review. | [task_6](file:///C:/Users/ISSUser/Desktop/Sachin/git/photo/v5.2/main.py#L479-L519) |
| **43** | `Refresh known‑match feedback` | Re‑tags only the already‑known matches (no untagged export) – useful after improving the face model. | [task_7](file:///C:/Users/ISSUser/Desktop/Sachin/git/photo/v5.2/main.py#L525-L545) |
| **0** | `Exit` | Terminates the program. |

---
## Core Functions (internal helpers)

| Function | Purpose | Key Modules Used |
|----------|---------|-----------------|
| `setup_log` | Initialise the logging system according to `config.yaml` – creates log file under `workspace.root/logs`. | `logging` |
| `save_bk` / `load_bk` | Simple pickle‑based backup of the full list of metadata records (used when a scan crashes). | `pickle`, `src.workspace_paths.records_backup_path` |
| `task_1` | Primary scan – builds the metadata vault, runs duplicate detection, optional similar‑image detection, and writes the vault to disk. | `src.scanner.ImageScanner`, `src.duplicate_handler.DuplicateHandler`, `src.metadata_store.MetadataStore` |
| `task_1b` | Excel export – loads the vault (or backup), optionally dedupes, and writes the Excel workbook via `src.excel_writer.ExcelWriter`. | `src.excel_writer.ExcelWriter` |
| `task_2` | Excel‑driven delete – parses the workbook, collects rows with a *Delete* flag, deletes files and JSON metadata, then runs a dedupe + reconcile. | `openpyxl`, `src.vault_maintenance.delete_media_cascade` |
| `task_3` | Library organisation – reads the Excel workbook, moves/renames files into the organised output folder, updates the vault paths. | `src.organizer.ImageOrganizer` |
| `task_reconcile_paths` | Re‑computes every record’s `full_path` based on the current filesystem and removes duplicate JSON rows. | `src.metadata_reconcile.reconcile_vault_paths` |
| `task_dedupe_vault` | Straight‑forward deduplication of the metadata vault (hash‑based). | `src.vault_maintenance.dedupe_vault` |
| `task_cleanup_untagged` | Deletes empty sample folders created by the people‑tag workflow. | `src.vault_maintenance.cleanup_untagged_orphans` |
| `task_convert_structure` | Re‑layouts the organised output folder (flat, year, or year‑month‑date). | `src.organizer.ImageOrganizer.convert_structure` |
| `task_merge_dates` | Merges folders that share the same date into a single folder. | `src.organizer.ImageOrganizer.merge_duplicate_dates` |
| `task_update_counts` | Writes a `picture_counts.json` (or similar) file for each folder in the organised tree. |
| `task_5` | Build or update the face index DB. |
| `task_6` | Sync people tags & optionally export untagged samples. |
| `task_7` | Refresh only known‑match feedback (no untagged export). |

---
## `config.yaml` – Detailed Options

The configuration file lives at the project root (`config.yaml`). Below is a concise guide to every top‑level section and the most useful fields.

### Workspace
```yaml
workspace:
  root: "C:\Users\ISSUser\Desktop\Sachin\hdd\pic\artifacts"
```
*All generated artefacts (metadata JSON, Excel workbooks, face index, logs, etc.) are stored under this directory.*

### Scan
```yaml
scan:
  folder_path: "C:\Users\ISSUser\Desktop\Sachin\hdd\pic\Sachin\sach_unorganized\test2"
  recursive: true
  extensions:
    images: [jpg, jpeg, png, gif, bmp, tiff, heic, raw, ...]
    videos: [mp4, mov, avi, mkv, ...]
```
Defines the **source** that will be walked during a metadata scan. `recursive` toggles sub‑folder traversal.

### Organization (output library)
```yaml
organization:
  output_folder: "C:\Users\ISSUser\Desktop\Sachin\hdd\organized"
  folder_structure: "flat"   # flat | year | year-month-date
  operation: "copy"          # copy keeps originals, move relocates them
  conflict_resolution: "overwrite"  # behaviour when a filename already exists
  day_threshold: 60          # threshold for daily vs. monthly folders
  use_exif_date: true
```
Controls how the library is physically organised after option 31.

### Metadata (vault)
```yaml
metadata:
  subfolder: metadata
  library_root: ""               # optional base path for relative paths
  store_relative_paths: true
  reconcile_prefer: "organized"   # which path wins during reconciliation
  load_recursive: false
  auto_reconcile_paths: true
  reconcile_remove_missing: true
  dedupe_on_reconcile: true
  dedupe_before_excel: true
  dedupe_after_scan: true
  dedupe_prefer: organized
  update_strategy: "update_missing"
  schema_version: "1.0"
```
All records are JSON files under `workspace.root/metadata`. The flags control automatic cleaning and path reconciliation.

### Faces (optional)
```yaml
faces:
  enabled: false
  data_subfolder: face_data
  index_db_filename: face_index.sqlite
  untagged_subfolder: untagged_people
  export_untagged: true
  untagged_max_samples: 1
  untagged_pick_best_quality: true
  similarity_threshold: 0.35
```
Enables facial‑recognition features (building an index, syncing tags, exporting untagged samples).

### Output (reports)
```yaml
output:
  subfolder: reports
  filename_prefix: "image-scan"
  sheets:
    all_images: true
    duplicates: true
    similar_images: true
    summary: true
    quality_report: true
    analytics: true
```
Controls the Excel workbook generation (sheets that are included, filename prefix, etc.).

### Thumbnails (optional)
```yaml
thumbnails:
  enabled: false
  size: [150, 100]
  embed_in_excel: false
```
If enabled, small preview images are generated for each file and optionally embedded in the Excel workbook.

### Logging
```yaml
logging:
  level: "INFO"
  subfolder: logs
  log_filename: image-scanner.log
  console: true
```
All log output is written to `workspace.root/logs`.

### Processing
```yaml
processing:
  threads: 4               # parallel workers for scanning
  checkpoint_enabled: true   # write JSON checkpoint every N files
  checkpoint_interval: 100
  fast_mode: false
```
Fine‑tunes performance and checkpointing behaviour.

### Workflow flags (affect Excel generation)
```yaml
workflow:
  reset_dup_sim_for_excel: false
  excel_exclude_missing_files: false
  excel_include_file_exists_column: true
```
These toggle how the Excel writer treats missing files and whether it clears duplicate/similar flags before export.

---
## Getting Started
1. **Adjust `config.yaml`** – ensure `workspace.root` points to a writable location and `scan.folder_path` points at your unorganised photos.
2. Run the tool:
   ```bash
   python main.py
   ```
3. Follow the on‑screen menu.  Typical first‑time flow:
   - `12` – build the metadata vault.
   - `21` – export the Excel workbook.
   - `31` – organise the library based on the Excel.
   - `41` – (optional) build a face index.
4. Use the *Help* section of the menu (or run the script with `--help` if you add argparse) to view the short descriptions again.

---
## Extending / Modifying
- **Add new menu items** – edit the `while True:` loop in `main.py` to print a line and add an `elif` block that calls a new function.
- **Plug‑in new processing steps** – implement them in `src/` and import them at the top of `main.py`.
- **Configuration extensions** – add entries under `config.yaml` and access them via `config.get('<section>.<key>')`.

---
## License
MIT – see the `LICENSE` file in the repository.

---
*This README was generated automatically to reflect the current code base and configuration.  Keep it in sync whenever you add or rename menu options or configuration fields.*
