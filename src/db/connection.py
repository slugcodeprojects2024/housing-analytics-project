"""Database connection helpers and schema initialization."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from src.config import DB_PATH

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def connection():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema() -> None:
    sql = SCHEMA_PATH.read_text()
    with connection() as conn:
        conn.executescript(sql)
    print(f"Schema initialized at {DB_PATH}")


def ensure_sqlite_geographies_columns() -> None:
    """Add geographies columns missing from older DB builds (e.g. release snapshots)."""
    if not DB_PATH.exists():
        return
    conn = sqlite3.connect(DB_PATH)
    try:
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='geographies'"
        ).fetchone():
            return
        cols = {row[1] for row in conn.execute("PRAGMA table_info(geographies)").fetchall()}
        alters: list[tuple[str, str]] = [
            ("state", "TEXT"),
            ("county", "TEXT"),
            ("metro", "TEXT"),
            ("latitude", "REAL"),
            ("longitude", "REAL"),
        ]
        for name, typ in alters:
            if name not in cols:
                conn.execute(f"ALTER TABLE geographies ADD COLUMN {name} {typ}")
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_schema()
