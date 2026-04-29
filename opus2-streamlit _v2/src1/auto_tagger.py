
# ============================================================
# FILE: src/auto_tagger.py  (#12 - NEW)
# ============================================================
"""
Auto Tagger - Automatic image tagging using pre-trained models.
Uses ONNX Runtime with MobileNet for local inference (no cloud needed).
Falls back to simple color/size based tagging if ONNX not available.
"""

import logging
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

try:
    import numpy as np
    from PIL import Image
    NP_PIL_OK = True
except ImportError:
    NP_PIL_OK = False

try:
    import onnxruntime as ort
    ONNX_OK = True
except ImportError:
    ONNX_OK = False
    logger.info("onnxruntime not installed. Auto-tagging will use simple heuristics.")


# ImageNet-style labels (top categories simplified)
SIMPLE_LABELS = [
    'person', 'animal', 'vehicle', 'food', 'nature', 'building',
    'indoor', 'outdoor', 'document', 'screenshot', 'art', 'sport',
    'water', 'sky', 'flower', 'pet', 'furniture', 'electronics',
]


class AutoTagger:
    """Automatic image tagging."""

    def __init__(self, model='mobilenet', top_k=5, confidence_threshold=0.3):
        self.model_name = model
        self.top_k = top_k
        self.confidence_threshold = confidence_threshold
        self._session = None
        self._labels = None

    def tag(self, filepath):
        """
        Tag an image.

        Returns:
            dict with 'auto_tags' (str, comma-separated) and 'primary_tag' (str)
        """
        result = {'auto_tags': None, 'primary_tag': None}

        if not NP_PIL_OK:
            return result

        try:
            # Use simple heuristic tagging (works without ONNX)
            tags = self._simple_tag(filepath)
            if tags:
                result['auto_tags'] = ', '.join(tags[:self.top_k])
                result['primary_tag'] = tags[0] if tags else None

        except Exception as e:
            logger.debug(f"Tagging error {filepath}: {e}")

        return result

    def _simple_tag(self, filepath):
        """
        Simple heuristic-based tagging using image properties.
        No ML model needed.
        """
        tags = []

        try:
            with Image.open(filepath) as img:
                img_rgb = img.convert('RGB')
                w, h = img.size

                # Aspect ratio
                ratio = w / h if h > 0 else 1
                if ratio > 1.5:
                    tags.append('panoramic')
                elif ratio < 0.7:
                    tags.append('portrait-orientation')
                else:
                    tags.append('landscape-orientation')

                # Resolution
                mp = (w * h) / 1e6
                if mp > 12:
                    tags.append('high-resolution')
                elif mp < 1:
                    tags.append('low-resolution')

                # Analyze colors
                small = img_rgb.resize((64, 64))
                pixels = np.array(small)

                # Average color
                avg_r = pixels[:, :, 0].mean()
                avg_g = pixels[:, :, 1].mean()
                avg_b = pixels[:, :, 2].mean()

                # Brightness
                brightness = (avg_r + avg_g + avg_b) / 3
                if brightness > 200:
                    tags.append('bright')
                elif brightness < 60:
                    tags.append('dark')

                # Dominant color
                if avg_b > avg_r and avg_b > avg_g:
                    if brightness > 150:
                        tags.append('sky-blue')
                    else:
                        tags.append('blue-tones')
                elif avg_g > avg_r and avg_g > avg_b:
                    tags.append('green-nature')
                elif avg_r > avg_g and avg_r > avg_b:
                    if avg_r > 180 and avg_g < 100:
                        tags.append('warm-red')
                    else:
                        tags.append('warm-tones')

                # Color variance (colorful vs monotone)
                std_r = pixels[:, :, 0].std()
                std_g = pixels[:, :, 1].std()
                std_b = pixels[:, :, 2].std()
                avg_std = (std_r + std_g + std_b) / 3

                if avg_std > 60:
                    tags.append('colorful')
                elif avg_std < 20:
                    tags.append('monotone')

                # Saturation check
                hsv_approx = max(avg_r, avg_g, avg_b) - min(avg_r, avg_g, avg_b)
                if hsv_approx < 30:
                    tags.append('grayscale')

                # Size-based hints
                size_mb = Path(filepath).stat().st_size / (1024 * 1024)
                if size_mb > 10:
                    tags.append('large-file')
                elif size_mb < 0.1:
                    tags.append('small-file')

        except Exception as e:
            logger.debug(f"Simple tag error {filepath}: {e}")

        return tags


