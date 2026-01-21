# pipelines/stats_pipeline.py
import json
from collections import defaultdict
import xml.etree.ElementTree as ET
from ..utils import safe_pct
from ..db import fetch_process_data

STATS_TABLES = [
    ("process_subprocess_mapping", """
        CREATE TABLE IF NOT EXISTS process_subprocess_mapping (
            parent_processid TEXT,
            parent_name TEXT,
            parent_description TEXT,
            called_process_id TEXT,
            called_process_name TEXT
        );
    """),
    ("summary_report", """
        CREATE TABLE IF NOT EXISTS summary_report (
            total_processes INTEGER,
            total_objects INTEGER,
            ratio_process_to_object FLOAT,
            bp_version TEXT
        );
    """),
    ("process_object_report", """
        CREATE TABLE IF NOT EXISTS process_object_report (
            processid TEXT,
            name TEXT,
            description TEXT,
            resource_object TEXT
        );
    """),
    ("object_process_report", """
        CREATE TABLE IF NOT EXISTS object_process_report (
            resource_object TEXT,
            process_name TEXT
        );
    """),
    ("process_details", """
        CREATE TABLE IF NOT EXISTS process_details (
            processid TEXT,
            process_stages TEXT,
            process_text TEXT
        );
    """),
    ("process_logging_report", """
        CREATE TABLE IF NOT EXISTS process_logging_report (
            processid TEXT,
            enabled_count INTEGER,
            inhibited_count INTEGER,
            enabled_names TEXT,
            inhibited_names TEXT
        );
    """),
    ("process_logging_summary", """
        CREATE TABLE IF NOT EXISTS process_logging_summary (
            processid TEXT,
            process_name TEXT,
            total_stages INTEGER,
            no_logging_count INTEGER,
            full_logging_count INTEGER,
            error_only_count INTEGER,
            no_logging_pct REAL,
            full_logging_pct REAL,
            error_only_pct REAL
        );
    """),
]

def run_stats(cursor) -> str:
    """
    Returns detected bp_version (best effort).
    """
    bp_version = None
    results = fetch_process_data(cursor)

    for (processid, process_name, process_description, processxml, ptype) in results:
        try:
            root = ET.fromstring(processxml)
            if not bp_version:
                bp_version = root.attrib.get("bpversion")

            # subprocess mapping
            unique_subprocess_calls = set()
            for stage in root.findall(".//stage[@type='Process']"):
                pid = stage.find("processid")
                if pid is not None and pid.text:
                    called_process_id = pid.text.upper()
                    cursor.execute(
                        "SELECT name FROM process_table WHERE UPPER(processid) = ? AND ProcessType = 'P';",
                        (called_process_id,)
                    )
                    row = cursor.fetchone()
                    called_process_name = row[0] if row else "Unknown"
                    unique_subprocess_calls.add((called_process_id, called_process_name))

            for called_process_id, called_process_name in unique_subprocess_calls:
                cursor.execute("""
                    INSERT INTO process_subprocess_mapping
                    (parent_processid, parent_name, parent_description, called_process_id, called_process_name)
                    VALUES (?, ?, ?, ?, ?);
                """, (processid, process_name, process_description, called_process_id, called_process_name))

            # object usage
            unique_resource_objects = {r.get("object") for r in root.findall(".//resource") if r.get("object")}
            for resource_object in unique_resource_objects:
                cursor.execute("""
                    INSERT INTO process_object_report (processid, name, description, resource_object)
                    VALUES (?, ?, ?, ?);
                """, (processid, process_name, process_description, resource_object))
                cursor.execute("""
                    INSERT INTO object_process_report (resource_object, process_name)
                    VALUES (?, ?);
                """, (resource_object, process_name))

            # logging summary + stage type counts
            type_count = {}
            enabled_names, inhibited_names = [], []
            enabled_count = inhibited_count = exception_count = 0

            for stage in root.iter("stage"):
                stage_type = stage.get("type", "N/A")
                stage_display_name = stage.get("name", "N/A")

                if stage_type == "Exception":
                    exception_count += 1

                is_inhibited = stage.find("loginhibit") is not None
                stage_name = stage.get("name") or "Unnamed Stage"
                if is_inhibited:
                    inhibited_count += 1
                    inhibited_names.append(stage_name)
                else:
                    enabled_count += 1
                    enabled_names.append(stage_name)

                if stage_type in type_count:
                    type_count[stage_type]["count"] += 1
                    type_count[stage_type]["names"].append(stage_display_name)
                else:
                    type_count[stage_type] = {"count": 1, "names": [stage_display_name]}

            total = enabled_count + inhibited_count

            cursor.execute("""
                INSERT INTO process_logging_report
                (processid, enabled_count, inhibited_count, enabled_names, inhibited_names)
                VALUES (?, ?, ?, ?, ?);
            """, (processid, enabled_count, inhibited_count, json.dumps(enabled_names), json.dumps(inhibited_names)))

            cursor.execute("""
                INSERT INTO process_logging_summary (
                    processid, process_name, total_stages,
                    no_logging_count, full_logging_count, error_only_count,
                    no_logging_pct, full_logging_pct, error_only_pct
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                processid, process_name, total,
                inhibited_count, enabled_count, exception_count,
                safe_pct(inhibited_count, total),
                safe_pct(enabled_count, total),
                safe_pct(exception_count, total)
            ))

            cursor.execute("""
                INSERT INTO process_details (processid, process_stages, process_text)
                VALUES (?, ?, ?);
            """, (processid, json.dumps(type_count), ", ".join([f"{t}: {d['count']}" for t, d in type_count.items()])))

        except ET.ParseError:
            continue

    # summary_report
    cursor.execute("""
        SELECT 
            SUM(CASE WHEN ProcessType = 'P' THEN 1 ELSE 0 END) AS total_processes,
            SUM(CASE WHEN ProcessType = 'O' THEN 1 ELSE 0 END) AS total_objects,
            (CAST(SUM(CASE WHEN ProcessType = 'P' THEN 1 ELSE 0 END) AS FLOAT) / 
             NULLIF(SUM(CASE WHEN ProcessType = 'O' THEN 1 ELSE 0 END), 0)) AS ratio_process_to_object
        FROM process_table;
    """)
    total_processes, total_objects, ratio = cursor.fetchone()
    cursor.execute("""
        INSERT INTO summary_report (total_processes, total_objects, ratio_process_to_object, bp_version)
        VALUES (?, ?, ?, ?);
    """, (total_processes, total_objects, ratio, bp_version))

    return bp_version or ""
