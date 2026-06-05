# Image Scanner v5.3 Menu And Duplicate Guide

This document explains what each `python main.py` menu option does and how duplicate tagging works in v5.3.

## Duplicate Tagging Rule

v5.3 marks a file as duplicate only when two or more scanned records have the same non-empty `md5_hash`.

In code terms:

```text
same md5_hash in 2 or more records => same duplicate group
```

That means duplicate detection is based on exact file bytes, not filename, folder, date, resolution, face count, or visual similarity.

## Why A Photo May Look "Not Duplicate" But Shows Duplicate

The current duplicate code does this:

- Groups records by exact `md5_hash`.
- If a group has 2 or more files, every file in that group gets `is_duplicate = YES`.
- One file in the group is selected as the best keeper.
- The keeper still shows `Duplicate? = YES`, because it is part of a duplicate group.
- The keeper gets `is_best_in_group = Yes`, `recommendation = Keep (Best)`, and `delete_flag = No`.
- The other files get `recommendation = Delete (Duplicate)` and `delete_flag = Yes`.

So when reviewing Excel, do not delete based only on `Duplicate? = YES`. Check these columns together:

- `Duplicate?`
- `Dup Group`
- `Is Best In Group`
- `Recommendation`
- `DELETE?`
- `MD5 Hash`
- `Full Path`

## What Is Not Used For Duplicate Matching

These fields do not decide whether something is a duplicate:

- Filename
- Folder path
- Date taken
- File modified time
- Size alone
- Resolution
- Face count
- Blur or quality score
- Similarity threshold

`duplicates.similarity_threshold` in `config.yaml` is not used by `DuplicateHandler` in v5.3. Near-match image comparison is handled separately by `similar_detection`, not duplicate detection.

## Common Reasons For Confusing Duplicate Results

1. Same photo copied into different folders  
   The paths look different, but the file bytes are identical, so the MD5 hash is the same.

2. Keeper row also says duplicate  
   This is expected. The keeper belongs to the duplicate group but is not marked for deletion.

3. Old metadata still has earlier duplicate flags  
   If files were moved/deleted or checkpoints skipped a fresh scan, old JSON may still contain previous duplicate fields. Use `21` for a fresh build, or `24` for a full metadata restart when you want to rebuild from scratch.

4. Similar-looking photos are not duplicates  
   Burst photos, resized images, edited images, WhatsApp compressed copies, or screenshots may look similar but usually have different MD5 hashes. They should be handled by `similar_detection`, not duplicates.

5. Exact same bytes but different metadata expectation  
   If two files are byte-for-byte identical, the tool treats them as duplicates even if they came from different folders or have different names.

## Duplicate Columns In Excel

The All Images sheet previously showed duplicate-related columns twice:

- `Duplicate?`
- `Dup Group`
- `Best?`
- `Recommendation`

That was redundant. The sheet now keeps one duplicate-status set near the start of the row and keeps `DELETE? (Yes/No)` near the file path/hash columns.

The Duplicates sheet is the safest place to review duplicates because it shows only duplicate-group rows and includes:

- `Group`
- `Best?`
- `Recommendation`
- `DELETE? (Yes/No)`
- `MD5 Hash`
- `Full Path`

Duplicate group labels are stable hash-based labels:

```text
MD5-<first12chars>
```

The metadata also stores:

```text
duplicate_type = exact_md5
```

## Which Excel Column Moves Files To Quarantine

Menu option `32. Apply Excel delete actions` moves files to quarantine only when the row has:

```text
DELETE? (Yes/No) = Yes
```

It does not act just because `Duplicate? = YES` or `Similar? = YES`.

This distinction is important because the keeper/original row in a duplicate group also has `Duplicate? = YES`, but it should normally have:

```text
DELETE? (Yes/No) = No
Recommendation = Keep (Best)
```

## Why Duplicate Info Is Stored In Metadata

Duplicate details are stored in each metadata JSON so reports and later workflows do not need to recompute duplicate groups every time.

The metadata stores fields such as:

- `duplicate.is_duplicate`
- `duplicate.duplicate_group`
- `duplicate.duplicate_type`
- `duplicate.is_best_in_group`
- `duplicate.recommendation`
- flat compatibility fields in `record`

This lets Excel generation, comparison reports, analytics, and delete workflows read the duplicate decision directly from the vault.

## What Happens When You Add One New Duplicate Later

After a scan, v5.3 now rechecks duplicates across the full metadata vault, not only the files scanned in the current run.

So if the original photo is already in metadata and you add one duplicate copy later:

1. The new file is scanned.
2. Its metadata JSON is written.
3. The tool loads all metadata records from the vault.
4. Duplicate detection runs across the complete vault.
5. Both the original and the newly added duplicate metadata JSON are updated with the same duplicate group.
6. The best row is marked `Keep (Best)`.
7. The other duplicate row is marked `Delete (Duplicate)` and `DELETE? = Yes`.

If results still look stale, use `24. Fresh restart metadata vault`, then run `21` and `31` again.

## Main Menu Options

### 11. Analyze scan folder and file counts

Walks the configured `scan.folder_path` and reports folder-level totals:

- Folder count
- Total size
- Image count
- Video count
- Other file count

It also writes an analysis report under the workspace folder.

### 12. Export Scanned-Pending report

Compares files found in `scan.folder_path` against the global checkpoint.

It exports a report showing:

- Total files found
- Files already processed
- Files still pending
- Pending size

This uses the configured global checkpoint file under `workspace.root/checkpoints`.

It saves both CSV and XLSX files under:

```text
workspace.root/folder_analysis
```

The files include a timestamp:

```text
scanned_pending_report_YYYYMMDD_HHMMSS.csv
scanned_pending_report_YYYYMMDD_HHMMSS.xlsx
```

## Metadata Operations

### 21. Build / Refresh Metadata Vault

This is the main scan.

It scans configured photos/videos and writes per-file JSON metadata under:

```text
workspace.root/metadata
```

It collects:

- File paths and sizes
- Hashes such as MD5 and SHA256
- Dates
- EXIF metadata
- Image dimensions
- Blur/quality information
- Face count/category when enabled
- Duplicate groups
- Similar groups when enabled

It also saves metadata in batches based on:

```yaml
processing.metadata_flush_interval
```

After the scan, it verifies whether scanned files have metadata JSON and offers repair/report options if anything is missing.

### 22. Reconcile Vault Paths

Updates existing metadata JSON paths after files were moved or organized.

Use this when:

- Files were organized into a new folder
- Metadata still points to an old path
- Excel says files are missing but they exist elsewhere

It can also dedupe duplicate JSON rows for the same media file.

### 23. Clean / Dedupe Metadata files

Removes duplicate metadata JSON records that point to the same actual file or same hash.

This cleans the metadata vault. It does not delete photos.

### 24. Fresh restart metadata vault

Moves generated metadata state to quarantine so the next scan starts clean.

It moves only generated artifacts:

- Metadata folder
- Checkpoints folder
- `records-backup.pkl`

It does not delete photos from:

- `scan.folder_path`
- `organization.output_folder`

It requires this exact typed confirmation:

```text
DELETE METADATA
```

Use this when old duplicate/similar/metadata results are confusing and you want a clean rebuild.

After quarantine, it recreates empty metadata/checkpoint folders and starts option `21` automatically.

### 25. Enrich existing metadata

Loads existing metadata JSON and fills missing newer schema fields without doing a full fresh start.

It ignores the global checkpoint and works from existing metadata records.

Use this after adding new metadata fields, when old JSON needs to be upgraded to the newer schema.

## Excel And Data

### 31. Generate/Refresh Excel

Loads records from the metadata vault and creates an Excel workbook.

The workbook includes configured sheets such as:

- All Images
- Blurry Images
- Duplicates
- Similar Images
- Summary
- Quality report
- Analytics

### 32. Apply Excel delete actions

Reads the Excel workbook and moves files marked for deletion into quarantine.

It only moves rows where the `DELETE? (Yes/No)` column is set to `Yes`, `true`, or `1`.

By default, use the Duplicates sheet. The tool can also apply Similar Images, All Images, or all available sheets when selected.

Files and matching metadata JSON are moved under:

```text
workspace.root/quarantine/delete-actions-YYYYMMDD-HHMMSS
```

It writes a manifest with the original path, quarantined path, metadata path, media id, MD5, duplicate group, and sheet name.

## Library Organization

### 41. Organize library from Excel

Reads the Excel workbook and copies or moves files into the configured organized folder.

The behavior depends on config values such as:

```yaml
organization.output_folder
organization.operation
organization.folder_structure
organization.conflict_resolution
```

### 42. Convert folder structure

Changes an already organized folder layout.

Supported structures:

- `flat`
- `year`
- `year-month-date`

### 43. Merge duplicate dates

Finds multiple organized folders that represent the same date and merges them.

Use this after organization if date folders were split or duplicated.

### 44. Update picture counts

Refreshes per-folder image counts in the organized library.

This helps UI or folder-based workflows show counts consistently.

## Faces And People

### 51. Build/Update face index

Builds or updates the face index database under:

```text
workspace.root/face_data
```

This is used for person matching and future face-search workflows.

### 52. Sync people tags

Matches indexed faces against seed people and updates metadata JSON with known or unknown person information.

It can also export untagged samples for manual review.

### 53. Refresh seed feedback

Refreshes known person matches without exporting new untagged samples.

Use this after improving seed photos or face settings.

### 54. Clean up untagged sample folders

Removes stale or empty untagged sample folders.

It is a cleanup task for face/person workflows.

## 0. Exit

Closes the menu.

## Practical Duplicate Review Workflow

1. Run `21. Build / Refresh Metadata Vault`.
2. Run `31. Generate/Refresh Excel`.
3. Open the Duplicates sheet.
4. Sort by `Dup Group`.
5. For each group, keep the row with `Recommendation = Keep (Best)`.
6. Only rows with `DELETE? = Yes` are intended for quarantine.
7. If duplicate results look stale, run `24. Fresh restart metadata vault`, then run `21` and `31` again.
