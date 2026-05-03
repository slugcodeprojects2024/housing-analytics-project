"""
Database connection helper that works with both SQLite (local) and Postgres (production).

If DATABASE_URL is set and starts with 'postgresql', uses Postgres.
Otherwise falls back to the local SQLite database.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")
DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "processed" / "housing.db"

USE_POSTGRES = DATABASE_URL.startswith("postgresql")


def get_connection():
    """Return a database connection — Postgres if available, SQLite otherwise."""
    if USE_POSTGRES:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn


def read_sql(query: str, params=None):
    """Execute a SELECT query and return results as list of dicts."""
    import pandas as pd
    conn = get_connection()
    try:
        df = pd.read_sql_query(query, conn, params=params)
        return df
    finally:
        conn.close()


def execute_query(query: str, params=None) -> tuple[list[dict], list[str]]:
    """Execute a query and return (rows_as_dicts, column_names)."""
    conn = get_connection()
    try:
        if USE_POSTGRES:
            import psycopg2.extras
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute(query, params)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = [dict(row) for row in cursor.fetchall()]
        else:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params or ())
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = [dict(row) for row in cursor.fetchall()]
        return rows, columns
    finally:
        conn.close()


def fetchone(query: str, params=None) -> dict | None:
    """Execute a query and return a single row as dict, or None."""
    conn = get_connection()
    try:
        if USE_POSTGRES:
            import psycopg2.extras
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute(query, params)
            row = cursor.fetchone()
            return dict(row) if row else None
        else:
            conn.row_factory = sqlite3.Row
            row = conn.execute(query, params or ()).fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def fetchall(query: str, params=None) -> list[dict]:
    """Execute a query and return all rows as list of dicts."""
    conn = get_connection()
    try:
        if USE_POSTGRES:
            import psycopg2.extras
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
        else:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params or ()).fetchall()
            return [dict(row) for row in rows]
    finally:
        conn.close()
