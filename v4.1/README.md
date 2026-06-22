# Image Scanner v4.1

> **Historical version.** Use [v6.2](../v6.2/README.md) for new work.

---

## What this version does

Version bump and minor stabilisation on top of v4.0. Same feature set as v4.0.

### Features (same as v4.0)
- Recursive scan of images and videos with full metadata extraction
- Blur detection, duplicate detection, similar-image detection
- Organization engine: copy/move into flat / year / year-month-date folders
- Screenshot detection and separation
- Excel workbook: All Images, Blurry, Duplicates, Quality Report, Analytics, Summary
- Excel-driven delete workflow
- Folder structure conversion and same-date folder merge
- Scan checkpoint/resume
- HTML comparison pages
- Optional thumbnails and web dashboard

### Still not present
- Per-file JSON vault (added in v5.0)
- Face tagging (added in v5.0)
- Quarantine workflow (added in v5.4)

---

## Quick start

```bash
cd v4.1
pip install -r requirements.txt
# Edit config.yaml: set scan.folder_path and organization.output_folder
python main.py
```
