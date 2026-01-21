# bp_analyzer/utils.py
from __future__ import annotations

from datetime import datetime
import hashlib
import html as _html


def format_date(date_str: str) -> str:
    """
    Best-effort BP dates often look like: 'YYYY-mm-dd HH:MM:SS.fff'
    """
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S.%f")
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return date_str


def safe_pct(part: int, whole: int) -> float:
    return round((part / whole) * 100.0, 2) if whole else 0.0


def sha256_text(s: str | None) -> str:
    if s is None:
        s = ""
    return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()


def normalize_code(s: str | None) -> str:
    """
    Stable normalization for hashing + display baselines:
      - Normalize line endings
      - Strip trailing whitespace on each line
      - Trim leading/trailing blank space
    """
    if not s:
        return ""
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = "\n".join(line.rstrip() for line in s.split("\n"))
    return s.strip()


def get_line_count(s: str | None) -> int:
    s = normalize_code(s)
    return 0 if not s else len(s.split("\n"))


def safe_html(s: str | None) -> str:
    return _html.escape(s or "")
