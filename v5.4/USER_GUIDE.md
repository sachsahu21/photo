# Image Scanner v5.4 — User Guide
*For first-time users and non-technical users*

---

## What Does This Tool Do?

This tool helps you manage a large collection of photos and videos on your PC. It can:

- **Scan** a folder of photos and build a database of everything it finds
- **Detect duplicate photos** so you can safely delete extras
- **Organize photos** into folders sorted by year or date
- **Find faces** in photos and tag which person appears in which photo
- **Generate Excel reports** so you can review and make decisions in a spreadsheet

Everything runs on your PC — no internet, no subscription, no cloud fees required.

---

## Before You Start

### Requirements
- Python 3.9 or later installed on your PC
- The following Python packages installed:
  ```
  pip install openpyxl pillow opencv-python face_recognition
  ```
- Your photos stored somewhere on your hard drive or an external drive

### Files You Will Work With
| File | What It Is |
|------|-----------|
| `config.yaml` | Settings file — you edit this once before first use |
| `main.py` | The program — run this to start the tool |

---

## First-Time Setup (3 Steps)

### Step 1 — Tell the tool where your photos are

Open `config.yaml` in Notepad and find this line:

```yaml
scan:
  folder_path: "C:\\Users\\ISSUser\\Desktop\\Sachin\\hdd\\pic"
```

Change the path inside the quotes to the folder where your photos live.

> **Tip:** Use double backslashes `\\` between folder names on Windows.
> Example: `"D:\\My Photos\\Family"`

---

### Step 2 — Tell the tool where to store its working files

Find this line:

```yaml
workspace:
  root: "C:\\Users\\ISSUser\\Desktop\\Sachin\\hdd\\artifacts"
```

Change it to an empty folder where the tool can store its database, reports, and logs.
This is NOT where your photos go — it is just a working area for the tool.

> **Example:** `"C:\\PhotoTool\\workspace"`

---

### Step 3 — Tell the tool where to put organized photos

Find this line:

```yaml
organization:
  output_folder: "C:\\Users\\ISSUser\\Desktop\\Sachin\\hdd\\organized"
```

Change it to a folder where you want your photos sorted into year/date folders.

> **Example:** `"D:\\Photos\\Organized"`

---

### Run the Tool

Open a terminal (Command Prompt or PowerShell), navigate to the `v5.4` folder, and run:

```
python main.py
```

You will see a menu. Type the option number and press Enter.

---

## The Menu — What Each Option Does

```
========================================================
  1. ANALYSIS
  --------------------------------------------------------
  11.  Analyze folder & file counts
  12.  Export scan progress report

  2. METADATA
  --------------------------------------------------------
  21.  Build / Refresh Metadata Vault
  22.  Enrich existing metadata
  23.  Reconcile vault paths
  24.  Dedupe metadata files
  25.  Fresh restart (clear vault)

  3. EXCEL & DATA
  --------------------------------------------------------
  31.  Generate / Refresh Excel
  32.  Apply delete actions (quarantine)

  4. LIBRARY
  --------------------------------------------------------
  41.  Organize from Excel
  42.  Convert folder structure
  43.  Merge duplicate dates
  44.  Update picture counts

  5. FACES & PEOPLE
  --------------------------------------------------------
  51.  Build / Update face index
  52.  Sync people tags
  53.  Refresh seed feedback
  54.  Cleanup untagged samples

   0.  Exit
========================================================
```

---

### Section 1: ANALYSIS

#### Option 11 — Analyze Folder & File Counts
**What it does:** Counts how many photos, videos, and other files are in each sub-folder of your photo library.

**Use it when:** You want to understand the size and structure of your photo library before doing anything else.

**What you get:**
- On-screen summary (size, image count, video count per folder)
- An Excel file saved to `workspace/folder_analysis/` with a detailed breakdown

**Steps:**
1. Type `11` and press Enter
2. The tool asks for a folder path — press Enter to use the default from your config, or type a different path

---

#### Option 12 — Export Scan Progress Report
**What it does:** Checks which files have been scanned (processed) and which are still waiting. Creates a detailed report.

**Use it when:** You want to know how many photos are left to scan, or which folders have not been processed yet.

**What you get:** An Excel file in `workspace/folder_analysis/` with five sheets:

| Sheet | What's In It |
|-------|-------------|
| **Summary** | Total files, scanned count, pending count, sizes |
| **By Directory** | Each folder with how many files are done vs pending |
| **Pending Files** | List of all files not yet scanned, with file sizes |
| **Scanned Files** | List of all files that have been scanned |
| **All Files** | Everything combined in one list |

**Steps:**
1. Type `12` and press Enter
2. Report is created automatically — look for the file path printed on screen

---

### Section 2: METADATA

*Metadata means extra information about each photo — when it was taken, its size, whether it's blurry, whether it's a duplicate, etc. The "vault" is a database of this information stored as small JSON files.*

#### Option 21 — Build / Refresh Metadata Vault ⭐ (Start Here)
**What it does:** Scans every photo and video in your scan folder, extracts all available information (date, size, resolution, GPS location, blur score, duplicate status), and saves it.

**Use it when:** First time you use the tool, or when you add new photos to your library.

**How long it takes:** Depends on library size. For 10,000 photos expect 10–30 minutes on first run. Subsequent runs are faster because it skips already-processed files.

**What happens during the scan:**
- Reads EXIF data from each photo (date taken, camera model, GPS, etc.)
- Calculates an MD5 hash to identify duplicate files
- Detects blurry photos
- Detects faces (if face detection is enabled in config)

**Steps:**
1. Type `21` and press Enter
2. Wait for the scan to complete — progress is shown on screen
3. At the end, if any files are missing metadata, you can choose to repair them or skip

---

#### Option 22 — Enrich Existing Metadata
**What it does:** Re-scans files that already have metadata, but only fills in fields that are missing or empty. It does NOT overwrite data you already have.

**Use it when:**
- You updated your config to extract more information (e.g. turned on blur detection)
- Some files were scanned quickly without full data
- A previous scan was interrupted and some records are incomplete

**Steps:**
1. Type `22` and press Enter
2. The tool shows how many files it will process
3. Type `yes` and press Enter to confirm
4. Progress is shown every 100 files

---

#### Option 23 — Reconcile Vault Paths
**What it does:** Updates the database if photos have been moved or renamed. The tool stores the full file path for each photo — if you reorganize your folders outside this tool, the paths in the database become outdated. This option fixes them.

**Use it when:** You moved photos to a different folder manually, or after running "Organize from Excel" (option 41).

**Steps:**
1. Type `23` and press Enter
2. The tool updates paths automatically — no input needed

---

#### Option 24 — Dedupe Metadata Files
**What it does:** Cleans up the metadata database by removing duplicate entries. Sometimes the same photo can get two entries in the database — this removes the extras.

**Use it when:** Your Excel report shows the same photo appearing twice, or after a fresh restart.

**Steps:**
1. Type `24` and press Enter
2. Completes automatically

---

#### Option 25 — Fresh Restart (Clear Vault)
**What it does:** Deletes all the metadata the tool has built up and starts from scratch. Your photos are NOT deleted — only the tool's database is cleared.

**Use it when:**
- Your database got corrupted
- You want to completely re-scan everything from zero
- You changed your scan folder to something completely different

> ⚠️ **Warning:** This cannot be undone. The old data is moved to a quarantine folder, not permanently deleted, but you will need to re-scan everything.

**Steps:**
1. Type `25` and press Enter
2. The tool shows exactly what it will delete
3. Type `DELETE METADATA` (exactly as shown) to confirm
4. The tool automatically starts a fresh scan afterward

---

### Section 3: EXCEL & DATA

#### Option 31 — Generate / Refresh Excel ⭐ (Do This After Scanning)
**What it does:** Takes all the metadata from the database and creates an Excel workbook you can open in Microsoft Excel or LibreOffice.

**Use it when:** After scanning (option 21), to get a spreadsheet view of your entire photo library.

**What the Excel contains:**

| Sheet | What's In It |
|-------|-------------|
| **All Images** | Every photo and video with all details |
| **Duplicates** | Only duplicate photos — shows which to keep and which to delete |
| **Similar Images** | Photos that look similar (if enabled) |
| **Blurry Images** | Photos detected as blurry |
| **Summary** | Overall statistics |
| **Analytics** | Storage and date-based statistics |

**Steps:**
1. Type `31` and press Enter
2. Excel file is saved to `workspace/reports/` — the path is shown on screen

---

#### Option 32 — Apply Delete Actions (Quarantine)
**What it does:** Reads your Excel file, finds photos you marked for deletion (`YES` in the DELETE? column), and moves them to a quarantine folder. Photos are NOT permanently deleted — they are moved to `workspace/quarantine/` so you can recover them if needed.

**Use it when:** You reviewed duplicates in Excel, marked some for deletion, and want to actually remove them from your library.

**Steps:**
1. Open the Excel file (from option 31)
2. In the Duplicates sheet, change `DELETE?` to `YES` for photos you want to remove
3. Save the Excel file
4. Type `32` and press Enter in the tool
5. Select which sheet to apply (Duplicates, Similar Images, All Images, or all)
6. Confirm with `yes`

---

### Section 4: LIBRARY

#### Option 41 — Organize from Excel ⭐ (Sort Photos Into Folders)
**What it does:** Takes your photos and copies (or moves) them into a neat folder structure sorted by year or date. For example: `Organized/2023/January/` or `Organized/2022/`.

**New feature — Selective directory:** When you run this option, the tool shows you all the source directories found in your Excel and lets you pick which ones to organize. Just enter the numbers of the directories you want (e.g. `1,3,5`) or press Enter to organize everything.

**Use it when:** After scanning and reviewing your Excel, you want to physically sort your photos into date folders.

**Steps:**
1. Generate your Excel first (option 31)
2. Type `41` and press Enter
3. Paste the path to your Excel file, or press Enter to use the last one
4. A list of source directories appears — enter numbers to pick specific ones, or press Enter for all
5. Confirm and the tool copies/moves photos to the organized folder

---

#### Option 42 — Convert Folder Structure
**What it does:** Changes how your organized photos are arranged. You can switch between:
- **Flat** — all photos in one folder
- **Year** — photos sorted by year (2022, 2023, 2024...)
- **Year-Month-Date** — photos sorted by year, then month, then day

**Use it when:** You want to change the folder layout of your already-organized library.

**Steps:**
1. Type `42` and press Enter
2. Choose the target structure (1=flat, 2=year, 3=year-month-date)
3. Optionally enter a different output folder, or press Enter for in-place
4. Confirm with `yes`

---

#### Option 43 — Merge Duplicate Dates
**What it does:** If your organized library has two folders for the same date (e.g. `2023-06-15` and `2023-6-15`), this merges them into one.

**Use it when:** You notice duplicate date folders after organizing.

**Steps:**
1. Type `43` and press Enter
2. Confirm with `yes`

---

#### Option 44 — Update Picture Counts
**What it does:** Walks through your organized library and updates count files that record how many photos are in each folder. Used by certain viewers and web interfaces.

**Use it when:** After organizing or moving photos, to keep folder counts accurate.

**Steps:**
1. Type `44` and press Enter
2. Confirm with `yes`

---

### Section 5: FACES & PEOPLE

*The faces section lets you find all photos of a specific person. You need to provide at least one "seed" photo of the person first.*

#### Option 51 — Build / Update Face Index
**What it does:** Scans all photos, detects faces, and builds a searchable database (face index). Each face is stored with its unique fingerprint so it can be matched to known people later.

**Use it when:** First time using face features, or after adding new photos to your library.

**How long it takes:** Longer than a regular scan — expect 1–3 minutes per 100 photos on a typical PC.

**Steps:**
1. Type `51` and press Enter
2. Wait for it to complete

---

#### Option 52 — Sync People Tags
**What it does:** Compares the face index against your "seed" photos (photos of known people you provided) and tags each photo with the person's name.

Also exports a folder of untagged faces (unknown people) so you can manually identify them and add them as new seed photos.

**Use it when:** After building the face index (option 51) and you want to tag photos by person.

**Before running:** Place seed photos in `workspace/seed/<person_name>/` folders. Example: `workspace/seed/Sachin/photo1.jpg`

**Steps:**
1. Type `52` and press Enter
2. The tool matches faces and shows counts
3. Check the `workspace/untagged_people/` folder to identify unknowns

---

#### Option 53 — Refresh Seed Feedback
**What it does:** Re-applies your known seed matches without re-exporting untagged samples. Faster than a full sync — useful after you add a new seed photo for an already-known person.

**Use it when:** You added more seed photos for a person already in your seed folder and want to re-tag without running a full sync.

**Steps:**
1. Type `53` and press Enter

---

#### Option 54 — Cleanup Untagged Samples
**What it does:** Deletes empty sample folders from the `untagged_people/` directory. These empty folders accumulate over time as unknowns get identified.

**Steps:**
1. Type `54` and press Enter

---

## Typical Workflows

### First Time Setup
```
1. Edit config.yaml (scan folder, workspace, organized folder)
2. Run: 21 → Build metadata vault (scan all photos)
3. Run: 31 → Generate Excel report
4. Open Excel → Review duplicates sheet
5. Run: 32 → Quarantine duplicates (after marking in Excel)
6. Run: 41 → Organize photos into year folders
```

### Adding New Photos (Ongoing)
```
1. Copy new photos to your scan folder
2. Run: 21 → Refresh metadata vault (only scans new files)
3. Run: 31 → Refresh Excel
4. Run: 32 → Quarantine any new duplicates
5. Run: 41 → Organize new photos
```

### Face Tagging Workflow
```
1. Run: 51 → Build face index (once, or after adding photos)
2. Place seed photos in workspace/seed/<person_name>/
3. Run: 52 → Sync people tags
4. Check untagged_people/ folder → identify unknowns → add as seeds
5. Run: 53 → Refresh seed feedback (after adding more seeds)
```

### Checking Scan Progress
```
1. Run: 12 → Export scan progress report
2. Open the XLSX file → check "By Directory" sheet
3. Look for directories with high "Pending" counts
```

---

## Understanding the config.yaml Settings

### Key Settings Quick Reference

| Setting | What It Does | Default |
|---------|-------------|---------|
| `workspace.root` | Where the tool stores its data | *Must set* |
| `scan.folder_path` | Where your photos are | *Must set* |
| `organization.output_folder` | Where organized photos go | *Must set* |
| `organization.operation` | `copy` = keep originals, `move` = relocate | `copy` |
| `organization.folder_structure` | `flat`, `year`, or `year-month-date` | `year` |
| `scan.recursive` | Scan sub-folders? | `true` |
| `duplicates.enabled` | Detect duplicate photos? | `true` |
| `blur_detection.enabled` | Mark blurry photos? | `true` |
| `faces.enabled` | Enable face features? | `true` |
| `processing.threads` | Parallel workers (higher = faster scan) | `4` |
| `processing.fast_mode` | Skip some checks for speed | `false` |

### Organization: Copy vs Move

```yaml
organization:
  operation: "copy"   # Keeps originals in scan folder
  operation: "move"   # Moves photos to organized folder (originals gone)
```

> **Recommendation:** Use `copy` until you are confident the organized output looks correct. Only switch to `move` once you have verified everything is in order.

### Folder Structure Options

```yaml
organization:
  folder_structure: "year"             # → Organized/2023/photo.jpg
  folder_structure: "year-month-date"  # → Organized/2023/June/2023-06-15/photo.jpg
  folder_structure: "flat"             # → Organized/photo.jpg
```

### Duplicate Detection

```yaml
duplicates:
  enabled: true           # Turn on/off
  hash_algorithm: "md5"   # How duplicates are detected (md5 is reliable)
  selection_criteria:
    - quality             # Keep the highest quality copy
    - resolution          # Prefer higher resolution
    - date                # Prefer earlier date
    - size                # Prefer larger file
```

### Face Detection

```yaml
faces:
  enabled: true
  similarity_threshold: 0.35   # Lower = stricter matching (fewer false positives)
  untagged_max_samples: 1      # How many sample photos to export per unknown person
  export_untagged: true        # Export unknowns for manual review
```

### Excel Sheets — Turn On/Off

```yaml
output:
  sheets:
    all_images: true       # Main sheet with all photos
    blurry_images: true    # Photos detected as blurry
    duplicates: true       # Duplicate groups
    similar_images: true   # Visually similar photos
    summary: true          # Stats overview
    quality_report: true   # Quality scores
    analytics: true        # Storage analytics
    clusters: true         # Photo clusters (if clustering enabled)
```

---

## Troubleshooting

### "Config.yaml error" on startup
- Open `config.yaml` and check that `workspace.root` and `scan.folder_path` are set to real folders that exist on your PC.

### Scan is very slow
- Set `processing.threads` to a higher number (e.g. `8`) if your PC has more CPU cores.
- Set `processing.fast_mode: true` to skip some slower checks.
- Turn off `similar_detection.enabled: false` — similar image detection is slow.

### Excel file not generated
- Run option 21 first to build the metadata vault.
- Check `workspace/logs/image-scanner.log` for error messages.

### Photos not being organized
- Make sure you have run option 31 to generate the Excel first.
- The Excel file path shown in option 41 must exist and be readable.

### Face detection not working
- Make sure `faces.enabled: true` in config.yaml.
- You need seed photos placed in `workspace/seed/<person_name>/`.
- Run option 51 first before option 52.

### "No records" message
- You need to run option 21 (Build Metadata Vault) before most other options work.

---

## Output Folder Structure

After running the tool, your workspace folder will look like this:

```
workspace/
├── metadata/           ← Database of photo information (JSON files)
├── face_data/          ← Face index database
├── untagged_people/    ← Unknown faces exported for review
├── seed/               ← Your seed photos for known people
├── reports/            ← Excel workbooks
├── folder_analysis/    ← Scan progress reports
├── comparisons/        ← HTML comparison pages for duplicates
├── logs/               ← Log files
├── checkpoints/        ← Scan progress checkpoints
├── quarantine/         ← Photos moved here by delete action
└── records-backup.pkl  ← Backup of latest scan data
```

---

*This guide covers Image Scanner v5.4. For technical details and developer reference, see [DEVELOPER_REFERENCE.md](DEVELOPER_REFERENCE.md).*
