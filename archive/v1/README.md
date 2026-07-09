# Image Scanner v1

> **Historical version.** Use [v6.2](../v6.2/README.md) for new work.

---

## What this version does

The first working release. Scans a folder of images, extracts EXIF metadata, scores blur, detects exact duplicates, and writes a multi-sheet Excel report.

### Features
- Recursive image scan (JPEG, PNG, BMP, GIF)
- EXIF extraction: date taken, camera model, GPS, dimensions
- Blur scoring via Laplacian variance
- MD5-based exact duplicate detection with best-copy selection
- Excel workbook with sheets: All Images, Blurry, Duplicates, Summary, Analytics

### What is not here yet
- Video metadata support
- Per-file JSON vault (added in v5.0)
- Organization engine (added in v4.0)
- Face tagging (added in v5.0)
- Quarantine workflow (added in v5.4)
- Checkpoint/resume (added in v3.x)

---

## Quick start

```bash
cd v1
pip install -r requirements.txt
# Edit config.yaml: set scan.folder_path
python main.py
```

Choose option `1` to scan, then `1b` to export Excel.
