# Photo — Image Scanner

**Scan · Analyze · Organize · Report**

A local-first Python toolkit to manage large photo and video collections. No internet required, no subscription, no cloud lock-in.

---

## Use v6.2 — the recommended version

```
cd v6.2
python main.py
```

All previous versions (v1 through v5.4) are kept for reference but are superseded by v6.2.

---

## Why v6.2?

| Improvement | Detail |
|-------------|--------|
| **Metadata vault** | Every photo gets its own `.json` record — scan once, query forever without rescanning |
| **Menu-driven workflow** | Numbered groups (Analysis / Metadata / Excel / Library / Faces) — do exactly the step you need |
| **Non-destructive deletes** | Nothing is permanently deleted; files go to a timestamped quarantine folder you can inspect and restore |
| **Checkpointing** | Scan interrupted? Resume exactly where you left off |
| **Vault path reconcile** | Moved files around? Option 22 re-links vault records to new locations without a full rescan |
| **Face tagging** | Build a face index, match against your seed photos, tag metadata — all offline |
| **Scan progress report** | Option 12 generates a 5-sheet XLSX showing per-folder scan completion, pending files, and sizes |
| **Workspace isolation** | All generated files (reports, face index, logs, quarantine) live in one folder you choose — photos are never touched unless you explicitly organize or quarantine |
| **Clean config** | Three required settings to get started; everything else has safe defaults |

---

## Version history at a glance

| Version | What it added |
|---------|--------------|
| v1 | Basic scan, EXIF extraction, blur detection, duplicate detection, 5-sheet Excel |
| v3.0–v3.2 | Comparison HTML pages, thumbnail generation, web dashboard |
| v4.0–v4.1 | Video metadata (ffprobe + MediaInfo), organization engine, screenshot separation |
| v5.0–v5.1 | Metadata-first workflow — per-file JSON vault, metadata-driven Excel and organization |
| v5.2–v5.3 | Full numbered menu (11–43), test suite, comprehensive config documentation |
| v5.4 | Quarantine workflow, enrich metadata option, scan progress sheets, face tag workflow |
| **v6.2** | Streamlined menu (11–54), vault path reconcile improvements, cleaner first-run experience |

---

## Quick start (v6.2)

### 1. Install dependencies

```bash
cd v6.2
pip install -r requirements.txt
```

### 2. Set three paths in `v6.2/config.yaml`

```yaml
workspace:
  root: "C:\\path\\to\\workspace"       # empty folder — all tool output goes here

scan:
  folder_path: "C:\\path\\to\\photos"   # your photo library

organization:
  output_folder: "C:\\path\\to\\organized"  # where sorted photos land
```

### 3. Run

```bash
python main.py
```

### 4. Typical first-time flow

```
21  →  Build metadata vault   (scan all photos, takes a while first time)
31  →  Generate Excel report
32  →  Apply delete actions    (quarantine duplicates marked in Excel)
41  →  Organize into folders   (copy/move into year/date tree)
```

---

## OneDrive users

If your photos are on OneDrive with Files On-Demand enabled, files must be locally synced before scanning. Either mark folders as "Always keep on this device" or reduce `processing.threads` to `1–2` to avoid flooding the OneDrive sync client.

---

## Requirements

Python 3.8+ and the packages in `v6.2/requirements.txt`. Core deps: `pillow`, `openpyxl`, `opencv-python`. Face tagging additionally needs `facenet-pytorch` and `torch`.
