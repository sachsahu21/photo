\
#!/usr/bin/env python3
import csv
import shutil
from pathlib import Path

# ===== CONFIGURE =====
CSV_PATH = Path("/volume2/reports/photos-not-found-in-primary-dedupe.csv")
SOURCE_ROOT = Path("/volume2/photo/Photos-Not-Found-In-Primary")
DEST_ROOT = Path("/volume2/photo/Backup-Photos")
DRY_RUN = True   # CHANGE TO False TO ACTUALLY MOVE FILES
# =====================

def safe_destination(dest_path: Path) -> Path:
    """
    Prevent overwrite by adding suffix if needed
    """
    if not dest_path.exists():
        return dest_path

    stem = dest_path.stem
    suffix = dest_path.suffix
    parent = dest_path.parent

    counter = 1
    while True:
        new_path = parent / f"{stem}__dup{counter}{suffix}"
        if not new_path.exists():
            return new_path
        counter += 1

def main():
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"CSV not found: {CSV_PATH}")

    moved = 0
    skipped = 0

    print(f"Reading CSV: {CSV_PATH}")

    with open(CSV_PATH, newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)

        for row in reader:
            status = row.get("status")

            if status != "duplicate_candidate":
                continue

            source_path = Path(row["full_path"])

            if not source_path.exists():
                print(f"SKIP missing: {source_path}")
                skipped += 1
                continue

            try:
                rel_path = source_path.relative_to(SOURCE_ROOT)
            except Exception:
                print(f"SKIP path not under source root: {source_path}")
                skipped += 1
                continue

            dest_path = DEST_ROOT / rel_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            dest_path = safe_destination(dest_path)

            if DRY_RUN:
                print(f"DRY RUN MOVE: {source_path} -> {dest_path}")
            else:
                print(f"MOVE: {source_path} -> {dest_path}")
                shutil.move(str(source_path), str(dest_path))

            moved += 1

    print("\nDone.")
    print(f"Files processed: {moved}")
    print(f"Skipped: {skipped}")
    print(f"DRY_RUN: {DRY_RUN}")

if __name__ == "__main__":
    main()
