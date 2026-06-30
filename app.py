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
_fetch_status = {m: "idle" for m in MARKETS}


def append_today_and_refresh(market: str):
    _fetch_status[market] = "fetching"
    today = datetime.date.today()
    print(f"[{market}] 오늘({today}) 데이터 수집 중...")

    try:
        returns_by_date, market_close = db.get_raw_data(market)
        if returns_by_date is None:
            print(f"[{market}] raw_data 없음 → import_excel.py 먼저 실행 필요")
            _fetch_status[market] = "error"
            return

        if today in returns_by_date:
            print(f"[{market}] 오늘 데이터 이미 있음")
            _fetch_status[market] = "done"
            return

        # KIS API로 오늘 업종 등락률 수집
        today_returns = krx.fetch_today_returns(market)
        if len(today_returns) < 5:
            print(f"[{market}] 수집 실패 (업종 수 부족: {len(today_returns)})")
            _fetch_status[market] = "error"
            return

        today_close = krx.fetch_today_market_close(market)

        returns_by_date[today] = today_returns
        if today_close:
            market_close[today] = today_close

        db.save_raw_json(market, returns_by_date, market_close)

        chart_data = calc.build_chart_data(market_close, returns_by_date)
        db.save_chart_cache(market, chart_data)
        print(f"[{market}] 오늘 데이터 추가 완료 ({len(chart_data['dates'])}일)")
        _fetch_status[market] = "done"

    except Exception as e:
        print(f"[{market}] 오류: {e}")
        import traceback; traceback.print_exc()
        _fetch_status[market] = "error"


def _rebuild_cache(market: str):
    _fetch_status[market] = "fetching"
    try:
        returns_by_date, market_close = db.get_raw_data(market)
        if returns_by_date is None:
            _fetch_status[market] = "error"
            return
        chart_data = calc.build_chart_data(market_close, returns_by_date)
        db.save_chart_cache(market, chart_data)
        print(f"[{market}] 캐시 재계산 완료 ({len(chart_data['dates'])}일)")
        _fetch_status[market] = "done"
    except Exception as e:
        print(f"[{market}] 재계산 오류: {e}")
        _fetch_status[market] = "error"


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    today = datetime.date.today()

    for market in MARKETS:
        cached = db.get_chart_cache(market)
        if not cached:
            ret, _ = db.get_raw_data(market)
            if ret is None:
                print(f"[{market}] 데이터 없음 → 먼저 실행:")
                print(f"  python3 import_excel.py <엑셀파일경로>")
                _fetch_status[market] = "no_data"
            else:
                t = threading.Thread(target=lambda m=market: _rebuild_cache(m), daemon=True)
                t.start()
        else:
            _fetch_status[market] = "done"
            last_date = cached["data"]["dates"][-1] if cached["data"]["dates"] else "?"
            print(f"[{market}] 캐시 있음 (최종: {last_date})")
            if last_date != today.isoformat():
                t = threading.Thread(target=append_today_and_refresh, args=(market,), daemon=True)
                t.start()

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
        msg = "python3 import_excel.py <파일> 실행 후 재시작" if status == "no_data" else f"준비 중... ({status})"
        return JSONResponse({"error": msg, "status": status}, status_code=202)

    result = cached["data"]
    result["updated_at"] = cached["updated_at"][:10]
    return JSONResponse(result)


@app.post("/api/refresh")
def refresh_all(background_tasks: BackgroundTasks):
    for market in MARKETS:
        background_tasks.add_task(append_today_and_refresh, market)
    return {"status": "오늘 데이터 수집 시작"}


@app.post("/api/refresh/{market}")
def refresh(market: str, background_tasks: BackgroundTasks):
    market = market.upper()
    if market not in MARKETS:
        return JSONResponse({"error": "unknown market"}, status_code=404)
    background_tasks.add_task(append_today_and_refresh, market)
    return {"status": "수집 시작됨"}


app.mount("/", StaticFiles(directory="static", html=True), name="static")
