## 2025-05-14 - Initial Assessment of Image Scanner v5.1
**Learning:** The MetadataStore architecture relies on thousands of individual JSON files. This results in an O(N) file I/O bottleneck during 'load_records' which is used for Excel generation and organization. Scanning also exhibits redundant disk I/O by opening images multiple times for EXIF, processing, and thumbnails.
**Action:** Prioritize optimizations that either reduce file I/O operations or utilize faster serialization for the metadata vault.
## 2025-05-14 - Parallelization Overhead on Small I/O Tasks
**Learning:** For extremely fast, purely local I/O and JSON parsing (like loading small metadata files), the overhead of 'ThreadPoolExecutor' in 'ParallelProcessor' actually made the process significantly slower (from ~0.4s to ~1.8s for 2000 files). This is likely due to the high volume of very short-lived tasks and the Python GIL.
**Action:** Always benchmark parallelization on the specific task size and environment. For metadata loading, sequential processing is actually more efficient unless the files are on a high-latency network share.
