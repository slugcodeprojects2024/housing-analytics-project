"""
Zillow data loader.

Loads both ZIP-level and Metro-level CSVs into the geographies and
housing_metrics tables. Handles the wide-to-long reshape, zero-pads
ZIP codes, and deduplicates geographies across files.

Data files expected in data/raw/zillow/:
  - Zip_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv
  - Zip_zori_uc_sfrcondomfr_sm_month.csv
  - Metro_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv
  - Metro_zori_uc_sfrcondomfr_sm_month.csv

Usage:
    python -m src.etl.load_zillow
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.config import RAW_DIR
from src.db.connection import connection, init_schema

ZILLOW_DIR = RAW_DIR / "zillow"


# ---- Helpers ---------------------------------------------------------------

def identify_columns(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    """Split DataFrame columns into ID (metadata) and date (value) columns."""
    id_cols = [c for c in df.columns if not c[0].isdigit()]
    date_cols = [c for c in df.columns if c[0].isdigit()]
    return id_cols, date_cols


def melt_wide_to_long(
    df: pd.DataFrame,
    id_cols: list[str],
    date_cols: list[str],
) -> pd.DataFrame:
    """Reshape a Zillow wide-format DataFrame to long format.

    Returns a DataFrame with columns from id_cols plus 'metric_date' and 'value'.
    Drops rows where value is NaN (no data for that ZIP/date).
    """
    long = df.melt(
        id_vars=id_cols,
        value_vars=date_cols,
        var_name="metric_date",
        value_name="value",
    )
    long["metric_date"] = pd.to_datetime(long["metric_date"]).dt.date
    return long.dropna(subset=["value"])


# ---- Geography upsert ------------------------------------------------------

def upsert_geographies_zip(df: pd.DataFrame, conn) -> dict[str, int]:
    """Insert ZIP-level geographies. Returns {geo_code: geography_id} mapping."""
    # Deduplicate — one row per ZIP
    geo_df = df[["RegionName", "State", "City", "Metro", "CountyName"]].drop_duplicates()

    geo_map = {}
    for _, row in geo_df.iterrows():
        geo_code = str(row["RegionName"]).zfill(5)  # Zero-pad ZIP codes
        city = row.get("City", "")
        name = f"{city}, {row['State']}" if pd.notna(city) and city else geo_code

        conn.execute(
            """INSERT OR IGNORE INTO geographies (geo_code, geo_type, name, state, county, metro)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (geo_code, "zip", name, row.get("State"), row.get("CountyName"), row.get("Metro")),
        )
        result = conn.execute(
            "SELECT geography_id FROM geographies WHERE geo_code = ? AND geo_type = ?",
            (geo_code, "zip"),
        ).fetchone()
        geo_map[str(row["RegionName"])] = result["geography_id"]

    return geo_map


def upsert_geographies_metro(df: pd.DataFrame, conn) -> dict[str, int]:
    """Insert Metro-level geographies. Returns {RegionName: geography_id} mapping."""
    geo_df = df[["RegionName", "RegionType", "StateName"]].drop_duplicates()

    geo_map = {}
    for _, row in geo_df.iterrows():
        region_name = row["RegionName"]
        region_type = row["RegionType"]  # 'msa' or 'country'
        geo_type = "national" if region_type == "country" else "metro"

        # Use RegionName as the geo_code for metros
        conn.execute(
            """INSERT OR IGNORE INTO geographies (geo_code, geo_type, name, state)
               VALUES (?, ?, ?, ?)""",
            (region_name, geo_type, region_name, row.get("StateName")),
        )
        result = conn.execute(
            "SELECT geography_id FROM geographies WHERE geo_code = ? AND geo_type = ?",
            (region_name, geo_type),
        ).fetchone()
        geo_map[region_name] = result["geography_id"]

    return geo_map


# ---- Metric loading ---------------------------------------------------------

def load_metrics(
    long_df: pd.DataFrame,
    geo_map: dict[str, int],
    geo_key_col: str,
    metric_type: str,
    conn,
) -> int:
    """Load long-format metric data into housing_metrics table.

    Args:
        long_df: melted DataFrame with geo_key_col, metric_date, value
        geo_map: mapping from geo key to geography_id
        geo_key_col: column name to look up in geo_map (e.g. 'RegionName')
        metric_type: e.g. 'zhvi', 'zori'
        conn: database connection

    Returns:
        Number of rows inserted.
    """
    rows = []
    for _, row in long_df.iterrows():
        geo_key = str(row[geo_key_col])
        geo_id = geo_map.get(geo_key)
        if geo_id is None:
            continue
        rows.append((geo_id, str(row["metric_date"]), metric_type, float(row["value"])))

    conn.executemany(
        """INSERT OR REPLACE INTO housing_metrics (geography_id, metric_date, metric_type, value)
           VALUES (?, ?, ?, ?)""",
        rows,
    )
    return len(rows)


# ---- File loaders -----------------------------------------------------------

def load_zip_file(csv_path: Path, metric_type: str) -> int:
    """Load a ZIP-level Zillow CSV. Returns row count."""
    print(f"  Reading {csv_path.name}...")
    df = pd.read_csv(csv_path)
    id_cols, date_cols = identify_columns(df)

    print(f"    {len(df):,} ZIPs × {len(date_cols)} months")

    # Reshape to long format
    print(f"    Reshaping to long format...")
    long = melt_wide_to_long(df, id_cols, date_cols)
    print(f"    {len(long):,} data points (after dropping NaN)")

    with connection() as conn:
        # Upsert geographies
        print(f"    Upserting geographies...")
        geo_map = upsert_geographies_zip(df, conn)

        # Load metrics
        print(f"    Loading {metric_type} metrics...")
        count = load_metrics(long, geo_map, "RegionName", metric_type, conn)

        # Log the load
        conn.execute(
            "INSERT INTO load_log (source, row_count, notes) VALUES (?, ?, ?)",
            (csv_path.name, count, f"{metric_type} from ZIP-level file"),
        )

    print(f"    Done: {count:,} rows loaded")
    return count


def load_metro_file(csv_path: Path, metric_type: str) -> int:
    """Load a Metro-level Zillow CSV. Returns row count."""
    print(f"  Reading {csv_path.name}...")
    df = pd.read_csv(csv_path)
    id_cols, date_cols = identify_columns(df)

    print(f"    {len(df):,} metros × {len(date_cols)} months")

    # Reshape to long format
    print(f"    Reshaping to long format...")
    long = melt_wide_to_long(df, id_cols, date_cols)
    print(f"    {len(long):,} data points (after dropping NaN)")

    with connection() as conn:
        # Upsert geographies
        print(f"    Upserting geographies...")
        geo_map = upsert_geographies_metro(df, conn)

        # Load metrics
        print(f"    Loading {metric_type} metrics...")
        count = load_metrics(long, geo_map, "RegionName", metric_type, conn)

        # Log the load
        conn.execute(
            "INSERT INTO load_log (source, row_count, notes) VALUES (?, ?, ?)",
            (csv_path.name, count, f"{metric_type} from metro-level file"),
        )

    print(f"    Done: {count:,} rows loaded")
    return count


# ---- Main entry point -------------------------------------------------------

def load_all() -> dict[str, int]:
    """Discover and load all Zillow CSVs. Returns {filename: row_count}."""
    results = {}

    # Define what we're looking for: (glob pattern, metric_type, loader_fn)
    file_specs = [
        ("Zip_zhvi_*.csv",   "zhvi", load_zip_file),
        ("Zip_zori_*.csv",   "zori", load_zip_file),
        ("Metro_zhvi_*.csv", "zhvi", load_metro_file),
        ("Metro_zori_*.csv", "zori", load_metro_file),
    ]

    for pattern, metric_type, loader_fn in file_specs:
        matches = list(ZILLOW_DIR.glob(pattern))
        if not matches:
            print(f"  Skipping {pattern} — file not found")
            continue

        # Skip forecast/growth files
        matches = [m for m in matches if "growth" not in m.name.lower()
                   and "zhvf" not in m.name.lower()
                   and "zorf" not in m.name.lower()]

        for csv_path in matches:
            count = loader_fn(csv_path, metric_type)
            results[csv_path.name] = count

    return results


if __name__ == "__main__":
    init_schema()
    print("\nLoading Zillow data...")
    results = load_all()
    print("\n=== Summary ===")
    total = 0
    for fname, count in results.items():
        print(f"  {fname}: {count:,} rows")
        total += count
    print(f"  Total: {total:,} rows")
