# db.py
import sqlite3
from typing import Iterable, Tuple
import os

def connect_db(db_file: str) -> sqlite3.Connection:
    print("DB path:", os.path.abspath(db_file))
    return sqlite3.connect(db_file)

def reset_tables(cursor, table_definitions: Iterable[Tuple[str, str]]):
    for table, create_sql in table_definitions:
        cursor.execute(f"DROP TABLE IF EXISTS {table};")
        cursor.execute(create_sql)

def fetch_process_data(cursor):
    # include ProcessType so we can detect Objects ('O') vs Processes ('P')
    cursor.execute("""
        SELECT UPPER(processid), name, description, processxml, ProcessType
        FROM process_table;
    """)
    return cursor.fetchall()
