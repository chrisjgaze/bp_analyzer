# scripts/run_details.py
import argparse
from bp_analyzer.config import SETTINGS
from bp_analyzer.db import connect_db, reset_tables
from bp_analyzer.pipelines.details_pipeline import DETAIL_TABLES, run_details, export_code_stages_jsonl
from bp_analyzer.reporting.html_renderer import create_html_section, render_report

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only-type", choices=["P","O"], default=None, help="Restrict to ProcessType (P or O)")
    ap.add_argument("--name-like", default=None, help="Only items whose name contains this text (case-insensitive)")
    args = ap.parse_args()

    conn = connect_db(SETTINGS.db_file)
    cur = conn.cursor()

    reset_tables(cur, DETAIL_TABLES)
    run_details(cur, only_process_type=args.only_type, name_like=args.name_like)
    conn.commit()

    # Export JSONL for LLM
    export_code_stages_jsonl(cur, SETTINGS.code_jsonl_output)

    # Simple details report
    sections = []
    tabs = []

    cur.execute("SELECT process_name, page_name, stage_name FROM credential_usage_report ORDER BY process_name;")
    rows = cur.fetchall()
    tabs.append(("Credential Usage", ""))
    sections.append(create_html_section(
        "Processes and Stages Using Credentials Actions",
        ["Process Name", "Page Name", "Stage Name"],
        rows
    ))

    cur.execute("""
      SELECT object_name, page_name, stage_name, language, line_count, sha256, code_preview
      FROM object_code_stage_report
      ORDER BY object_name, page_name, stage_name;
    """)
    rows = cur.fetchall()
    tabs.append(("Object Code Stages", ""))
    sections.append(create_html_section(
        "Object Code Stages (Summary)",
        ["Object","Page","Stage","Language","Lines","SHA256","Preview"],
        rows
    ))

    html = render_report(SETTINGS.customer_name, tabs, sections)
    with open("details_report.html", "w", encoding="utf-8") as f:
        f.write(html)

    cur.close()
    conn.close()
    print("Created: details_report.html")
    print(f"Created: {SETTINGS.code_jsonl_output}")

if __name__ == "__main__":
    main()
