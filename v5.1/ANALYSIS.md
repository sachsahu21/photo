# Analysis of Image Scanner v5.1

## Activities

Image Scanner v5.1 is a comprehensive tool for managing, analyzing, and organizing photo and video libraries. Its primary activities include:

1.  **Media Scanning & Extraction**:
    *   Recursively scans folders for images and videos.
    *   Extracts technical metadata (dimensions, format, size).
    *   Reads EXIF data (camera model, date taken, GPS coordinates) from images.
    *   Extracts video metadata using tools like `ffprobe` or `MediaInfo`.

2.  **Quality Assessment**:
    *   **Blur Detection**: Calculates a blur score for images to identify out-of-focus shots.
    *   **Quality Scoring**: Assigns an overall quality rating based on resolution, blur, and EXIF presence.

3.  **Duplicate & Similarity Handling**:
    *   **Exact Duplicates**: Uses MD5 hashing to find identical files.
    *   **Similar Images**: Uses various hashing techniques (aHash, pHash, dHash) and color histograms to find visually similar photos (e.g., bursts or near-misses).
    *   **Best Copy Selection**: Automatically marks which file in a duplicate group should be kept based on quality and resolution.

4.  **Advanced AI Features**:
    *   **Face Detection & Search**: Detects faces in images and can search for specific people across the library using "seed" photos.
    *   **Auto-Tagging**: Uses AI models (like MobileNet) to suggest tags for images.
    *   **Image Clustering**: Groups similar images together based on visual features.

5.  **Data Persistence (New in v5.1)**:
    *   **Metadata Store**: Saves extracted information into individual JSON files for every media item. This allows for faster subsequent scans and easier integration with other tools.
    *   **Face Index**: Maintains a SQLite database for face embeddings to enable fast person-searching.

6.  **Organization & Maintenance**:
    *   **Date-Based Filing**: Automatically moves or copies files into structured folders (e.g., `2023/2023-10-25-0042pic-beach`).
    *   **Screenshot Separation**: Detects and moves screenshots into separate folders.
    *   **Folder Conversion**: Can change the entire library structure between "flat", "year", or "year-month-date" hierarchies.
    *   **Merge Folders**: Combines folders from the same date to keep the library tidy.

7.  **Reporting & Visualization**:
    *   **Excel Reports**: Generates detailed workbooks listing all images, blurry files, duplicates, and analytics.
    *   **Visual Comparisons**: Creates HTML pages to compare duplicate or similar images side-by-side.
    *   **Web Dashboard**: Offers a Streamlit-based dashboard for interactive exploration of the library.

---

## Deep Dive: Face Data vs. Untagged People

A common point of confusion is the difference between these two:

*   **Face Data**: This is "raw" detection. During a scan, the tool identifies *how many* faces are in a photo and categorizes it (e.g., "Portrait" if 1 face, "Group" if 5 faces). It doesn't know *who* the people are.
*   **Untagged People**: These are detected faces that haven't been matched to a specific identity yet.

**How to resolve same people in multiple folders?**
If the same person appears across many folders, you can resolve this using **Task 10 (Find Person)**. By providing "seed photos" (photos you know are of that person), the tool will search the entire library—regardless of which folder the files are in—and link them to a single name (label) in your Excel report and Metadata Store.

*Note: This resolves their identity in the records, but it does not physically move all their photos into one folder.*

---

## Deep Dive: Step 7 (Convert Folder Structure)

**Step 7** is a powerful utility used **after** you have already organized your photos. If you decide you don't like your current folder layout, Step 7 lets you change it without re-scanning everything.

It converts between three styles:
1.  **Flat**: All date-folders in one big list.
2.  **Year**: Folders grouped by year (e.g., `2023/2023-01-01...`).
3.  **Year-Month-Date**: Folders grouped by year and then month (e.g., `2023/01-Jan/2023-01-01...`).

It is highly recommended to run **Step 8 (Merge Same-Date Folders)** after using Step 7 to ensure any folders that ended up in the same place are combined.

---

## Dos and Don'ts

### Dos
*   **Do use `copy` operation first**: When organizing files for the first time, use `operation: copy` in `config.yaml` to ensure the results are what you expect before deleting originals.
*   **Do install optional dependencies**: For the best results, ensure `ffprobe` (FFmpeg) and `MediaInfo` are installed on your system for accurate video metadata.
*   **Do use the Metadata Store**: Keep the `metadata` feature enabled. It creates a robust sidecar JSON for every file, which is much faster to "resume" than re-scanning thousands of images.
*   **Do review the Excel report before deleting**: Always check the `Duplicates` sheet in the generated Excel file and use the `DELETE?` column to mark files before running the "Delete Marked" task.
*   **Do keep backups**: Especially when using the `move` operation or the "Delete Marked" feature, ensure you have a separate backup of your precious memories.
*   **Do tune the Blur Threshold**: If too many good photos are marked as blurry, increase the `blur_detection.threshold` in `config.yaml`.

### Don'ts
*   **Don't interrupt the initial scan**: Large libraries can take time. v5.1 has checkpointing, but it's best to let the first full scan complete to build the initial Metadata Store.
*   **Don't move files manually after scanning**: If you move files on disk outside of the tool, the system will **lose their metadata**. Because metadata is linked to the exact file path, moving or renaming a file manually makes it look like a "new" file to the scanner, and it will lose all previously detected faces, tags, or blur scores. Always use the tool's "Organize" or "Convert" features to move files safely.
*   **Don't ignore the "fast_mode"**: If you have a massive library and only care about basic organization, enable `processing.fast_mode` to skip expensive AI features like face detection and blur analysis.
*   **Don't use high thread counts on Cloud/OneDrive folders**: If scanning folders synced with OneDrive or Google Drive, set `processing.threads` to 1 or 2 to avoid overwhelming the sync client or triggering massive simultaneous downloads.
*   **Don't delete the `face_index.sqlite` file**: If you've spent time building a face index or identifying people, deleting this file will force you to re-index the entire library.
