# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A local, offline CLI tool for scanning, analysing, organising, de-duplicating, and face-tagging large photo/video libraries. No network calls, no subscription. Driven by an interactive numbered menu in [main.py](main.py); all heavy lifting lives in single-responsibility modules under [src/](src/). A thin Streamlit dashboard exists at [web/streamlit_app.py](web/streamlit_app.py).

## Commands

Python **3.11** is required (venv is `.venv311`).

```bash
# Setup
py -3.11 -m venv .venv311
.venv311\Scripts\activate
pip install -r requirements.txt

# Run the tool (interactive menu)
python main.py

# Tests (pytest; tiered by cohort size). PowerShell wrapper:
.\run_tests.ps1                 # all tiers, verbose
.\run_tests.ps1 -Tier micro     # one tier: micro|small|medium|large
.\run_tests.ps1 -Fast           # skip @pytest.mark.slow

# Tests (direct)
python -m pytest tests/ -v
python -m pytest tests/test_micro.py -v              # single file
python -m pytest tests/test_small.py::test_name -v   # single test
python -m pytest tests/ -m "not slow"                # skip slow

# Full end-to-end smoke run (exercises task_* against the real config, writes run_full_test_summary.json)
python run_full_test.py
```

There is no lint/format config in the repo.

## Architecture — the big picture

**Vault-based pipeline.** The core idea: scan once into a **metadata vault** (one JSON per file under `workspace/metadata/`), then every other operation reads/writes that vault instead of re-touching the originals. Originals are never modified unless the user explicitly runs an organise (41/42) or quarantine (32) action.

**Control flow:** [main.py](main.py) prints a numbered menu and dispatches each choice to a `task_*` function in the same file. Those orchestrators pull paths/flags from [ConfigManager](src/config_manager.py) and call into `src/` modules. There is no API layer — the menu *is* the entry point. Key modules: [scanner.py](src/scanner.py) (extract/scan), [metadata_store.py](src/metadata_store.py) + [metadata_paths.py](src/metadata_paths.py) (the vault), [organizer.py](src/organizer.py) (organise/convert/merge/counts), [excel_writer.py](src/excel_writer.py) + [generate_report.py](src/generate_report.py) (reports), [face_indexer.py](src/face_indexer.py) + [people_sync.py](src/people_sync.py) (faces).

**`config.yaml` is the single source of truth.** Every feature is toggled there (scan paths, operation copy/move, dedupe strategy, face/blur/similar toggles, thread count, etc.). Change the three paths at the top (`workspace.root`, `scan.folder_path`, `organization.output_folder`) to point at a new disk. Read [README.md](README.md) for the full menu reference and the recommended first-time workflow (`21 → 31 → 32 → 24 → 31 → 41`).

**Menu → task map** (numbers are stable; see [main.py](main.py) `main()`):
`11/12` analysis · `21` build vault / `22` enrich / `23` reconcile paths / `24` dedupe vault / `25` quarantine orphans / `26` fresh start · `31` Excel / `32` quarantine marked · `41` organise / `42` convert structure / `43` merge duplicate dates / `44` update counts · `51–54` faces/people.

**Workspace layout** (all tool output, under `workspace.root`): `metadata/` (per-file JSON), `face_data/` (SQLite embeddings), `seed/<person>/`, `untagged_people/`, `reports/`, `comparisons/`, `checkpoints/`, `quarantine/`, `logs/`.

## Folder-naming subsystem (organizer.py)

Organised day/month folders use the convention **`<date>-<label>-<NNNpic>`** — the pic count is always the **trailing** badge (e.g. `2023-05-14-SG-042pic`, `2015-10-00-IN-005pic`). This is centralised in a few helpers in [organizer.py](src/organizer.py); change naming there, not in call sites:

- `_strip_count(name)` — removes **all** `-NNNpic` tokens and normalises separators (`" - SG"` → `"-SG"`), keeping real label spaces (`Goa Trip`). Normalises **before** stripping so a spaced count (`- 003pic`) is still recognised.
- `_compose_count_name(old, count)` — rebuilds `<identity>-<NNNpic>`; auto-migrates legacy `date-NNNpic-text` → `date-text-NNNpic`; returns `None` for no-op or empty untagged folders.
- `_extract_text_suffix(name)` — label between date and count, layout-agnostic (used by option 43 merge).
- `_extract_date_key` / `is_valid_date_folder` / `is_valid_month_folder` — date detection relies on a **full `yyyy-mm-dd` leaf name** (the `-00` day is the month sentinel). Do not rename leaves to day-only (`dd-...`) — it breaks detection in merge/counts/collect.

Options 41/42/43/44 all run `_cleanup_empty_dirs` to remove truly-empty folders (no items). `_merge_folders` / `_move_file_no_overwrite` dedupe identical files on merge and `rmdir` emptied sources.

## Non-obvious gotchas

- **Live code is at the repo root** (`main.py`, `src/`, `web/`). `archive/` holds frozen old versions (v1–v5.2, each originally written by a different AI tool per [run_steps.txt](run_steps.txt)) — only touch it for version comparisons.
- **`processing.fast_mode: true` silently skips** blur/face/thumbnail analysis at scan time (option 21) even though those flags are `enabled`. Turn it off, or fill the fields later via option 22 (enrich).
- **Restart `python main.py` after editing `src/`.** It's a long-running interactive process; Python caches imported modules, so code changes don't take effect in an already-open menu session.
- **Windows file locks are swallowed silently.** `rmdir`/move failures (folder open in Explorer, OneDrive/antivirus holding a handle) are caught with `except: pass`, so empty folders can linger with no warning. Re-running the operation (folder closed) clears them.
- Destructive options (quarantine 32, merge 43, convert 42, update counts 44) mutate real folders. Option 44 has a dry-run preview + confirm; 42/43 have a `yes` confirm. Prefer a dry-run / temp-dir test before applying to a real library.
- After any option **32** (quarantine), always run **24 → 31** to keep the vault consistent with disk.
