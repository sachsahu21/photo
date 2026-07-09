# Setup Guide

## Requirements
- Python 3.11
- All dependencies in `requirements.txt` (single file covers all versions)

## First-time setup (current version)

```bash
py -3.11 -m venv .venv311
.venv311\Scripts\activate
pip install -r requirements.txt
```

## Running current version

```bash
.venv311\Scripts\activate
python main.py
```

## Running an archived version

All archived versions share the same dependencies. Use the root venv:

```bash
.venv311\Scripts\activate
cd archive\v5.2
python main.py
```

```bash
.venv311\Scripts\activate
cd archive\v3.2
python main.py
```

## Archived versions reference

| Version | Notable feature introduced |
|---------|---------------------------|
| v1      | Baseline scanner |
| v2      | Code reorganisation |
| v3.0    | Streamlit UI, parallel processing, face detection, clustering |
| v3.1    | Checkpoint/resume |
| v3.2    | Tests framework |
| v3.3    | Similar image detection (aHash, pHash, dHash, SIFT) |
| v4.0    | Major architectural refactor |
| v4.1    | Face indexer with SQLite embeddings |
| v5.0    | Metadata vault (JSON), path reconciliation |
| v5.1    | Bug fixes on v5.0 |
| v5.2    | Locked stable — generate_report, global checkpoint |
| v5.3    | Identical to v5.2 (doc-only changes) |

## When to update this file
- When `requirements.txt` changes
- When a new archived version is added
- When the Python version requirement changes
