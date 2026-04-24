
import unittest
from pathlib import Path
from src.scanner import ImageScanner
from src.config_manager import ConfigManager


class TestImageScanner(unittest.TestCase):
    """Test image scanner"""

    def setUp(self):
        """Setup test fixtures"""
        self.config = ConfigManager()

    def test_scanner_initialization(self):
        """Test scanner initialization"""
        scanner = ImageScanner(self.config.to_dict())
        self.assertIsNotNone(scanner)

    def test_find_images(self):
        """Test finding image files"""
        scanner = ImageScanner(self.config.to_dict())
        # This would need a test folder with images
        # Placeholder for actual test


if __name__ == '__main__':
    unittest.main()