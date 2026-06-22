# Image Scanner v5.1

> **Historical version.** Use [v6.2](../v6.2/README.md) for new work.

---

## What this version does

Stabilisation release on top of v5.0. Same feature set as v5.0.

### Features (same as v5.0)
- Per-file JSON vault — one `.json` per photo/video under `workspace.root/metadata/`
- Metadata-driven Excel export and organization
- People tagging with seed photos
- Vault path reconcile and deduplication
- Scan checkpoint/resume

### Still not present
- Numbered grouped menu (added in v5.2)
- Quarantine workflow (added in v5.4)
- Enrich metadata option (added in v5.4)
- Scan progress report (added in v5.4)

---

## Quick start

```bash
cd v5.1
pip install -r requirements.txt
# Edit config.yaml: set workspace.root, scan.folder_path, organization.output_folder
python main.py
```
