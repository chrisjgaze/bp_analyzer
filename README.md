# Blue Prism Process & Object Analyzer

This project analyzes **Blue Prism Process and Object XML exports** stored in a Blue Prism database and produces:

- High-level **process statistics**
- **Process → Process** (subprocess) mappings
- **Process → Object** and **Object → Process** usage reports
- **Stage logging analysis** (enabled / inhibited / exception-only)
- **Credential usage detection**
- **Object code extraction** (Code stages + Global code)
- **Static code findings** (SQL, HTTP, file IO, crypto, credentials, etc.)
- **HTML reports**
- **JSONL exports** suitable for LLM / AI analysis

The project is intentionally split into **small, focused pipelines** so you can run:
- Stats only
- Details only
- Everything together

## Project Structure

bp_analyzer/
  ingest/
    load_process_csv.py    # One-time CSV → SQLite bootstrap
  config.py
  db.py
  utils.py
  xml_common.py
  pipelines/
    stats_pipeline.py
    details_pipeline.py
  reporting/
    html_renderer.py
  run.py
  scripts/
    run_stats.py
    run_details.py
    run_all.py


## Requirements

- Python 3.10+
- SQLite access to a Blue Prism database containing `process_table`
- No external Python dependencies

## Quick start (run from project root)

All commands should be run from the **project root**. Do not `cd` into subfolders.

### 1) Ingest (required first step)
Load the Blue Prism export CSV into SQLite as the canonical `process_table`:

```bash
python run.py ingest --csv "Exported Processes.csv" --db process_data.db

## Data Ingestion (Required First Step)

Before running any analysis, you must load the Blue Prism export CSV
into SQLite as the canonical `process_table`.

```bash
python bp_analyzer/ingest/load_process_csv.py \
  --csv "Exported Processes.csv" \
  --db process_data.db \
  --replace


## Configuration

Edit `config.py` to set:
- customer name
- database file path
- output filenames

## Usage

### Run statistics only
python scripts/run_stats.py

Creates: stats_report.html

### Run details / code analysis only
python scripts/run_details.py
Optional filters:
  --only-type P|O
  --name-like <text>

Creates:
- details_report.html
- code_stages.jsonl

### Run everything
python scripts/run_all.py

Populates all analysis tables and exports JSONL.

## JSONL Export

The file `code_stages.jsonl` contains one record per Code stage and is suitable for GPT / LLM ingestion.

## Extending

- Add new analysis → create a new pipeline
- Add new reports → extend html_renderer
- Add new heuristics → xml_common.simple_code_findings

See AGENTS.md for AI-specific guidance.
