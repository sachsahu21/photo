# Image Scanner v4.1

Image Scanner v4.1 scans photos/videos, extracts metadata, detects duplicates, and organizes your media into date-based folders with Excel reporting.

## Highlights

- Reliable video metadata via ffprobe + MediaInfo + OpenCV fallback.
- Excel report with summary, duplicates, blurry, analytics, and optional sheets.
- Organization modes:
  - `flat`
  - `year`
  - `year-month-date`
- Folder conversion (Option 7) and same-date merge (Option 8).
- Screenshot separation with keyword + resolution logic.
- Unaligned folder support: keeps folder in place during conversion and can normalize count naming.

## Install

1. Create Python environment (recommended).
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Optional tools for best video metadata:
   - `ffprobe` (from FFmpeg) available in PATH
   - MediaInfo runtime (for `pymediainfo`)

## Run

From repository root:

```bash
python v4.1/main.py
```

## Main Menu

- `1` Scan & Extract  
  Scans configured source folder and builds records with metadata.

- `1b` Resume Excel  
  Regenerates report from backup records.

- `2` Delete Marked  
  Deletes files marked for deletion in Excel.

- `3` Organize  
  Organizes based on current config and scanned records.

- `4` Full (1>2>3)  
  Full flow: scan, optional delete, optional organize.

- `5` Web Dashboard  
  Launches Streamlit dashboard (if available).

- `6` Comparisons  
  Generates visual comparison pages from backup records.

- `7` Convert Folder Structure  
  Converts existing organized tree among `flat/year/year-month-date`.

- `8` Merge Same-Date Folders  
  Detects actual current structure from disk and merges duplicate-date folders.

## Folder Naming Rules

### Organized Date Folders

- Daily bucket: `yyyy-mm-dd-xxxxpic-[text]`
- Monthly bucket: `yyyy-mm-00-xxxxpic-[text]`

`xxxxpic` is updated from actual file count (including `videos/` child files where applicable).

### Unaligned Folders

If a folder does not match date/month formats during conversion:

- It is **not moved** to a misc bucket.
- It stays where it is.
- Name can be normalized with count injection, e.g.:
  - `2016-singapore` -> `2016-0123pic-singapore`

## Organization Structures

### 1) `flat`

```text
Organized/
  2024-04-13-0032pic-goa/
  2024-04-00-0110pic-family/
```

### 2) `year`

```text
Organized/
  2024/
    2024-04-13-0032pic-goa/
    2024-04-00-0110pic-family/
```

### 3) `year-month-date`

```text
Organized/
  2024/
    04-Apr/
      2024-04-13-0032pic-goa/
      2024-04-00-0110pic-family/
```

## Screenshot Detection

Screenshots are detected by:

1. Filename keyword match (`screenshot`, `capture`, etc.), then
2. Optional resolution fallback when EXIF is weak/missing.

`FB_IMG*` files are treated as non-screenshot photos to avoid false positives.

## Config Guide

Use `v4.1/config.yaml`.

Important keys:

- `scan.folder_path`: source folder to scan.
- `organization.output_folder`: where organized library is created.
- `organization.folder_structure`: `flat`, `year`, `year-month-date`.
- `organization.operation`: `copy` or `move`.
- `organization.conflict_resolution`: `rename`, `skip`, `overwrite`.
- `organization.separate_screenshots`: enable/disable screenshot split.
- `output.sheets.*`: enable/disable report sheets.

See inline comments in `config.yaml` for full examples.

## Conversion and Merge Workflow

Recommended sequence when changing structure:

1. Run Option `7` to convert structure.
2. Run Option `8` to merge same-date folders.
3. Verify count naming (`xxxxpic`) after merges.

Option 8 now uses detected on-disk structure so it works even if config still has older structure value.

If two folders share the same date prefix but have **different** non-empty text suffixes (for example `-singapore` vs `-malaysia`), Option 8 **does not merge** them so trips or locations stay separate.

## Troubleshooting

- Video metadata missing:
  - Ensure ffprobe is installed and available.
  - Install MediaInfo runtime for `pymediainfo`.
  - Confirm video extension is listed in `scan.extensions.videos`.

- Merge not finding folders:
  - Run Option 8 and confirm detected structure line.
  - Check folder names begin with expected date format.

- Screenshot misclassification:
  - Tune `organization.screenshot_keywords`.
  - Disable `organization.screenshot_detect_by_resolution` if needed.

- Slow scans:
  - Increase `processing.threads`.
  - Use `processing.fast_mode` where acceptable.

## Notes

- Keep backups before large move operations.
- Prefer `operation: copy` for first run validation.
- Excel and logs provide best traceability for cleanup decisions.
