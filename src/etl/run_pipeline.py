"""
ETL pipeline entry point.

Run with: python -m src.etl.run_pipeline

Each step is idempotent — safe to re-run.
"""
from __future__ import annotations

import time

from src.db.connection import init_schema
from src.etl.load_zillow import load_all as load_zillow
from src.etl.load_fred import load_all_series as load_fred


def main() -> None:
    print("=" * 60)
    print("Housing Analytics ETL Pipeline")
    print("=" * 60)

    print("\n[1/4] Initializing database schema...")
    init_schema()

    print("\n[2/4] Loading Zillow data...")
    start = time.time()
    zillow_results = load_zillow()
    elapsed = time.time() - start
    print(f"\n  Zillow load completed in {elapsed:.1f}s")
    for fname, count in zillow_results.items():
        print(f"    {fname}: {count:,} rows")

    print("\n[3/4] Loading FRED macro indicators...")
    start = time.time()
    fred_results = load_fred()
    elapsed = time.time() - start
    print(f"\n  FRED load completed in {elapsed:.1f}s")
    for indicator, count in fred_results.items():
        print(f"    {indicator}: {count:,} rows")

    print("\n[4/4] Computing derived metrics...")
    # TODO: implement in src/etl/derived.py
    print("  (not yet implemented)")

    print("\n" + "=" * 60)
    print("Pipeline complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
