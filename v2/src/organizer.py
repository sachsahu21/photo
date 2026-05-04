import logging, shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict
from collections import defaultdict

logger = logging.getLogger(__name__)

class ImageOrganizer:
    def __init__(self, config: Dict):
        org = config.get('organization', {})
        output_path = org.get('output_folder')
        if not output_path:
            raise ValueError("Missing organization.output_folder in config")
        self.output_folder = Path(output_path)
        self.operation     = org.get('operation', 'copy')
        self.day_threshold = org.get('day_threshold', 60)
        self.date_counts: Dict[str, int] = defaultdict(int)

    def organize(self, records: List[Dict]) -> List[Dict]:
        self.output_folder.mkdir(parents=True, exist_ok=True)
        self._calculate_date_counts(records)
        movements = []
        for record in records:
            delete_val = (record.get('DELETE? (Yes/No)') or record.get('delete_flag', ''))
            if str(delete_val).strip().lower() == 'yes':
                continue
            try:
                movements.append(self._move_or_copy(record))
            except Exception as e:
                fn  = record.get('Filename') or record.get('filename', '?')
                src = record.get('Full Path') or record.get('full_path', '')
                logger.error(f"Error organising {fn}: {e}")
                movements.append({'source_filename': fn, 'source_path': src,
                                   'destination_path': '', 'folder_path': '',
                                   'status': f'Error: {str(e)[:50]}'})
        logger.info(f"Organised {len(movements)} files")
        return movements

    def _calculate_date_counts(self, records: List[Dict]):
        for r in records:
            self.date_counts[self._dt(r).strftime('%Y%m%d')] += 1

    def _get_dest_folder(self, record: Dict) -> Path:
        dt      = self._dt(record)
        day_key = dt.strftime('%Y%m%d')          # used for counting only
        if self.date_counts.get(day_key, 0) >= self.day_threshold:
            name = dt.strftime('%Y-%m-%d')        # e.g. 2026-02-04
        else:
            name = dt.strftime('%Y-%m') + '-00'   # e.g. 2026-02-00
        return self.output_folder / name

    def _move_or_copy(self, record: Dict) -> Dict:
        src = record.get('Full Path') or record.get('full_path')
        if not src:
            raise ValueError("Missing full_path")
        src_path    = Path(src)
        dest_folder = self._get_dest_folder(record)
        dest_folder.mkdir(parents=True, exist_ok=True)
        dest_path = dest_folder / src_path.name
        if dest_path.exists():
            dest_path.unlink()
        if self.operation == 'move':
            shutil.move(str(src_path), str(dest_path))
        else:
            shutil.copy2(str(src_path), str(dest_path))
        return {
            'source_filename':  src_path.name,
            'source_path':      str(src_path),
            'destination_path': str(dest_path),
            'folder_path':      str(dest_folder.relative_to(self.output_folder)),
            'status': 'Success'
        }

    def _dt(self, record: Dict) -> datetime:
        val = (record.get('Date Taken') or record.get('date_taken')
               or record.get('File Modified') or record.get('file_modified'))
        if isinstance(val, datetime):
            return val
        if isinstance(val, str):
            for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
                try:
                    return datetime.strptime(val.strip(), fmt)
                except ValueError:
                    continue
        return datetime.now()
