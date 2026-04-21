\
#!/usr/bin/env python3
import os
import csv
from pathlib import Path
from datetime import datetime

# ===== CONFIGURE =====
PHOTO_ROOT = Path("/volume2/photo")
QUARANTINE_DIR = PHOTO_ROOT / "Photos-Not-Found-In-Primary"
OUTPUT_CSV = Path("/volume2/reports/quarantine-photo-classification.csv")
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

EXCLUDED_DIRS = {
    "Backup-Photos",
    "Photos-Not-Found-In-Primary"
}

SKIP_DIR_NAMES = {
    "@eaDir",
    "#recycle",
    "@tmp",
    ".@__thumb",
    ".Trash",
    ".Trashes"
}

SKIP_FILE_NAMES = {
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini"
}

def format_time(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")

def is_valid_photo_file(path: Path) -> bool:
    name = path.name
    suffix = path.suffix.lower()

    if name in SKIP_FILE_NAMES or name.startswith("."):
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

def main():
    if not PHOTO_ROOT.exists():
        raise FileNotFoundError(f"PHOTO_ROOT not found: {PHOTO_ROOT}")
    if not QUARANTINE_DIR.exists():
        raise FileNotFoundError(f"QUARANTINE_DIR not found: {QUARANTINE_DIR}")

    print("Indexing PRIMARY library (excluding Backup and Quarantine)...")

    primary_exact = {}
    primary_stem = {}

    primary_count = 0
    quarantine_count = 0
    skipped = 0

    for root, dirs, files in os.walk(PHOTO_ROOT):
        root_path = Path(root)

        pruned_dirs = []
        for d in dirs:
            if d in EXCLUDED_DIRS:
                continue
            if should_skip_dir(d):
                continue
            pruned_dirs.append(d)
        dirs[:] = pruned_dirs

        for name in files:
            path = root_path / name

            if not is_valid_photo_file(path):
                continue

            try:
                primary_exact.setdefault(path.name.lower(), []).append(path)
                primary_stem.setdefault(normalized_stem(path), []).append(path)
                primary_count += 1
            except Exception as e:
                print(f"SKIP primary: {path} -> {e}")
                skipped += 1

    print("Classifying quarantine files...")

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([
            "file_name",
            "full_path",
            "relative_path",
            "extension",
            "size_bytes",
            "modified_time",
            "classification",
            "exact_match_count",
            "stem_match_count",
            "exact_match_paths",
            "stem_match_paths"
        ])

        for root, dirs, files in os.walk(QUARANTINE_DIR):
            root_path = Path(root)
            dirs[:] = [d for d in dirs if not should_skip_dir(d)]

            for name in files:
                path = root_path / name

                if not is_valid_photo_file(path):
                    continue

                try:
                    stat = path.stat()
                    quarantine_count += 1

                    exact_matches = primary_exact.get(path.name.lower(), [])
                    stem_matches = primary_stem.get(normalized_stem(path), [])

                    if exact_matches:
                        classification = "EXACT_NAME_MATCH_IN_PRIMARY"
                    elif stem_matches:
                        classification = "SAME_BASENAME_MATCH_IN_PRIMARY"
                    else:
                        classification = "NO_MATCH_IN_PRIMARY"

                    writer.writerow([
                        path.name,
                        str(path),
                        str(path.relative_to(QUARANTINE_DIR)),
                        path.suffix.lower(),
                        stat.st_size,
                        format_time(stat.st_mtime),
                        classification,
                        len(exact_matches),
                        len(stem_matches),
                        " | ".join(str(p) for p in exact_matches),
                        " | ".join(str(p) for p in stem_matches)
                    ])

                except Exception as e:
                    print(f"SKIP quarantine: {path} -> {e}")
                    skipped += 1

    print("\nDone.")
    print(f"Primary files indexed: {primary_count}")
    print(f"Quarantine files classified: {quarantine_count}")
    print(f"Skipped: {skipped}")
    print(f"CSV written to: {OUTPUT_CSV}")

if __name__ == "__main__":
    main()
