"""
BLS Occupational Employment and Wage Statistics (OEWS) loader.

Downloads/loads the MSA-level wage data from BLS and builds a crosswalk
mapping BLS metro names to Zillow metro names.

Data source:
  Download from: https://www.bls.gov/oes/2024/may/oessrcma.htm
  Or direct: https://www.bls.gov/oes/special-requests/oesm24ma.zip
  Unzip and place the Excel file in data/raw/bls/

The file contains ~830 occupations × ~530 MSAs with employment and wage data.

We filter to a curated list of ~20 common occupations to keep the data
manageable and the dashboard usable.

Usage:
    python -m src.etl.load_bls
"""
from __future__ import annotations

from pathlib import Path
from difflib import SequenceMatcher

import pandas as pd

from src.config import RAW_DIR
from src.db.connection import connection, init_schema

BLS_DIR = RAW_DIR / "bls"

# Occupations to keep — these are common, recognizable, and span income ranges.
# SOC codes from the 2018 SOC system.
TARGET_OCCUPATIONS = {
    "11-1021": "General and Operations Managers",
    "13-2011": "Accountants and Auditors",
    "15-1252": "Software Developers",
    "15-1211": "Computer Systems Analysts",
    "15-1244": "Network and Computer Systems Administrators",
    "17-2051": "Civil Engineers",
    "17-2112": "Industrial Engineers",
    "21-1021": "Child, Family, and School Social Workers",
    "23-1011": "Lawyers",
    "25-2021": "Elementary School Teachers, Except Special Education",
    "25-2031": "Secondary School Teachers, Except Special and Career/Technical Education",
    "29-1141": "Registered Nurses",
    "29-1215": "Family Medicine Physicians",
    "31-1131": "Nursing Assistants",
    "33-3051": "Police and Sheriff's Patrol Officers",
    "35-2014": "Cooks, Restaurant",
    "37-2011": "Janitors and Cleaners",
    "41-3021": "Insurance Sales Agents",
    "43-6014": "Secretaries, Except Legal, Medical, and Executive",
    "47-2061": "Construction Laborers",
    "49-9021": "Heating, AC, and Refrigeration Mechanics and Installers",
    "53-3032": "Heavy and Tractor-Trailer Truck Drivers",
}


def find_bls_file() -> Path | None:
    """Find the OEWS Excel file in data/raw/bls/."""
    if not BLS_DIR.exists():
        return None

    # Look for Excel files matching OEWS naming patterns
    for pattern in ["oesm*.xlsx", "MSA_M*.xlsx", "all_data*.xlsx", "*.xlsx"]:
        matches = list(BLS_DIR.glob(pattern))
        if matches:
            return matches[0]

    # Also check for CSV
    for pattern in ["oesm*.csv", "MSA_M*.csv", "all_data*.csv", "*.csv"]:
        matches = list(BLS_DIR.glob(pattern))
        if matches:
            return matches[0]

    return None


def load_bls_data() -> int:
    """Load BLS OEWS data into metro_wages table. Returns row count."""
    data_file = find_bls_file()
    if not data_file:
        print(f"  No BLS data file found in {BLS_DIR}/")
        print(f"  Download from: https://www.bls.gov/oes/special-requests/oesm24ma.zip")
        print(f"  Unzip and place the Excel file in {BLS_DIR}/")
        return 0

    print(f"  Reading {data_file.name}...")

    # Read the file
    if data_file.suffix == ".xlsx":
        df = pd.read_excel(data_file)
    else:
        df = pd.read_csv(data_file)

    print(f"    Raw data: {len(df):,} rows × {len(df.columns)} columns")
    print(f"    Columns: {list(df.columns)}")

    # Standardize column names to uppercase for consistency
    df.columns = [c.upper().strip() for c in df.columns]

    # Identify the key columns — BLS naming varies slightly by year
    col_map = {}
    for c in df.columns:
        c_lower = c.lower()
        if c_lower == "area" or ("area" in c_lower and ("code" in c_lower or "fips" in c_lower)):
            col_map["area_code"] = c
        elif "area" in c_lower and ("title" in c_lower or "name" in c_lower):
            col_map["area_name"] = c
        elif c_lower in ("area_type", "areatype"):
            col_map["area_type"] = c
        elif "occ_code" in c_lower or c_lower == "occ code":
            col_map["occ_code"] = c
        elif "occ_title" in c_lower or c_lower == "occ title":
            col_map["occ_title"] = c
        elif c_lower in ("tot_emp", "employment"):
            col_map["tot_emp"] = c
        elif c_lower in ("a_median", "annual median wage"):
            col_map["a_median"] = c
        elif c_lower in ("a_mean", "annual mean wage"):
            col_map["a_mean"] = c
        elif c_lower in ("a_pct10",):
            col_map["a_pct10"] = c
        elif c_lower in ("a_pct25",):
            col_map["a_pct25"] = c
        elif c_lower in ("a_pct75",):
            col_map["a_pct75"] = c
        elif c_lower in ("a_pct90",):
            col_map["a_pct90"] = c

    print(f"    Mapped columns: {col_map}")

    # Filter to MSA areas only (area_type == 2 means MSA in BLS data)
    if "area_type" in col_map:
        df = df[df[col_map["area_type"]].astype(str).isin(["2", "4", "M"])]
        print(f"    After MSA filter: {len(df):,} rows")

    # Filter to target occupations
    if "occ_code" in col_map:
        df = df[df[col_map["occ_code"]].isin(TARGET_OCCUPATIONS.keys())]
        print(f"    After occupation filter: {len(df):,} rows")

    # Convert wage columns to numeric (BLS uses '*' and '#' for suppressed data)
    wage_cols = ["a_median", "a_mean", "a_pct10", "a_pct25", "a_pct75", "a_pct90", "tot_emp"]
    for col_key in wage_cols:
        if col_key in col_map:
            df[col_map[col_key]] = pd.to_numeric(df[col_map[col_key]], errors="coerce")

    # Build rows for insertion
    rows = []
    for _, row in df.iterrows():
        area_code = str(row.get(col_map.get("area_code", ""), "")).strip()
        area_name = str(row.get(col_map.get("area_name", ""), "")).strip()
        occ_code = str(row.get(col_map.get("occ_code", ""), "")).strip()
        occ_title = str(row.get(col_map.get("occ_title", ""), "")).strip()

        if not area_code or not occ_code:
            continue

        rows.append((
            area_code,
            area_name,
            occ_code,
            occ_title,
            row.get(col_map.get("tot_emp")),
            row.get(col_map.get("a_median")),
            row.get(col_map.get("a_mean")),
            row.get(col_map.get("a_pct10")),
            row.get(col_map.get("a_pct25")),
            row.get(col_map.get("a_pct75")),
            row.get(col_map.get("a_pct90")),
            2024,  # data year
        ))

    with connection() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO metro_wages 
               (area_code, area_name, occ_code, occ_title, total_employed,
                median_wage, mean_wage, pct10_wage, pct25_wage, pct75_wage, pct90_wage, data_year)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        conn.execute(
            "INSERT INTO load_log (source, row_count, notes) VALUES (?, ?, ?)",
            (data_file.name, len(rows), "BLS OEWS May 2024 MSA wage data"),
        )

    print(f"    Loaded: {len(rows):,} rows")
    return len(rows)


def _extract_first_city_state(metro_name: str) -> str:
    """Extract 'City, ST' from a full metro name.
    
    'San Jose-Sunnyvale-Santa Clara, CA' → 'San Jose, CA'
    'Austin-Round Rock-San Marcos, TX' → 'Austin, TX'
    'New York-Newark-Jersey City, NY-NJ-PA' → 'New York, NY'
    """
    # Split on comma to get city part and state part
    parts = metro_name.split(",")
    if len(parts) < 2:
        return metro_name.strip()
    
    city_part = parts[0].strip()
    state_part = parts[1].strip()
    
    # Get first city (before any dash)
    first_city = city_part.split("-")[0].strip()
    
    # Get first state code (before any dash)
    first_state = state_part.split("-")[0].strip()
    
    return f"{first_city}, {first_state}"


def build_crosswalk() -> int:
    """Build a crosswalk between BLS metro names and Zillow metro names.
    
    Strategy:
      1. Exact match on full name
      2. Match BLS first-city-state to Zillow first-city-state
      3. Fuzzy match on full name as fallback
    
    Returns number of matched metros.
    """
    print("  Building BLS → Zillow metro crosswalk...")

    with connection() as conn:
        # Get distinct BLS metros
        bls_metros = conn.execute(
            "SELECT DISTINCT area_code, area_name FROM metro_wages"
        ).fetchall()

        # Get all Zillow metros
        zillow_metros = conn.execute(
            "SELECT geo_code FROM geographies WHERE geo_type = 'metro'"
        ).fetchall()

        zillow_names = [r["geo_code"] for r in zillow_metros]
        
        # Build a lookup: first_city_state → full zillow name
        zillow_by_city = {}
        for z in zillow_names:
            key = _extract_first_city_state(z).lower()
            zillow_by_city[key] = z

        matched = 0
        for bls in bls_metros:
            bls_code = bls["area_code"]
            bls_name = bls["area_name"]

            # Strategy 1: Exact match on full name
            if bls_name in zillow_names:
                conn.execute(
                    """INSERT OR REPLACE INTO metro_crosswalk 
                       (bls_area_code, bls_area_name, zillow_metro, match_quality)
                       VALUES (?, ?, ?, 'exact')""",
                    (bls_code, bls_name, bls_name),
                )
                matched += 1
                continue

            # Strategy 2: Match on first city + state
            bls_city_key = _extract_first_city_state(bls_name).lower()
            if bls_city_key in zillow_by_city:
                zillow_match = zillow_by_city[bls_city_key]
                conn.execute(
                    """INSERT OR REPLACE INTO metro_crosswalk 
                       (bls_area_code, bls_area_name, zillow_metro, match_quality)
                       VALUES (?, ?, ?, 'city_match')""",
                    (bls_code, bls_name, zillow_match),
                )
                matched += 1
                continue

            # Strategy 3: Fuzzy match on full name as fallback
            best_score = 0
            best_match = None
            for zillow_name in zillow_names:
                score = SequenceMatcher(None, bls_name.lower(), zillow_name.lower()).ratio()
                if score > best_score:
                    best_score = score
                    best_match = zillow_name

            if best_score >= 0.65:
                conn.execute(
                    """INSERT OR REPLACE INTO metro_crosswalk 
                       (bls_area_code, bls_area_name, zillow_metro, match_quality)
                       VALUES (?, ?, ?, 'fuzzy')""",
                    (bls_code, bls_name, best_match),
                )
                matched += 1
            else:
                conn.execute(
                    """INSERT OR REPLACE INTO metro_crosswalk 
                       (bls_area_code, bls_area_name, zillow_metro, match_quality)
                       VALUES (?, ?, NULL, 'unmatched')""",
                    (bls_code, bls_name),
                )

    print(f"    {matched} / {len(bls_metros)} BLS metros matched to Zillow metros")
    return matched


if __name__ == "__main__":
    init_schema()
    print("\nLoading BLS wage data...")
    count = load_bls_data()
    if count > 0:
        build_crosswalk()
    print("\nDone.")
