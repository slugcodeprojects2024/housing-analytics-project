"""
Download the database from GitHub Releases if it doesn't exist locally.

Called at app startup. Skips download if the database already exists.
"""
from __future__ import annotations

import gzip
import shutil
import urllib.request
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "housing.db"
DB_URL = "https://github.com/slugcodeprojects2024/housing-analytics-project/releases/download/v1.0-data/housing.db.gz"


def ensure_database():
    """Download and decompress the database if it doesn't exist."""
    if DB_PATH.exists():
        return

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    gz_path = DB_PATH.parent / "housing.db.gz"

    print(f"Database not found. Downloading from GitHub Releases...")
    print(f"  URL: {DB_URL}")
    print(f"  This may take a few minutes...")

    urllib.request.urlretrieve(DB_URL, gz_path)
    print(f"  Downloaded: {gz_path.stat().st_size / 1e6:.0f} MB (compressed)")

    print(f"  Decompressing...")
    with gzip.open(gz_path, "rb") as f_in:
        with open(DB_PATH, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)

    gz_path.unlink()
    print(f"  Database ready: {DB_PATH.stat().st_size / 1e6:.0f} MB")


if __name__ == "__main__":
    ensure_database()
