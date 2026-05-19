# Image Scanner v5.1 Technical Analysis & Guide

## Redesigned Menu Breakdown (main.py)

The menu has been reorganized into logical functional blocks for better usability.

### Category: FULL WORKFLOW
| Option | Task Name | Description | What's Missing / Can be Added |
| :--- | :--- | :--- | :--- |
| **1** | **FULL AUTOMATIC FLOW** | Sequence: Scan -> Excel -> Delete -> Organize. The "one-click" way to process a new dump of photos. | Missing a "Dry Run" mode to preview moves/deletions without actually touching files. |

### Category: DATA MANAGEMENT
| Option | Task Name | Description | What's Missing / Can be Added |
| :--- | :--- | :--- | :--- |
| **2 -> 1** | **New Scan** | Pure scanning phase. Computes hashes, detects duplicates/blur, and builds the Metadata Store. | Could add "Delta Scanning" to skip folders that haven't changed since the last run. |
| **2 -> 2** | **Generate Excel** | Rebuilds the Excel report using existing sidecar JSON files (the Metadata Store). | Needs an option to "Sync Metadata" (read manual tag edits from Excel back into the JSON files). |
| **2 -> 3** | **Execute Deletions** | Reads the Excel report and deletes files marked 'Yes'. | **Safety Gap**: Should move files to a `.trash` folder first instead of permanent deletion. |
| **2 -> 4** | **Vault Maintenance** | Combined tool to fix broken file paths in metadata and remove duplicate JSON records. | Progress indicator for large metadata vaults. |

### Category: LIBRARY TOOLS
| Option | Task Name | Description | What's Missing / Can be Added |
| :--- | :--- | :--- | :--- |
| **3 -> 1** | **Organize from Excel** | The filing engine. Groups photos into date-based folders according to configuration. | Needs an "Undo" feature to reverse the last organization operation. |
| **3 -> 2** | **Convert Structure** | Migrates organized library between Flat, Year, and Month hierarchies. | Path Safety: Should verify destination disk space before starting large moves. |
| **3 -> 3** | **Merge Same-Date** | Consolidates multiple folders from the same date into one. | Smarter Merging: Merge even if folder names have slight suffix differences. |

### Category: AI & FACE DISCOVERY
| Option | Task Name | Description | What's Missing / Can be Added |
| :--- | :--- | :--- | :--- |
| **4 -> 1** | **Face Index** | Scans the library to create AI embeddings for every face found, storing them in SQLite. | Hardware Acceleration: Support for GPU (CUDA) to speed up embedding generation. |
| **4 -> 2** | **People Tag Sync** | Matches indexed faces against "Seed Photos" and exports untagged samples for review. | Interactive UI: A way to click "Yes/No" on identified faces in the browser. |
| **4 -> 3** | **Seed Feedback** | Re-runs the identification logic after you've updated your Seed Photos. | Auto-Discovery: Cluster unknown people and ask the user to name them. |

---

## Deep Dive: Face Data vs. Untagged People

A common point of confusion is the difference between these two:

*   **Face Data**: This is "raw" detection. During a scan, the tool identifies *how many* faces are in a photo and categorizes it (e.g., "Portrait" if 1 face, "Group" if 5 faces). It doesn't know *who* the people are.
*   **Untagged People**: These are detected faces that haven't been matched to a specific identity yet.

**How to resolve same people in multiple folders?**
If the same person appears across many folders, you can resolve this using **Option 4 -> 2 (People Tag Sync)**. By providing "seed photos" (photos you know are of that person), the tool will search the entire library—regardless of which folder the files are in—and link them to a single name (label) in your Excel report and Metadata Store.

---

## Deep Dive: What happens when you delete photos?

When you use **Option 2 -> 3 (Execute Deletions)**, it is important to understand its limitations:

1.  **Metadata remains**: The tool only deletes the image or video file itself. It does **not** delete the corresponding JSON file in the `metadata/` folder. These files become "orphans"—they stay on your disk but no longer point to an active photo.
2.  **Folder counts are NOT updated**: If a folder is named `2023-05-01-0010pic-beach` and you delete 5 photos from it, the folder name will **still** say `0010pic`. The tool does not automatically rename folders after a deletion.

**Recommendation**: After a large deletion, if you want your folder counts to be accurate again, you should run **Option 3 -> 2 (Convert)** followed by **Option 3 -> 3 (Merge)**. This will force the tool to re-scan the folders and update the counts in the names.

---

## Debugging & Technical Risks

During a technical review of the v5.1 codebase, the following risks and "gotchas" were identified:

1.  **Metadata Path Sensitivity**: The system uses a SHA1 hash of the **absolute file path** as the key for its metadata JSON files.
    *   *Risk*: If you move a file manually (e.g., via Windows Explorer), the path changes, and the tool can no longer find the existing metadata. A re-scan will treat it as a brand new file with no tags or scores.
2.  **Excel-Dependent Deletion**: Deletion relies entirely on the text values in the Excel file.
    *   *Risk*: If you accidentally drag-and-drop or use "Fill Down" in Excel on the `DELETE?` column, you could delete your entire library with one confirmation.
3.  **Silent Error Handling**: The code contains many generic `except Exception` blocks that silently swallow errors.
    *   *Risk*: While this prevents the app from crashing, it means processing failures for specific files are often hidden from the user, making troubleshooting difficult.
4.  **Implicit Folder Naming**: Merge tool (Option 3 -> 3) relies on a very specific regex for folder names (e.g., `yyyy-mm-dd...`).
    *   *Risk*: If you name your folders manually in a different format, the Merge tool won't "see" them.

---

## Better Approaches (Recommended Improvements)

1.  **Hash-Based Metadata**: Use file content MD5 instead of file paths as keys for JSON metadata. This allows metadata to survive manual file moves.
2.  **Organization Rollback**: Add a log-based rollback feature to undo "Organize" operations.
3.  **Trash Folder**: Instead of `unlink`, move deleted files to a temporary `.trash` directory for a 30-day safety period.
4.  **Unified UI**: Transition from a CLI menu to a modern web UI (Streamlit) for all operations to allow for visual review of AI results.
