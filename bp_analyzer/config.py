# config.py
from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    customer_name: str = "Atmaal"
    db_file: str = "process_data.db"

    # Outputs (each script can override)
    report_output: str = "combined_report.html"
    code_jsonl_output: str = "code_stages.jsonl"

SETTINGS = Settings()
