# Image Scanner v5.0

> **Historical version.** Use [v6.2](../v6.2/README.md) for new work.

---

## What this version does

Introduces the metadata-first workflow: instead of holding everything in memory, each photo gets its own JSON record on disk (the "vault"). All subsequent steps — Excel export, organization, deletion — read from the vault rather than re-scanning.

### Features added over v4.x
- Per-file JSON vault under `workspace.root/metadata/` — one `.json` per photo/video
- Metadata-driven Excel export (reads vault, not memory)
- Metadata-driven organization (reads vault for date and path info)
- People tagging: place seed photos in `seed/<person_name>/`, run face matching
- Vault path reconcile: update records after files are moved
- Vault deduplication: remove duplicate JSON entries

### Menu options
```
1   Build / Refresh Metadata Vault
1b  Export Excel from Vault
2   Apply deletions from Excel
3   Organise library from Excel
4   Build / Update Face Index
5   Sync people tags
6   Refresh seed feedback
0   Exit
```

### Still not present
- Numbered grouped menu (added in v5.2)
- Quarantine workflow (added in v5.4) — deletes are permanent in this version
- Enrich metadata option (added in v5.4)
- Scan progress report (added in v5.4)

---

## Quick start

```bash
cd v5.0
pip install -r requirements.txt
# Edit config.yaml: set workspace.root, scan.folder_path, organization.output_folder
python main.py
```

Key config settings:
```yaml
workspace:
  root: "C:\\path\\to\\workspace"
scan:
  folder_path: "C:\\path\\to\\photos"
organization:
  output_folder: "C:\\path\\to\\organized"
```
