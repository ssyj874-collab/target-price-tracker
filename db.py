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
            CREATE TABLE IF NOT EXISTS sector_returns (
                market TEXT NOT NULL,
                sector_code TEXT NOT NULL,
                date TEXT NOT NULL,
                close REAL,
                change_rate REAL,
                PRIMARY KEY (market, sector_code, date)
            );

            CREATE TABLE IF NOT EXISTS market_index (
                market TEXT NOT NULL,
                date TEXT NOT NULL,
                close REAL,
                PRIMARY KEY (market, date)
            );

            CREATE TABLE IF NOT EXISTS chart_cache (
                market TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)


def upsert_sector_returns(market: str, sector_code: str, rows: list[dict]):
    with get_conn() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO sector_returns (market, sector_code, date, close, change_rate)
               VALUES (?, ?, ?, ?, ?)""",
            [(market, sector_code, r["date"], r.get("close"), r.get("change_rate")) for r in rows],
        )


def upsert_market_index(market: str, rows: list[dict]):
    with get_conn() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO market_index (market, date, close)
               VALUES (?, ?, ?)""",
            [(market, r["date"], r.get("close")) for r in rows],
        )


def get_sector_returns(market: str, sector_code: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT date, close, change_rate FROM sector_returns WHERE market=? AND sector_code=? ORDER BY date",
            (market, sector_code),
        ).fetchall()
        return [dict(r) for r in rows]


def get_all_sector_returns(market: str) -> dict:
    """Returns {sector_code: [{date, change_rate}, ...]}"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT sector_code, date, change_rate FROM sector_returns WHERE market=? ORDER BY date",
            (market,),
        ).fetchall()
    result = {}
    for r in rows:
        code = r["sector_code"]
        if code not in result:
            result[code] = []
        result[code].append({"date": r["date"], "change_rate": r["change_rate"]})
    return result


def get_market_index(market: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT date, close FROM market_index WHERE market=? ORDER BY date",
            (market,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_latest_date(market: str) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT MAX(date) as d FROM sector_returns WHERE market=?",
            (market,),
        ).fetchone()
        return row["d"] if row else None


def save_chart_cache(market: str, data: dict):
    import datetime
    with get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO chart_cache (market, data, updated_at)
               VALUES (?, ?, ?)""",
            (market, json.dumps(data), datetime.datetime.now().isoformat()),
        )


def get_chart_cache(market: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT data FROM chart_cache WHERE market=?", (market,)
        ).fetchone()
        if row:
            return json.loads(row["data"])
        return None
