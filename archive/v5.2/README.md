# Image Scanner v5.2

> **Historical version.** Use [v6.2](../v6.2/README.md) for new work.

---

## What this version does

Introduces the numbered grouped menu (11–43), a test suite, and comprehensive config documentation.

### Features added over v5.1
- Numbered grouped menu — options organized into sections: Analysis, Metadata, Excel, Library, Faces
- Test suite in `tests/`
- Full config.yaml documentation
- `MENU_AND_DUPLICATE_GUIDE.md` — guide to duplicate handling options

### Menu options
```
11  Analyze folder & file counts
12  Export Scanned-Pending CSV

21  Build / Refresh Metadata Vault
22  Execute deletions from Excel    <- permanent delete (not quarantine)
31  Export Excel from Vault
32  Convert folder structure
33  Merge duplicate dates
34  Refresh folder image counts

41  Organise library from Excel
42  Build / Update Face Index
43  Sync people tags & export untagged
44  Refresh seed feedback

0   Exit
```

### Still not present
- Quarantine workflow (added in v5.4) — deletes in this version are permanent
- Enrich metadata option (added in v5.4)
- Scan progress XLSX report (added in v5.4)
- Fresh restart option (added in v5.4)

---

## Quick start

```bash
cd v5.2
pip install -r requirements.txt
# Edit config.yaml: set workspace.root, scan.folder_path, organization.output_folder
python main.py
```
