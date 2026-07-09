# Image Scanner v5.4

A command-line tool for scanning, analysing, organising, and face-tagging large photo and video collections. Runs locally — no internet, no subscription required.

---

## Quick Start

### 1. Edit `config.yaml` — set three required paths

```yaml
workspace:
  root: "C:\\path\\to\\your\\workspace"   # tool's working folder (empty dir)

scan:
  folder_path: "C:\\path\\to\\your\\photos"  # where your photos are

organization:
  output_folder: "C:\\path\\to\\organized"    # where sorted photos will go
```

### 2. Run

```bash
python main.py
```

### 3. Typical first-time workflow

```
21  →  Build metadata vault   (scan all photos)
31  →  Generate Excel report
32  →  Quarantine duplicates  (after marking DELETE?=YES in Excel)
24  →  Dedupe Vault           (clean up orphaned metadata after quarantine)
31  →  Refresh Excel          (rebuild report from updated vault)
41  →  Organize into year/date folders
```

> **After every option 32 (quarantine), always run 24 → 31 in that order to keep the vault clean.**

---

## Menu Reference

```
========================================================
  1. ANALYSIS
  --------------------------------------------------------
  11.  Analyze folder & file counts
  12.  Export scan progress report (5-sheet XLSX)

  2. METADATA
  --------------------------------------------------------
  21.  Build / Refresh Metadata Vault  ← start here
  22.  Enrich existing metadata
  23.  Reconcile vault paths
  24.  Dedupe metadata files
  25.  Fresh restart (clear vault)

  3. EXCEL & DATA
  --------------------------------------------------------
  31.  Generate / Refresh Excel
  32.  Apply delete actions (quarantine)

  4. LIBRARY
  --------------------------------------------------------
  41.  Organize from Excel             ← selective by directory
  42.  Convert folder structure
  43.  Merge duplicate dates
  44.  Update picture counts

  5. FACES & PEOPLE
  --------------------------------------------------------
  51.  Build / Update face index
  52.  Sync people tags
  53.  Refresh seed feedback
  54.  Cleanup untagged samples

   0.  Exit
========================================================
```

---

## All Options — What Each One Does

### Section 1 — Analysis

| Option | Name | What it does | When to use |
|--------|------|-------------|-------------|
| **11** | Analyze folder & file counts | Walks the scan folder and prints a summary: total files, by extension, by subfolder, estimated scan time | Before first scan to understand library size |
| **12** | Export scan progress report | Writes a 5-sheet XLSX to `reports/` showing Total / Scanned / Pending per directory, with file lists | Track progress during large multi-session scans |

### Section 2 — Metadata

| Option | Name | What it does | When to use |
|--------|------|-------------|-------------|
| **21** | Build / Refresh Metadata Vault | Scans every photo and video — extracts EXIF, detects blur, detects duplicates (MD5), optionally detects faces. Saves one `.json` per file in `metadata/`. Supports checkpoint/resume | First time, or after adding new photos |
| **22** | Enrich existing metadata | Re-scans files that already have a vault record but are missing specific fields (e.g. blur score, GPS). Non-destructive — only fills empty fields | When you enable a new analysis feature (e.g. blur detection) on an existing library |
| **23** | Reconcile vault paths | Detects vault records whose `full_path` no longer exists and tries to match them to moved files by filename+size. Updates paths in-place | After manually moving or renaming folders outside the tool |
| **24** | Dedupe metadata files | Removes duplicate `.json` files in the vault (same MD5, multiple records). Also purges orphaned records pointing to missing files if you confirm | **Run after every option 32 quarantine** |
| **25** | Fresh restart (clear vault) | Moves the entire vault to quarantine and starts from zero. Requires typing `DELETE METADATA` to confirm | Fixing a corrupt vault or starting completely clean |

### Section 3 — Excel & Data

| Option | Name | What it does | When to use |
|--------|------|-------------|-------------|
| **31** | Generate / Refresh Excel | Writes a multi-sheet Excel workbook to `reports/` from current vault records. Sheets: Summary, All Images, Blurry Images, Duplicates, Quality Report, Analytics, Clusters, Scan Summary, By Directory, Pending Files, Scanned Files | After every vault update; after running option 24 |
| **32** | Apply delete actions (quarantine) | Reads an Excel file, finds all rows where `DELETE?=YES`, moves those image files to `quarantine/`. Uses O(1) path-hash lookup — fast regardless of library size. **Does not rebuild the vault** — run 24 → 31 after | After reviewing duplicates in Excel and marking files for deletion |

> **Option 32 recommended order:** `32` → `24` → `31`
>
> - **32** moves the files (fast)
> - **24** removes the now-orphaned metadata JSON files
> - **31** rebuilds the Excel with the cleaned vault

### Section 4 — Library

| Option | Name | What it does | When to use |
|--------|------|-------------|-------------|
| **41** | Organize from Excel | Reads the Excel report, copies or moves photos into date-tree folders (`year/` or `year/month/date/`). Lets you filter by specific source directories | Final step to sort a library into a clean folder structure |
| **42** | Convert folder structure | Converts an existing `flat` folder layout to `year-month-date` subfolders (or vice versa) without needing an Excel file | Restructuring an already-organized library |
| **43** | Merge duplicate dates | Finds `YYYY-MM-DD` folders with identical dates across different parent folders and merges their contents | Cleaning up after multiple partial organize runs |
| **44** | Update picture counts | Renames date folders to include the photo count suffix (e.g. `2023-05-14 042pic`) | After adding or removing photos from organized folders |

### Section 5 — Faces & People

| Option | Name | What it does | When to use |
|--------|------|-------------|-------------|
| **51** | Build / Update face index | Detects faces in all photos, generates embeddings, saves to SQLite (`face_data/`). Required before people tagging | First time, or after adding many new photos |
| **52** | Sync people tags | Matches face embeddings against your seed photos (`seed/<name>/`). Tags matching records in the vault, exports unknowns to `untagged_people/` for manual review | After building the face index and adding seed photos |
| **53** | Refresh seed feedback | Re-runs the matching step only (no re-export). Fast way to retag after adding new seed photos | After adding new seeds to `seed/` without re-running full export |
| **54** | Cleanup untagged samples | Deletes `untagged_people/` folders for people you have already fully tagged in the vault | After completing a round of manual face identification |

---

## Workspace Layout

All tool-generated data lives under `workspace.root`. Your photos are never modified unless you explicitly run an organize or quarantine action.

```
workspace/
├── metadata/           ← per-file JSON records (one .json per photo)
├── face_data/          ← face index SQLite + embeddings
├── seed/               ← your seed photos: seed/<person_name>/*.jpg
├── untagged_people/    ← unknown faces exported for manual review
├── reports/            ← Excel workbooks
├── folder_analysis/    ← scan progress XLSX reports
├── comparisons/        ← HTML duplicate comparison pages
├── logs/               ← image-scanner.log
├── checkpoints/        ← scan resume checkpoints
├── quarantine/         ← files moved by delete/fresh-restart
└── records-backup.pkl  ← pickle backup of latest scan data
```

---

## Key config.yaml Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `organization.operation` | `copy` | `copy` keeps originals; `move` relocates them |
| `organization.folder_structure` | `year` | `flat` / `year` / `year-month-date` |
| `organization.conflict_resolution` | `overwrite` | `rename` / `skip` / `overwrite` |
| `scan.recursive` | `true` | Scan subfolders |
| `duplicates.enabled` | `true` | MD5-based duplicate detection |
| `blur_detection.enabled` | `true` | Laplacian blur scoring |
| `faces.enabled` | `true` | Face detection and indexing |
| `similar_detection.enabled` | `false` | Perceptual hash similarity (slow) |
| `processing.threads` | `4` | Parallel scan workers |
| `processing.fast_mode` | `false` | Skip slower analysis steps |
| `metadata.update_strategy` | `update_missing` | `skip_if_present` / `update_missing` / `refresh` / `full_overwrite` |

---

## Excel Output Sheets

Generated by option 31. Sheets are toggled via `output.sheets.*` in config.

| Sheet | Contents |
|-------|---------|
| Summary | Library statistics |
| All Images | Every photo/video with full metadata |
| Blurry Images | Photos below the blur threshold |
| Duplicates | Duplicate groups — mark DELETE?=YES to quarantine |
| Quality Report | Quality score distribution |
| Analytics | Storage by year/type/camera |
| Clusters | Color-based clusters (if enabled) |
| Scan Summary | Total / Scanned / Pending counts + completion % + pending size |
| By Directory | Per-folder: total, scanned, pending, pending size, % done |
| Pending Files | Every unscanned file with directory, filename, full path, size |
| Scanned Files | Every processed file with directory, filename, full path |

---

## Face Tagging Workflow

1. Place seed photos in `workspace/seed/<person_name>/` (e.g. `seed/Sachin/photo1.jpg`)
2. Run **51** → Build face index
3. Run **52** → Sync people tags
4. Check `workspace/untagged_people/` → identify unknown faces → add as new seeds
5. Run **53** → Refresh seed feedback (fast re-tag without full re-export)

---

## v5.4 vs v6.2 — Which Version to Use

| Feature | v5.4 | v6.2 |
|---------|------|------|
| Menu options | 11, 12, 21–25, 31–32, 41–44, 51–54 | 11–12, 21–23, 31–32, 41–44, 51–54 |
| Enrich metadata (option 22) | ✅ Fill only missing fields, checkpoint/resume | ❌ Removed |
| Fresh restart (option 25) | ✅ Clear vault with confirmation | ❌ Removed |
| Quarantine (option 32) | ✅ Fast (O(1) path-hash, no vault scan) | ✅ Simpler, no sheet selection |
| Duplicate detection | ✅ MD5 + `_recompute_duplicate_metadata` | ✅ MD5 |
| Vault dedupe | ✅ Manifest-tracked, purge orphans | ✅ Simpler |
| Path reconciliation | ✅ Full reconcile + purge orphans | ✅ Basic |
| Checkpoint / resume for large scans | ✅ | ✅ |
| Sheet selection in option 32 | ✅ Pick Duplicates / Similar / All Images / All | ❌ Processes all sheets |
| Directory filtering in option 41 | ✅ Choose specific source dirs | ❌ Processes all |
| Scan progress report (option 12) | ✅ 5-sheet XLSX | ✅ |
| Face tagging (51–54) | ✅ | ✅ |

### Recommendation

**Use v5.4** if you:
- Have a large library and need to scan in multiple sessions (checkpoint/resume on option 22)
- Want to enrich an existing vault without re-scanning everything
- Need to select which Excel sheet to apply delete actions from (Duplicates vs All Images)
- Want to filter by source directory when organizing (option 41)
- Need the fresh-restart option (25) to nuke and rebuild the vault

**Use v6.2** if you:
- Are starting fresh and want a simpler, smaller codebase
- Don't need the enrich or fresh-restart workflows
- Prefer fewer options with less complexity

**Bottom line: v5.4 has more features and is the better choice for managing an existing large library.**

---

## Documentation

| File | Audience |
|------|---------|
| [USER_GUIDE.md](USER_GUIDE.md) | First-time / non-technical users — all options explained in plain English + config walkthrough |
| [DEVELOPER_REFERENCE.md](DEVELOPER_REFERENCE.md) | Developers — all task functions, source modules, config keys, extension points |
| [CHANGELOG.md](CHANGELOG.md) | Version history |

---

## Requirements

```
pip install openpyxl pillow opencv-python face_recognition
```

Optional (enables additional features):
```
pip install streamlit msal  # web dashboard + OneDrive scanning
```

---

## License

MIT — see the `LICENSE` file in the repository.
