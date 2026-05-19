# Image Scanner v5.1 Technical Analysis & Guide

## Detailed Menu Breakdown (main.py)

| Option | Task Name | Description |
| :--- | :--- | :--- |
| **1** | **Scan & Extract** | Performs a full scan of the source folder. Computes hashes, detects duplicates/similar images, runs blur detection, and extracts metadata into the Metadata Store and an Excel report. |
| **1b** | **Resume Excel** | Reloads records from the Metadata Store or backup file to regenerate the Excel report without re-scanning the files. |
| **2** | **Delete Marked** | Reads the Excel report and physically deletes files that have a 'Yes' or 'True' in the `DELETE?` column. |
| **3** | **Organize** | Moves or copies files into the structured library (e.g., date-based folders) based on the scan records and configuration. |
| **4** | **Full (1>2>3)** | A shortcut that runs the Scan, then asks to Delete, then asks to Organize in one sequence. |
| **5** | **Web Dashboard** | Launches an external Streamlit application for a visual, browser-based view of the scan results. |
| **6** | **Comparisons** | Generates HTML pages allowing side-by-side visual comparison of duplicate and similar image groups. |
| **7** | **Convert Structure**| Refactors an *already organized* library between hierarchies (Flat vs. Year vs. Year-Month-Date). |
| **8** | **Merge Folders** | Detects folders from the same date (e.g., from different scan batches) and merges them into a single folder. |
| **9** | **Face Index** | Scans the library to create AI embeddings for every face found, storing them in a SQLite database. |
| **10** | **Find Person** | Uses "Seed Photos" to find and tag a specific person across the entire library using the Face Index. |
| **0** | **Exit** | Safely closes the application. |

---

## Debugging & Technical Risks

During a technical review of the v5.1 codebase, the following risks and "gotchas" were identified:

1.  **Metadata Path Sensitivity**: The system uses a SHA1 hash of the **absolute file path** as the key for its metadata JSON files.
    *   *Risk*: If you move a file manually (e.g., via Windows Explorer), the path changes, and the tool can no longer find the existing metadata. A re-scan will treat it as a brand new file with no tags or scores.
2.  **Excel-Dependent Deletion**: Task 2 relies entirely on the text values in the Excel file.
    *   *Risk*: If you accidentally drag-and-drop or use "Fill Down" in Excel on the `DELETE?` column, you could delete your entire library with one confirmation.
3.  **Heavy AI Dependencies**: Features like Face Indexing (Task 9/10) require `torch` and `facenet-pytorch`.
    *   *Risk*: These are large, complex libraries. If they aren't installed correctly, the tool will fail gracefully but these options will simply do nothing.
4.  **Implicit Folder Naming**: Task 8 (Merge) relies on a very specific regex for folder names (e.g., `yyyy-mm-dd...`).
    *   *Risk*: If you name your folders manually in a different format, the Merge tool won't "see" them.
5.  **Subprocess Vulnerability**: Task 5 launches Streamlit using a subprocess.
    *   *Risk*: On some systems, `sys.executable` might not point to the environment where Streamlit is installed, causing the dashboard to fail to launch.

---

## Better Approaches & Missing Features

If you are looking to improve the tool, here are the top recommendations:

### 1. Hash-Based Metadata (Recommended)
**Current**: Metadata filename = `hash(absolute_path).json`
**Better**: Metadata filename = `hash(file_content_md5).json`
*Why*: This makes metadata "follow" the file. If you move or rename the file manually, the tool can still find its scores and face tags by looking at the file's content hash.

### 2. Organization Rollback (Missing)
**Current**: Once you move files into folders, there is no automatic way to put them back where they were.
**Better**: Add a "Rollback" or "Undo" feature that uses a `mapping.json` log to move files back to their original source paths.

### 3. Integrated Face Management (Missing)
**Current**: You have to manually put "Seed Photos" in a specific folder to identify people.
**Better**: An interactive interface where the tool shows you a face and asks, "Is this Sachin?" Once you say yes, it automatically builds the person's profile.

### 4. Safe-Delete Preview (Recommended)
**Current**: Task 2 shows a count and asks for confirmation.
**Better**: Task 2 should generate a "Trash" folder and move files there first instead of permanently deleting them (`unlink`), allowing for a final human review before the trash is emptied.

### 5. Delta-Scanning (Recommended)
**Current**: Scanning large libraries can still be slow as it checks every file.
**Better**: Use a "Last Scanned" timestamp on folders. If the folder hasn't changed since the last run, skip it entirely to make re-scans near-instant.
