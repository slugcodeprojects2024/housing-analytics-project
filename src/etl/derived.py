"""
Compute derived metrics and store in the derived_metrics table.

Metrics computed:
  - purchasing_power_index: For each metro × occupation, how much home 
    can you afford relative to the national average?
  - price_to_local_wage: Metro home price / occupation median wage
  - monthly_payment_pct_income: Estimated mortgage payment as % of gross monthly income
  - rent_to_wage_ratio: Monthly rent / monthly gross wage

Usage:
    python -m src.etl.derived
"""
from __future__ import annotations

from src.db.connection import connection, init_schema


def compute_purchasing_power() -> int:
    """Compute purchasing power index for each metro × occupation.
    
    Formula:
      monthly_wage = median_wage / 12
      monthly_mortgage = mortgage_payment(home_price, current_rate, 20% down, 30yr)
      housing_cost_ratio = monthly_mortgage / monthly_wage
      national_housing_cost_ratio = same calculation for national median
      purchasing_power_index = national_housing_cost_ratio / housing_cost_ratio * 100
    
    Index of 100 = same as national average
    Index > 100 = better purchasing power (more affordable relative to wages)
    Index < 100 = worse purchasing power (less affordable relative to wages)
    """
    with connection() as conn:
        # Get current mortgage rate
        rate_row = conn.execute("""
            SELECT value FROM macro_indicators 
            WHERE indicator = 'mortgage_30y' 
            ORDER BY obs_date DESC LIMIT 1
        """).fetchone()
        if not rate_row:
            print("  No mortgage rate data found, skipping.")
            return 0
        annual_rate = rate_row["value"] / 100
        monthly_rate = annual_rate / 12
        n_payments = 360  # 30 years

        # Get national median home price
        national_row = conn.execute("""
            SELECT h.value 
            FROM housing_metrics h
            JOIN geographies g ON g.geography_id = h.geography_id
            WHERE g.geo_type = 'national' AND h.metric_type = 'zhvi'
            ORDER BY h.metric_date DESC LIMIT 1
        """).fetchone()
        if not national_row:
            print("  No national home price data found, skipping.")
            return 0
        national_price = national_row["value"]

        # Get national median income (from FRED)
        income_row = conn.execute("""
            SELECT value FROM macro_indicators
            WHERE indicator = 'median_income'
            ORDER BY obs_date DESC LIMIT 1
        """).fetchone()
        national_income = income_row["value"] if income_row else 70000

        # Helper: compute monthly mortgage payment
        def monthly_payment(home_price, down_pct=0.20):
            loan = home_price * (1 - down_pct)
            if monthly_rate > 0:
                return loan * (monthly_rate * (1 + monthly_rate)**n_payments) / ((1 + monthly_rate)**n_payments - 1)
            return loan / n_payments

        national_payment = monthly_payment(national_price)
        national_monthly_income = national_income / 12
        national_ratio = national_payment / national_monthly_income if national_monthly_income > 0 else 1

        # Get all matched metros with both wage data and home price data
        rows = conn.execute("""
            SELECT 
                mw.area_code,
                mw.area_name,
                mw.occ_code,
                mw.occ_title,
                mw.median_wage,
                mc.zillow_metro,
                g.geography_id,
                h.value as home_price,
                h.metric_date
            FROM metro_wages mw
            JOIN metro_crosswalk mc ON mc.bls_area_code = mw.area_code
            JOIN geographies g ON g.geo_code = mc.zillow_metro AND g.geo_type = 'metro'
            JOIN housing_metrics h ON h.geography_id = g.geography_id AND h.metric_type = 'zhvi'
            WHERE mc.zillow_metro IS NOT NULL
              AND mw.median_wage IS NOT NULL
              AND h.metric_date = (
                  SELECT MAX(h2.metric_date) FROM housing_metrics h2 
                  JOIN geographies g2 ON g2.geography_id = h2.geography_id
                  WHERE g2.geo_type = 'metro' AND h2.metric_type = 'zhvi'
              )
        """).fetchall()

        if not rows:
            print("  No matched metro+wage data found. Run load_bls.py first.")
            return 0

        # Compute and insert derived metrics
        inserts = []
        for r in rows:
            geo_id = r["geography_id"]
            metric_date = r["metric_date"]
            home_price = r["home_price"]
            median_wage = r["median_wage"]
            occ_code = r["occ_code"]
            monthly_wage = median_wage / 12

            # Monthly mortgage payment
            payment = monthly_payment(home_price)

            # Housing cost ratio for this metro+occupation
            local_ratio = payment / monthly_wage if monthly_wage > 0 else 999

            # Purchasing power index (100 = national average)
            ppi = (national_ratio / local_ratio * 100) if local_ratio > 0 else 0

            # Price-to-wage ratio
            price_to_wage = home_price / median_wage if median_wage > 0 else 0

            # Monthly payment as % of gross income
            payment_pct = (payment / monthly_wage * 100) if monthly_wage > 0 else 0

            # Use occ_code as suffix so we can store per-occupation metrics
            inserts.append((geo_id, metric_date, f"ppi_{occ_code}", ppi))
            inserts.append((geo_id, metric_date, f"price_to_wage_{occ_code}", price_to_wage))
            inserts.append((geo_id, metric_date, f"payment_pct_{occ_code}", payment_pct))

        conn.executemany(
            """INSERT OR REPLACE INTO derived_metrics 
               (geography_id, metric_date, metric_name, value)
               VALUES (?, ?, ?, ?)""",
            inserts,
        )

        print(f"  Computed {len(inserts):,} derived metrics for {len(rows):,} metro-occupation pairs")
        return len(inserts)


def compute_rent_to_wage() -> int:
    """Compute rent-to-wage ratio for each metro × occupation."""
    with connection() as conn:
        rows = conn.execute("""
            SELECT 
                mw.occ_code,
                mw.median_wage,
                g.geography_id,
                h.value as rent,
                h.metric_date
            FROM metro_wages mw
            JOIN metro_crosswalk mc ON mc.bls_area_code = mw.area_code
            JOIN geographies g ON g.geo_code = mc.zillow_metro AND g.geo_type = 'metro'
            JOIN housing_metrics h ON h.geography_id = g.geography_id AND h.metric_type = 'zori'
            WHERE mc.zillow_metro IS NOT NULL
              AND mw.median_wage IS NOT NULL
              AND h.metric_date = (
                  SELECT MAX(h2.metric_date) FROM housing_metrics h2 
                  JOIN geographies g2 ON g2.geography_id = h2.geography_id
                  WHERE g2.geo_type = 'metro' AND h2.metric_type = 'zori'
              )
        """).fetchall()

        inserts = []
        for r in rows:
            monthly_wage = r["median_wage"] / 12
            rent = r["rent"]
            if monthly_wage > 0:
                ratio = rent / monthly_wage * 100  # as percentage
                inserts.append((r["geography_id"], r["metric_date"],
                               f"rent_pct_{r['occ_code']}", ratio))

        if inserts:
            conn.executemany(
                """INSERT OR REPLACE INTO derived_metrics
                   (geography_id, metric_date, metric_name, value)
                   VALUES (?, ?, ?, ?)""",
                inserts,
            )

        print(f"  Computed {len(inserts):,} rent-to-wage metrics")
        return len(inserts)


if __name__ == "__main__":
    init_schema()
    print("\nComputing derived metrics...")
    compute_purchasing_power()
    compute_rent_to_wage()
    print("\nDone.")
