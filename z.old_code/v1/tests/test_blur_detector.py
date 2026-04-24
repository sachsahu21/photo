
"""
Unit tests for blur detector module
"""

import unittest
from src.blur_detector import BlurDetector


class TestBlurDetector(unittest.TestCase):
    """Test blur detector"""

    def setUp(self):
        """Setup test fixtures"""
        self.detector = BlurDetector(threshold=100)

    def test_detector_initialization(self):
        """Test detector initialization"""
        self.assertEqual(self.detector.threshold, 100)

    def test_set_threshold(self):
        """Test setting threshold"""
        self.detector.set_threshold(150)
        self.assertEqual(self.detector.threshold, 150)


if __name__ == '__main__':
    unittest.main()