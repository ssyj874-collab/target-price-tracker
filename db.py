"""DB 접근 (순수 Python, pandas 없음)."""
import sqlite3, json, os, datetime

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


def _date_key(d):
    """date 객체 → ISO string."""
    return d.isoformat() if hasattr(d, "isoformat") else str(d)


def save_raw_json(market: str, returns_by_date: dict, market_close: dict):
    """순수 Python dict 저장. key는 date 객체 또는 ISO string."""
    ret_serializable = {_date_key(k): v for k, v in returns_by_date.items()}
    mc_serializable = {_date_key(k): float(v) for k, v in market_close.items()}
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO raw_data (market, returns_json, market_close_json, updated_at) VALUES (?, ?, ?, ?)",
            (market, json.dumps(ret_serializable), json.dumps(mc_serializable),
             datetime.datetime.now().isoformat()),
        )


def get_raw_json(market: str):
    """returns_by_date {str→dict}, market_close {str→float} 반환."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT returns_json, market_close_json FROM raw_data WHERE market=?", (market,)
        ).fetchone()
        if not row:
            return None, None
        return json.loads(row["returns_json"]), json.loads(row["market_close_json"])


def get_raw_json_as_dates(market: str):
    """date 객체 키로 반환."""
    from datetime import date
    ret_str, mc_str = get_raw_json(market)
    if ret_str is None:
        return None, None
    returns_by_date = {date.fromisoformat(k): v for k, v in ret_str.items()}
    market_close = {date.fromisoformat(k): v for k, v in mc_str.items()}
    return returns_by_date, market_close


# 하위호환 (app.py에서 사용)
def save_raw_data(market, returns_by_date, market_close):
    save_raw_json(market, returns_by_date, market_close)


def get_raw_data(market):
    return get_raw_json_as_dates(market)
