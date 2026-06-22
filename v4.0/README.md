# Image Scanner v4.0

> **Historical version.** Use [v6.2](../v6.2/README.md) for new work.

---

## What this version does

Major release adding video metadata extraction and a full organization engine.

### Features added over v3.x
- Video metadata via ffprobe + MediaInfo + OpenCV fallback
- Organization engine: copies or moves photos into date-based folders
  - Folder modes: `flat`, `year`, `year-month-date`
  - Configurable conflict resolution: rename / skip / overwrite
  - `day_threshold` to choose between daily and monthly folders
- Screenshot detection and separation into a dedicated subfolder
- Folder structure conversion (reorganize an existing library)
- Same-date folder merge
- Excel-driven delete workflow (mark rows in Excel → delete files)
- Improved multi-sheet Excel: Quality Report, Analytics sheets added

### Menu options (run `python main.py`)
```
1   Scan & extract metadata
1b  Resume from backup / export Excel
2   Delete flagged files from Excel
3   Organize library
4   Convert folder structure
5   Merge duplicate date folders
```

### Still not present
- Per-file JSON vault (added in v5.0)
- Face tagging (added in v5.0)
- Quarantine workflow (added in v5.4)

---

## Quick start

```bash
cd v4.0
pip install -r requirements.txt
# Edit config.yaml: set scan.folder_path and organization.output_folder
python main.py
```

Key config settings:
```yaml
scan:
  folder_path: "C:\\path\\to\\photos"
organization:
  output_folder: "C:\\path\\to\\organized"
  operation: "copy"          # copy | move
  folder_structure: "year"   # flat | year | year-month-date
```
