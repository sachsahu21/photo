
# ============================================================
# FILE: src/image_clusterer.py  (#7 - NEW)
# ============================================================
"""
Image Clustering - Group visually similar images.
Uses color histograms + KMeans (scikit-learn optional).
Falls back to simple binning if sklearn unavailable.
"""

import logging
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

try:
    import cv2
    import numpy as np
    CV2_OK = True
except ImportError:
    CV2_OK = False

try:
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler
    SKLEARN_OK = True
except ImportError:
    SKLEARN_OK = False


class ImageClusterer:
    """Cluster images by visual similarity."""

    def __init__(self, n_clusters=10, method='color_histogram', min_cluster_size=3):
        self.n_clusters = n_clusters
        self.method = method
        self.min_cluster_size = min_cluster_size

    def cluster(self, records):
        """
        Cluster image records.

        Args:
            records: List of image records (must have 'full_path', 'file_type')

        Returns:
            Updated records with 'cluster_id' and 'cluster_label'
        """
        if not CV2_OK:
            logger.warning("OpenCV not available for clustering")
            return records

        # Filter images only
        image_indices = [i for i, r in enumerate(records) if r.get('file_type') == 'image']

        if len(image_indices) < self.min_cluster_size:
            logger.info("Too few images for clustering")
            return records

        logger.info(f"Clustering {len(image_indices)} images into ~{self.n_clusters} groups")

        # Extract features
        features = []
        valid_indices = []

        for idx in image_indices:
            feat = self._extract_features(records[idx].get('full_path', ''))
            if feat is not None:
                features.append(feat)
                valid_indices.append(idx)

        if len(features) < self.min_cluster_size:
            logger.info("Too few valid features for clustering")
            return records

        # Cluster
        try:
            labels = self._do_clustering(features)

            if labels is not None:
                for i, idx in enumerate(valid_indices):
                    records[idx]['cluster_id'] = int(labels[i])
                    records[idx]['cluster_label'] = f"Cluster_{int(labels[i]):03d}"

                n_clusters_found = len(set(labels))
                logger.info(f"Clustering done: {n_clusters_found} clusters found")

        except Exception as e:
            logger.error(f"Clustering error: {e}")

        return records

    def _extract_features(self, filepath):
        """Extract color histogram features from image."""
        try:
            img = cv2.imread(str(filepath))
            if img is None:
                return None

            # Resize for consistency
            img = cv2.resize(img, (128, 128))
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

            # Color histogram (H: 16 bins, S: 8 bins, V: 8 bins)
            hist_h = cv2.calcHist([hsv], [0], None, [16], [0, 180])
            hist_s = cv2.calcHist([hsv], [1], None, [8], [0, 256])
            hist_v = cv2.calcHist([hsv], [2], None, [8], [0, 256])

            # Normalize
            cv2.normalize(hist_h, hist_h)
            cv2.normalize(hist_s, hist_s)
            cv2.normalize(hist_v, hist_v)

            feature = np.concatenate([hist_h.flatten(), hist_s.flatten(), hist_v.flatten()])
            return feature

        except Exception as e:
            logger.debug(f"Feature extraction error {filepath}: {e}")
            return None

    def _do_clustering(self, features):
        """Perform clustering on features."""
        import numpy as np
        features_array = np.array(features)

        n_clusters = min(self.n_clusters, len(features))

        if SKLEARN_OK:
            scaler = StandardScaler()
            scaled = scaler.fit_transform(features_array)
            kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
            labels = kmeans.fit_predict(scaled)
            return labels
        else:
            # Simple fallback: assign based on dominant hue bin
            logger.info("sklearn not available, using simple hue-based grouping")
            labels = np.argmax(features_array[:, :16], axis=1)
            return labels

