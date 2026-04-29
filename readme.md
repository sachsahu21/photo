<div align="center">

# 📸 Photo Library Scanner

**Scan · Analyse · Organise · Report**

*A professional-grade Python CLI that transforms a chaotic photo library into a clean, dated folder structure — with blur detection, duplicate removal, and a rich Excel report.*

<br/>

[![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Pillow](https://img.shields.io/badge/Pillow-EXIF%20%26%20Metadata-11557c?style=for-the-badge)](https://pillow.readthedocs.io)
[![OpenCV](https://img.shields.io/badge/OpenCV-Blur%20Detection-5C3EE8?style=for-the-badge&logo=opencv&logoColor=white)](https://opencv.org)
[![openpyxl](https://img.shields.io/badge/openpyxl-Excel%20Reports-217346?style=for-the-badge)](https://openpyxl.readthedocs.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

<br/>

```
╔══════════════════════════════════════════════╗
║   Photo Library Scanner  v2.1 (recommended) ║
║   Scan · Detect · Organise                  ║
╚══════════════════════════════════════════════╝
```

</div>

---

## ✨ What It Does

| Feature | Detail |
|---|---|
| 🔍 **Deep Scan** | Recursively walks every subfolder for images & videos |
| 🧠 **EXIF Extraction** | Date taken, camera make/model, focal length, aperture, ISO, GPS |
| 🌫️ **Blur Detection** | Laplacian variance scoring → Very Blurry / Blurry / Fair / Sharp |
| 🔗 **Duplicate Detection** | MD5 content hashing — finds identical files across different folders |
| 🏆 **Best-Copy Selection** | Auto-picks the highest-quality copy from each duplicate group |
| 📁 **Smart Organisation** | `YYYYMMDD` folder if ≥ 60 pics that day, `YYYYMM00` bucket otherwise |
| 📊 **Excel Report** | 5-7 sheet workbook with filters, colour coding, and delete flags (depends on config) |
| 🗑️ **Safe Deletion** | Mark files in Excel → script deletes only what you approved |

---

## 🗂️ Codebase Layout (variants)

This repo contains multiple “generations” of the same photo scanner pipeline. Pick the folder you want to run:

```
photo/
├── opus2-streamlit/          (v2.0)  CLI + Streamlit dashboard
│   ├── main.py
│   ├── config.yaml
│   ├── requirements.txt
│   ├── src/
│   └── web/streamlit_app.py
├── opus2-streamlit _v2/     (v2.1)  Recommended CLI + Streamlit + comparison pages
│   ├── main.py
│   ├── config.yaml
│   ├── requirements.txt
│   ├── src/
│   └── web/streamlit_app.py
├── pic_manage/               (v1.0.0) Earlier/scaled-down scanner
│   ├── main.py
│   ├── config.yaml
│   ├── requirements.txt
│   └── src/
├── claude_v1/                Prototype
└── z.old_code/              Archived experiments (v1/v2/v3)
```

### What the pipeline does (shared across variants)
Scan a folder tree → extract EXIF/metadata → blur score → duplicate grouping + best-copy selection → write an Excel report → optionally delete marked files → organize (copy/move) into date-based folders (`YYYYMMDD` / `YYYYMM00`).

### Outputs you can expect
- Excel reports in the configured `output_folder` (defaults to `./reports`)
- Logs in the configured `logging.file`
- Backups for resuming mid-scan (pickle file, see “Task 1”)
- Duplicate comparison HTML pages when enabled (v2.1: `./comparisons/DUP_*.html`)

---

## ⚡ Quick Start

### 1 — Choose a variant & set up a virtual environment

```bash
# Recommended (latest) variant:
cd "opus2-streamlit _v2"

python -m venv venv
venv\Scripts\activate

# Older alternatives:
# cd "opus2-streamlit"
# cd "pic_manage"
```

### 2 — Install dependencies

```bash
pip install -r requirements.txt
```

### 3 — Point it at your photos

Open `config.yaml` and edit the two paths:

```yaml
scan:
  folder_path: "C:\\Users\\YourName\\Pictures"

organization:
  output_folder: "C:\\Users\\YourName\\Pictures\\Organised"
```

### 4 — Run

```bash
python main.py
```

You'll see the interactive menu:

```
┌──────────────────────────────────────────────┐
│  1. Scan & Extract Metadata                  │
│  1b. Resume Excel write (from backup)        │
│  2. Delete Marked Files (from Excel)         │
│  3. Organise Images by Date                  │
│  4. Full Workflow  (1 → 2 → 3)               │
│  5. Launch Web Dashboard (Streamlit)        │
│  6. Generate Comparison Pages               │
│  0. Exit                                     │
└──────────────────────────────────────────────┘
```

---

## 🔄 Workflow

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Task 1     │────▶│  Review      │────▶│  Task 2      │────▶│  Task 3      │
│  Scan all   │     │  Excel file  │     │  Delete      │     │  Organise    │
│  photos     │     │  Mark 'Yes'  │     │  flagged     │     │  by date     │
└─────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
```

### Task 1 — Scan & Extract Metadata
Walks the entire folder tree, extracts all metadata, scores blur, detects duplicates, and produces a full Excel workbook. A `records-backup.pkl` is saved so you can resume if anything interrupts. If you enable comparison generation in `config.yaml`, it can also produce `./comparisons/DUP_*.html`.

### Task 2 — Delete Marked Files
Opens the Excel report, reads every row where `DELETE? (Yes/No)` = `Yes`, and permanently deletes those files from disk.

> ⚠️ **Deletion is permanent.** Review the Excel carefully before running Task 2.

### Task 3 — Organise Images by Date
Copies (or moves) every non-deleted image into a smart date folder:

| Photos on that day | Folder name | Example |
|---|---|---|
| **≥ 60** (busy day — event, trip) | `YYYYMMDD` | `20260204` |
| **< 60** (quiet day) | `YYYYMM00` | `20260200` |

Date source priority: **EXIF date taken → file modified date → today**.

---

## 📊 Excel Report Sheets

| Sheet | Contents |
|---|---|
| **Summary** | Totals, size, quality averages, format breakdown, EXIF/GPS coverage |
| **All Images** | Full catalogue — every file with all metadata, colour-coded rows |
| **Blurry Images** | Only blurry files, sorted worst-first, with editable delete flags |
| **Duplicates** | Grouped by MD5 hash — best copy auto-selected, others flagged |
| **Quality Report** | Score distribution: Excellent / Good / Fair / Poor |
| **Analytics** | Optional scan analytics (quality/format/camera breakdowns) |
| **Clusters** | Optional clustering/groups (e.g., color-histogram clusters) |

### Colour coding in All Images

| Row colour | Meaning |
|---|---|
| 🟠 Orange | Blurry image |
| 🔴 Light red | Duplicate file |
| ⬜ Alternating grey/white | Normal image |

---

## 🌫️ Blur Detection

Uses **Laplacian variance** — a fast, reliable measure of edge sharpness.

| Score range | Rating | Meaning |
|---|---|---|
| `< 50` | Very Blurry | Almost certainly unusable |
| `50 – 100` | Blurry | Noticeably soft |
| `100 – 200` | Fair | Acceptable |
| `> 200` | Sharp | Crisp and clear |

Tune sensitivity in `config.yaml`:

```yaml
blur_detection:
  threshold: 100   # lower = more sensitive
```

---

## 🔗 Duplicate Detection & Best-Copy Selection

Files are compared by **MD5 content hash** — identical bytes = duplicate, regardless of filename or folder.

When duplicates are found, the best copy is automatically selected based on (in order):

1. **Quality score** — highest overall score wins
2. **Resolution** — highest megapixels
3. **Date** — newest file
4. **Size** — largest file

All criteria and their order are configurable in `config.yaml`:

```yaml
duplicates:
  selection_criteria:
    - quality
    - resolution
    - date
    - size
```


---

## ⚙️ Configuration Reference

```yaml
# ── Scan ──────────────────────────────────────────────────
scan:
  folder_path: "C:\\Users\\YourName\\Pictures"
  recursive: true
  extensions:
    images: [jpg, jpeg, png, gif, bmp, tiff, webp, heic, raw, cr2, nef, arw, dng]
    videos: [mp4, mov, avi, mkv, 3gp, m4v]

# ── Organisation ──────────────────────────────────────────
organization:
  output_folder: "C:\\Users\\YourName\\Pictures\\Organised"
  day_threshold: 60        # >= 60 pics → YYYYMMDD, else YYYYMM00
  operation: "copy"        # "copy" (safe) or "move"
  use_exif_date: true

# ── Blur Detection ────────────────────────────────────────
blur_detection:
  threshold: 100           # lower = more sensitive to blur

# ── Duplicates ────────────────────────────────────────────
duplicates:
  hash_algorithm: "md5"    # "md5" (fast) or "sha256" (more accurate)
  selection_criteria: [quality, resolution, date, size]

# ── Output ────────────────────────────────────────────────
output:
  output_folder: "./output"
```

---

## 📦 Requirements

```
Pillow
openpyxl
PyYAML
tqdm
numpy
opencv-python (or opencv-python-headless)
python-dateutil

# v2.x extras (enable in config.yaml)
pillow-heif (HEIC/HEIF support)
streamlit (web dashboard)
reverse_geocoder (geocoding)
scikit-learn (clustering)
Jinja2 (comparison page templates)
pymediainfo (richer video metadata; requires MediaInfo installed)
```

Install all at once:

```bash
pip install -r requirements.txt
```

---

## 🧩 Module Overview

| Module | Responsibility |
|---|---|
| `main.py` | Interactive CLI menu, orchestrates all tasks |
| `config_manager.py` | Loads `config.yaml`, dot-notation access, validates paths |
| `scanner.py` | Walks folders, opens images with Pillow, extracts all EXIF fields |
| `blur_detector.py` | Reads image with OpenCV, computes Laplacian variance, returns rating |
| `duplicate_handler.py` | Builds MD5 hash map, groups duplicates, scores and selects best copy |
| `organizer.py` | Pre-counts images per day, applies threshold logic, copies/moves files |
| `excel_writer.py` | Writes a multi-sheet workbook (5-7 tabs) with colours, filters, and freeze panes |
| `utils.py` | `file_hash`, `get_gps`, `get_date_from_exif`, `safe_string` |
| `main_utils.py` | `setup_logging`, `save_backup`, `load_backup` |

---

## 🛠️ Troubleshooting

**No images found**
- Check `scan.folder_path` in `config.yaml` — must be an absolute path
- Verify the folder exists and Python has read permission
- Confirm your file extensions are listed under `scan.extensions.images`

**Blur detection returns errors**
- Ensure `opencv-python` is installed: `pip install opencv-python --break-system-packages`
- Some RAW formats (`.cr2`, `.nef`) cannot be read by OpenCV — they will show `Error: Cannot read image` and be skipped gracefully

**Excel file is locked / won't save**
- Close the Excel file before running any task
- Only one process can write to an `.xlsx` file at a time

**Task 1 interrupted mid-scan**
- A `records-backup.pkl` is saved automatically after scanning
- Use menu option `1b` to skip re-scanning and write the Excel from the backup

**Out of memory on very large libraries**
- Reduce `processing.threads` in `config.yaml`
- Split into smaller subfolders and scan each separately

---

## 🗺️ Roadmap

- [x] Streamlit dashboard (run `python -m streamlit run web/streamlit_app.py`)
- [x] Comparison pages generator (HTML in `./comparisons`)
- [ ] Face detection & grouping (if you want it fully integrated/enabled)
- [ ] Google Drive / OneDrive upload
- [ ] Machine-learning quality assessment
- [ ] Thumbnail preview column in Excel
- [ ] Scheduled / watched-folder scanning

---

## 📄 License

MIT — see [LICENSE](LICENSE) for details.

---

<div align="center">

Made with ☕ and too many duplicate holiday photos.

</div>