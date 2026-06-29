import time
import datetime
import pandas as pd
from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

import db
import kis_client as kis
import calculator as calc

# ── 상수 ────────────────────────────────────────────────────────────────────
MARKETS = {
    "kospi": {
        "index_code": "0001",
        "sectors": calc.KOSPI_SECTORS,
        "label": "코스피",
    },
    "kosdaq": {
        "index_code": "1001",
        "sectors": calc.KOSDAQ_SECTORS,
        "label": "코스닥",
    },
}

FETCH_FROM = "20240101"   # 과거 데이터 시작일


# ── 데이터 수집 ──────────────────────────────────────────────────────────────
def fetch_and_store(market_key: str):
    cfg = MARKETS[market_key]
    today = datetime.date.today().strftime("%Y%m%d")

    latest = db.get_latest_date(market_key)
    date_from = FETCH_FROM
    if latest:
        # 마지막 저장일 다음날부터 (오늘과 같으면 스킵)
        last_dt = datetime.datetime.strptime(latest, "%Y%m%d").date()
        next_dt = last_dt + datetime.timedelta(days=1)
        if next_dt.strftime("%Y%m%d") > today:
            print(f"[{market_key}] 이미 최신 데이터")
            return
        date_from = next_dt.strftime("%Y%m%d")

    print(f"[{market_key}] 데이터 수집: {date_from} ~ {today}")

    # 시장 지수
    try:
        idx_rows = kis.get_index_daily_prices(cfg["index_code"], date_from, today)
        db.upsert_market_index(market_key, idx_rows)
        print(f"  지수 {len(idx_rows)}행 저장")
    except Exception as e:
        print(f"  지수 수집 오류: {e}")

    # 업종별 수익률
    for code, name in cfg["sectors"].items():
        try:
            rows = kis.get_sector_daily_prices(code, date_from, today)
            db.upsert_sector_returns(market_key, code, rows)
            print(f"  {name}({code}) {len(rows)}행 저장")
            time.sleep(0.2)  # API rate limit
        except Exception as e:
            print(f"  {name}({code}) 오류: {e}")

    # 차트 캐시 재계산
    rebuild_cache(market_key)


def rebuild_cache(market_key: str):
    sector_returns = db.get_all_sector_returns(market_key)
    market_rows = db.get_market_index(market_key)
    if not sector_returns or not market_rows:
        return

    market_df = pd.DataFrame(market_rows).set_index("date")
    sectors = MARKETS[market_key]["sectors"]
    chart_data = calc.build_chart_data(market_df, sector_returns, sectors)
    db.save_chart_cache(market_key, chart_data)
    print(f"[{market_key}] 차트 캐시 갱신 완료 ({len(chart_data['dates'])}일)")


# ── FastAPI ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    # 최초 실행 시 백그라운드로 데이터 수집
    import threading
    for mk in MARKETS:
        t = threading.Thread(target=fetch_and_store, args=(mk,), daemon=True)
        t.start()
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/api/chart/{market_key}")
def get_chart(market_key: str):
    if market_key not in MARKETS:
        return JSONResponse({"error": "unknown market"}, status_code=404)
    data = db.get_chart_cache(market_key)
    if not data:
        return JSONResponse({"error": "데이터 준비 중입니다. 잠시 후 새로고침 해주세요."}, status_code=202)
    return JSONResponse(data)


@app.post("/api/refresh/{market_key}")
def refresh(market_key: str, background_tasks: BackgroundTasks):
    if market_key not in MARKETS:
        return JSONResponse({"error": "unknown market"}, status_code=404)
    background_tasks.add_task(fetch_and_store, market_key)
    return {"status": "수집 시작됨"}


@app.post("/api/refresh")
def refresh_all(background_tasks: BackgroundTasks):
    for mk in MARKETS:
        background_tasks.add_task(fetch_and_store, mk)
    return {"status": "전체 수집 시작됨"}


app.mount("/", StaticFiles(directory="static", html=True), name="static")
