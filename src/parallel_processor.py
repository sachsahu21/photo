"""
Parallel Processor - Multi-threaded file processing.
"""

import os
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from tqdm import tqdm
from .utils import get_record_defaults

logger = logging.getLogger(__name__)


class ParallelProcessor:
    """Process files in parallel using thread pool."""

    def __init__(self, max_workers=0, show_progress=True):
        if max_workers <= 0:
            max_workers = min(os.cpu_count() or 4, 8)
        self.max_workers = max_workers
        self.show_progress = show_progress
        logger.info(f"Parallel processor: {self.max_workers} workers")

    def process(self, items, process_func, desc="Processing"):
        """
        Process items in parallel.

        Args:
            items: List of items to process
            process_func: Function that takes one item and returns result
            desc: Progress bar description

        Returns:
            List of results (in order)
        """
        results = [None] * len(items)

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_idx = {
                executor.submit(process_func, item): idx
                for idx, item in enumerate(items)
            }

            pbar = tqdm(
                total=len(items), desc=desc, unit="file",
                disable=not self.show_progress
            )

            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    logger.error(f"Parallel processing error at index {idx}: {e}")
                    err_rec = get_record_defaults()
                    err_rec['error'] = str(e)
                    results[idx] = err_rec
                pbar.update(1)

            pbar.close()

        return results

