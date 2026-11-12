"""Run every query in a .sql file against weather.db and print readable tables.

Run:  python run_sql.py                      (runs sql/week1_queries.sql)
      python run_sql.py path/to/other.sql

Works without installing the sqlite3 command-line tool. Each query is printed
with the comment lines written above it, so the business question is visible.
"""
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent


def split_statements(sql_text: str) -> list[tuple[str, str]]:
    """Return (comment, statement) pairs, using sqlite3.complete_statement to find the ends."""
    pairs, comment, buffer = [], [], ""
    for line in sql_text.splitlines():
        stripped = line.strip()
        if not buffer and stripped.startswith("--"):
            comment.append(stripped.lstrip("- ").rstrip())
            continue
        if not buffer and not stripped:
            if comment and not comment[-1]:
                continue
            comment.append("")
            continue
        buffer += line + "\n"
        if sqlite3.complete_statement(buffer):
            # keep only the comment block that sits directly above this statement
            block = "\n".join(comment).strip().split("\n\n")[-1]
            pairs.append((block, buffer.strip()))
            comment, buffer = [], ""
    return pairs


def main() -> None:
    sql_file = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJECT_ROOT / "sql" / "week1_queries.sql"
    db_path = PROJECT_ROOT / "weather.db"
    if not db_path.exists():
        sys.exit("weather.db not found. Run `python etl_v1.py` first.")
    with closing(sqlite3.connect(db_path)) as conn:
        for comment, statement in split_statements(sql_file.read_text(encoding="utf-8")):
            print("=" * 100)
            print(comment)
            print("-" * 100)
            print(pd.read_sql_query(statement, conn).to_string(index=False))
            print()


if __name__ == "__main__":
    main()
