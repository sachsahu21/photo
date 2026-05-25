# import required modules
import csv
from pathlib import Path
from typing import Set

from src.config_manager import ConfigManager

# openpyxl is used for XLSX generation
from openpyxl import Workbook


def collect_files(base_path: Path, recursive: bool, extensions: dict) -> Set[str]:
    """Return a set of file paths (as strings) matching the given extensions.
    extensions dict looks like {'images': ['jpg', 'jpeg'], 'videos': ['mp4', ...]}
    """
    ext_set = {f".{e.lower()}" for cat in extensions.values() for e in cat}
    if recursive:
        files = {str(p) for p in base_path.rglob("*") if p.is_file() and p.suffix.lower() in ext_set}
    else:
        files = {str(p) for p in base_path.iterdir() if p.is_file() and p.suffix.lower() in ext_set}
    return files


def load_global_checkpoint(ck_path: Path) -> Set[str]:
    if not ck_path.is_file():
        return set()
    try:
        import json
        data = json.loads(ck_path.read_text(encoding='utf-8'))
        return set(data.get('processed', []))
    except Exception:
        return set()


def human_readable_size(num_bytes: int) -> str:
    """Convert bytes to a human‑readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num_bytes < 1024:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.2f} PB"


def main():
    cfg = ConfigManager().to_dict()
    workspace_root = Path(cfg['workspace']['root'])
    scan_cfg = cfg['scan']
    scan_path = Path(scan_cfg['folder_path'])
    recursive = bool(scan_cfg.get('recursive', True))
    extensions = scan_cfg.get('extensions', {})

    all_files = collect_files(scan_path, recursive, extensions)
    ck_path = workspace_root / "global_checkpoint.json"
    processed = load_global_checkpoint(ck_path)
    pending = all_files - processed

    # Statistics
    scanned_count = len(processed)
    pending_count = len(pending)
    pending_size_bytes = sum(Path(p).stat().st_size for p in pending if Path(p).exists())
    pending_size_human = human_readable_size(pending_size_bytes)

    reports_dir = workspace_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    # Write CSV (original behaviour)
    csv_path = reports_dir / "scanned_pending_report.csv"
    with csv_path.open('w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["status", "full_path"])
        for f in sorted(processed):
            writer.writerow(["scanned", f])
        for f in sorted(pending):
            writer.writerow(["pending", f])

    # Write detailed XLSX
    xlsx_path = reports_dir / "scanned_pending_report.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Report"
    # Summary rows
    ws.append(["Scanned Count", scanned_count])
    ws.append(["Pending Count", pending_count])
    ws.append(["Pending Size (bytes)", pending_size_bytes])
    ws.append(["Pending Size (readable)", pending_size_human])
    ws.append([])  # empty row before detailed list
    ws.append(["status", "full_path"])
    for f in sorted(processed):
        ws.append(["scanned", f])
    for f in sorted(pending):
        ws.append(["pending", f])
    wb.save(xlsx_path)

    print(f"CSV report written to: {csv_path}")
    print(f"XLSX report written to: {xlsx_path}")


if __name__ == "__main__":
    main()
