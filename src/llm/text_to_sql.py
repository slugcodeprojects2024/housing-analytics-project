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
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import anthropic

from src.config import ANTHROPIC_API_KEY, CLAUDE_MODEL, require

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "processed" / "housing.db"

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

derived_metrics — Pre-computed analytics (may be empty if not yet populated)
  geography_id  INTEGER     — FK to geographies
  metric_date   DATE
  metric_name   TEXT
  value         REAL

KEY FACTS:
- ZIP codes are STRINGS, always 5 digits, zero-padded (e.g. '08701' not 8701)
- geo_type values: 'zip', 'metro', 'national'
- metric_type values: 'zhvi' (Zillow Home Value Index = median home value), 'zori' (Zillow Observed Rent Index = median rent)
- macro_indicators.indicator values: 'mortgage_30y', 'median_income', 'cpi', 'case_shiller'
- Housing data spans 2000-01 to 2026-03, ~26K ZIPs and ~900 metros
- The 'United States' geography has geo_type = 'national'
- To get "Bay Area": look for metro names containing 'San Jose' or 'San Francisco'
- To get Santa Clara County ZIPs: WHERE county = 'Santa Clara County' AND geo_type = 'zip'

RESPONSE FORMAT:
Always respond with a JSON object (no markdown fences) containing:
{
  "sql": "YOUR SQL QUERY HERE",
  "explanation": "Brief explanation of what this query does"
}

RULES:
- Only generate SELECT statements
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

Provide a clear, concise summary of what this data shows. Highlight key findings, notable trends, or surprising values. If the data includes prices, format them as currency (e.g. $1,234,567). Do NOT use any markdown formatting like bold (**), italic (*), or headers (#). Write in plain text only. Keep it to 2-4 sentences unless the data warrants more detail."""


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

    # Must be a SELECT
    if not sql_upper.startswith("SELECT"):
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
    api_key = require("ANTHROPIC_API_KEY", ANTHROPIC_API_KEY)
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
