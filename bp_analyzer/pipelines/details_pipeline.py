# bp_analyzer/pipelines/details_pipeline.py
from __future__ import annotations

import json
import xml.etree.ElementTree as ET

from ..db import fetch_process_data
from ..utils import normalize_code, sha256_text, safe_pct
from ..xml_common import (
    extract_first_text,
    extract_code_from_possible_stage_xml,
    detect_language,
    infer_language_from_code,
    pretty_print_code,
    simple_code_findings,
    count_display_lines,
)

DETAIL_TABLES = [
    ("process_subprocess_mapping", """
        CREATE TABLE IF NOT EXISTS process_subprocess_mapping (
            parent_processid TEXT,
            parent_name TEXT,
            parent_description TEXT,
            called_process_id TEXT,
            called_process_name TEXT
        );"""),

    ("process_object_report", """
        CREATE TABLE IF NOT EXISTS process_object_report (
            processid TEXT,
            name TEXT,
            description TEXT,
            resource_object TEXT
        );"""),

    ("object_process_report", """
        CREATE TABLE IF NOT EXISTS object_process_report (
            resource_object TEXT,
            process_name TEXT
        );"""),

    ("process_details", """
        CREATE TABLE IF NOT EXISTS process_details (
            processid TEXT,
            process_stages TEXT,
            process_text TEXT
        );"""),

    ("credential_usage_report", """
        CREATE TABLE IF NOT EXISTS credential_usage_report (
            process_name TEXT,
            page_name TEXT,
            stage_name TEXT
        );"""),

    ("process_logging_report", """
        CREATE TABLE IF NOT EXISTS process_logging_report (
            processid TEXT,
            enabled_count INTEGER,
            inhibited_count INTEGER,
            enabled_names TEXT,
            inhibited_names TEXT
        );"""),

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
        );"""),

    ("object_code_stage_report", """
        CREATE TABLE IF NOT EXISTS object_code_stage_report (
            object_id TEXT,
            object_name TEXT,
            page_name TEXT,
            stage_id TEXT,
            stage_name TEXT,
            language TEXT,
            code_text TEXT,
            code_preview TEXT,
            line_count INTEGER,
            sha256 TEXT,
            findings_json TEXT
        );"""),

    ("object_global_code_report", """
        CREATE TABLE IF NOT EXISTS object_global_code_report (
            object_id TEXT,
            object_name TEXT,
            language TEXT,
            global_code_text TEXT,
            line_count INTEGER,
            sha256 TEXT
        );"""),
]


def reset_detail_tables(cursor) -> None:
    for table, ddl in DETAIL_TABLES:
        cursor.execute(f"DROP TABLE IF EXISTS {table};")
        cursor.execute(ddl)


def export_code_stages_jsonl(cursor, out_path: str) -> int:
    cursor.execute("""
        SELECT object_name, page_name, stage_name, language, sha256, code_text, findings_json
        FROM object_code_stage_report
        ORDER BY object_name, page_name, stage_name;
    """)
    rows = cursor.fetchall()

    with open(out_path, "w", encoding="utf-8") as f:
        for object_name, page_name, stage_name, language, sha, code_text, findings_json in rows:
            rec = {
                "object_name": object_name,
                "page_name": page_name,
                "stage_name": stage_name,
                "language": language,
                "sha256": sha,
                "code": code_text,
                "findings": json.loads(findings_json) if findings_json else {}
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    return len(rows)


def run_details(cursor, only_process_type: str | None = None, name_like: str | None = None) -> dict:
    """
    Runs the DETAILS pipeline:
      - parses BP XML
      - writes detail tables
      - (does NOT render HTML)
    """
    results = fetch_process_data(cursor)
    bp_version = None

    for (processid, process_name, process_description, processxml, ptype) in results:
        if only_process_type and ptype != only_process_type:
            continue
        if name_like and (name_like.lower() not in (process_name or "").lower()):
            continue

        try:
            root = ET.fromstring(processxml)
            if not bp_version:
                bp_version = root.attrib.get("bpversion")

            subsheet_id_to_name = {
                subsheet.get("subsheetid"): (
                    subsheet.find("name").text if subsheet.find("name") is not None else "Unnamed Subsheet"
                )
                for subsheet in root.iter("subsheet")
            }

            # -----------------------------
            # Object: global code + code stages
            # -----------------------------
            if ptype == "O":
                # Best-effort global code capture (schema varies)
                global_code = ""
                for tag in ["globalcode", "global", "globalcodesection", "globalcodeinfo"]:
                    n = root.find(f".//{tag}")
                    if n is not None and n.text:
                        global_code = n.text
                        break

                if global_code:
                    lang_guess = detect_language(root, root)
                    gc_norm = normalize_code(global_code)
                    cursor.execute("""
                        INSERT INTO object_global_code_report (
                            object_id, object_name, language,
                            global_code_text, line_count, sha256
                        ) VALUES (?, ?, ?, ?, ?, ?);
                    """, (
                        processid, process_name, lang_guess,
                        gc_norm,
                        get_line_count(gc_norm),
                        sha256_text(gc_norm),
                    ))

                # Extract Code stages
                code_tag_candidates = ["code", "codetext", "script", "text", "body", "vb", "csharp"]

                for stage in root.findall(".//stage[@type='Code']"):
                    stage_id = stage.get("stageid") or ""
                    stage_name = stage.get("name") or "Unnamed Code Stage"

                    subsheet_id = stage.find("subsheetid").text if stage.find("subsheetid") is not None else "Main Sheet"
                    page_name = subsheet_id_to_name.get(subsheet_id, "Main Sheet")

                    code_text = extract_first_text(stage, code_tag_candidates)
                    if not code_text:
                        # fallback: store stage XML for later refinement
                        code_text = ET.tostring(stage, encoding="unicode", method="xml")

                    code_norm, source_kind = extract_code_from_possible_stage_xml(code_text)

                    # language: detect + infer (critical for pretty printing)
                    language = detect_language(root, stage)
                    language = infer_language_from_code(language, code_norm)

                    findings = simple_code_findings(code_norm)

                    # Pretty format for display
                    pretty = pretty_print_code(code_norm, language)
                    preview = pretty[:300].replace("\n", " ") + ("..." if len(pretty) > 300 else "")
                    display_line_count = count_display_lines(pretty)

                    cursor.execute("""
                        INSERT INTO object_code_stage_report (
                            object_id, object_name, page_name,
                            stage_id, stage_name, language,
                            code_text, code_preview, line_count, sha256,
                            findings_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """, (
                        processid, process_name, page_name,
                        stage_id, stage_name, language,
                        pretty,                    # what you show in HTML
                        preview,
                        display_line_count,    # count what user sees
                        sha256_text(code_norm),    # hash raw normalized
                        json.dumps(findings),
                    ))

            # -----------------------------
            # Subprocess mappings
            # -----------------------------
            unique_subprocess_calls = set()
            for stage in root.findall(".//stage[@type='Process']"):
                process_id_node = stage.find("processid")
                if process_id_node is not None and process_id_node.text:
                    called_process_id = process_id_node.text.upper()
                    cursor.execute(
                        "SELECT name FROM process_table WHERE UPPER(processid) = ? AND ProcessType = 'P';",
                        (called_process_id,),
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

            # -----------------------------
            # Resource object usage
            # -----------------------------
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

            # -----------------------------
            # Stage logging + credential usage
            # -----------------------------
            enabled_names = []
            inhibited_names = []
            enabled_count = 0
            inhibited_count = 0
            exception_count = 0

            for stage in root.iter("stage"):
                # Credential usage
                resource = stage.find("resource")
                if resource is not None and resource.get("object") == "Blueprism.Automate.clsCredentialsActions":
                    stage_name = stage.get("name") or "Unnamed Stage"
                    subsheet_id = stage.find("subsheetid").text if stage.find("subsheetid") is not None else "Main Sheet"
                    page_name = subsheet_id_to_name.get(subsheet_id, "Main Sheet")
                    cursor.execute("""
                        INSERT INTO credential_usage_report (process_name, page_name, stage_name)
                        VALUES (?, ?, ?);
                    """, (process_name, page_name, stage_name))

                stage_type = stage.get("type", "N/A")
                if stage_type == "Exception":
                    exception_count += 1

                is_log_inhibited = stage.find("loginhibit") is not None
                sname = stage.get("name") or "Unnamed Stage"

                if is_log_inhibited:
                    inhibited_count += 1
                    inhibited_names.append(sname)
                else:
                    enabled_count += 1
                    enabled_names.append(sname)

            total_stages = enabled_count + inhibited_count

            cursor.execute("""
                INSERT INTO process_logging_report
                (processid, enabled_count, inhibited_count, enabled_names, inhibited_names)
                VALUES (?, ?, ?, ?, ?);
            """, (processid, enabled_count, inhibited_count, json.dumps(enabled_names), json.dumps(inhibited_names)))

            cursor.execute("""
                INSERT INTO process_logging_summary (
                    processid, process_name,
                    total_stages,
                    no_logging_count, full_logging_count, error_only_count,
                    no_logging_pct, full_logging_pct, error_only_pct
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                processid, process_name,
                total_stages,
                inhibited_count,
                enabled_count,
                exception_count,
                safe_pct(inhibited_count, total_stages),
                safe_pct(enabled_count, total_stages),
                safe_pct(exception_count, total_stages),
            ))

        except ET.ParseError:
            # best-effort, never hard fail
            continue
        except Exception:
            continue

    return {"bp_version": bp_version}
