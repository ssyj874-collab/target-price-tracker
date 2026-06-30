import datetime
import threading
from contextlib import asynccontextmanager
import pandas as pd
from fastapi import FastAPI, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

import db
import pykrx_client as krx
import calculator as calc

MARKETS = ["KOSPI", "KOSDAQ"]

_fetch_status = {m: "idle" for m in MARKETS}


def append_today_and_refresh(market: str):
    """KIS API로 오늘 데이터를 가져와 raw_data에 추가하고 chart_cache 갱신."""
    _fetch_status[market] = "fetching"
    today = datetime.date.today()
    print(f"[{market}] 오늘({today}) 데이터 수집 중...")

    try:
        returns_df, market_close = db.get_raw_data(market)
        if returns_df is None:
            print(f"[{market}] raw_data 없음 → import_excel.py 먼저 실행 필요")
            _fetch_status[market] = "error"
            return

        # 이미 오늘 데이터가 있으면 스킵
        if today in returns_df.index:
            print(f"[{market}] 오늘 데이터 이미 있음")
            _fetch_status[market] = "done"
            return

        # 오늘 업종 등락률
        today_returns = krx.fetch_today_returns(market)
        if len(today_returns) < 5:
            print(f"[{market}] 수집 실패 (업종 수 부족: {len(today_returns)})")
            _fetch_status[market] = "error"
            return

        # 오늘 시장지수
        today_close = krx.fetch_today_market_close(market)

        # raw_data에 추가
        new_row = pd.DataFrame([today_returns], index=[today])
        new_row.index.name = "date"
        combined_returns = pd.concat([returns_df, new_row])

        if today_close:
            new_mc = pd.Series({today: today_close})
            combined_market = pd.concat([market_close, new_mc])
        else:
            combined_market = market_close

        db.save_raw_data(market, combined_returns, combined_market)

        # chart_cache 재계산
        chart_data = calc.build_chart_data(combined_market, combined_returns)
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
        returns_df, market_close = db.get_raw_data(market)
        if returns_df is None:
            _fetch_status[market] = "error"
            return
        chart_data = calc.build_chart_data(market_close, returns_df)
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
            returns_df, _ = db.get_raw_data(market)
            if returns_df is None:
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

            # 오늘 데이터가 없으면 자동 추가
            if last_date != today.isoformat():
                t = threading.Thread(
                    target=append_today_and_refresh, args=(market,), daemon=True
                )
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
        if status == "no_data":
            return JSONResponse(
                {"error": "데이터 없음. python3 import_excel.py <파일> 실행 후 재시작", "status": status},
                status_code=202,
            )
        return JSONResponse(
            {"error": f"데이터 준비 중... ({status})", "status": status},
            status_code=202,
        )
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
