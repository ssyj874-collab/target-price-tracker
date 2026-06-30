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
            CREATE TABLE IF NOT EXISTS raw_data (
                market TEXT PRIMARY KEY,
                returns_json TEXT NOT NULL,
                market_close_json TEXT NOT NULL,
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


def save_raw_data(market: str, returns_df, market_close):
    import datetime, pandas as pd
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO raw_data (market, returns_json, market_close_json, updated_at) VALUES (?, ?, ?, ?)",
            (
                market,
                returns_df.to_json(date_format="iso"),
                market_close.to_json(date_format="iso"),
                datetime.datetime.now().isoformat(),
            ),
        )


def get_raw_data(market: str):
    import pandas as pd
    with get_conn() as conn:
        row = conn.execute(
            "SELECT returns_json, market_close_json FROM raw_data WHERE market=?", (market,)
        ).fetchone()
        if not row:
            return None, None
        returns_df = pd.read_json(row["returns_json"])
        returns_df.index = pd.to_datetime(returns_df.index).date
        market_close = pd.read_json(row["market_close_json"], typ="series")
        market_close.index = pd.to_datetime(market_close.index).date
        return returns_df, market_close


def get_chart_cache(market: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT data, updated_at FROM chart_cache WHERE market=?", (market,)
        ).fetchone()
        if row:
            return {"data": json.loads(row["data"]), "updated_at": row["updated_at"]}
        return None
