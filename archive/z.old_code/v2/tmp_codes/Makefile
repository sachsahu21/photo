.PHONY: help install test run clean

help:
@echo "Image Scanner - Available Commands"
@echo "===================================="
@echo "make install    - Install dependencies"
@echo "make test       - Run tests"
@echo "make run        - Run application"
@echo "make clean      - Clean generated files"
@echo "make lint       - Run code linting"

install:
pip install -r requirements.txt

test:
python -m pytest tests/ -v

run:
python main.py

clean:
rm -rf __pycache__ .pytest_cache logs/*.log output/*.xlsx

lint:
python -m pylint src/

format:
python -m black src/ main.py