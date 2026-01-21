# scripts/run_stats.py
from bp_analyzer.config import SETTINGS
from bp_analyzer.db import connect_db, reset_tables
from bp_analyzer.pipelines.stats_pipeline import STATS_TABLES, run_stats
from bp_analyzer.reporting.html_renderer import create_html_section, render_report
from bp_analyzer.utils import safe_html

def main():
    conn = connect_db(SETTINGS.db_file)
    cur = conn.cursor()

    reset_tables(cur, STATS_TABLES)
    bp_version = run_stats(cur)
    conn.commit()

    # Build a small report: summary + mappings + usage + logging summary
    sections = []
    tabs = []

    cur.execute("SELECT * FROM summary_report;")
    summary = cur.fetchone()
    summary_html = f"""
      <div class="tab-content active">
        <h2>Summary</h2>
        <p>Total Processes: {summary[0]}</p>
        <p>Total Objects: {summary[1]}</p>
        <p>Ratio of Processes to Objects: {summary[2]:.2f}</p>
        <p>Blue Prism Version: {safe_html(summary[3] or '')}</p>
      </div>
    """
    tabs.append(("Summary", ""))
    sections.append(summary_html)

    cur.execute("""
      SELECT parent_name, parent_description,
             COUNT(called_process_name),
             GROUP_CONCAT(called_process_name, ', ')
      FROM process_subprocess_mapping
      GROUP BY parent_processid, parent_name, parent_description
      ORDER BY parent_name;
    """)
    rows = cur.fetchall()
    tabs.append(("Process-to-Process", ""))
    sections.append(create_html_section(
        "Process-to-Process Mapping",
        ["Process Name", "Description", "Sub-Process Call Count", "Sub-Processes Called"],
        rows
    ))

    cur.execute("""
      SELECT name, description,
             COUNT(resource_object),
             GROUP_CONCAT(resource_object, ', ')
      FROM process_object_report
      GROUP BY processid, name, description
      ORDER BY name;
    """)
    rows = cur.fetchall()
    tabs.append(("Processes → Objects", ""))
    sections.append(create_html_section(
        "Processes and Objects Used",
        ["Process Name", "Description", "Object Count", "Objects Used"],
        rows
    ))

    cur.execute("""
      SELECT process_name, total_stages,
             no_logging_count, no_logging_pct,
             error_only_count, error_only_pct,
             full_logging_count, full_logging_pct
      FROM process_logging_summary
      ORDER BY process_name;
    """)
    rows = cur.fetchall()
    tabs.append(("Logging Summary", ""))
    sections.append(create_html_section(
        "Stage Logging Summary (Counts & %)",
        ["Process Name","Total Stages","No Logging (Count)","No Logging (%)","Errors Only (Count)","Errors Only (%)","Full Logging (Count)","Full Logging (%)"],
        rows
    ))

    html = render_report(SETTINGS.customer_name, tabs, sections)
    with open("stats_report.html", "w", encoding="utf-8") as f:
        f.write(html)

    cur.close()
    conn.close()
    print("Created: stats_report.html")

if __name__ == "__main__":
    main()
