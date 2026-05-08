"""Geocoder v2.4"""

import logging

logger = logging.getLogger(__name__)

try:
    import reverse_geocoder as rg
    RG_OK = True
except ImportError:
    RG_OK = False


class Geocoder:
    def __init__(self, method='offline'):
        pass

    def geocode_batch(self, coords):
        if not RG_OK or not coords:
            return [{}] * len(coords)
        try:
            return [
                {
                    'location_city': r.get('name', ''),
                    'location_country': r.get('cc', ''),
                    'location_name': r.get('admin1', ''),
                }
                for r in rg.search(coords)
            ]
        except Exception:
            return [{}] * len(coords)

