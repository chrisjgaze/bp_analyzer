# bp_analyzer/reporting/html_renderer.py
from __future__ import annotations

import json

from ..utils import safe_html, format_date


def create_html_section(title: str, headers: list[str], rows: list[tuple]) -> str:
    html_out = f"""
    <div class="tab-content">
        <h2>{safe_html(title)}</h2>
        <p class="row-count">Total Rows: {len(rows)}</p>
        <table>
            <thead>
                <tr>{''.join(f'<th onclick="sortTable(this)">{safe_html(h)}</th>' for h in headers)}</tr>
            </thead>
            <tbody>
    """
    for row in rows:
        formatted_row = []
        for header, col in zip(headers, row):
            if "date" in header.lower() and isinstance(col, str):
                formatted_row.append(format_date(col))
            else:
                formatted_row.append(col)

        html_out += (
            "<tr>"
            + "".join(f"<td>{safe_html(str(col))}</td>" for col in formatted_row)
            + "</tr>"
        )

    html_out += """
            </tbody>
        </table>
    </div>
    """
    return html_out


def create_code_stage_html_section(title: str, rows: list[tuple]) -> str:
    """
    rows schema:
      object_name, page_name, stage_name, language, line_count, sha256, code_preview, code_text, findings_json
    """
    html_out = f"""
    <div class="tab-content">
        <h2>{safe_html(title)}</h2>
        <p class="row-count">Total Rows: {len(rows)}</p>
        <table>
            <thead>
                <tr>
                    <th onclick="sortTable(this)">Object</th>
                    <th onclick="sortTable(this)">Page</th>
                    <th onclick="sortTable(this)">Stage</th>
                    <th onclick="sortTable(this)">Language</th>
                    <th onclick="sortTable(this)">Lines</th>
                    <!--<th onclick="sortTable(this)">SHA256</th>-->
                    <th onclick="sortTable(this)">Findings</th>
                    <!--<th onclick="sortTable(this)">Preview</th>-->
                    <th>Code (Drill-down)</th>
                </tr>
            </thead>
            <tbody>
    """

    for (
        object_name,
        page_name,
        stage_name,
        language,
        line_count,
        sha,
        preview,
        code_text,
        findings_json,
    ) in rows:
        try:
            findings = json.loads(findings_json) if findings_json else {}
        except Exception:
            findings = {"parse_error": True}

        keys = [
            "has_sql_keywords",
            "has_http",
            "has_file_io",
            "has_crypto",
            "has_reflection",
            "has_process_start",
            "has_hardcoded_credential_like",
        ]
        bits = []
        for k in keys:
            if findings.get(k):
                bits.append(k.replace("has_", ""))

        if findings.get("urls"):
            bits.append(f"urls({len(findings['urls'])})")

        findings_str = ", ".join(bits) if bits else "—"

        # NOTE:
        # data-code stores HTML-escaped code. This is fine for typical stage sizes.
        # If you hit very large code stages, consider storing code in a hidden <textarea>
        # or a JS map keyed by sha to avoid huge attributes.
        html_out += f"""
            <tr>
                <td>{safe_html(object_name)}</td>
                <td>{safe_html(page_name)}</td>
                <td>{safe_html(stage_name)}</td>
                <td>{safe_html(language)}</td>
                <td>{int(line_count)}</td>
                <!--<td style="font-family: monospace;">{safe_html(sha)}</td>-->
                <td>{safe_html(findings_str)}</td>
                <!--<td>{safe_html(preview)}</td>-->
                <td>
                    <button class="code-btn"
                            onclick="openCodeModal(this)"
                            data-code="{safe_html(code_text)}"
                            data-title="{safe_html(object_name)} / {safe_html(page_name)} / {safe_html(stage_name)}">
                      View code
                    </button>
                </td>
            </tr>
        """

    html_out += """
            </tbody>
        </table>
        <p style="margin-top: 10px; color: #555;">
            Tip: use SHA256 to find duplicates across objects (same code copied around).
        </p>
    </div>
    """
    return html_out


def render_details_report(
    cursor,
    customer_name: str,
    output_path: str,
    bp_version: str | None,
    code_jsonl_output: str,
) -> None:
    """
    DB → HTML only. Deterministic rendering.
    """

    sections: list[str] = []

    # Summary (minimal: you can expand later)
    sections.append(
        f"""
        <div class="tab-content active">
            <h2>Summary</h2>
            <p>Customer: {safe_html(customer_name)}</p>
            <p>Blue Prism Version: {safe_html(bp_version or '')}</p>
            <p>JSONL export: <strong>{safe_html(code_jsonl_output)}</strong></p>
        </div>
    """
    )

    # Stage Logging Summary
    cursor.execute(
        """
        SELECT
            process_name,
            total_stages,
            no_logging_count, no_logging_pct,
            error_only_count, error_only_pct,
            full_logging_count, full_logging_pct
        FROM process_logging_summary
        ORDER BY process_name;
    """
    )
    sections.append(
        create_html_section(
            "Stage Logging Summary (Counts & %)",
            [
                "Process Name",
                "Total Stages",
                "No Logging (Count)",
                "No Logging (%)",
                "Errors Only (Exception Stages Count)",
                "Errors Only (%)",
                "Full Logging (Count)",
                "Full Logging (%)",
            ],
            cursor.fetchall(),
        )
    )

    # Credential Usage
    cursor.execute(
        """
        SELECT process_name, page_name, stage_name
        FROM credential_usage_report
        ORDER BY process_name;
    """
    )
    sections.append(
        create_html_section(
            "Processes and Stages Using Credentials Actions",
            ["Process Name", "Page Name", "Stage Name"],
            cursor.fetchall(),
        )
    )

    # Object Global Code summary
    cursor.execute(
        """
        SELECT object_name, language, line_count, sha256
        FROM object_global_code_report
        ORDER BY object_name;
    """
    )
    sections.append(
        create_html_section(
            "Object Global Code (Detected)",
            ["Object Name", "Language", "Line Count", "SHA256"],
            cursor.fetchall(),
        )
    )

    # Object Code Stages drilldown
    cursor.execute(
        """
        SELECT
            object_name,
            page_name,
            stage_name,
            language,
            line_count,
            sha256,
            code_preview,
            code_text,
            findings_json
        FROM object_code_stage_report
        ORDER BY object_name, page_name, stage_name;
    """
    )
    sections.append(
        create_code_stage_html_section(
            "Object Code Stages (Drill-down)",
            cursor.fetchall(),
        )
    )

    # IMPORTANT:
    # This is an f-string, so any literal { or } inside the HTML/JS must be doubled as {{ or }}.
    # In particular, JS arrow functions like () => {} MUST be written as () => {{}} here.
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Details Report for {safe_html(customer_name)}</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            h1, h2 {{ text-align: center; }}
            .tabbed-section {{ margin-top: 20px; }}
            .tabs {{ display: flex; flex-wrap: wrap; border-bottom: 2px solid #ccc; cursor: pointer; }}
            .tab {{ padding: 10px 20px; border: 1px solid #ccc; border-bottom: none; background-color: #e0e0e0; }}
            .tab.active {{ background-color: #f4f4f4; font-weight: bold; }}
            .tab-content {{ display: none; padding: 20px; border: 1px solid #ccc; }}
            .tab-content.active {{ display: block; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            th, td {{ border: 1px solid #ccc; padding: 8px; text-align: left; vertical-align: top; }}
            th {{ background-color: #f4f4f4; cursor: pointer; }}
            .row-count {{ font-weight: bold; margin-bottom: 10px; }}

            .code-btn {{
              padding: 6px 10px;
              cursor: pointer;
              border: 1px solid #888;
              border-radius: 6px;
              background: #f4f4f4;
            }}

            .code-modal-overlay {{
              display: none;
              position: fixed;
              inset: 0;
              background: rgba(0,0,0,0.6);
              z-index: 9999;
              align-items: center;
              justify-content: center;
            }}

            .code-modal-overlay.open {{
              display: flex;
            }}

            .code-modal {{
              width: min(1200px, 92vw);
              height: min(800px, 86vh);
              background: #fff;
              border-radius: 10px;
              box-shadow: 0 10px 30px rgba(0,0,0,0.35);
              display: flex;
              flex-direction: column;
              overflow: hidden;
            }}

            .code-modal-header {{
              display: flex;
              align-items: center;
              justify-content: space-between;
              padding: 10px 12px;
              border-bottom: 1px solid #ddd;
              background: #f6f8fa;
            }}

            .code-modal-title {{
              font-weight: bold;
              font-family: Arial, sans-serif;
              font-size: 14px;
              overflow: hidden;
              text-overflow: ellipsis;
              white-space: nowrap;
              max-width: 70%;
            }}

            .code-modal-actions button {{
              margin-left: 8px;
            }}

            .code-modal-action {{
              padding: 6px 10px;
              cursor: pointer;
              border: 1px solid #888;
              border-radius: 6px;
              background: #fff;
            }}

            /* Prevent word-wrap and keep code formatting */
            .code-modal-pre {{
              margin: 0;
              padding: 12px;
              height: 100%;
              overflow: auto;
              background: #ffffff;
              border: none;
              font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
              font-size: 12px;
              line-height: 1.35;
              white-space: pre;      /* no wrap */
              word-break: normal;    /* no wrap */
              tab-size: 4;
            }}
        </style>

        <script>
            function sortTable(header) {{
                const table = header.closest('table');
                const index = Array.from(header.parentNode.children).indexOf(header);
                const rows = Array.from(table.querySelectorAll('tbody tr'));
                const isAscending = !header.classList.contains('ascending');

                rows.sort((a, b) => {{
                    const aText = a.children[index].textContent.trim();
                    const bText = b.children[index].textContent.trim();

                    const aDate = new Date(aText.split('/').reverse().join('/'));
                    const bDate = new Date(bText.split('/').reverse().join('/'));
                    if (!isNaN(aDate) && !isNaN(bDate)) {{
                        return isAscending ? aDate - bDate : bDate - aDate;
                    }}

                    const aNum = parseFloat(aText.replace(/,/g,''));
                    const bNum = parseFloat(bText.replace(/,/g,''));
                    if (!isNaN(aNum) && !isNaN(bNum)) {{
                        return isAscending ? aNum - bNum : bNum - aNum;
                    }}

                    return isAscending ? aText.localeCompare(bText) : bText.localeCompare(aText);
                }});

                rows.forEach(row => table.querySelector('tbody').appendChild(row));
                header.classList.toggle('ascending', isAscending);
            }}

            document.addEventListener('DOMContentLoaded', function() {{
                const tabs = document.querySelectorAll('.tab');
                const contents = document.querySelectorAll('.tab-content');
                tabs.forEach((tab, index) => {{
                    tab.addEventListener('click', () => {{
                        tabs.forEach(t => t.classList.remove('active'));
                        contents.forEach(c => c.classList.remove('active'));
                        tab.classList.add('active');
                        contents[index].classList.add('active');
                    }});
                }});
            }});
        </script>

        <script>
          function openCodeModal(btn) {{
            const overlay = document.getElementById("code-modal-overlay");
            const pre = document.getElementById("code-modal-pre");
            const title = document.getElementById("code-modal-title");

            const code = btn.getAttribute("data-code") || "";
            const t = btn.getAttribute("data-title") || "Code";

            // Put HTML-escaped code into <pre> safely
            pre.innerHTML = code;
            title.textContent = t;

            overlay.classList.add("open");
            document.body.style.overflow = "hidden"; // lock background scroll
          }}

          function closeCodeModal(evt) {{
            const overlay = document.getElementById("code-modal-overlay");
            overlay.classList.remove("open");
            document.body.style.overflow = "";
          }}

          function copyCode() {{
            const pre = document.getElementById("code-modal-pre");
            const text = pre.textContent || "";
            // NOTE: double braces because this HTML is built via a Python f-string
            navigator.clipboard.writeText(text).catch(() => {{}});
          }}

          document.addEventListener("keydown", function(e) {{
            if (e.key === "Escape") {{
              const overlay = document.getElementById("code-modal-overlay");
              if (overlay.classList.contains("open")) closeCodeModal();
            }}
          }});
        </script>
    </head>
    <body>
        <h1>Details Report for {safe_html(customer_name)}</h1>
        <div class="tabbed-section">
            <div class="tabs">
                <div class="tab active">Summary</div>
                <div class="tab">Stage Logging Summary</div>
                <div class="tab">Credential Usage</div>
                <div class="tab">Object Global Code</div>
                <div class="tab">Object Code Stages</div>
            </div>
            {''.join(sections)}
        </div>

        <!-- Modal (hidden until opened) -->
        <div id="code-modal-overlay" class="code-modal-overlay" onclick="closeCodeModal(event)">
          <div class="code-modal" role="dialog" aria-modal="true" aria-labelledby="code-modal-title" onclick="event.stopPropagation()">
            <div class="code-modal-header">
              <div id="code-modal-title" class="code-modal-title">Code</div>
              <div class="code-modal-actions">
                <button class="code-modal-action" onclick="copyCode()">Copy</button>
                <button class="code-modal-action" onclick="closeCodeModal()">Close</button>
              </div>
            </div>
            <pre id="code-modal-pre" class="code-modal-pre"></pre>
          </div>
        </div>
    </body>
    </html>
    """

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
