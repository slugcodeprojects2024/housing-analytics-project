"""
Query helpers for the dashboard.

Each function returns a pandas DataFrame ready for display or charting.
Keeps SQL out of the dashboard code so the app stays clean.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

# Resolve DB path relative to this file
DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "processed" / "housing.db"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---- KPI Queries -----------------------------------------------------------

def get_national_kpis() -> dict:
    """Return headline KPIs for the national market."""
    conn = _conn()

    # Latest national ZHVI
    r = conn.execute("""
        SELECT h.value, h.metric_date
        FROM housing_metrics h
        JOIN geographies g ON g.geography_id = h.geography_id
        WHERE g.geo_type = 'national' AND h.metric_type = 'zhvi'
        ORDER BY h.metric_date DESC LIMIT 1
    """).fetchone()
    current_price = r["value"] if r else None
    current_date = r["metric_date"] if r else None

    # YoY change: compare to same month last year
    if current_date:
        year_ago = current_date[:4]
        year_ago = str(int(year_ago) - 1) + current_date[4:]
        r2 = conn.execute("""
            SELECT h.value
            FROM housing_metrics h
            JOIN geographies g ON g.geography_id = h.geography_id
            WHERE g.geo_type = 'national' AND h.metric_type = 'zhvi'
              AND h.metric_date <= ? 
            ORDER BY h.metric_date DESC LIMIT 1
        """, (year_ago,)).fetchone()
        yoy_change = ((current_price - r2["value"]) / r2["value"] * 100) if r2 else None
    else:
        yoy_change = None

    # Latest mortgage rate
    r = conn.execute("""
        SELECT value, obs_date FROM macro_indicators
        WHERE indicator = 'mortgage_30y'
        ORDER BY obs_date DESC LIMIT 1
    """).fetchone()
    mortgage_rate = r["value"] if r else None

    # Latest median income
    r = conn.execute("""
        SELECT value FROM macro_indicators
        WHERE indicator = 'median_income'
        ORDER BY obs_date DESC LIMIT 1
    """).fetchone()
    median_income = r["value"] if r else None

    # National price-to-income ratio
    price_to_income = (current_price / median_income) if (current_price and median_income) else None

    conn.close()
    return {
        "current_price": current_price,
        "current_date": current_date,
        "yoy_change": yoy_change,
        "mortgage_rate": mortgage_rate,
        "median_income": median_income,
        "price_to_income": price_to_income,
    }


def get_metro_kpis(metro_name: str) -> dict:
    """Return KPIs for a specific metro area."""
    conn = _conn()

    r = conn.execute("""
        SELECT h.value, h.metric_date
        FROM housing_metrics h
        JOIN geographies g ON g.geography_id = h.geography_id
        WHERE g.geo_code = ? AND g.geo_type = 'metro' AND h.metric_type = 'zhvi'
        ORDER BY h.metric_date DESC LIMIT 1
    """, (metro_name,)).fetchone()
    current_price = r["value"] if r else None
    current_date = r["metric_date"] if r else None

    # YoY
    if current_date:
        year_ago = str(int(current_date[:4]) - 1) + current_date[4:]
        r2 = conn.execute("""
            SELECT h.value
            FROM housing_metrics h
            JOIN geographies g ON g.geography_id = h.geography_id
            WHERE g.geo_code = ? AND g.geo_type = 'metro' AND h.metric_type = 'zhvi'
              AND h.metric_date <= ?
            ORDER BY h.metric_date DESC LIMIT 1
        """, (metro_name, year_ago)).fetchone()
        yoy_change = ((current_price - r2["value"]) / r2["value"] * 100) if r2 else None
    else:
        yoy_change = None

    # Rent
    r = conn.execute("""
        SELECT h.value
        FROM housing_metrics h
        JOIN geographies g ON g.geography_id = h.geography_id
        WHERE g.geo_code = ? AND g.geo_type = 'metro' AND h.metric_type = 'zori'
        ORDER BY h.metric_date DESC LIMIT 1
    """, (metro_name,)).fetchone()
    current_rent = r["value"] if r else None

    conn.close()
    return {
        "current_price": current_price,
        "current_date": current_date,
        "yoy_change": yoy_change,
        "current_rent": current_rent,
    }


# ---- Chart Queries ---------------------------------------------------------

def get_price_trends(geo_codes: list[str], metric_type: str = "zhvi") -> pd.DataFrame:
    """Get time series for one or more geographies.

    Returns DataFrame with columns: metric_date, geo_code, name, value
    """
    conn = _conn()
    placeholders = ",".join("?" for _ in geo_codes)
    df = pd.read_sql_query(f"""
        SELECT h.metric_date, g.geo_code, g.name, h.value
        FROM housing_metrics h
        JOIN geographies g ON g.geography_id = h.geography_id
        WHERE g.geo_code IN ({placeholders})
          AND h.metric_type = ?
        ORDER BY h.metric_date
    """, conn, params=[*geo_codes, metric_type])
    conn.close()
    df["metric_date"] = pd.to_datetime(df["metric_date"])
    return df


def get_mortgage_vs_price() -> pd.DataFrame:
    """Get national ZHVI and mortgage rate on a monthly basis for comparison."""
    conn = _conn()
    # National ZHVI (monthly)
    prices = pd.read_sql_query("""
        SELECT h.metric_date as date, h.value as home_price
        FROM housing_metrics h
        JOIN geographies g ON g.geography_id = h.geography_id
        WHERE g.geo_type = 'national' AND h.metric_type = 'zhvi'
        ORDER BY h.metric_date
    """, conn)

    # Mortgage rate — resample weekly to monthly (take last observation per month)
    rates = pd.read_sql_query("""
        SELECT obs_date as date, value as mortgage_rate
        FROM macro_indicators
        WHERE indicator = 'mortgage_30y'
        ORDER BY obs_date
    """, conn)
    conn.close()

    prices["date"] = pd.to_datetime(prices["date"])
    rates["date"] = pd.to_datetime(rates["date"])

    # Resample rates to month-end to match ZHVI dates
    rates = rates.set_index("date").resample("ME").last().reset_index()

    merged = pd.merge(prices, rates, on="date", how="inner")
    return merged


def get_affordability_over_time() -> pd.DataFrame:
    """Get national price-to-income ratio over time."""
    conn = _conn()
    prices = pd.read_sql_query("""
        SELECT h.metric_date as date, h.value as home_price
        FROM housing_metrics h
        JOIN geographies g ON g.geography_id = h.geography_id
        WHERE g.geo_type = 'national' AND h.metric_type = 'zhvi'
        ORDER BY h.metric_date
    """, conn)

    income = pd.read_sql_query("""
        SELECT obs_date as date, value as income
        FROM macro_indicators
        WHERE indicator = 'median_income'
        ORDER BY obs_date
    """, conn)
    conn.close()

    prices["date"] = pd.to_datetime(prices["date"])
    prices["year"] = prices["date"].dt.year
    income["date"] = pd.to_datetime(income["date"])
    income["year"] = income["date"].dt.year

    # Join on year — income is annual, prices are monthly
    merged = pd.merge(prices, income[["year", "income"]], on="year", how="inner")
    merged["price_to_income"] = merged["home_price"] / merged["income"]
    return merged[["date", "home_price", "income", "price_to_income"]]


def get_metro_comparison(metro_names: list[str]) -> pd.DataFrame:
    """Get latest ZHVI for a list of metros for bar chart comparison."""
    conn = _conn()
    placeholders = ",".join("?" for _ in metro_names)

    df = pd.read_sql_query(f"""
        SELECT g.geo_code as metro, h.value as home_price, h.metric_date
        FROM housing_metrics h
        JOIN geographies g ON g.geography_id = h.geography_id
        WHERE g.geo_code IN ({placeholders})
          AND g.geo_type = 'metro'
          AND h.metric_type = 'zhvi'
          AND h.metric_date = (
              SELECT MAX(h2.metric_date) 
              FROM housing_metrics h2 
              JOIN geographies g2 ON g2.geography_id = h2.geography_id
              WHERE g2.geo_type = 'metro' AND h2.metric_type = 'zhvi'
          )
        ORDER BY h.value DESC
    """, conn, params=metro_names)
    conn.close()
    return df


def get_zip_comparison(county_name: str) -> pd.DataFrame:
    """Get latest ZHVI for all ZIPs in a county."""
    conn = _conn()
    df = pd.read_sql_query("""
        SELECT g.geo_code as zip_code, g.name as city, h.value as home_price
        FROM housing_metrics h
        JOIN geographies g ON g.geography_id = h.geography_id
        WHERE g.county = ? AND g.geo_type = 'zip' AND h.metric_type = 'zhvi'
          AND h.metric_date = (
              SELECT MAX(h2.metric_date)
              FROM housing_metrics h2
              JOIN geographies g2 ON g2.geography_id = h2.geography_id
              WHERE g2.geo_type = 'zip' AND h2.metric_type = 'zhvi'
          )
        ORDER BY h.value DESC
    """, conn, params=(county_name,))
    conn.close()
    return df


# ---- Filter helpers --------------------------------------------------------

def get_all_metros() -> list[str]:
    """Return list of all metro names for dropdowns."""
    conn = _conn()
    rows = conn.execute("""
        SELECT DISTINCT geo_code FROM geographies
        WHERE geo_type = 'metro'
        ORDER BY geo_code
    """).fetchall()
    conn.close()
    return [r["geo_code"] for r in rows]


def get_all_counties() -> list[str]:
    """Return list of all counties that have ZIP-level data."""
    conn = _conn()
    rows = conn.execute("""
        SELECT DISTINCT county FROM geographies
        WHERE geo_type = 'zip' AND county IS NOT NULL
        ORDER BY county
    """).fetchall()
    conn.close()
    return [r["county"] for r in rows]


def get_states() -> list[str]:
    """Return list of all states."""
    conn = _conn()
    rows = conn.execute("""
        SELECT DISTINCT state FROM geographies
        WHERE state IS NOT NULL
        ORDER BY state
    """).fetchall()
    conn.close()
    return [r["state"] for r in rows]
