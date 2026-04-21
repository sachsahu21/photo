\
#!/usr/bin/env python3
import os
import shutil
from pathlib import Path

# ===== CONFIGURE =====
PHOTO_ROOT = Path("/volume2/photo")
DUPLICATE_DIR = PHOTO_ROOT / "exact-matches-Duplicates"
DRY_RUN = True   # Set to False to actually move files
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
    "exact-matches-Duplicates"
}

SKIP_FILE_NAMES = {
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini"
}

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

def safe_destination(src_path: Path, dest_root: Path) -> Path:
    rel = src_path.relative_to(PHOTO_ROOT)
    dest = dest_root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)

    if not dest.exists():
        return dest

    stem = dest.stem
    suffix = dest.suffix
    counter = 1
    while True:
        candidate = dest.parent / f"{stem}__dup{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1

def main():
    if not PHOTO_ROOT.exists():
        raise FileNotFoundError(f"PHOTO_ROOT not found: {PHOTO_ROOT}")

    print(f"Scanning for exact matches in: {PHOTO_ROOT}")
    seen = {}
    moved = 0
    skipped = 0
    scanned = 0

    for root, dirs, files in os.walk(PHOTO_ROOT):
        root_path = Path(root)
        dirs[:] = [d for d in dirs if not should_skip_dir(d)]

        for name in files:
            path = root_path / name

            if not is_valid_photo_file(path):
                continue

            try:
                stat = path.stat()
                key = (path.name.lower(), stat.st_size, int(stat.st_mtime))
                scanned += 1

                if key not in seen:
                    seen[key] = path
                    continue

                dest = safe_destination(path, DUPLICATE_DIR)

                if DRY_RUN:
                    print(f"DRY RUN MOVE: {path} -> {dest}")
                else:
                    print(f"MOVE: {path} -> {dest}")
                    shutil.move(str(path), str(dest))

                moved += 1

            except Exception as e:
                print(f"SKIP: {path} -> {e}")
                skipped += 1

    print("\nDone.")
    print(f"Files scanned: {scanned}")
    print(f"Duplicate files moved: {moved}")
    print(f"Skipped: {skipped}")
    print(f"DRY_RUN: {DRY_RUN}")
    print(f"Duplicate destination: {DUPLICATE_DIR}")

if __name__ == "__main__":
    main()
