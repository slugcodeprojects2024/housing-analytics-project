"""
Download the database from GitHub Releases if it doesn't exist locally.

Called at app startup. Skips download if the database already exists.
"""
from __future__ import annotations

import gzip
import shutil
from pathlib import Path

import requests

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "housing.db"
DB_URL = "https://github.com/slugcodeprojects2024/housing-analytics-project/releases/download/v1.0-data/housing.db.gz"


def ensure_database():
    """Download and decompress the database if it doesn't exist."""
    if DB_PATH.exists():
        # Quick sanity check — file should be > 100MB
        if DB_PATH.stat().st_size > 100_000_000:
            return
        else:
            DB_PATH.unlink()

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    gz_path = DB_PATH.parent / "housing.db.gz"

    print(f"Database not found. Downloading from GitHub Releases...")
    print(f"  URL: {DB_URL}")

    response = requests.get(DB_URL, stream=True, allow_redirects=True)
    response.raise_for_status()

    total_size = int(response.headers.get("content-length", 0))
    downloaded = 0

    with open(gz_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192 * 1024):
            f.write(chunk)
            downloaded += len(chunk)
            if total_size > 0:
                pct = downloaded * 100 // total_size
                print(f"  Downloaded: {downloaded // 1_000_000}MB / {total_size // 1_000_000}MB ({pct}%)")

    print(f"  Decompressing...")
    with gzip.open(gz_path, "rb") as f_in:
        with open(DB_PATH, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)

    gz_path.unlink()
    print(f"  Database ready: {DB_PATH.stat().st_size // 1_000_000} MB")


if __name__ == "__main__":
    ensure_database()