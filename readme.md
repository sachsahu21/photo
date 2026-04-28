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
║   Photo Library Scanner  v2.0               ║
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
| 📊 **Excel Report** | 5-sheet workbook with filters, colour coding, and delete flags |
| 🗑️ **Safe Deletion** | Mark files in Excel → script deletes only what you approved |

---

## 🗂️ Project Structure

```
photo_scanner/
│
├── main.py                  ← Entry point — interactive task menu
├── config.yaml              ← All settings (paths, thresholds, extensions)
│
└── src/
    ├── __init__.py          ← Package exports
    ├── config_manager.py    ← Loads & validates config.yaml
    ├── scanner.py           ← Walks folders, extracts EXIF metadata
    ├── blur_detector.py     ← Laplacian variance blur scoring
    ├── duplicate_handler.py ← MD5 grouping, best-copy selection
    ├── organizer.py         ← Smart YYYYMMDD / YYYYMM00 folder logic
    ├── excel_writer.py      ← Generates 5-sheet formatted Excel report
    ├── utils.py             ← Hash, GPS, date, string helpers
    └── main_utils.py        ← Logging setup & pickle backup helpers

output/                      ← Excel reports saved here  (auto-created)
logs/                        ← scanner.log saved here    (auto-created)
```

---

## ⚡ Quick Start

### 1 — Clone & set up a virtual environment

```bash
git clone https://github.com/yourname/photo-scanner.git
cd photo-scanner

python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
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
│  5. Exit                                     │
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
Walks the entire folder tree, extracts all metadata, scores blur, detects duplicates, and produces a full Excel workbook. A `records_backup.pkl` is saved so you can resume if anything interrupts.

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
Pillow>=9.0.0
openpyxl>=3.1.5
opencv-python>=4.5.0
PyYAML>=6.0
tqdm>=4.62.0
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
| `excel_writer.py` | Writes 5-sheet formatted workbook with colours, filters, and freeze panes |
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
- A `records_backup.pkl` is saved automatically after scanning
- Use menu option `1b` to skip re-scanning and write the Excel from the backup

**Out of memory on very large libraries**
- Reduce `processing.threads` in `config.yaml`
- Split into smaller subfolders and scan each separately

---

## 🗺️ Roadmap

- [ ] Web UI (Flask / FastAPI)
- [ ] Face detection & grouping
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