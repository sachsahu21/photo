C:\Users\ISSUser\Desktop\Sachin\git\photo\pic_manage\output\image_scan_Goa_20260417_225240.xlsx

python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt


# Image Scanner - Professional Edition v1.0.0

Scan, analyze, and organize image & video collections.

## Features

- **20+ image formats + 12 video formats**
- **EXIF extraction**: Camera, GPS, dates, exposure (images)
- **Video metadata**: Duration, resolution, FPS, codec, bitrate
- **Blur detection**: Laplacian variance
- **Duplicate detection**: Exact (MD5/SHA256) or Similar (perceptual hash)
- **Smart organization**: YYYYMMDD for busy days, YYYYMM00 for quiet months
- **Excel reports**: 5 sheets with color coding
- **Pickle backup + CSV fallback**

## Video Metadata

Videos now extract:
| Field | Description | Source |
|-------|-------------|--------|
| Duration | Length in seconds + formatted | OpenCV / pymediainfo |
| Resolution | Width x Height pixels | OpenCV / pymediainfo |
| FPS | Frames per second | OpenCV / pymediainfo |
| Codec | Video codec (H.264, HEVC, etc.) | OpenCV fourcc / pymediainfo |
| Bitrate | Kilobits per second | pymediainfo only |

> **Note**: `pymediainfo` requires [MediaInfo](https://mediaarea.net/en/MediaInfo) 
> installed on your system. OpenCV provides basic video metadata without it.

### Install MediaInfo (for full video metadata)

**Windows**: Download from https://mediaarea.net/en/MediaInfo/Download/Windows  
**macOS**: `brew install mediainfo`  
**Linux**: `sudo apt install mediainfo`

## Installation

```bash
# 1. Clone
git clone <repo-url>
cd image_scanner

# 2. Virtual environment
python -m venv venv
# Windows: venv\Scripts\activate
# Linux/Mac: source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure
# Edit config.yaml with your paths

# 5. Run
python main.py
```

### If dependency issues:
```bash
pip install numpy==1.26.4 openpyxl==3.1.5 opencv-python==4.9.0.80
```

## Usage

### Task 1: Scan
- Scans all images + videos
- Extracts EXIF (images), video metadata (videos)
- Detects blur (images only)
- Finds duplicates
- Generates Excel report

### Task 2: Delete
- Open Excel → Duplicates sheet
- Set `DELETE? (Yes/No)` to `Yes`
- Save Excel → Run Task 2

### Task 3: Organize
- Copies/moves files to date folders
- `>= 60 files/day` → `YYYYMMDD/`
- `< 60 files/day` → `YYYYMM00/`

### Task 4: Full Workflow
Scan → Delete → Organize with confirmations

## Duplicate Detection Modes

### Exact Match (default)
```yaml
duplicates:
  match_mode: "exact"
  hash_algorithm: "md5"
```

### Similar Match (perceptual)
```yaml
duplicates:
  match_mode: "similar"
  similarity_threshold: 90
```

## Excel Sheets

1. **Summary**: Stats, video totals, format distribution
2. **All Images**: Complete metadata (images + videos)
3. **Blurry Images**: Sorted by blur score
4. **Duplicates**: ALL group members shown
5. **Quality Report**: Distribution + video stats + camera stats

## Project Structure

```
image_scanner/
├── main.py
├── config.yaml
├── requirements.txt
├── src/
│   ├── __init__.py
│   ├── config_manager.py
│   ├── scanner.py
│   ├── blur_detector.py
│   ├── duplicate_handler.py
│   ├── organizer.py
│   ├── excel_writer.py
│   ├── video_metadata.py    ← NEW
│   └── utils.py
├── logs/
└── reports/
```


