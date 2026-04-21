\
#!/usr/bin/env python3
import os
import shutil
from pathlib import Path

# ===== CONFIGURE =====
PHOTO_ROOT = Path("/volume2/photo")
DUP_DIR = PHOTO_ROOT / "exact-matches-Duplicates"
DRY_RUN = True
# =====================

IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".heic", ".heif", ".png", ".tif", ".tiff",
    ".dng", ".cr2", ".cr3", ".nef", ".arw", ".orf", ".rw2"
}

def find_matching_image(base_path: Path):
    stem = base_path.stem

    for root, _, files in os.walk(DUP_DIR):
        for f in files:
            p = Path(root) / f
            if p.stem == stem and p.suffix.lower() in IMAGE_EXTENSIONS:
                return p
    return None

def main():
    moved = 0
    skipped = 0

    print("Scanning for orphaned XMP files...")

    for root, _, files in os.walk(PHOTO_ROOT):
        for name in files:
            if not name.lower().endswith(".xmp"):
                continue

            xmp_path = Path(root) / name

            matching_local = any(
                (Path(root) / (xmp_path.stem + ext)).exists()
                for ext in IMAGE_EXTENSIONS
            )

            if matching_local:
                continue

            match = find_matching_image(xmp_path)

            if not match:
                continue

            rel = match.relative_to(DUP_DIR)
            dest = DUP_DIR / rel.parent / (xmp_path.stem + ".xmp")
            dest.parent.mkdir(parents=True, exist_ok=True)

            if DRY_RUN:
                print(f"DRY RUN MOVE: {xmp_path} -> {dest}")
            else:
                print(f"MOVE: {xmp_path} -> {dest}")
                shutil.move(str(xmp_path), str(dest))

            moved += 1

    print("\nDone.")
    print(f"XMP files moved: {moved}")
    print(f"Skipped: {skipped}")
    print(f"DRY_RUN: {DRY_RUN}")

if __name__ == "__main__":
    main()
