\
#!/usr/bin/env python3
import csv
import shutil
from pathlib import Path

# ===== CONFIGURE =====
CSV_PATH = Path("/volume2/reports/quarantine-photo-classification.csv")
SOURCE_ROOT = Path("/volume2/photo/Photos-Not-Found-In-Primary")
DEST_ROOT = Path("/volume2/photo")

DRY_RUN = True
# =====================

CLASSIFICATION_TO_FOLDER = {
    "NO_MATCH_IN_PRIMARY": "No-Match-In-Primary",
    "SAME_BASENAME_MATCH_IN_PRIMARY": "Same-Basename-Match-In-Primary",
    "EXACT_NAME_MATCH_IN_PRIMARY": "Exact-Name-Match-In-Primary",
}

def safe_destination(dest_path: Path) -> Path:
    if not dest_path.exists():
        return dest_path

    stem = dest_path.stem
    suffix = dest_path.suffix
    parent = dest_path.parent

    counter = 1
    while True:
        candidate = parent / f"{stem}__cat{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1

def main():
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"CSV not found: {CSV_PATH}")
    if not SOURCE_ROOT.exists():
        raise FileNotFoundError(f"SOURCE_ROOT not found: {SOURCE_ROOT}")
    if not DEST_ROOT.exists():
        raise FileNotFoundError(f"DEST_ROOT not found: {DEST_ROOT}")

    moved = 0
    skipped = 0
    by_class = {}

    print(f"Reading classification CSV: {CSV_PATH}")

    with open(CSV_PATH, newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)

        for row in reader:
            classification = row.get("classification", "").strip()
            source_path_str = row.get("full_path", "").strip()

            if classification not in CLASSIFICATION_TO_FOLDER:
                print(f"SKIP unknown classification: {classification}")
                skipped += 1
                continue

            if not source_path_str:
                print("SKIP missing full_path in CSV row")
                skipped += 1
                continue

            source_path = Path(source_path_str)

            if not source_path.exists():
                print(f"SKIP source missing: {source_path}")
                skipped += 1
                continue

            try:
                rel_path = source_path.relative_to(SOURCE_ROOT)
            except Exception:
                print(f"SKIP path not under source root: {source_path}")
                skipped += 1
                continue

            category_folder = DEST_ROOT / CLASSIFICATION_TO_FOLDER[classification]
            dest_path = category_folder / rel_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path = safe_destination(dest_path)

            if DRY_RUN:
                print(f"DRY RUN MOVE: {source_path} -> {dest_path}")
            else:
                print(f"MOVE: {source_path} -> {dest_path}")
                shutil.move(str(source_path), str(dest_path))

            moved += 1
            by_class[classification] = by_class.get(classification, 0) + 1

    print("\nDone.")
    print(f"Files processed: {moved}")
    print(f"Skipped: {skipped}")
    print(f"DRY_RUN: {DRY_RUN}")
    print("Breakdown:")
    for k in sorted(by_class):
        print(f"  {k}: {by_class[k]}")

if __name__ == "__main__":
    main()
