"""
Fast migration: SQLite → Neon Postgres using COPY command.

COPY is orders of magnitude faster than INSERT for bulk loads.

Usage:
    python -m scripts.migrate_to_postgres_fast
"""
from __future__ import annotations

import csv
import io
import os
import sqlite3
import time
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv()

SQLITE_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "housing.db"
PG_URL = os.getenv("DATABASE_URL")

PG_SCHEMA = """
DROP TABLE IF EXISTS derived_metrics CASCADE;
DROP TABLE IF EXISTS housing_metrics CASCADE;
DROP TABLE IF EXISTS metro_wages CASCADE;
DROP TABLE IF EXISTS metro_crosswalk CASCADE;
DROP TABLE IF EXISTS macro_indicators CASCADE;
DROP TABLE IF EXISTS load_log CASCADE;
DROP TABLE IF EXISTS geographies CASCADE;

CREATE TABLE geographies (
    geography_id   INTEGER PRIMARY KEY,
    geo_code       TEXT NOT NULL,
    geo_type       TEXT NOT NULL,
    name           TEXT NOT NULL,
    state          TEXT,
    county         TEXT,
    metro          TEXT,
    latitude       DOUBLE PRECISION,
    longitude      DOUBLE PRECISION,
    UNIQUE(geo_code, geo_type)
);
CREATE INDEX idx_geo_state ON geographies(state);
CREATE INDEX idx_geo_type  ON geographies(geo_type);

CREATE TABLE housing_metrics (
    geography_id   INTEGER NOT NULL REFERENCES geographies(geography_id),
    metric_date    DATE NOT NULL,
    metric_type    TEXT NOT NULL,
    value          DOUBLE PRECISION,
    PRIMARY KEY (geography_id, metric_date, metric_type)
);
CREATE INDEX idx_hm_date    ON housing_metrics(metric_date);
CREATE INDEX idx_hm_metric  ON housing_metrics(metric_type);

CREATE TABLE macro_indicators (
    indicator      TEXT NOT NULL,
    obs_date       DATE NOT NULL,
    value          DOUBLE PRECISION,
    PRIMARY KEY (indicator, obs_date)
);

CREATE TABLE metro_wages (
    area_code      TEXT NOT NULL,
    area_name      TEXT NOT NULL,
    occ_code       TEXT NOT NULL,
    occ_title      TEXT NOT NULL,
    total_employed INTEGER,
    median_wage    DOUBLE PRECISION,
    mean_wage      DOUBLE PRECISION,
    pct10_wage     DOUBLE PRECISION,
    pct25_wage     DOUBLE PRECISION,
    pct75_wage     DOUBLE PRECISION,
    pct90_wage     DOUBLE PRECISION,
    data_year      INTEGER NOT NULL,
    PRIMARY KEY (area_code, occ_code, data_year)
);
CREATE INDEX idx_mw_occ ON metro_wages(occ_code);
CREATE INDEX idx_mw_area ON metro_wages(area_code);

CREATE TABLE metro_crosswalk (
    bls_area_code  TEXT NOT NULL PRIMARY KEY,
    bls_area_name  TEXT NOT NULL,
    zillow_metro   TEXT,
    match_quality  TEXT
);

CREATE TABLE derived_metrics (
    geography_id   INTEGER NOT NULL REFERENCES geographies(geography_id),
    metric_date    DATE NOT NULL,
    metric_name    TEXT NOT NULL,
    value          DOUBLE PRECISION,
    PRIMARY KEY (geography_id, metric_date, metric_name)
);

CREATE TABLE load_log (
    load_id        SERIAL PRIMARY KEY,
    source         TEXT NOT NULL,
    loaded_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    row_count      INTEGER,
    notes          TEXT
);
"""

BATCH_SIZE = 100000


def copy_table(sqlite_conn, pg_url, table_name, columns):
    """Migrate a table using Postgres COPY with reconnection on failure."""
    print(f"\n  {table_name}...")

    cursor = sqlite_conn.execute(f"SELECT COUNT(*) FROM {table_name}")
    total = cursor.fetchone()[0]

    # Check how many rows already exist (for resume)
    pg_conn = psycopg2.connect(pg_url)
    pg_cursor = pg_conn.cursor()
    pg_cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    existing = pg_cursor.fetchone()[0]
    pg_conn.close()

    if existing >= total:
        print(f"    Already complete: {existing:,} rows")
        return

    if existing > 0:
        print(f"    Resuming from {existing:,} / {total:,} rows")

    col_list = ", ".join(columns)
    start = time.time()
    offset = existing
    copied = existing

    while offset < total:
        # Reconnect for each batch to avoid SSL timeout
        try:
            pg_conn = psycopg2.connect(pg_url)
            pg_cursor = pg_conn.cursor()

            rows = sqlite_conn.execute(
                f"SELECT {col_list} FROM {table_name} LIMIT {BATCH_SIZE} OFFSET {offset}"
            ).fetchall()

            if not rows:
                pg_conn.close()
                break

            buf = io.StringIO()
            writer = csv.writer(buf, delimiter='\t', quoting=csv.QUOTE_MINIMAL)
            for row in rows:
                writer.writerow([r if r is not None else '\\N' for r in row])

            buf.seek(0)
            pg_cursor.copy_from(buf, table_name, columns=columns, null='\\N')
            pg_conn.commit()
            pg_conn.close()

            copied += len(rows)
            offset += BATCH_SIZE
            elapsed = time.time() - start
            rate = (copied - existing) / elapsed if elapsed > 0 else 0
            print(f"    {copied:,} / {total:,} ({copied * 100 // total}%) — {rate:,.0f} rows/sec")

        except Exception as e:
            print(f"    Error at offset {offset}: {e}")
            print(f"    Retrying in 3 seconds...")
            try:
                pg_conn.close()
            except:
                pass
            time.sleep(3)
            continue

    elapsed = time.time() - start
    print(f"    Done in {elapsed:.1f}s")


def main():
    if not PG_URL:
        print("ERROR: DATABASE_URL not set in .env")
        return

    print("=" * 60)
    print("Fast SQLite → Postgres Migration (COPY)")
    print("=" * 60)

    sqlite_conn = sqlite3.connect(SQLITE_PATH)

    # Check if schema exists, create if not
    pg_conn = psycopg2.connect(PG_URL)
    pg_cursor = pg_conn.cursor()
    pg_cursor.execute("SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='geographies')")
    schema_exists = pg_cursor.fetchone()[0]
    
    if not schema_exists:
        print("\n[1] Creating schema...")
        pg_cursor.execute(PG_SCHEMA)
        pg_conn.commit()
    else:
        print("\n[1] Schema already exists, resuming migration...")
    pg_conn.close()

    tables = [
        ("geographies", ["geography_id", "geo_code", "geo_type", "name", "state", "county", "metro", "latitude", "longitude"]),
        ("housing_metrics", ["geography_id", "metric_date", "metric_type", "value"]),
        ("macro_indicators", ["indicator", "obs_date", "value"]),
        ("metro_wages", ["area_code", "area_name", "occ_code", "occ_title", "total_employed", "median_wage", "mean_wage", "pct10_wage", "pct25_wage", "pct75_wage", "pct90_wage", "data_year"]),
        ("metro_crosswalk", ["bls_area_code", "bls_area_name", "zillow_metro", "match_quality"]),
        ("derived_metrics", ["geography_id", "metric_date", "metric_name", "value"]),
    ]

    print("\n[2] Copying tables...")
    for table_name, columns in tables:
        copy_table(sqlite_conn, PG_URL, table_name, columns)

    print("\n[3] Verifying...")
    pg_conn = psycopg2.connect(PG_URL)
    pg_cursor = pg_conn.cursor()
    for table_name, _ in tables:
        pg_cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = pg_cursor.fetchone()[0]
        print(f"  {table_name}: {count:,}")

    sqlite_conn.close()
    pg_conn.close()
    print("\nMigration complete!")


if __name__ == "__main__":
    main()