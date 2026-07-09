

# ============================================================
# FILE: src/geocoder.py  (#10 - NEW)
# ============================================================
"""
Geocoder - Reverse geocode GPS coordinates to location names.
Uses reverse_geocoder (offline) for privacy.
"""

import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)

try:
    import reverse_geocoder as rg
    RG_OK = True
except ImportError:
    RG_OK = False
    logger.info("reverse_geocoder not installed. Install with: pip install reverse_geocoder")


class Geocoder:
    """Reverse geocode GPS coordinates."""

    def __init__(self, method='offline'):
        self.method = method
        self._initialized = False

        if RG_OK:
            try:
                # Pre-warm the geocoder (loads data on first call)
                rg.search((0, 0))
                self._initialized = True
                logger.info("Geocoder initialized (offline)")
            except Exception as e:
                logger.warning(f"Geocoder init error: {e}")

    def geocode(self, lat, lon):
        """
        Reverse geocode coordinates.

        Returns:
            dict with 'location_city', 'location_country', 'location_name'
        """
        result = {'location_city': None, 'location_country': None, 'location_name': None}

        if not RG_OK or not self._initialized:
            return result

        if lat is None or lon is None:
            return result

        try:
            results = rg.search((lat, lon))
            if results and len(results) > 0:
                r = results[0]
                result['location_city'] = r.get('name', '')
                result['location_country'] = r.get('cc', '')
                admin1 = r.get('admin1', '')
                result['location_name'] = f"{r.get('name', '')}, {admin1}" if admin1 else r.get('name', '')

        except Exception as e:
            logger.debug(f"Geocode error ({lat}, {lon}): {e}")

        return result

    def geocode_batch(self, coordinates):
        """
        Batch geocode list of (lat, lon) tuples.

        Returns:
            List of result dicts
        """
        if not RG_OK or not self._initialized or not coordinates:
            return [{'location_city': None, 'location_country': None, 'location_name': None}
                    for _ in coordinates]

        try:
            valid = [(lat, lon) for lat, lon in coordinates if lat is not None and lon is not None]
            if not valid:
                return [{'location_city': None, 'location_country': None, 'location_name': None}
                        for _ in coordinates]

            results_raw = rg.search(valid)

            # Map back
            results = []
            valid_idx = 0
            for lat, lon in coordinates:
                if lat is not None and lon is not None and valid_idx < len(results_raw):
                    r = results_raw[valid_idx]
                    admin1 = r.get('admin1', '')
                    results.append({
                        'location_city': r.get('name', ''),
                        'location_country': r.get('cc', ''),
                        'location_name': f"{r.get('name', '')}, {admin1}" if admin1 else r.get('name', ''),
                    })
                    valid_idx += 1
                else:
                    results.append({'location_city': None, 'location_country': None, 'location_name': None})

            return results

        except Exception as e:
            logger.error(f"Batch geocode error: {e}")
            return [{'location_city': None, 'location_country': None, 'location_name': None}
                    for _ in coordinates]
