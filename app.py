import datetime
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

import db
import pykrx_client as krx
import calculator as calc

MARKETS = ["KOSPI", "KOSDAQ"]
FETCH_FROM = "20240101"

_fetch_status = {m: "idle" for m in MARKETS}


def fetch_and_cache(market: str, fromdate: str = None):
    _fetch_status[market] = "fetching"
    today = datetime.date.today().strftime("%Y%m%d")
    from_dt = fromdate or FETCH_FROM
    print(f"[{market}] 데이터 수집 시작: {from_dt} ~ {today}")
    try:
        returns_df = krx.fetch_all_sector_returns(market, from_dt, today)
        market_close = krx.fetch_market_close(market, from_dt, today)
        if returns_df.empty or market_close.empty:
            print(f"[{market}] 데이터 없음")
            _fetch_status[market] = "error"
            return
        chart_data = calc.build_chart_data(market_close, returns_df)
        db.save_chart_cache(market, chart_data)
        print(f"[{market}] 완료 ({len(chart_data['dates'])}일)")
        _fetch_status[market] = "done"
    except Exception as e:
        print(f"[{market}] 오류: {e}")
        _fetch_status[market] = "error"


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    for market in MARKETS:
        cached = db.get_chart_cache(market)
        if not cached:
            t = threading.Thread(target=fetch_and_cache, args=(market,), daemon=True)
            t.start()
        else:
            _fetch_status[market] = "done"
            print(f"[{market}] 캐시 있음 ({cached['updated_at'][:10]})")
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/api/chart/{market}")
def get_chart(market: str):
    market = market.upper()
    if market not in MARKETS:
        return JSONResponse({"error": "unknown market"}, status_code=404)

    cached = db.get_chart_cache(market)
    if not cached:
        status = _fetch_status.get(market, "idle")
        return JSONResponse(
            {"error": f"데이터 수집 중... ({status})", "status": status},
            status_code=202,
        )
    result = cached["data"]
    result["updated_at"] = cached["updated_at"][:10]
    return JSONResponse(result)


@app.post("/api/refresh/{market}")
def refresh(market: str, background_tasks: BackgroundTasks):
    market = market.upper()
    if market not in MARKETS:
        return JSONResponse({"error": "unknown market"}, status_code=404)
    _fetch_status[market] = "fetching"
    background_tasks.add_task(fetch_and_cache, market)
    return {"status": "수집 시작됨"}


@app.post("/api/refresh")
def refresh_all(background_tasks: BackgroundTasks):
    for market in MARKETS:
        _fetch_status[market] = "fetching"
        background_tasks.add_task(fetch_and_cache, market)
    return {"status": "전체 수집 시작됨"}


app.mount("/", StaticFiles(directory="static", html=True), name="static")
