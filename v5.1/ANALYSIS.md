# Image Scanner v5.1 Technical Analysis & Guide

## Redesigned Menu Structure (v5.1)

The menu has been reorganized into logical functional blocks to streamline the photo management workflow and remove redundant steps.

### Category: 1. FULL WORKFLOW
| Option | Task Name | Description | Future Enhancements |
| :--- | :--- | :--- | :--- |
| **1** | **FULL AUTOMATIC FLOW** | The recommended "one-click" sequence: Scan -> Report -> Delete -> Organize. | Add a "Dry Run" mode to preview moves/deletions without touching files. |

### Category: 2. DATA MANAGEMENT
| Option | Task Name | Description | Future Enhancements |
| :--- | :--- | :--- | :--- |
| **2 -> 1** | **New Scan** | Scans folders, computes hashes, detects duplicates/blur, and builds the Metadata Store. | "Delta Scanning" to skip folders that haven't changed since the last run. |
| **2 -> 2** | **Generate Excel** | Rebuilds the Excel report using existing Metadata Store JSON files. | "Sync Metadata": Read manual tag edits from Excel back into the JSON files. |
| **2 -> 3** | **Execute Deletions** | **SAFE CASCADE**: Deletes media files AND their metadata. Files are moved to `.trash/`. | Automated trash cleanup (e.g., delete files older than 30 days). |
| **2 -> 4** | **Vault Maintenance** | Combined tool to fix broken file paths and remove duplicate JSON records. | Progress indicator for very large metadata vaults. |
| **2 -> 5** | **Cleanup Untagged** | Removes sample folders for people who have since been identified. | - |

### Category: 3. LIBRARY TOOLS
| Option | Task Name | Description | Future Enhancements |
| :--- | :--- | :--- | :--- |
| **3 -> 1** | **Organize Library** | Files photos into date-based folders. Now saves an Undo Log automatically. | Path Safety: Verify destination disk space before starting large moves. |
| **3 -> 2** | **Convert Structure** | Refactors existing library between Flat, Year, and Month hierarchies. | - |
| **3 -> 3** | **Merge Same-Date** | Consolidates multiple folders from the same date into one. | Smarter Merging: Merge even if folder names have slight suffix differences. |
| **3 -> 4** | **Rollback (Undo)** | **NEW**: Fully reverses the last organization session using the Undo Log. | - |

### Category: 4. AI & FACE DISCOVERY
| Option | Task Name | Description | Future Enhancements |
| :--- | :--- | :--- | :--- |
| **4 -> 1** | **Face Index** | Scans the library to create AI embeddings for every face found. | Hardware Acceleration: Support for GPU (CUDA) to speed up embedding. |
| **4 -> 2** | **People Tag Sync** | Matches faces against "Seed Photos" and exports unknown samples for review. | Interactive UI: A way to click "Yes/No" on identified faces in the browser. |
| **4 -> 3** | **Seed Feedback** | Re-runs identification after you've updated your Seed Photos. | Auto-Discovery: Cluster unknown people and ask the user to name them. |

---

## Deep Dive: Key Architectural Features

### 1. Hash-Based Metadata (Implemented)
Metadata sidecar files are now named using the file's **MD5 content hash** (e.g., `hash-abc123...json`).
*   **Benefit**: Metadata now "follows" the file. If you move or rename a photo manually using your OS, the tool will still find its faces, tags, and blur scores as soon as it re-scans the file content.

### 2. Safe Cascade Deletion (Implemented)
When you delete photos through the tool:
*   The media file is moved to a hidden `.trash` folder (not permanently unlinked).
*   The associated Metadata JSON is deleted.
*   Face Index entries and untagged samples are removed.
*   *Note: Folder counts (the `xxxxpic` names) still require a manual refresh via Convert/Merge to update.*

### 3. Organization Rollback (Implemented)
Every "Organize" operation now generates an `organize_undo_log.json`.
*   **Benefit**: If you make a mistake or don't like a new structure, you can use the **Rollback** option to move everything back to its exact original location.

---

## Technical Risks & Debugging Notes

1.  **Excel Dependency**: The tool relies heavily on the "DELETE?" column in the Excel report. **Do not** modify the sheet names or column headers, as this will cause Task 2 and 3 to fail.
2.  **Silent Error Handling**: The code uses many `except Exception` blocks to ensure high-volume processing doesn't crash. While stable, this can occasionally hide errors (like a single corrupted image failing to be indexed). Check the `logs/` folder if you suspect data is missing.
3.  **Pathing**: The tool expects a consistent `workspace.root` in `config.yaml` to store all its internal data.
