
# ============================================================================
# FILE: setup.py
# ============================================================================
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="image-scanner",
    version="1.0.0",
    author="Your Name",
    description="Professional image scanner with metadata extraction and organization",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=[
        "Pillow>=9.5.0",
        "piexif>=1.1.3",
        "pillow-heif>=0.13.0",
        "opencv-python>=4.7.0",
        "numpy>=1.24.0",
        "openpyxl>=3.10.0",
        "pyyaml>=6.0",
        "tqdm>=4.65.0",
        "python-dateutil>=2.8.2",
    ],
)