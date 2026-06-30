"""KIS OpenAPI를 이용한 업종 일별 데이터 수집."""
import os, time, datetime, requests, pandas as pd
from dotenv import load_dotenv

load_dotenv()

BASE    = "https://openapi.koreainvestment.com:9443"
APP_KEY = os.getenv("KIS_APP_KEY")
APP_SEC = os.getenv("KIS_APP_SECRET")

_token = {"v": None, "exp": 0}


def _get_token() -> str:
    if _token["v"] and time.time() < _token["exp"]:
        return _token["v"]
    r = requests.post(f"{BASE}/oauth2/tokenP", json={
        "grant_type": "client_credentials",
        "appkey": APP_KEY, "appsecret": APP_SEC,
    }, timeout=10)
    r.raise_for_status()
    d = r.json()
    _token["v"] = d["access_token"]
    _token["exp"] = time.time() + int(d.get("expires_in", 86400)) - 60
    return _token["v"]


def _headers(tr_id: str) -> dict:
    return {
        "authorization": f"Bearer {_get_token()}",
        "appkey": APP_KEY, "appsecret": APP_SEC,
        "tr_id": tr_id, "custtype": "P",
    }


# KRX 업종코드
KOSPI_SECTORS = {
    "1005": "음식료품",   "1006": "섬유의복",    "1007": "종이목재",
    "1008": "화학",       "1009": "의약품",       "1010": "비금속광물",
    "1011": "철강금속",   "1012": "기계",         "1013": "전기전자",
    "1014": "의료정밀",   "1015": "운수장비",     "1016": "유통업",
    "1017": "전기가스업", "1018": "건설업",       "1019": "운수창고업",
    "1020": "통신업",     "1021": "금융업",       "1022": "은행",
    "1023": "증권",       "1024": "보험",         "1025": "서비스업",
}
KOSDAQ_SECTORS = {
    "2006": "음식료담배", "2007": "섬유의류",    "2008": "종이목재",
    "2010": "화학",       "2011": "제약",        "2012": "비금속",
    "2013": "금속",       "2014": "기계장비",    "2015": "IT부품",
    "2016": "반도체",     "2017": "전자부품",    "2018": "기타전자",
    "2019": "통신장비",   "2020": "정보기기",    "2023": "소프트웨어",
    "2025": "통신서비스",
}
MARKET_IDX  = {"KOSPI": "0001", "KOSDAQ": "1001"}
SECTOR_MAP  = {"KOSPI": KOSPI_SECTORS, "KOSDAQ": KOSDAQ_SECTORS}


def _fetch_sector_now(iscd: str) -> dict | None:
    """업종 현재가 (오늘 등락률 포함)."""
    try:
        r = requests.get(
            f"{BASE}/uapi/domestic-stock/v1/quotations/inquire-index-price",
            headers=_headers("FHPUP02100000"),
            params={"FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": iscd},
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get("output", {})
    except Exception as e:
        print(f"  [{iscd}] 오류: {e}")
        return None


def fetch_today_returns(market: str) -> dict[str, float]:
    """오늘 업종별 등락률(%) 딕셔너리 반환."""
    sectors = SECTOR_MAP.get(market, KOSPI_SECTORS)
    result = {}
    for code, name in sectors.items():
        data = _fetch_sector_now(code)
        if data:
            try:
                pct = float(data.get("bstp_nmix_prdy_ctrt", "0"))
                result[code] = pct
            except Exception:
                pass
        time.sleep(0.15)
    return result


def fetch_today_market_close(market: str) -> float | None:
    """오늘 시장지수 종가."""
    code = MARKET_IDX.get(market, "0001")
    data = _fetch_sector_now(code)
    if data:
        try:
            return float(data.get("bstp_nmix_prpr", "0"))
        except Exception:
            pass
    return None
