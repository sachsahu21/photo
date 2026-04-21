\
#!/usr/bin/env python3
import os
import csv
from pathlib import Path
from datetime import datetime

# ===== CONFIGURE =====
PRIMARY_DIR = Path("C:\Users\ISSUser\Desktop\Sachin\hdd\Domestic\2008")
OUTPUT_CSV = Path("duplicate_report.csv")
# =====================

def format_time(ts):
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')

def main():
    seen = {}
    duplicates = {}
    group_id = 0

    print("Scanning files...")

    for root, _, files in os.walk(PRIMARY_DIR):
        for name in files:
            path = Path(root) / name

            try:
                stat = path.stat()
            except Exception as e:
                print(f"SKIP: {path} -> {e}")
                continue

            key = (name, stat.st_size, int(stat.st_mtime))

            if key not in seen:
                seen[key] = path
            else:
                if key not in duplicates:
                    group_id += 1
                    duplicates[key] = {
                        "group_id": group_id,
                        "files": [seen[key]]
                    }
                duplicates[key]["files"].append(path)

    print(f"Writing CSV to {OUTPUT_CSV}...")

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([
            "group_id",
            "type",
            "file_name",
            "full_path",
            "size_bytes",
            "modified_time"
        ])

        for entry in duplicates.values():
            files = entry["files"]
            gid = entry["group_id"]

            for i, f in enumerate(files):
                try:
                    stat = f.stat()
                    writer.writerow([
                        gid,
                        "original" if i == 0 else "duplicate",
                        f.name,
                        str(f),
                        stat.st_size,
                        format_time(stat.st_mtime)
                    ])
                except Exception as e:
                    print(f"SKIP writing: {f} -> {e}")

    print("Done.")
    print(f"Duplicate groups found: {len(duplicates)}")

if __name__ == "__main__":
    main()
