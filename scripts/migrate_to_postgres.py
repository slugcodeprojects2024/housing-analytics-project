"""
Migrate SQLite database to Neon Postgres.

Reads all data from the local SQLite database and pushes it to
a Neon Postgres instance. Run this once to populate the remote database.

Usage:
    python -m scripts.migrate_to_postgres
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

SQLITE_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "housing.db"
PG_URL = os.getenv("DATABASE_URL")

# Postgres schema — adapted from SQLite schema
PG_SCHEMA = """
DROP TABLE IF EXISTS derived_metrics CASCADE;
DROP TABLE IF EXISTS housing_metrics CASCADE;
DROP TABLE IF EXISTS metro_wages CASCADE;
DROP TABLE IF EXISTS metro_crosswalk CASCADE;
DROP TABLE IF EXISTS macro_indicators CASCADE;
DROP TABLE IF EXISTS load_log CASCADE;
DROP TABLE IF EXISTS geographies CASCADE;

CREATE TABLE geographies (
    geography_id   SERIAL PRIMARY KEY,
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

BATCH_SIZE = 10000


def migrate_table(sqlite_conn, pg_conn, table_name, columns, id_col_is_serial=False):
    """Migrate a single table from SQLite to Postgres."""
    print(f"\n  Migrating {table_name}...")

    cursor = sqlite_conn.execute(f"SELECT COUNT(*) FROM {table_name}")
    total = cursor.fetchone()[0]
    print(f"    {total:,} rows to migrate")

    if total == 0:
        return

    col_list = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))

    pg_cursor = pg_conn.cursor()

    # Read and insert in batches
    offset = 0
    inserted = 0
    while offset < total:
        rows = sqlite_conn.execute(
            f"SELECT {col_list} FROM {table_name} LIMIT {BATCH_SIZE} OFFSET {offset}"
        ).fetchall()

        if not rows:
            break

        # Convert to list of tuples
        values = [tuple(row) for row in rows]

        insert_sql = f"INSERT INTO {table_name} ({col_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"
        pg_cursor.executemany(insert_sql, values)
        pg_conn.commit()

        inserted += len(rows)
        offset += BATCH_SIZE
        print(f"    {inserted:,} / {total:,} rows ({inserted * 100 // total}%)")

    print(f"    Done: {inserted:,} rows inserted")


def main():
    if not PG_URL:
        print("ERROR: DATABASE_URL not set in .env")
        return

    print("=" * 60)
    print("SQLite → Neon Postgres Migration")
    print("=" * 60)

    # Connect to both databases
    print(f"\nSQLite: {SQLITE_PATH}")
    print(f"Postgres: {PG_URL[:50]}...")

    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    pg_conn = psycopg2.connect(PG_URL)

    # Create schema
    print("\n[1/7] Creating Postgres schema...")
    pg_cursor = pg_conn.cursor()
    pg_cursor.execute(PG_SCHEMA)
    pg_conn.commit()
    print("  Schema created.")

    # Migrate tables in order (respecting foreign keys)
    print("\n[2/7] Migrating geographies...")
    migrate_table(sqlite_conn, pg_conn, "geographies",
                  ["geography_id", "geo_code", "geo_type", "name", "state", "county", "metro", "latitude", "longitude"])

    print("\n[3/7] Migrating housing_metrics...")
    migrate_table(sqlite_conn, pg_conn, "housing_metrics",
                  ["geography_id", "metric_date", "metric_type", "value"])

    print("\n[4/7] Migrating macro_indicators...")
    migrate_table(sqlite_conn, pg_conn, "macro_indicators",
                  ["indicator", "obs_date", "value"])

    print("\n[5/7] Migrating metro_wages...")
    migrate_table(sqlite_conn, pg_conn, "metro_wages",
                  ["area_code", "area_name", "occ_code", "occ_title", "total_employed",
                   "median_wage", "mean_wage", "pct10_wage", "pct25_wage", "pct75_wage",
                   "pct90_wage", "data_year"])

    print("\n[6/7] Migrating metro_crosswalk...")
    migrate_table(sqlite_conn, pg_conn, "metro_crosswalk",
                  ["bls_area_code", "bls_area_name", "zillow_metro", "match_quality"])

    print("\n[7/7] Migrating derived_metrics...")
    migrate_table(sqlite_conn, pg_conn, "derived_metrics",
                  ["geography_id", "metric_date", "metric_name", "value"])

    # Verify
    print("\n" + "=" * 60)
    print("Verification:")
    pg_cursor = pg_conn.cursor()
    for table in ["geographies", "housing_metrics", "macro_indicators", "derived_metrics", "metro_wages", "metro_crosswalk"]:
        pg_cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = pg_cursor.fetchone()[0]
        print(f"  {table}: {count:,} rows")

    sqlite_conn.close()
    pg_conn.close()
    print("\nMigration complete!")


if __name__ == "__main__":
    main()
