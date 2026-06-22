# Image Scanner v5.3

> **Historical version.** Use [v6.2](../v6.2/README.md) for new work.

---

## What this version does

Stabilisation and bug-fix release on top of v5.2. Same feature set as v5.2.

### Features (same as v5.2)
- Numbered grouped menu (options 11–44)
- Per-file JSON vault under `workspace.root/metadata/`
- Metadata-driven Excel export and library organization
- Duplicate and blur detection
- People tagging with seed photos
- Vault path reconcile and deduplication
- Scan checkpoint/resume
- Test suite

### Still not present
- Quarantine workflow (added in v5.4)
- Enrich metadata option (added in v5.4)
- Scan progress XLSX report (added in v5.4)
- Fresh restart option (added in v5.4)

---

## Quick start

```bash
cd v5.3
pip install -r requirements.txt
# Edit config.yaml: set workspace.root, scan.folder_path, organization.output_folder
python main.py
```
