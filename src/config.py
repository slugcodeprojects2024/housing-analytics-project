"""Central configuration loaded from environment variables."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

RAW_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{PROCESSED_DIR / 'housing.db'}")
DB_PATH = PROCESSED_DIR / "housing.db"

try:
    import streamlit as st
    ANTHROPIC_API_KEY = st.secrets.get("ANTHROPIC_API_KEY", os.getenv("ANTHROPIC_API_KEY"))
except:
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

try:
    import streamlit as st
    FRED_API_KEY = st.secrets.get("FRED_API_KEY", os.getenv("FRED_API_KEY"))
except:
    FRED_API_KEY = os.getenv("FRED_API_KEY")

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5")


def require(name: str, value: str | None) -> str:
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Copy .env.example to .env and fill it in."
        )
    return value
