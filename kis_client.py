import os
import time
import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://openapi.koreainvestment.com:9443"

APP_KEY = os.getenv("KIS_APP_KEY")
APP_SECRET = os.getenv("KIS_APP_SECRET")

_token_cache = {"token": None, "expires_at": 0}


def get_access_token() -> str:
    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"]:
        return _token_cache["token"]

    resp = httpx.post(
        f"{BASE_URL}/oauth2/tokenP",
        json={
            "grant_type": "client_credentials",
            "appkey": APP_KEY,
            "appsecret": APP_SECRET,
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = now + int(data.get("expires_in", 86400)) - 60
    return _token_cache["token"]


def _headers(tr_id: str) -> dict:
    return {
        "content-type": "application/json",
        "authorization": f"Bearer {get_access_token()}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": tr_id,
        "custtype": "P",
    }


def get_sector_daily_prices(iscd: str, date_from: str, date_to: str) -> list[dict]:
    """업종 기간별 시세 (일별). Returns list of {date, close, change_rate}."""
    params = {
        "FID_COND_MRKT_DIV_CODE": "U",
        "FID_INPUT_ISCD": iscd,
        "FID_INPUT_DATE_1": date_from,
        "FID_INPUT_DATE_2": date_to,
        "FID_PERIOD_DIV_CODE": "D",
    }
    resp = httpx.get(
        f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-index-chartprice",
        headers=_headers("FHKUP03500100"),
        params=params,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    rows = []
    for item in data.get("output2", []):
        date = item.get("stck_bsop_date", "")
        close = item.get("bstp_nmix_prpr", "0")
        change_rate = item.get("bstp_nmix_prdy_ctrt", "0")
        if date:
            rows.append({
                "date": date,
                "close": float(close) if close else 0.0,
                "change_rate": float(change_rate) if change_rate else 0.0,
            })
    return rows


def get_index_daily_prices(iscd: str, date_from: str, date_to: str) -> list[dict]:
    """코스피/코스닥 지수 기간별 시세. iscd: 0001=코스피, 1001=코스닥"""
    params = {
        "FID_COND_MRKT_DIV_CODE": "U",
        "FID_INPUT_ISCD": iscd,
        "FID_INPUT_DATE_1": date_from,
        "FID_INPUT_DATE_2": date_to,
        "FID_PERIOD_DIV_CODE": "D",
    }
    resp = httpx.get(
        f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-index-chartprice",
        headers=_headers("FHKUP03500100"),
        params=params,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    rows = []
    for item in data.get("output2", []):
        date = item.get("stck_bsop_date", "")
        close = item.get("bstp_nmix_prpr", "0")
        if date:
            rows.append({
                "date": date,
                "close": float(close) if close else 0.0,
            })
    return rows
