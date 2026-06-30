import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS chart_cache (
                market TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)


def save_chart_cache(market: str, data: dict):
    import datetime
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO chart_cache (market, data, updated_at) VALUES (?, ?, ?)",
            (market, json.dumps(data), datetime.datetime.now().isoformat()),
        )


def get_chart_cache(market: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT data, updated_at FROM chart_cache WHERE market=?", (market,)
        ).fetchone()
        if row:
            return {"data": json.loads(row["data"]), "updated_at": row["updated_at"]}
        return None
