"""
Bootstrap / ingest script.

Loads a Blue Prism 'Exported Processes.csv' into SQLite as process_table.

This script is intentionally separate from analysis pipelines.
"""

import argparse
import pandas as pd
import sqlite3
from pathlib import Path

DEFAULT_TABLE = "process_table"
DEFAULT_CHUNK_SIZE = 100_000

COLUMN_NAMES = [
    "processid",
    "ProcessType",
    "name",
    "description",
    "version",
    "createdate",
    "createdby",
    "lastmodifieddate",
    "lastmodifiedby",
    "AttributeID",
    "compressedxml",
    "processxml",
    "wspublishname",
    "runmode",
    "sharedObject",
    "forceLiteralForm",
    "useLegacyNamespace",
    "hasStartupParameters",
    "b2",
]

def load_csv_to_sqlite(
    csv_path: Path,
    db_path: Path,
    table_name: str,
    chunk_size: int,
    replace: bool,
):
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    conn = sqlite3.connect(db_path)

    # Create or validate table schema
    sample_df = pd.read_csv(
        csv_path,
        header=None,
        names=COLUMN_NAMES,
        nrows=1,
        delimiter=",",
        quotechar='"',
    )

    if replace:
        sample_df.to_sql(table_name, conn, if_exists="replace", index=False)
    else:
        sample_df.to_sql(table_name, conn, if_exists="append", index=False)

    # Load full data in chunks
    for chunk in pd.read_csv(
        csv_path,
        header=None,
        names=COLUMN_NAMES,
        chunksize=chunk_size,
        delimiter=",",
        quotechar='"',
    ):
        chunk.to_sql(table_name, conn, if_exists="append", index=False)

    conn.commit()
    conn.close()

    print(f"Loaded CSV → SQLite")
    print(f"  CSV   : {csv_path}")
    print(f"  DB    : {db_path}")
    print(f"  Table : {table_name}")
    print(f"  Rows  : ~{sum(1 for _ in open(csv_path)) - 1}")

def main():
    parser = argparse.ArgumentParser(description="Load Blue Prism process CSV into SQLite")
    parser.add_argument(
        "--csv",
        required=True,
        help="Path to 'Exported Processes.csv'",
    )
    parser.add_argument(
        "--db",
        default="process_data.db",
        help="SQLite database file (default: process_data.db)",
    )
    parser.add_argument(
        "--table",
        default=DEFAULT_TABLE,
        help="Target table name (default: process_table)",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help="CSV read chunk size (default: 100000)",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Drop and recreate the target table",
    )

    args = parser.parse_args()

    load_csv_to_sqlite(
        csv_path=Path(args.csv),
        db_path=Path(args.db),
        table_name=args.table,
        chunk_size=args.chunk_size,
        replace=args.replace,
    )

if __name__ == "__main__":
    main()
