"""SQLite access. The DB is built locally with `python -m ingest.build_db` and is never committed."""
import sqlite3

from app import config


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
