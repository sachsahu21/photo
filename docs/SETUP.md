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

## Git tags

Each promoted version is tagged on the commit where it became the root version.

| Tag | What you get |
|-----|-------------|
| `v5.4` | Current root state (July 2026) |

### Checking out a tagged version
```bash
git checkout v5.4
```

### Tagging convention for future versions
Before promoting a new version to root:
```bash
# 1. Tag the outgoing version (while it's still root)
git tag -a v5.4 -m "v5.4 — brief description"
git push origin v5.4

# 2. Move old root to archive/, promote new version, commit
# 3. Tag the new version
git tag -a v6.0 -m "v6.0 — brief description"
git push origin v6.0
```

## When to update this file
- When `requirements.txt` changes
- When a new archived version is added
- When the Python version requirement changes
- When a new git tag is created
