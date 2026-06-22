# Image Scanner v3.2

> **Historical version.** Use [v6.2](../v6.2/README.md) for new work.

---

## What this version does

Stabilisation and bug-fix release on top of v3.1. Same feature set as v3.1.

### Features (same as v3.1)
- Recursive image scan with EXIF, blur, and duplicate detection
- HTML comparison pages
- Thumbnail generation
- Scan checkpoint/resume
- Multi-sheet Excel report
- Optional web dashboard

### Still not present
- Video metadata support (added in v4.0)
- Per-file JSON vault (added in v5.0)
- Organization engine (added in v4.0)
- Face tagging (added in v5.0)

---

## Quick start

```bash
cd v3.2
pip install -r requirements.txt
# Edit config.yaml: set scan.folder_path
python main.py
```
