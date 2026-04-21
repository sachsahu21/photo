"""
Image Organization Module
Organize images into folder structure
"""

from fileinput import filename
import logging
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple

# from numpy import record

logger = logging.getLogger(__name__)


class ImageOrganizer:
    """Organize images into folder structure"""

    def __init__(self, config: Dict):
        """
        Initialize organizer

        Args:
            config: Configuration dictionary
        """
        
        self.config = config.get('organization', {})
        print(self.config)

        print(self.config)
        output_path = self.config.get('output_folder')
        if not output_path:
            raise ValueError("Missing organization.output_folder in config")

        self.output_folder = Path(output_path)
        self.folder_structure = self.config.get('folder_structure', 'year/month')
        self.use_exif_date = self.config.get('use_exif_date', True)
        self.operation = self.config.get('operation', 'copy')
        self.conflict_resolution = self.config.get('conflict_resolution', 'rename')

    def organize(self, records: List[Dict]) -> List[Dict]:
        """
        Organize images into folder structure

        Args:
            records: List of image records

        Returns:
            List of movement records
        """
        self.output_folder.mkdir(parents=True, exist_ok=True)

        movements = []

        for record in records:
            # Skip deleted files
            if record.get('delete_flag', '').upper() == 'YES':
                continue

            try:
                movement = self._move_or_copy_file(record)
                movements.append(movement)
            except Exception as e:
                # logger.error(f"Error organizing {record['filename']}: {e}")
                filename = record.get('filename') or record.get('Filename')
                logger.error(f"Error organizing {filename}: {e}")
                movements.append({
                    # 'source_filename': record['filename'],
                    # 'source_path': record['full_path'],
                    'source_filename': record.get('filename') or record.get('Filename'),
                    'source_path': record.get('full_path') or record.get('Full Path'),
                    'destination_path': '',
                    'folder_path': '',
                    'status': f'Error: {str(e)[:50]}'
                })

        logger.info(f"Organized {len(movements)} images")
        return movements

    def _move_or_copy_file(self, record: Dict) -> Dict:
        """Move or copy single file"""
        # src_path = Path(record['full_path'])
        src = record.get('full_path') or record.get('Full Path')
        if not src:
            raise ValueError("Missing full_path in record")

        src_path = Path(src)

        # Get destination folder
        dest_folder = self._get_destination_folder(record)
        dest_folder.mkdir(parents=True, exist_ok=True)

        # Get destination path
        dest_path = self._get_destination_path(src_path, dest_folder)

        # Perform operation
        if self.operation == 'move':
            shutil.move(str(src_path), str(dest_path))
        else:  # copy
            shutil.copy2(str(src_path), str(dest_path))

        logger.info(f"{'Moved' if self.operation == 'move' else 'Copied'}: {src_path.name} -> {dest_folder}")

        return {
            'source_filename': src_path.name,
            'source_path': str(src_path),
            'destination_path': str(dest_path),
            'folder_path': str(dest_folder.relative_to(self.output_folder)),
            'status': 'Success'
        }

    # def _get_destination_folder(self, record: Dict) -> Path:
    #     """Get destination folder based on configuration"""
    #     # Get date
    #     date_taken = record.get('date_taken')
    #     if isinstance(date_taken, datetime):
    #         dt = date_taken
    #     else:
    #         # Fallback to file modified date
    #         try:
    #             dt = datetime.strptime(record['file_modified'], '%Y-%m-%d %H:%M:%S')
    #         except:
    #             dt = datetime.now()

    #     # Build folder path based on structure
    #     parts = []

    #     if 'year' in self.folder_structure:
    #         parts.append(dt.strftime('%Y'))

    #     if 'month' in self.folder_structure:
    #         parts.append(dt.strftime('%m'))

    #     if 'day' in self.folder_structure:
    #         parts.append(dt.strftime('%d'))

    #     if not parts:
    #         parts = [dt.strftime('%Y'), dt.strftime('%m')]

    #     dest_folder = self.output_folder
    #     for part in parts:
    #         dest_folder = dest_folder / part

    #     return dest_folder

    def _get_destination_folder(self, record: Dict) -> Path:
        """Get destination folder based on picture Date Taken"""

        # 1. Extract date safely (handle Excel header variations)
        date_value = (
            record.get('date_taken')
            or record.get('Date Taken')
            or record.get('file_modified')
        )

        dt = None

        # 2. Convert to datetime
        if isinstance(date_value, datetime):
            dt = date_value

        elif isinstance(date_value, str):
            for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
                try:
                    dt = datetime.strptime(date_value.strip(), fmt)
                    break
                except:
                    continue

        # fallback
        if not dt:
            dt = datetime.now()

        # 3. Build folder structure (ONLY YEAR/MONTH as required)
        year = dt.strftime('%Y')
        month = dt.strftime('%m')

        return self.output_folder / year / month    

    # def _get_destination_path(self, src_path: Path, dest_folder: Path) -> Path:
    #     """Get destination file path, handling conflicts"""
    #     dest_path = dest_folder / src_path.name

    #     if not dest_path.exists():
    #         return dest_path

    #     # Handle conflict
    #     if self.conflict_resolution == 'skip':
    #         raise FileExistsError(f"File exists: {dest_path}")

    #     elif self.conflict_resolution == 'overwrite':
    #         return dest_path

    #     elif self.conflict_resolution == 'rename':
    #         # Add counter to filename
    #         counter = 1
    #         stem = src_path.stem
    #         suffix = src_path.suffix

    #         while True:
    #             new_name = f"{stem}_{counter}{suffix}"
    #             dest_path = dest_folder / new_name
    #             if not dest_path.exists():
    #                 return dest_path
    #             counter += 1

    #     return dest_path

    def _get_destination_path(self, src_path: Path, dest_folder: Path) -> Path:
        """Get destination path and overwrite if file already exists"""

        dest_path = dest_folder / src_path.name

        # Ensure folder exists
        dest_folder.mkdir(parents=True, exist_ok=True)

        # 🔥 If file exists, delete it (overwrite behavior)
        if dest_path.exists():
            dest_path.unlink()

        return dest_path