# scripts/run_all.py
from bp_analyzer.config import SETTINGS
from bp_analyzer.db import connect_db, reset_tables
from bp_analyzer.pipelines.stats_pipeline import STATS_TABLES, run_stats
from bp_analyzer.pipelines.details_pipeline import DETAIL_TABLES, run_details, export_code_stages_jsonl

def main():
    conn = connect_db(SETTINGS.db_file)
    cur = conn.cursor()

    # If you want all tables in one DB run, reset BOTH sets in one go
    reset_tables(cur, STATS_TABLES + DETAIL_TABLES)

    run_stats(cur)
    run_details(cur)

    conn.commit()
    export_code_stages_jsonl(cur, SETTINGS.code_jsonl_output)

    cur.close()
    conn.close()
    print("Done (stats + details). Now run your renderer of choice.")

if __name__ == "__main__":
    main()
