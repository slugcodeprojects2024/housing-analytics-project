"""
FRED macro indicator loader.

Pulls key economic time series and loads them into the macro_indicators table.

Series:
  - MORTGAGE30US: 30-Year Fixed Rate Mortgage Average (weekly)
  - MEHOINUSA672N: Real Median Household Income (annual)
  - CPIAUCSL: Consumer Price Index for All Urban Consumers (monthly)
  - CSUSHPINSA: S&P/Case-Shiller U.S. National Home Price Index (monthly)

Usage:
    python -m src.etl.load_fred
"""
from __future__ import annotations

from fredapi import Fred

from src.config import FRED_API_KEY, require
from src.db.connection import connection, init_schema

FRED_SERIES = {
    "mortgage_30y": "MORTGAGE30US",
    "median_income": "MEHOINUSA672N",
    "cpi": "CPIAUCSL",
    "case_shiller": "CSUSHPINSA",
}


def load_all_series() -> dict[str, int]:
    """Pull every series and load into macro_indicators. Returns {indicator: row_count}."""
    api_key = require("FRED_API_KEY", FRED_API_KEY)
    fred = Fred(api_key=api_key)

    results = {}

    for indicator_name, series_id in FRED_SERIES.items():
        print(f"  Fetching {indicator_name} ({series_id})...")

        try:
            series = fred.get_series(series_id)
        except Exception as e:
            print(f"    ERROR: {e}")
            results[indicator_name] = 0
            continue

        # Drop NaN values
        series = series.dropna()

        # Build rows for insertion
        rows = [
            (indicator_name, str(date.date()), float(value))
            for date, value in series.items()
        ]

        with connection() as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO macro_indicators (indicator, obs_date, value)
                   VALUES (?, ?, ?)""",
                rows,
            )
            conn.execute(
                "INSERT INTO load_log (source, row_count, notes) VALUES (?, ?, ?)",
                (f"FRED:{series_id}", len(rows), indicator_name),
            )

        print(f"    {len(rows):,} observations ({series.index.min().date()} to {series.index.max().date()})")
        results[indicator_name] = len(rows)

    return results


if __name__ == "__main__":
    init_schema()
    print("\nLoading FRED data...")
    results = load_all_series()
    print("\n=== Summary ===")
    for indicator, count in results.items():
        print(f"  {indicator}: {count:,} rows")
    print(f"  Total: {sum(results.values()):,} rows")
