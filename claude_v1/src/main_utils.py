"""Task helpers shared by main.py"""
import logging, pickle
from pathlib import Path
from typing import Optional

def setup_logging(config):
    log_file = config.get('logging.file', './logs/image_scanner.log')
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, config.get('logging.level', 'INFO')),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.FileHandler(log_file), logging.StreamHandler()]
    )
    return logging.getLogger('main')

def save_backup(records, path='records_backup.pkl'):
    try:
        pickle.dump(records, open(path,'wb'))
        print(f"✓ Backup saved: {path}")
    except Exception as e:
        print(f"⚠ Backup failed: {e}")

def load_backup(path='records_backup.pkl'):
    try:
        if not Path(path).exists():
            print(f"✗ Backup not found: {path}"); return None
        r = pickle.load(open(path,'rb'))
        print(f"✓ Loaded {len(r)} records from backup")
        return r
    except Exception as e:
        print(f"✗ Backup load failed: {e}"); return None
