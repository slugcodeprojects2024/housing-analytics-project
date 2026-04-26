"""
Text-to-SQL via Claude.

Pipeline:
  1. Take a user question in natural language
  2. Build a prompt that includes the relevant schema
  3. Ask Claude to generate a read-only SQL query
  4. Validate the SQL (parse, check tables/columns, enforce SELECT-only)
  5. Execute against SQLite
  6. Send results back to Claude for a plain-English summary
  7. Return both the data and the summary to the caller

Build this incrementally in weeks 5-6. Start with steps 1-3 and a simple
schema dump in the prompt; add validation and result interpretation after
the basic loop works end-to-end.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.config import ANTHROPIC_API_KEY, CLAUDE_MODEL, require


@dataclass
class QueryResult:
    question: str
    sql: str
    rows: list[dict]
    summary: str


def ask(question: str) -> QueryResult:
    """Answer a natural-language question about the housing database."""
    require("ANTHROPIC_API_KEY", ANTHROPIC_API_KEY)
    # TODO: implement in week 5
    raise NotImplementedError("Implement in week 5")
