# Image Scanner v5.1 Technical Analysis & Guide

## Redesigned Menu Breakdown (main.py)

The menu has been reorganized into logical functional blocks for better usability.

### Category: CORE WORKFLOW
| Option | Task Name | Description | What's Missing / Can be Added |
| :--- | :--- | :--- | :--- |
| **1** | **Full Automatic Flow** | Sequence: Scan -> Delete Marked -> Organize. Ideal for one-click processing. | Missing a "Dry Run" mode to see what would happen before any files are moved or deleted. |
| **2** | **Scan & Extract** | Pure scanning phase. Computes hashes, detects duplicates/blur, and builds the initial Metadata Store. | Could add "Delta Scanning" to only scan files changed since the last run. |
| **3** | **Resume / Regenerate** | Rebuilds the Excel report using existing sidecar JSON files without touching the original media. | Needs an option to "Sync Metadata" (backfill missing tags into JSONs from existing Excel edits). |
| **4** | **Execute Deletions** | Deletes files marked 'Yes' in the Excel report. | **Safety Gap**: Should move files to a `.trash` folder instead of permanent `unlink`. |
| **5** | **Organize Files** | The filing engine. Groups photos into date-based folders according to configuration. | Needs an "Undo" feature to reverse the last organization operation. |

### Category: AI & VISUAL TOOLS
| Option | Task Name | Description | What's Missing / Can be Added |
| :--- | :--- | :--- | :--- |
| **6** | **Face Discovery Suite** | Submenu for Building Face Index (embeddings) and Finding People (seed search). | Interactive "Face Review": Show a cluster of unknown faces and let the user tag them in-app. |
| **7** | **Visual Comparisons** | Generates side-by-side HTML comparison pages for duplicate/similar groups. | Currently static; could be an interactive web view where you can click "Keep This" or "Delete That". |
| **8** | **Web Dashboard** | Launches the Streamlit dashboard for a visual overview of the library. | Integration: Let the user perform actions (like tagging) directly from the dashboard. |

### Category: MAINTENANCE
| Option | Task Name | Description | What's Missing / Can be Added |
| :--- | :--- | :--- | :--- |
| **9** | **Convert Structure** | Migrates organized library between Flat, Year, and Month hierarchies. | Path Safety: Should verify destination disk space before starting large moves. |
| **10** | **Merge Same-Date** | Consolidates multiple folders from the same date into one. | Smarter Merging: Merge even if folder names have slight suffix differences (with user approval). |

---

## Deep Dive: Face Data vs. Untagged People

A common point of confusion is the difference between these two:

*   **Face Data**: This is "raw" detection. During a scan, the tool identifies *how many* faces are in a photo and categorizes it (e.g., "Portrait" if 1 face, "Group" if 5 faces). It doesn't know *who* the people are.
*   **Untagged People**: These are detected faces that haven't been matched to a specific identity yet.

**How to resolve same people in multiple folders?**
If the same person appears across many folders, you can resolve this using **Option 6 -> Find Person**. By providing "seed photos" (photos you know are of that person), the tool will search the entire library—regardless of which folder the files are in—and link them to a single name (label) in your Excel report and Metadata Store.

*Note: This resolves their identity in the records, but it does not physically move all their photos into one folder.*

---

## Deep Dive: What happens when you delete photos?

When you use **Option 4 (Execute Deletions)**, it is important to understand its limitations:

1.  **Metadata remains**: The tool only deletes the image or video file itself. It does **not** delete the corresponding JSON file in the `metadata/` folder. These files become "orphans"—they stay on your disk but no longer point to an active photo.
2.  **Folder counts are NOT updated**: If a folder is named `2023-05-01-0010pic-beach` and you delete 5 photos from it, the folder name will **still** say `0010pic`. The tool does not automatically rename folders after a deletion.

**Recommendation**: After a large deletion, if you want your folder counts to be accurate again, you should run **Option 9 (Convert)** followed by **Option 10 (Merge)**. This will force the tool to re-scan the folders and update the `xxxxpic` counts in the names.

---

## Debugging & Technical Risks

During a technical review of the v5.1 codebase, the following risks and "gotchas" were identified:

1.  **Metadata Path Sensitivity**: The system uses a SHA1 hash of the **absolute file path** as the key for its metadata JSON files.
    *   *Risk*: If you move a file manually (e.g., via Windows Explorer), the path changes, and the tool can no longer find the existing metadata. A re-scan will treat it as a brand new file with no tags or scores.
2.  **Excel-Dependent Deletion**: Option 4 relies entirely on the text values in the Excel file.
    *   *Risk*: If you accidentally drag-and-drop or use "Fill Down" in Excel on the `DELETE?` column, you could delete your entire library with one confirmation.
3.  **Heavy AI Dependencies**: Features like Face Indexing (Option 6) require `torch` and `facenet-pytorch`.
    *   *Risk*: These are large, complex libraries. If they aren't installed correctly, the tool will fail gracefully but these options will simply do nothing.
4.  **Implicit Folder Naming**: Option 10 (Merge) relies on a very specific regex for folder names (e.g., `yyyy-mm-dd...`).
    *   *Risk*: If you name your folders manually in a different format, the Merge tool won't "see" them.
5.  **Subprocess Vulnerability**: Option 8 launches Streamlit using a subprocess.
    *   *Risk*: On some systems, `sys.executable` might not point to the environment where Streamlit is installed, causing the dashboard to fail to launch.

---

## Better Approaches & Missing Features (Architectural)

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
**Current**: Option 4 shows a count and asks for confirmation.
**Better**: Option 4 should generate a "Trash" folder and move files there first instead of permanently deleting them (`unlink`), allowing for a final human review before the trash is emptied.

### 5. Delta-Scanning (Recommended)
**Current**: Scanning large libraries can still be slow as it checks every file.
**Better**: Use a "Last Scanned" timestamp on folders. If the folder hasn't changed since the last run, skip it entirely to make re-scans near-instant.
