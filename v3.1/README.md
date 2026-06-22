# Image Scanner v3.1

> **Historical version.** Use [v6.2](../v6.2/README.md) for new work.

---

## What this version does

Adds thumbnail generation on top of v3.0.

### Features added over v3.0
- Thumbnail generation: small preview JPEGs written to `thumbnails/`
- Optional embedding of thumbnails in Excel

### Still not present
- Video metadata support (added in v4.0)
- Per-file JSON vault (added in v5.0)
- Organization engine (added in v4.0)
- Face tagging (added in v5.0)

---

## Quick start

```bash
cd v3.1
pip install -r requirements.txt
# Edit config.yaml: set scan.folder_path
python main.py
```
