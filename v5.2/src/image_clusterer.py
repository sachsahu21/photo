"""Clusterer v2.4"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import numpy as np
    from PIL import Image as PILImage
    NP_OK = True
except ImportError:
    NP_OK = False

try:
    from sklearn.cluster import KMeans
    SK_OK = True
except ImportError:
    SK_OK = False


class ImageClusterer:
    def __init__(self, n_clusters=10, method='color_histogram', min_cluster_size=3):
        self.n_clusters = n_clusters
        self.min_cluster_size = min_cluster_size

    def cluster(self, records):
        if not NP_OK or not SK_OK:
            return records
        images = [
            (i, r['full_path'])
            for i, r in enumerate(records)
            if r.get('file_type') == 'image'
            and r.get('full_path')
            and Path(r['full_path']).exists()
        ]
        if len(images) < self.n_clusters:
            return records
        features, valid = [], []
        for idx, fp in images:
            try:
                features.append(
                    np.array(
                        PILImage.open(fp).convert('RGB').resize((32, 32), PILImage.LANCZOS)
                    ).flatten().astype(float) / 255.0
                )
                valid.append(idx)
            except Exception:
                pass
        if len(features) < self.n_clusters:
            return records
        labels = KMeans(
            n_clusters=min(self.n_clusters, len(features)),
            random_state=42,
            n_init=10
        ).fit_predict(np.array(features))
        from collections import Counter
        counts = Counter(labels)
        for vi, lb in zip(valid, labels):
            if counts[lb] >= self.min_cluster_size:
                records[vi]['cluster_id'] = int(lb)
                records[vi]['cluster_label'] = 'Cluster-' + str(int(lb)).zfill(3)
        return records

