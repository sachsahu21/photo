import os
import re
import hashlib
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter

from PIL import Image
from PIL.ExifTags import TAGS
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# OPTIONAL: location lookup
try:
    from geopy.geocoders import Nominatim
    GEO_OK = True
    geolocator = Nominatim(user_agent="image_scanner")
except:
    GEO_OK = False

SCAN_FOLDER = r"C:\Users\ISSUser\Desktop\Sachin\hdd\Sachin\Moht shoot 2025"

# ──────────────────────────────────────────────
# CLEAN STRINGS (Fix Excel error)
# ──────────────────────────────────────────────
ILLEGAL_CHARACTERS_RE = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F]')
def clean(val):
    if isinstance(val, str):
        return ILLEGAL_CHARACTERS_RE.sub('', val)
    return val


# ──────────────────────────────────────────────
# HASH
# ──────────────────────────────────────────────
def file_hash(fp):
    h = hashlib.md5()
    try:
        with open(fp, 'rb') as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
    except:
        return None


# ──────────────────────────────────────────────
# GPS
# ──────────────────────────────────────────────
def get_gps(exif):
    try:
        gps = exif.get('GPSInfo')
        if not gps:
            return None, None

        def conv(v):
            return float(v[0]) + float(v[1])/60 + float(v[2])/3600

        lat = conv(gps[2])
        lon = conv(gps[4])

        if gps[1] == 'S': lat = -lat
        if gps[3] == 'W': lon = -lon

        return round(lat, 6), round(lon, 6)
    except:
        return None, None


# ──────────────────────────────────────────────
# REVERSE GEOCODE
# ──────────────────────────────────────────────
def get_location(lat, lon):
    if not GEO_OK or not lat:
        return None
    try:
        loc = geolocator.reverse((lat, lon), timeout=5)
        return loc.address if loc else None
    except:
        return None


# ──────────────────────────────────────────────
# METADATA
# ──────────────────────────────────────────────
def get_metadata(fp):
    data = {
        'width': None, 'height': None, 'mode': None,
        'dpi': None, 'format': None,

        'date_taken': None,
        'camera_make': None,
        'camera_model': None,
        'lens_model': None,

        'focal_length': None,
        'aperture': None,
        'iso': None,
        'exposure_time': None,
        'flash': None,
        'white_balance': None,
        'orientation': None,

        'gps_lat': None,
        'gps_lon': None,
        'location': None,

        'has_exif': False,
        'error': None
    }

    try:
        with Image.open(fp) as img:
            data['width'] = img.width
            data['height'] = img.height
            data['mode'] = img.mode
            data['format'] = img.format

            dpi = img.info.get('dpi')
            if dpi:
                data['dpi'] = f"{int(dpi[0])}x{int(dpi[1])}"

            exif_raw = img.getexif()

            if exif_raw:
                data['has_exif'] = True
                exif = {TAGS.get(k, k): v for k, v in exif_raw.items()}

                data['camera_make'] = str(exif.get('Make', '')).strip()
                data['camera_model'] = str(exif.get('Model', '')).strip()
                data['lens_model'] = str(exif.get('LensModel', '')).strip()

                data['orientation'] = exif.get('Orientation')
                data['white_balance'] = exif.get('WhiteBalance')
                data['flash'] = exif.get('Flash')

                # Date
                dt = exif.get('DateTimeOriginal')
                if dt:
                    try:
                        data['date_taken'] = datetime.strptime(dt, '%Y:%m:%d %H:%M:%S')
                    except:
                        data['date_taken'] = dt

                # Camera settings
                if exif.get('FNumber'):
                    data['aperture'] = f"f/{float(exif['FNumber']):.1f}"

                if exif.get('FocalLength'):
                    data['focal_length'] = f"{float(exif['FocalLength']):.1f}mm"

                if exif.get('ISOSpeedRatings'):
                    data['iso'] = exif['ISOSpeedRatings']

                if exif.get('ExposureTime'):
                    exp = float(exif['ExposureTime'])
                    data['exposure_time'] = f"1/{round(1/exp)}s" if exp < 1 else f"{exp}s"

                # GPS
                lat, lon = get_gps(exif)
                data['gps_lat'], data['gps_lon'] = lat, lon

                if lat and lon:
                    data['location'] = get_location(lat, lon)

    except Exception as e:
        data['error'] = str(e)

    return data


# ──────────────────────────────────────────────
# SCAN
# ──────────────────────────────────────────────
def scan(folder):
    files = []
    for root, _, fns in os.walk(folder):
        for f in fns:
            if f.lower().endswith(('.jpg','.jpeg','.png','.heic','.webp','.tiff')):
                files.append(Path(root) / f)

    records = []
    hash_map = defaultdict(list)

    for i, fp in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {fp.name}", end='\r')

        stat = fp.stat()
        md5 = file_hash(fp)
        meta = get_metadata(fp)

        rec = {
            'filename': fp.name,
            'folder': str(fp.parent),
            'full_path': str(fp),
            'size_kb': round(stat.st_size/1024,1),
            'modified': datetime.fromtimestamp(stat.st_mtime),
            'md5': md5,
            **meta
        }

        records.append(rec)
        if md5:
            hash_map[md5].append(str(fp))

    # duplicates
    dup = {}
    gid = 1
    for h, paths in hash_map.items():
        if len(paths) > 1:
            for p in paths:
                dup[p] = gid
            gid += 1

    for r in records:
        r['duplicate'] = 'YES' if r['full_path'] in dup else 'No'
        r['dup_group'] = dup.get(r['full_path'], '')

    return records


# ──────────────────────────────────────────────
# WRITE EXCEL
# ──────────────────────────────────────────────
def write_excel(records, folder):
    parent = Path(folder).name
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    out = Path(folder) / f"image_scan_{parent}_{ts}.xlsx"

    wb = openpyxl.Workbook()
    ws = wb.active

    headers = list(records[0].keys())

    # header
    for c, h in enumerate(headers, 1):
        ws.cell(row=1, column=c, value=h)

    # data
    for r, rec in enumerate(records, 2):
        for c, key in enumerate(headers, 1):
            val = rec.get(key)

            if isinstance(val, datetime):
                val = val.strftime('%Y-%m-%d %H:%M:%S')

            val = clean(val)

            ws.cell(row=r, column=c, value=val)

    wb.save(out)
    print(f"\nSaved: {out}")


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────
if __name__ == "__main__":
    records = scan(SCAN_FOLDER)

    if records:
        write_excel(records, SCAN_FOLDER)
    else:
        print("No images found.")