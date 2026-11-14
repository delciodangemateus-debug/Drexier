import sqlite3
from pathlib import Path

from backend.database import SQL_SCHEMA_FOR_TESTS, _ensure_sqlite_schema
from backend.main import app


def test_website_integration_routes_and_widget_are_removed():
    paths = {route.path for route in app.routes}

    assert not any(path.startswith("/api/integrations/website") for path in paths)
    assert not any(path.startswith("/api/widget/") for path in paths)
    assert "/widget.js" not in paths
    assert not (Path(__file__).resolve().parents[1] / "frontend" / "widget.js").exists()


def test_sqlite_schema_removes_legacy_website_integration_table():
    with sqlite3.connect(":memory:") as conn:
        conn.row_factory = sqlite3.Row
        conn.executescript(SQL_SCHEMA_FOR_TESTS)
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='website_integrations'"
        ).fetchone() is None
        conn.execute("CREATE TABLE website_integrations (id INTEGER PRIMARY KEY)")

        _ensure_sqlite_schema(conn)

        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "website_integrations" not in tables
        assert {"users", "contacts", "messages", "email_integrations"} <= tables
