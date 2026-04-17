
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="image-scanner",
    version="1.0.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="Professional image metadata scanner with blur detection and organization",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/image-scanner",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=[
        "Pillow>=9.0.0",
        "openpyxl>=3.8.0",
        "opencv-python>=4.5.0",
        "PyYAML>=6.0",
        "tqdm>=4.62.0",
        "python-dotenv>=0.19.0",
    ],
    entry_points={
        "console_scripts": [
            "image-scanner=main:main",
        ],
    },
)