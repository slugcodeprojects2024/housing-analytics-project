"""
Text-to-SQL via Claude.

Pipeline:
  1. User asks a question in natural language
  2. Build a prompt with the database schema and context
  3. Claude generates a SQL query
  4. Validate the SQL (SELECT only, known tables/columns, add LIMIT)
  5. Execute against SQLite
  6. Send results back to Claude for plain-English summary
  7. Return both the data and summary to the caller
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from src.config import CLAUDE_MODEL, require

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "processed" / "housing.db"


def _resolve_anthropic_api_key() -> str | None:
    """Env first (.env via load_dotenv), then Streamlit secrets when running in Streamlit."""
    load_dotenv()
    key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    if key:
        return key
    try:
        import streamlit as st
        sec = st.secrets.get("ANTHROPIC_API_KEY", "")
        if isinstance(sec, str) and sec.strip():
            return sec.strip()
    except Exception:
        pass
    return None

# Tables and columns Claude is allowed to reference
SCHEMA_INFO = {
    "geographies": [
        "geography_id", "geo_code", "geo_type", "name",
        "state", "county", "metro", "latitude", "longitude",
    ],
    "housing_metrics": [
        "geography_id", "metric_date", "metric_type", "value",
    ],
    "macro_indicators": [
        "indicator", "obs_date", "value",
    ],
    "derived_metrics": [
        "geography_id", "metric_date", "metric_name", "value",
    ],
    "metro_wages": [
        "area_code", "area_name", "occ_code", "occ_title",
        "total_employed", "median_wage", "mean_wage",
        "pct10_wage", "pct25_wage", "pct75_wage", "pct90_wage", "data_year",
    ],
    "metro_crosswalk": [
        "bls_area_code", "bls_area_name", "zillow_metro", "match_quality",
    ],
}

VALID_TABLES = set(SCHEMA_INFO.keys())
VALID_COLUMNS = set()
for cols in SCHEMA_INFO.values():
    VALID_COLUMNS.update(cols)

SYSTEM_PROMPT = """You are a SQL analyst for a housing market analytics database. When the user asks a question, generate a SQLite query to answer it, then explain the results.

DATABASE SCHEMA:

geographies — One row per geographic area
  geography_id  INTEGER PRIMARY KEY
  geo_code      TEXT        — ZIP code (5-digit, zero-padded string like '95051') or metro name like 'San Jose-Sunnyvale-Santa Clara, CA' or 'United States'
  geo_type      TEXT        — 'zip' | 'metro' | 'national'
  name          TEXT        — Display name (e.g. 'Santa Clara, CA' for ZIPs, or the metro name)
  state         TEXT        — 2-letter state code (e.g. 'CA')
  county        TEXT        — County name (e.g. 'Santa Clara County') — only for ZIP-level
  metro         TEXT        — Metro area name — only for ZIP-level
  latitude      REAL
  longitude     REAL

housing_metrics — Time series housing data (long format: one row per geography per date per metric)
  geography_id  INTEGER     — FK to geographies
  metric_date   DATE        — e.g. '2026-02-28'
  metric_type   TEXT        — 'zhvi' (home value) or 'zori' (rent)
  value         REAL        — Dollar amount

macro_indicators — National economic indicators
  indicator     TEXT        — 'mortgage_30y' | 'median_income' | 'cpi' | 'case_shiller'
  obs_date      DATE
  value         REAL        — Rate (%), dollars, or index value

metro_wages — BLS occupational wage data by metro area (May 2024)
  area_code     TEXT        — BLS MSA code (e.g. '41940')
  area_name     TEXT        — BLS MSA name (e.g. 'San Jose-Sunnyvale-Santa Clara, CA')
  occ_code      TEXT        — SOC occupation code (e.g. '15-1252')
  occ_title     TEXT        — Occupation name (e.g. 'Software Developers')
  total_employed INTEGER    — Number of workers in this occupation in this metro
  median_wage   REAL        — Annual median wage
  mean_wage     REAL        — Annual mean wage
  pct10_wage    REAL        — 10th percentile annual wage
  pct25_wage    REAL        — 25th percentile annual wage
  pct75_wage    REAL        — 75th percentile annual wage
  pct90_wage    REAL        — 90th percentile annual wage
  data_year     INTEGER     — Year of data (2024)

metro_crosswalk — Maps BLS metro names to Zillow metro names
  bls_area_code TEXT        — BLS area code
  bls_area_name TEXT        — BLS metro name
  zillow_metro  TEXT        — Matching Zillow metro name (geo_code from geographies)
  match_quality TEXT        — 'exact', 'fuzzy', or 'unmatched'

derived_metrics — Pre-computed analytics per metro
  geography_id  INTEGER     — FK to geographies
  metric_date   DATE
  metric_name   TEXT        — e.g. 'ppi_15-1252' (purchasing power index for software devs)
                            — 'price_to_wage_15-1252', 'payment_pct_15-1252', 'rent_pct_15-1252'
  value         REAL

KEY FACTS:
- SQL aliases: use `g` or `geo` ONLY for the `geographies` table when referencing state, county, metro, geo_code, or name. Never use `g` for `housing_metrics` (use `h` or `hm`).
- West Coast metros: filter with `g.state IN ('CA','OR','WA')` when `state` is populated; if unsure, also allow `g.geo_type = 'metro' AND (g.geo_code LIKE '%, CA' OR g.geo_code LIKE '%, OR' OR g.geo_code LIKE '%, WA')`.
- ZIP codes are STRINGS, always 5 digits, zero-padded (e.g. '08701' not 8701)
- geo_type values: 'zip', 'metro', 'national'
- metric_type values: 'zhvi' (Zillow Home Value Index = median home value), 'zori' (Zillow Observed Rent Index = median rent)
- macro_indicators.indicator values: 'mortgage_30y', 'median_income', 'cpi', 'case_shiller'
- Housing data spans 2000-01 to 2026-03, ~26K ZIPs and ~900 metros
- The 'United States' geography has geo_type = 'national'
- To get "Bay Area": look for metro names containing 'San Jose' or 'San Francisco'
- To get Santa Clara County ZIPs: WHERE county = 'Santa Clara County' AND geo_type = 'zip'
- To join wage data to housing data: use metro_crosswalk to map BLS area_code to Zillow metro geo_code
- Purchasing power index (PPI): 100 = national average. Higher = more affordable relative to wages. Lower = less affordable.
- Common occupations in metro_wages include: Software Developers (15-1252), Registered Nurses (29-1141), Elementary School Teachers (25-2021), Lawyers (23-1011), Construction Laborers (47-2061), Truck Drivers (53-3032), Restaurant Cooks (35-2014), Police Officers (33-3051)
- derived_metrics metric_name format: 'ppi_{occ_code}', 'price_to_wage_{occ_code}', 'payment_pct_{occ_code}', 'rent_pct_{occ_code}'

RESPONSE FORMAT:
Always respond with a JSON object (no markdown fences) containing:
{
  "sql": "YOUR SQL QUERY HERE",
  "explanation": "Brief explanation of what this query does"
}

RULES:
- Only generate SELECT statements (WITH ... AS (...) SELECT ... is allowed for CTEs)
- Always include a LIMIT clause (max 100 rows unless the user asks for all)
- Use JOINs between geographies and housing_metrics via geography_id
- For "latest" or "current" data, use ORDER BY metric_date DESC LIMIT 1 or a subquery for MAX(metric_date)
- For year-over-year comparisons, join the table to itself with a 1-year date offset
- Always alias columns for readability
- If you cannot answer the question with the available data, set sql to null and explain why
"""

SUMMARY_PROMPT = """The user asked: "{question}"

The SQL query returned the following results:
{results}

Provide a clear, concise summary of what this data shows. Highlight key findings, notable trends, or surprising values. If the data includes prices, format them as currency. Keep it to 2-4 sentences unless the data warrants more detail."""


@dataclass
class QueryResult:
    question: str
    sql: str | None
    explanation: str
    rows: list[dict] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    summary: str = ""
    error: str | None = None


def validate_sql(sql: str) -> str | None:
    """Validate SQL for safety. Returns error message if invalid, None if OK."""
    sql_upper = sql.strip().upper()

    # Must be read-only: plain SELECT or WITH ... SELECT (CTE)
    if not (sql_upper.startswith("SELECT") or sql_upper.startswith("WITH")):
        return "Only SELECT queries are allowed."

    # Block dangerous statements
    dangerous = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE", "EXEC"]
    for keyword in dangerous:
        # Check for keyword as a standalone word
        if re.search(rf'\b{keyword}\b', sql_upper):
            return f"Query contains disallowed keyword: {keyword}"

    # Add LIMIT if missing
    if "LIMIT" not in sql_upper:
        sql = sql.rstrip(";") + " LIMIT 100;"

    return None


def execute_query(sql: str) -> tuple[list[dict], list[str]]:
    """Execute SQL and return (rows_as_dicts, column_names)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(sql)
    columns = [desc[0] for desc in cursor.description] if cursor.description else []
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows, columns


def ask(question: str, conversation_history: list[dict] | None = None) -> QueryResult:
    """Answer a natural-language question about the housing database."""
    api_key = require("ANTHROPIC_API_KEY", _resolve_anthropic_api_key())
    client = anthropic.Anthropic(api_key=api_key)

    # Build messages — include conversation history for follow-ups
    messages = []
    if conversation_history:
        messages.extend(conversation_history)
    messages.append({"role": "user", "content": question})

    # Step 1: Generate SQL
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        raw_text = response.content[0].text.strip()
    except Exception as e:
        return QueryResult(
            question=question,
            sql=None,
            explanation="",
            error=f"Claude API error: {str(e)}",
        )

    # Parse the JSON response
    try:
        # Strip markdown fences if Claude added them despite instructions
        clean = re.sub(r'^```(?:json)?\s*', '', raw_text)
        clean = re.sub(r'\s*```$', '', clean)
        parsed = json.loads(clean)
        sql = parsed.get("sql")
        explanation = parsed.get("explanation", "")
    except (json.JSONDecodeError, AttributeError):
        return QueryResult(
            question=question,
            sql=None,
            explanation=raw_text,
            error="Could not parse Claude's response as JSON.",
        )

    # If Claude said it can't answer
    if not sql:
        return QueryResult(
            question=question,
            sql=None,
            explanation=explanation,
        )

    # Step 2: Validate
    validation_error = validate_sql(sql)
    if validation_error:
        return QueryResult(
            question=question,
            sql=sql,
            explanation=explanation,
            error=f"Query validation failed: {validation_error}",
        )

    # Ensure LIMIT exists
    if "LIMIT" not in sql.upper():
        sql = sql.rstrip(";") + " LIMIT 100;"

    # Step 3: Execute
    try:
        rows, columns = execute_query(sql)
    except Exception as e:
        return QueryResult(
            question=question,
            sql=sql,
            explanation=explanation,
            error=f"SQL execution error: {str(e)}",
        )

    # Step 4: Summarize results
    if rows:
        # Truncate results for the summary prompt to avoid huge token usage
        results_for_summary = rows[:20]
        results_str = json.dumps(results_for_summary, indent=2, default=str)

        try:
            summary_response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=512,
                messages=[{
                    "role": "user",
                    "content": SUMMARY_PROMPT.format(
                        question=question,
                        results=results_str,
                    ),
                }],
            )
            summary = summary_response.content[0].text.strip()
        except Exception:
            summary = f"Query returned {len(rows)} rows."
    else:
        summary = "The query returned no results. Try broadening your search criteria."

    return QueryResult(
        question=question,
        sql=sql,
        explanation=explanation,
        rows=rows,
        columns=columns,
        summary=summary,
    )
