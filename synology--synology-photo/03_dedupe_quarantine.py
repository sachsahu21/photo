\
#!/usr/bin/env python3
import os
import csv
from pathlib import Path
from datetime import datetime

# ===== CONFIGURE =====
TARGET_DIR = Path("/volume2/photo/Photos-Not-Found-In-Primary")
OUTPUT_CSV = Path("/volume2/reports/photos-not-found-in-primary-dedupe.csv")
# =====================

IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp",
    ".gif", ".webp", ".heic", ".heif", ".dng",
    ".raw", ".cr2", ".cr3", ".nef", ".arw", ".orf", ".rw2",
    ".srw", ".raf", ".pef", ".3fr", ".erf", ".kdc", ".mrw",
    ".nrw", ".x3f"
}

SKIP_EXTENSIONS = {
    ".xmp", ".aae", ".pp3", ".dop", ".on1",
    ".txt", ".json", ".xml",
    ".db", ".ini", ".dat",
    ".thm", ".thumb",
    ".mov", ".mp4", ".avi", ".mkv", ".mts", ".m2ts",
    ".lrcat", ".lrdata"
}

SKIP_DIR_NAMES = {
    "@eaDir",
    "#recycle",
    "@tmp",
    ".@__thumb",
    ".Trash",
    ".Trashes",
    "Backup-Photos"
}

SKIP_FILE_NAMES = {
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini"
}

EXTENSION_PRIORITY = {
    ".heic": 1,
    ".heif": 1,
    ".dng": 2,
    ".raw": 2,
    ".cr3": 2,
    ".cr2": 2,
    ".nef": 2,
    ".arw": 2,
    ".orf": 2,
    ".rw2": 2,
    ".raf": 2,
    ".jpg": 3,
    ".jpeg": 3,
    ".tif": 4,
    ".tiff": 4,
    ".png": 5,
    ".webp": 6,
    ".bmp": 7,
    ".gif": 8
}

def format_time(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")

def is_valid_photo_file(path: Path) -> bool:
    name = path.name
    suffix = path.suffix.lower()

    if name in SKIP_FILE_NAMES:
        return False
    if name.startswith("."):
        return False
    if suffix in SKIP_EXTENSIONS:
        return False
    if suffix not in IMAGE_EXTENSIONS:
        return False
    return True

def should_skip_dir(dir_name: str) -> bool:
    return dir_name in SKIP_DIR_NAMES or dir_name.startswith(".")

def normalized_stem(path: Path) -> str:
    return path.stem.lower()

def extension_rank(path: Path) -> int:
    return EXTENSION_PRIORITY.get(path.suffix.lower(), 99)

def build_keep_sort_key(entry: dict):
    return (
        extension_rank(entry["path"]),
        -entry["size_bytes"],
        -entry["mtime"],
        str(entry["path"]).lower(),
    )

def recommendation(entry: dict, keep_entry: dict) -> str:
    if entry["path"] == keep_entry["path"]:
        return "KEEP"

    e_ext = entry["path"].suffix.lower()
    k_ext = keep_entry["path"].suffix.lower()

    if e_ext in {".jpg", ".jpeg"} and k_ext in {".heic", ".heif"}:
        return "REMOVE_JPG_HAS_HEIC"
    if e_ext == k_ext and entry["size_bytes"] < keep_entry["size_bytes"]:
        return "REMOVE_SMALLER_SAME_FORMAT"
    if e_ext == k_ext:
        return "REVIEW_SAME_FORMAT"
    return "REVIEW_CROSS_FORMAT"

def main():
    if not TARGET_DIR.exists():
        raise FileNotFoundError(f"TARGET_DIR not found: {TARGET_DIR}")

    print(f"Scanning only: {TARGET_DIR}")
    groups = {}
    scanned = 0
    skipped = 0

    for root, dirs, files in os.walk(TARGET_DIR):
        root_path = Path(root)
        dirs[:] = [d for d in dirs if not should_skip_dir(d)]

        for name in files:
            path = root_path / name

            if not is_valid_photo_file(path):
                continue

            try:
                stat = path.stat()
                key = normalized_stem(path)

                entry = {
                    "path": path,
                    "size_bytes": stat.st_size,
                    "mtime": stat.st_mtime,
                }

                groups.setdefault(key, []).append(entry)
                scanned += 1

            except Exception as e:
                print(f"SKIP: {path} -> {e}")
                skipped += 1

    duplicate_groups = {k: v for k, v in groups.items() if len(v) > 1}

    print("Writing CSV report...")
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([
            "group_id",
            "status",
            "recommendation",
            "file_name",
            "full_path",
            "relative_path",
            "extension",
            "size_bytes",
            "modified_time",
            "basename_key",
            "kept_file_path",
            "kept_extension",
            "kept_size_bytes",
            "group_file_count"
        ])

        group_id = 0

        for basename_key in sorted(duplicate_groups.keys()):
            group_id += 1
            files = sorted(duplicate_groups[basename_key], key=build_keep_sort_key)
            keep_entry = files[0]

            for idx, entry in enumerate(files):
                writer.writerow([
                    group_id,
                    "keep" if idx == 0 else "duplicate_candidate",
                    recommendation(entry, keep_entry),
                    entry["path"].name,
                    str(entry["path"]),
                    str(entry["path"].relative_to(TARGET_DIR)),
                    entry["path"].suffix.lower(),
                    entry["size_bytes"],
                    format_time(entry["mtime"]),
                    basename_key,
                    str(keep_entry["path"]),
                    keep_entry["path"].suffix.lower(),
                    keep_entry["size_bytes"],
                    len(files)
                ])

    print("Done.")
    print(f"Files scanned in target folder: {scanned}")
    print(f"Duplicate groups found: {len(duplicate_groups)}")
    print(f"Skipped: {skipped}")
    print(f"CSV written to: {OUTPUT_CSV}")

if __name__ == "__main__":
    main()
