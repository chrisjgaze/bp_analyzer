# bp_analyzer/xml_common.py
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Iterable, Tuple, Dict, Any

from .utils import normalize_code


# -----------------------------
# XML helpers
# -----------------------------

def indent_xml(elem: ET.Element, level: int = 0) -> None:
    i = "\n" + ("  " * level)
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        for child in elem:
            indent_xml(child, level + 1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i


def pretty_print_xml(xml_str: str) -> str:
    """
    Minimal XML pretty printer (no external libs).
    """
    try:
        root = ET.fromstring(xml_str)
        indent_xml(root)
        return ET.tostring(root, encoding="unicode")
    except Exception:
        return xml_str

def normalize_language(language: str) -> str:
    l = (language or "").strip().lower()

    # VB variants
    if l in ("vb", "vb.net", "visualbasic", "visual basic", "visual_basic"):
        return "VB"

    # C# variants
    if l in ("c#", "csharp", "cs", "c sharp"):
        return "C#"

    return language or "Unknown"

# -----------------------------
# Extraction
# -----------------------------

def extract_first_text(stage: ET.Element, tag_candidates: Iterable[str]) -> str:
    """
    Best-effort: BP exports differ; code text might sit in different nodes.
    Search for first found candidate anywhere under the stage.
    """
    for t in tag_candidates:
        node = stage.find(f".//{t}")
        if node is not None and node.text is not None:
            return node.text
    return ""


def extract_code_from_possible_stage_xml(code_text: str) -> Tuple[str, str]:
    """
    Returns (clean_code, source_kind)
    source_kind: "code" | "xml_pretty" | "raw"
    """
    if not code_text:
        return "", "raw"

    txt = code_text.strip()

    # Looks like xml blob containing stage xml
    if txt.startswith("<") and ("<stage" in txt or "</stage>" in txt):
        try:
            stage = ET.fromstring(txt)

            # common inner nodes used across exports
            code_candidates = ["code", "codetext", "script", "body", "text", "vb", "csharp"]
            for tag in code_candidates:
                n = stage.find(f".//{tag}")
                if n is not None and n.text and n.text.strip():
                    return normalize_code(n.text), "code"

            # nothing found → pretty-print the stage xml so it’s at least readable
            return pretty_print_xml(txt), "xml_pretty"

        except Exception:
            # not valid xml after all
            return normalize_code(code_text), "raw"

    return normalize_code(code_text), "raw"


# -----------------------------
# Language detection
# -----------------------------

def detect_language(root: ET.Element, stage: ET.Element) -> str:
    """
    Best-effort:
      - some exports store language per stage
      - some store language on root / object node
    """
    candidates = [
        (stage, ["language", "codelanguage", "lang"]),
        (root,  ["language", "codelanguage", "lang"]),
    ]
    for elem, tags in candidates:
        for t in tags:
            n = elem.find(f".//{t}")
            if n is not None and n.text:
                return n.text.strip()
    return "Unknown"


def infer_language_from_code(language: str, code: str) -> str:
    """
    If BP metadata is missing/weak, infer from code content.
    """
    lang = (language or "").strip()
    if lang and lang.lower() != "unknown":
        return lang

    c = code or ""
    cl = c.lower()

    # VB signals
    if re.search(r"^\s*(dim|set|byval|byref|end if|end sub|end function|select case|end select)\b", cl, re.MULTILINE):
        return "VB"
    if re.search(r"^\s*if\s+.*\bthen\b", cl, re.MULTILINE):
        return "VB"

    # C# signals
    if re.search(r"^\s*(using\s+\w+|public|private|protected|internal)\b", cl, re.MULTILINE):
        return "C#"
    if ("{" in c and "}" in c and ";" in c):
        return "C#"

    return "Unknown"


# -----------------------------
# Pretty printing (heuristic)
# -----------------------------

def normalize_whitespace(code: str) -> str:
    lines = (code or "").replace("\t", "    ").split("\n")
    out = []
    blank_run = 0
    for ln in lines:
        if ln.strip() == "":
            blank_run += 1
            if blank_run <= 1:
                out.append("")
        else:
            blank_run = 0
            out.append(ln.rstrip())
    return "\n".join(out).strip()


def split_csharp_one_liners(code: str) -> str:
    """
    Turns common one-line brace style into multi-line code so indentation can work.
    """
    if not code:
        return ""

    s = code.replace("\r\n", "\n").replace("\r", "\n")

    # Newlines around braces
    s = s.replace("{", "{\n")
    s = s.replace("}", "\n}\n")

    # else/catch/finally readability
    s = re.sub(r"\)\s*else\s*\{", ")\nelse\n{", s, flags=re.IGNORECASE)
    s = re.sub(r"\}\s*else\s*\{", "}\nelse\n{", s, flags=re.IGNORECASE)
    s = re.sub(r"\}\s*catch\s*\(", "}\ncatch(", s, flags=re.IGNORECASE)
    s = re.sub(r"\}\s*finally\s*\{", "}\nfinally\n{", s, flags=re.IGNORECASE)

    # Split semicolon statements onto new lines (avoid for(;;))
    out = []
    in_for = False
    for line in s.split("\n"):
        t = line.strip()
        if t.lower().startswith("for(") or t.lower().startswith("for ("):
            in_for = True
        if in_for and ")" in t:
            in_for = False

        if (not in_for) and ";" in line:
            parts = line.split(";")
            for p in parts[:-1]:
                if p.strip():
                    out.append(p.strip() + ";")
            if parts[-1].strip():
                out.append(parts[-1].strip())
        else:
            out.append(line)

    s = "\n".join(out)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def pretty_print_csharp_braces(code: str) -> str:
    """
    Heuristic C# formatter:
      - splits BP one-liners into multiple lines
      - indents by braces
      - cleans up ugly alignment whitespace
    """
    code = split_csharp_one_liners(code)
    if not code:
        return ""

    def collapse_spaces_outside_strings(line: str) -> str:
        out = []
        in_str = False
        esc = False
        prev_space = False
        for ch in line:
            if in_str:
                out.append(ch)
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue

            if ch == '"':
                in_str = True
                out.append(ch)
                prev_space = False
                continue

            if ch.isspace():
                if not prev_space:
                    out.append(" ")
                prev_space = True
            else:
                out.append(ch)
                prev_space = False

        return "".join(out).rstrip()

    lines = code.replace("\t", "    ").split("\n")
    indent = 0
    out = []

    for raw in lines:
        line = raw.strip()
        if not line:
            # keep at most one blank line
            if out and out[-1] != "":
                out.append("")
            continue

        # normalize spacing (but preserve string literals)
        line = collapse_spaces_outside_strings(line)

        # pre-dedent if line starts with close brace
        if line.startswith("}"):
            indent = max(indent - 1, 0)

        out.append(("    " * indent) + line)

        # adjust indent based on brace delta for this line
        indent += line.count("{") - line.count("}")
        if indent < 0:
            indent = 0

    return "\n".join(out).strip()



def split_vb_one_liners(code: str) -> str:
    """
    Safer VB splitter:
      - Joins line continuations: " _"
      - Splits ':' statement separators ONLY when not inside string literals
      - Splits mid-line VB statements (Dim/If/For/Return/etc) when BP has jammed them together
      - Converts single-line If/Then/Else into multi-line blocks

    Notes:
      - Still heuristic, but much more readable for BP-exported VB code.
      - Does NOT attempt a full VB parse; just makes lines sane for indenting.
    """
    if not code:
        return ""

    s = code.replace("\r\n", "\n").replace("\r", "\n")

    # 1) Join VB line continuations " _"
    joined_lines = []
    buf = ""
    for raw in s.split("\n"):
        line = raw.rstrip()
        if buf:
            buf += line.lstrip()
        else:
            buf = line

        # VB line continuation often looks like: " _" at end (possibly with tabs/spaces)
        if re.search(r"\s+_\s*$", buf):
            buf = re.sub(r"\s+_\s*$", " ", buf)  # remove the continuation marker, keep space
            continue
        else:
            joined_lines.append(buf)
            buf = ""
    if buf:
        joined_lines.append(buf)

    s = "\n".join(joined_lines)

    # 2) Split ':' separators safely (not inside quotes)
    def split_colons_outside_strings(line: str) -> list[str]:
        parts = []
        cur = []
        in_string = False
        i = 0
        while i < len(line):
            ch = line[i]

            if ch == '"':
                # VB uses "" to escape a quote inside a string
                if in_string and i + 1 < len(line) and line[i + 1] == '"':
                    cur.append('""')
                    i += 2
                    continue
                in_string = not in_string
                cur.append(ch)
                i += 1
                continue

            if (ch == ":") and (not in_string):
                part = "".join(cur).strip()
                if part:
                    parts.append(part)
                cur = []
                i += 1
                # skip any immediate whitespace after colon
                while i < len(line) and line[i].isspace():
                    i += 1
                continue

            cur.append(ch)
            i += 1

        last = "".join(cur).strip()
        if last:
            parts.append(last)
        return parts

    split_lines = []
    for raw in s.split("\n"):
        raw = raw.strip()
        if not raw:
            split_lines.append("")
            continue
        split_lines.extend(split_colons_outside_strings(raw))

    # 2.5) NEW: Split mid-line VB statements when BP jams many statements onto one line
    # Example:
    #   Dim x = 1 y = 2 If Not ok Then Return Dim z = 3
    VB_STATEMENT_KEYWORDS = (
        # common declarations / flow
        "dim ",
        "set ",
        "const ",
        "if ",
        "elseif ",
        "else",
        "end if",
        "select case",
        "case ",
        "end select",

        # try/catch
        "try",
        "catch ",
        "finally",
        "end try",

        # loops
        "for each ",
        "for ",
        "while ",
        "do ",
        "loop",
        "next",

        # exits/returns
        "return",
        "exit sub",
        "exit function",
        "exit for",
        "exit while",
    )


    def split_midline_vb_statements(line: str) -> list[str]:
        parts = []
        cur = []
        in_string = False
        low = line.lower()
        i = 0

        while i < len(line):
            ch = line[i]

            if ch == '"':
                # VB escaped quotes: ""
                if in_string and i + 1 < len(line) and line[i + 1] == '"':
                    cur.append('""')
                    i += 2
                    continue
                in_string = not in_string
                cur.append(ch)
                i += 1
                continue

            if not in_string:
                # split only at keyword boundaries AND only if we already have content
                for kw in VB_STATEMENT_KEYWORDS:
                    if low.startswith(kw, i) and cur:
                        part = "".join(cur).strip()
                        if part:
                            parts.append(part)
                        cur = []
                        break

            cur.append(ch)
            i += 1

        tail = "".join(cur).strip()
        if tail:
            parts.append(tail)

        return parts

    expanded_lines = []
    for raw in split_lines:
        raw = raw.strip()
        if not raw:
            expanded_lines.append("")
            continue
        expanded_lines.extend(split_midline_vb_statements(raw))

    split_lines = expanded_lines

    # 3) Convert single-line IF statements into blocks (after splitting)
    out_lines = []
    i = 0
    while i < len(split_lines):
        t = split_lines[i].strip()
        if not t:
            out_lines.append("")
            i += 1
            continue

        # If ... Then ... Else ...
        m = re.match(r"^if\s+(.*?)\s+then\s+(.*?)\s+else\s+(.*)$", t, flags=re.IGNORECASE)
        if m:
            cond = m.group(1).strip()
            then_part = m.group(2).strip()
            else_part = m.group(3).strip()
            out_lines.append(f"If {cond} Then")
            out_lines.append(f"    {then_part}")
            out_lines.append("Else")
            out_lines.append(f"    {else_part}")
            out_lines.append("End If")
            i += 1
            continue

        # If ... Then ... (no Else)
        m2 = re.match(r"^if\s+(.*?)\s+then\s+(.+)$", t, flags=re.IGNORECASE)
        if m2 and not t.lower().endswith("then"):
            cond = m2.group(1).strip()
            then_part = m2.group(2).strip()
            out_lines.append(f"If {cond} Then")
            out_lines.append(f"    {then_part}")
            out_lines.append("End If")
            i += 1
            continue

        out_lines.append(t)
        i += 1

    s2 = "\n".join(out_lines)
    s2 = re.sub(r"\n{3,}", "\n\n", s2)
    return s2.strip()



def pretty_print_vb_blocks(code: str) -> str:
    code = split_vb_one_liners(normalize_code(code))
    if not code:
        return ""

    lines = code.replace("\t", "    ").split("\n")
    indent = 0
    out = []

    enders = (
        "end if", "end sub", "end function", "end select", "end try",
        "next", "loop", "wend", "end while", "end with"
    )
    starters = (
        "if ", "select case", "try", "for ", "while ", "with ", "do ", "sub ", "function "
    )
    miders = ("else", "elseif", "case ", "catch", "finally")

    for raw in lines:
        line = raw.strip()
        if not line:
            out.append("")
            continue

        low = line.lower()

        if any(low.startswith(e) for e in enders):
            indent = max(indent - 1, 0)

        if any(low.startswith(m) for m in miders):
            indent = max(indent - 1, 0)
            out.append(("    " * indent) + line)
            indent += 1
            continue

        out.append(("    " * indent) + line)

        if any(low.startswith(s) for s in starters):
            if low.startswith("if ") and low.endswith("then"):
                indent += 1
            elif low.startswith("if ") and (" then " in low) and (not low.endswith("then")):
                # should be rare after splitting
                pass
            else:
                indent += 1

    return "\n".join(out).strip()


def pretty_print_code(code: str, language: str) -> str:
    code = normalize_code(code)
    if not code:
        return ""

    language = normalize_language(language)
    lang = language.lower()

    if language == "C#":
        return pretty_print_csharp_braces(code)

    if language == "VB":
        return pretty_print_vb_blocks(code)

    return normalize_whitespace(code)

def count_display_lines(code: str) -> int:
    """
    Count lines exactly as rendered.
    No normalization, no trimming, no collapsing.
    """
    if not code:
        return 0
    return code.count("\n") + 1


# -----------------------------
# Static findings (no LLM)
# -----------------------------

def simple_code_findings(code: str) -> Dict[str, Any]:
    c = code or ""
    c_low = c.lower()

    def has_any(*subs: str) -> bool:
        return any(s in c_low for s in subs)

    findings: Dict[str, Any] = {
        "has_sql_keywords": has_any("select ", "insert ", "update ", "delete ", "exec ", "sp_", "merge "),
        "has_http": has_any("http://", "https://", "webrequest", "httpclient", "restsharp"),
        "has_file_io": has_any("filesystem", "file.", "directory.", "streamreader", "streamwriter"),
        "has_crypto": has_any("sha", "md5", "aes", "rsa", "cryptography", "rijndael"),
        "has_reflection": has_any("reflection", "gettype(", "activator.createinstance"),
        "has_process_start": has_any("process.start", "shell(", "wscript.shell"),
        "has_hardcoded_credential_like": bool(re.search(r"(password\s*=|pwd\s*=|apikey|api_key|token\s*=|bearer\s+)", c_low)),
        "mentions_blueprism_internal": has_any("blueprism", "automate", "session", "resourcepc"),
    }

    urls = re.findall(r"https?://[^\s\"\'<>]+", c)
    findings["urls"] = sorted(set(urls))[:50]
    return findings
