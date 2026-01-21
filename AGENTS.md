# AGENTS.md — AI Context & Modification Guide

This document provides context for AI agents (GPT, LLMs) to understand and safely modify this project.

## Purpose

Analyze Blue Prism Processes and Objects by parsing XML, extracting structure, logging behavior, credentials, and embedded code, and producing audit-grade reports and LLM-ready exports.

## Architecture Rules

Strict separation of concerns:

- pipelines/: XML parsing + DB writes
- reporting/: DB reads + HTML rendering
- utils.py: pure helpers only
- xml_common.py: XML and code parsing utilities
- scripts/: CLI entry points

Do not mix responsibilities.

## Entrypoint Runner (run.py)

`run.py` is the **single orchestrator** for common workflows:

- `python run.py ingest --csv ... --db ...` (bootstrap source data into `process_table`)
- `python run.py stats` (stats pipeline)
- `python run.py details` (details pipeline + JSONL export)
- `python run.py all` (runs both pipelines)

Rules:
- `run.py` may call scripts under `bp_analyzer/scripts/` or ingest tools under `bp_analyzer/ingest/`
- `run.py` must remain **thin orchestration only** (no XML parsing, no HTML rendering logic)
- Pipelines remain the source of truth for analysis logic and table ownership


## Ingest Layer (Source Data Creation)

Scripts under `ingest/` are responsible for creating and populating
source tables such as `process_table`.
Ingest is invoked via `run.py ingest` so the user has one consistent entrypoint.
Pipelines must still assume ingest has already completed and must never load CSVs directly.


Characteristics:
- May DROP / REPLACE tables
- May use pandas or heavy I/O
- Are run explicitly and infrequently
- Accept all inputs via CLI parameters

Rules:
- Pipelines must NEVER create or modify source tables
- Pipelines must assume ingest has already completed
- Analysis code must not depend on CSV paths


## Pipelines

Each pipeline:
- Owns its tables
- Can run independently
- Should not depend on side effects from other pipelines

Add new analysis by creating a new pipeline rather than extending existing ones.

## Database Rules

- Database is derived state
- Tables may be dropped and recreated
- Never mutate Blue Prism source tables
- Prefer INSERT-only analysis logic

## XML Parsing Philosophy

Blue Prism XML varies by version and export.
All parsing must be best-effort and defensive.
Missing nodes should never cause failure.

## Code Extraction Rules

- Normalize line endings
- Hash normalized original code, not prettified output
- Formatting is heuristic
- Never execute extracted code

## Static Findings

- Regex and substring based only
- No external calls
- No runtime execution

## Reporting Rules

HTML rendering must:
- Read from DB only
- Be deterministic
- Contain no analysis logic

## JSONL Export Rules

- One logical record per code unit
- Stable fields (name, page, stage, language, sha256)
- No HTML or UI artifacts

## Prohibited Changes

- Do not re-monolith the codebase
- Do not add business logic to HTML
- Do not hard-code Blue Prism version assumptions
- Do not introduce heavy dependencies without justification
- Do not move ingest logic into pipelines
- Do not auto-run ingest from analysis scripts


## Safe Change Checklist

Before returning code changes:
- Are responsibilities still separated?
- Are pipelines independently runnable?
- Are schemas explicit and stable?
- Are errors handled defensively?

If unsure, add a new pipeline instead of modifying existing ones.

## Execution Convention

Always run commands from the **project root**.
Do not `cd` into `bp_analyzer/ingest` or `bp_analyzer/scripts` before running commands.
This keeps imports and paths stable for humans and AI agents.


## Design Goal

Clarity over cleverness.
Auditability over abstraction.
