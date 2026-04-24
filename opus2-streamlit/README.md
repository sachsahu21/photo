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



<!-- --- -->

# Image Scanner - Professional Edition

Professional image metadata scanner with blur detection, duplicate handling, and automated organization.

## Features

✨ **Core Features**
- 📸 Extract comprehensive image metadata (EXIF, GPS, camera info)
- 🔍 Blur detection using Laplacian variance analysis
- 📊 Quality scoring and assessment
- 🔗 Duplicate detection using MD5 hashing
- 🤖 Automatic best-of-group selection for duplicates
- 📁 Organize images into date-based folder structure
- 📈 Generate detailed Excel reports with multiple sheets
- ⚡ Multi-threaded processing with progress bars
- 📝 Comprehensive logging

## Installation

### Prerequisites
- Python 3.8+
- pip

### Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/image-scanner.git
   cd image-scanner

<!-- Create virtual environment -->
<!-- run the below command 1st time  if the folders already exisit then run the nxt command -->
python -m venv venv

# On Windows
venv\Scripts\activate
 

<!-- Install dependencies -->

pip install -r requirements.txt

Configuration
Edit config.yaml to customize:

yaml
Copy code
scan:
  folder_path: "C:\\path\\to\\your\\images"
  recursive: true

blur_detection:
  enabled: true
  threshold: 100  # Lower = more sensitive

duplicates:
  enabled: true
  auto_select_best: true
  selection_criteria:
    - quality
    - resolution
    - date
    - size

organization:
  output_folder: "C:\\path\\to\\organized"
  folder_structure: "year/month"  # or year, year/month/day
  operation: "copy"  # or move
Usage
Interactive Mode
bash
Copy code
python main.py
Follow the menu to:

Scan and extract metadata
Review and mark files for deletion
Organize remaining images
Command Line (Future)
bash
Copy code
# Scan only
image-scanner scan --folder "C:\path\to\images"

# Full workflow
image-scanner workflow --folder "C:\path\to\images" --config config.yaml
Workflow
Task 1: Scan & Extract Metadata
Scans all images in specified folder
Extracts EXIF metadata
Detects blur using Laplacian variance
Calculates quality scores
Identifies duplicates
Generates Excel report with 5 sheets:
All Images: Complete metadata
Blurry Images: Sorted by blur score
Duplicates: Grouped with best selected
Quality Report: Quality analysis
Summary: Statistics overview

Task 2: Delete Marked Files
Open generated Excel file
Review "Blurry Images" and "Duplicates" sheets
Mark files with "Yes" in "DELETE? (Yes/No)" column
Run Task 2 to delete marked files
Generates deletion report
Task 3: Organize Images
Creates folder structure (YYYY/MM by default)
Copies/moves images to organized folders
Uses EXIF date if available, else file modified date
Handles filename conflicts (rename/skip/overwrite)
Generates organization report
Excel Report Structure
All Images Sheet
Complete metadata for all images with:

File information (name, size, format)
Image properties (resolution, color mode, DPI)
EXIF data (camera, lens, settings)
Blur detection results
Quality scores
Duplicate information
Editable delete flags
Blurry Images Sheet
Sorted by blur score (worst first)
Quality ratings and scores
Identified issues
Editable delete flags
Duplicates Sheet
Grouped by MD5 hash
Best selected automatically
Recommendation column
Quality comparison
Editable delete flags
Quality Report Sheet
Quality statistics (average, min, max)
Distribution by quality ranges
Issue analysis
Summary Sheet
Scan statistics
Quality metrics
Format distribution
Metadata coverage
Blur Detection
Uses Laplacian variance method:

Very Blurry: Score < 50
Blurry: Score 50-100
Fair: Score 100-200
Sharp: Score > 200
Adjust threshold in config.yaml:

yaml
Copy code
blur_detection:
  threshold: 100  # Increase for less sensitivity
Duplicate Selection Criteria
Automatic best selection based on:

Quality: Highest quality score
Resolution: Highest megapixels
Date: Newest file
Size: Largest file
Customize in config.yaml:

yaml
Copy code
duplicates:
  selection_criteria:
    - quality
    - resolution
    - date
    - size
Logging
Logs are saved to ./logs/image_scanner.log

Configure in config.yaml:

yaml
Copy code
logging:
  level: "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
  file: "./logs/image_scanner.log"
  console: true
Performance
Threading: Auto-detects CPU count for parallel processing
Progress: Real-time progress bars for all operations
Memory: Efficient streaming for large files
Speed: Processes ~100-200 images/minute (depends on image size)
Troubleshooting
No images found
Check scan.folder_path in config.yaml
Verify folder permissions
Ensure image extensions are in scan.extensions
Blur detection not working
Ensure opencv-python is installed: pip install opencv-python
Check image file is not corrupted
Excel file locked
Close Excel file before running Task 2/3
Ensure no other program is accessing the file
Out of memory
Reduce number of threads in config.yaml
Process smaller folders at a time
Project Structure
image-scanner/
├── main.py                 # Entry point
├── config.yaml             # Configuration file
├── requirements.txt        # Dependencies
├── README.md              # This file
├── src/
│   ├── __init__.py
│   ├── config_manager.py  # Configuration handling
│   ├── scanner.py         # Image scanning
│   ├── blur_detector.py   # Blur detection
│   ├── duplicate_handler.py # Duplicate handling
│   ├── organizer.py       # Image organization
│   ├── excel_writer.py    # Report generation
│   └── utils.py           # Utility functions
├── tests/                 # Unit tests
├── logs/                  # Log files
└── output/                # Generated reports
Contributing
Contributions welcome! Please:

Fork the repository
Create a feature branch
Make your changes
Add tests
Submit a pull request
License
MIT License - see LICENSE file for details

Support
For issues and questions:

Open an issue on GitHub
Check existing issues for solutions
Review logs in ./logs/image_scanner.log
Roadmap
[ ] Web UI interface
[ ] Batch processing API
[ ] Cloud storage integration (Google Drive, OneDrive)
[ ] Image preview in Excel
[ ] Advanced filtering options
[ ] Scheduled scanning
[ ] Machine learning-based quality assessment
[ ] Face detection and grouping
Changelog
v1.0.0 (2024)
Initial release
Core scanning and metadata extraction
Blur detection
Duplicate handling with auto-selection
Image organization
Excel report generation
Full workflow integration
