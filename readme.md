<div align="center">

# 📸 Photo — Image Scanner v4.0

**Scan · Analyze · Organize · Report**

_A polished, local-first Python toolkit to tame your photo chaos — v4.0 is the latest and recommended version._

[![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Release](https://img.shields.io/badge/Release-v4.0-blue?style=for-the-badge)](https://github.com/sachsahu21/photo/tree/main/v4.0)

</div>

---

Welcome to the fanciest README you've ever read for a photo-scanning tool ✨ — you asked for a polished, v4.0-centric doc, so here it is. This project contains multiple versions; v4.0 (in folder `v4.0`) is the most feature-complete and stable release. If you want the shiny new behavior, use v4.0.

Quick links
- Latest (recommended): v4.0 — folder: `v4.0`
- Other versions / historical: `v3.3`, `v3.2`, `v3.1`, `v3.0`, `v2`, `v1` (see repo root)

Highlights — why v4.0?
- Interactive CLI with sensible defaults and a small web dashboard (optional)
- Full EXIF/video metadata extraction, blur scoring, duplicate detection and best-copy selection
- Excel reporting (multi-sheet) and safe Excel-driven deletion workflow
- Organization engine that groups by date and creates human-friendly folders
- Checkpointing and resume support to handle long scans

Table of contents
- Features
- Quick start (v4.0)
- Configuration (important keys)
- Example: run a smoke test
- OneDrive & cloud notes (local-first advice)
- Internals & module map (v4.0/src)
- Troubleshooting
- Contributing & License

---

Features
- 🔍 Scan images & videos recursively and extract metadata (EXIF, dimensions, GPS)
- 🌫️ Blur detection using Laplacian variance (fast, tunable)
- 🔗 Duplicate detection (MD5 by default) and automated best-copy selection
- 📊 Excel workbook with multiple sheets: All Images, Blurry, Duplicates, Summary, Analytics, etc.
- 🗂️ Smart organization (copy or move) into date-based folders with configurable threshold
- ⚡ Parallel processing (configurable thread count) with checkpointing
- 🧩 Optional extras: Similar-image detection, clustering, face detection, thumbnails, Streamlit dashboard

---

Quick start (run v4.0)
1. Open a terminal and change to the v4.0 folder:

```bash
cd path/to/photo/v4.0
```

2. Create & activate a virtual environment:
- macOS / Linux
```bash
python3 -m venv venv
source venv/bin/activate
```
- Windows (Powershell)
```powershell
py -3 -m venv venv
.\venv\Scripts\Activate.ps1
```

3. Install dependencies (recommended):
```bash
pip install -r requirements.txt
```
If you want a lightweight smoke test, installing Pillow and openpyxl may be enough for basic scanning of JPEGs.

4. Edit `v4.0/config.yaml` and set `scan.folder_path` to the folder you want scanned (example given is Windows path; change to a local folder). Optionally set `processing.threads` to tune parallelism.

5. Run the interactive CLI:
```bash
python main.py
```
Choose `1` to Scan & Extract, `1b` to resume from backup, `2` to delete flagged files from an Excel workbook, `3` to organize, etc.

---

Configuration (most important keys — located in `v4.0/config.yaml`)
- scan.folder_path: Path to your pictures (absolute recommended)
- scan.recursive: true/false
- processing.threads: number of parallel workers (set `1` to disable parallel scanning)
- blur_detection.threshold: numeric threshold (lower = more sensitive)
- duplicates.enabled / hash_algorithm: `md5` by default
- organization.output_folder and folder_structure: where and how to write organized photos
- output.output_folder: where Excel reports are written

Tip: If scanning OneDrive or cloud-backed folders, set threads to 1–2 or ensure files are "Always keep on this device" to avoid many on-demand downloads.

---

Smoke test (quick validation)
If you just want to verify v4.0 will run on your machine, use this minimal test (create `test_scan.py` in the `v4.0` folder):

```python
# test_scan.py
from pathlib import Path
from src.config_manager import ConfigManager
from src.scanner import ImageScanner
from PIL import Image

cfg = ConfigManager('config.yaml')
# use a tiny sample folder inside v4.0
cfg.set('scan.folder_path', './sample_images')
cfg.set('processing.threads', 1)

# create sample image
p = Path('./sample_images')
p.mkdir(parents=True, exist_ok=True)
img = Image.new('RGB', (100,100), (255,0,0))
img.save(p / 'sample_test_image.jpg')

scanner = ImageScanner(cfg.to_dict())
records = scanner.scan(cfg.get('scan.folder_path'))
print('Records found:', len(records))
if records:
    print(records[0])
```

Run:
```bash
python test_scan.py
```

---

OneDrive / Cloud-backed folders — practical notes
- The scanner reads the local filesystem. If your OneDrive uses Files On-Demand (cloud-only placeholders), the scanner may trigger downloads or fail to open some placeholders. Recommended approaches:
  - Mark folders as "Always keep on this device" so they exist locally before scanning.
  - Reduce `processing.threads` to 1 or 2 for cloud folders to avoid flooding the OneDrive client with simultaneous downloads.
  - For server-only scanning (no local sync), consider a Graph API integration (not included by default).

---

Internals (v4.0/src) — quick map
- config_manager.py — load/validate config
- scanner.py — core scanning, extraction, blur & duplicate hooks
- parallel_processor.py — threaded worker pool with progress bar
- duplicate_handler.py — group duplicates & best-copy selection
- organizer.py — move/copy logic to create date-based folders
- excel_writer.py — writes the multi-sheet report
- comparison_generator.py — HTML comparison pages
- blur_detector.py, face_detector.py, thumbnail_generator.py, similar_detector.py, image_clusterer.py — helper modules

---

Tips & Troubleshooting
- "4 workers" message: Controlled by `processing.threads` in the config. Set to `1` to force single-threaded scanning.
- If `scan.folder_path not found`, update `v4.0/config.yaml` to the correct path.
- Missing OpenCV / pillow-heif / pymediainfo: install from `requirements.txt` or disable optional features in `config.yaml`.
- Excel workbook locked: close Excel before running tasks that write to the file.

---

Contributing
- Found a bug or have a feature idea? Open an issue or a PR on GitHub. Keep changes scoped to the `v4.0/src` modules unless you are updating other versions intentionally.

---

Made with ☕, a stubborn love for clean photo folders, and an unreasonable number of vacation duplicates. v4.0 — go tidy up those memories.
