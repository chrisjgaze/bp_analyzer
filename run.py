# bp_analyzer/run.py
from __future__ import annotations

import argparse

from bp_analyzer.config import SETTINGS
from bp_analyzer.db import connect_db
from bp_analyzer.pipelines.details_pipeline import (
    reset_detail_tables,
    run_details,
    export_code_stages_jsonl,
)
from bp_analyzer.reporting.html_renderer import render_details_report


def cmd_details(args) -> None:
    conn = connect_db(args.db)
    cursor = conn.cursor()

    # Reset + run details pipeline
    reset_detail_tables(cursor)
    meta = run_details(
        cursor,
        only_process_type=args.only_type,
        name_like=args.name_like,
    )

    # Export JSONL (LLM-ready)
    jsonl_rows = export_code_stages_jsonl(cursor, args.code_jsonl)

    # Render HTML from DB only
    render_details_report(
        cursor=cursor,
        customer_name=args.customer,
        output_path=args.out,
        bp_version=meta.get("bp_version"),
        code_jsonl_output=args.code_jsonl,
    )

    conn.commit()
    conn.close()

    print(f"[details] HTML report : {args.out}")
    print(f"[details] JSONL export: {args.code_jsonl} (rows={jsonl_rows})")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("details", help="Run details pipeline + render report")

    d.add_argument(
        "--db",
        default=SETTINGS.db_file,
        help="SQLite database file",
    )
    d.add_argument(
        "--customer",
        default=SETTINGS.customer_name,
        help="Customer name for reports",
    )
    d.add_argument(
        "--out",
        default=SETTINGS.report_output,
        help="HTML output file",
    )
    d.add_argument(
        "--code-jsonl",
        dest="code_jsonl",
        default=SETTINGS.code_jsonl_output,
        help="JSONL code export file",
    )

    d.add_argument("--only-type", choices=["P", "O"])
    d.add_argument("--name-like")

    d.set_defaults(func=cmd_details)
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
