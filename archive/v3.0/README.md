# Image Scanner v3.0

> **Historical version.** Use [v6.2](../v6.2/README.md) for new work.

---

## What this version does

Builds on v1 by adding comparison HTML pages, scan checkpointing, and a basic web dashboard.

### Features added over v1
- HTML comparison pages for duplicate and similar image groups
- Scan checkpoint: interrupted scans can be resumed
- Optional web dashboard (Streamlit-based, in `web/`)
- Comparison output saved to `comparisons/` folder

### Still not present
- Video metadata support (added in v4.0)
- Per-file JSON vault (added in v5.0)
- Organization engine (added in v4.0)
- Face tagging (added in v5.0)
- Quarantine workflow (added in v5.4)

---

## Quick start

```bash
cd v3.0
pip install -r requirements.txt
# Edit config.yaml: set scan.folder_path
python main.py
```
