"""Smoke test: schema initializes and tables exist."""
from src.db.connection import connection, init_schema


def test_schema_creates_tables(tmp_path, monkeypatch):
    # Point the DB at a temp file so we don't touch the real one
    import src.config
    import src.db.connection as conn_mod

    test_db = tmp_path / "test.db"
    monkeypatch.setattr(src.config, "DB_PATH", test_db)
    monkeypatch.setattr(conn_mod, "DB_PATH", test_db)

    init_schema()

    expected = {
        "geographies",
        "housing_metrics",
        "macro_indicators",
        "derived_metrics",
        "load_log",
    }
    with connection() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    found = {r["name"] for r in rows}
    assert expected.issubset(found), f"Missing tables: {expected - found}"
