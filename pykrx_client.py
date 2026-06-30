import os, time, requests, pandas as pd
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

# KRX 업종코드 (코스피: 1005~1025, 코스닥: 2001~)
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
    "2006": "음식료·담배", "2007": "섬유·의류",  "2008": "종이·목재",
    "2010": "화학",        "2011": "제약",        "2012": "비금속",
    "2013": "금속",        "2014": "기계·장비",   "2015": "IT부품",
    "2016": "반도체",      "2017": "전자부품",    "2018": "기타전자",
    "2019": "통신장비",    "2020": "정보기기",    "2023": "소프트웨어",
    "2025": "통신서비스",
}

SECTOR_MAP  = {"KOSPI": KOSPI_SECTORS,  "KOSDAQ": KOSDAQ_SECTORS}
MARKET_IDX  = {"KOSPI": "0001",         "KOSDAQ": "1001"}


def _fetch_period(iscd: str, from_date: str, to_date: str) -> list[dict]:
    """업종 기간별 시세 (tr: FHKUP03500100)"""
    r = requests.get(
        f"{BASE}/uapi/domestic-stock/v1/quotations/inquire-index-chartprice",
        headers=_headers("FHKUP03500100"),
        params={
            "FID_COND_MRKT_DIV_CODE": "U",
            "FID_INPUT_ISCD": iscd,
            "FID_INPUT_DATE_1": from_date,
            "FID_INPUT_DATE_2": to_date,
            "FID_PERIOD_DIV_CODE": "D",
        },
        timeout=15,
    )
    r.raise_for_status()
    return r.json().get("output2", [])


def fetch_all_sector_returns(market: str, fromdate: str, todate: str) -> pd.DataFrame:
    sectors = SECTOR_MAP.get(market, KOSPI_SECTORS)
    all_returns = {}

    for code, name in sectors.items():
        try:
            rows = _fetch_period(code, fromdate, todate)
            if not rows:
                print(f"  [{name}] 데이터 없음")
                continue
            df = pd.DataFrame(rows)
            # 날짜·종가 컬럼 탐지
            date_col  = next(c for c in df.columns if "date" in c.lower() or "bsop" in c.lower())
            close_col = next(c for c in df.columns if "prpr" in c.lower() or "prdy" not in c.lower() and "prpr" in c.lower(), None)
            if close_col is None:
                close_col = [c for c in df.columns if "prpr" in c.lower()][0]
            df = df[[date_col, close_col]].copy()
            df.columns = ["date", "close"]
            df["close"] = pd.to_numeric(df["close"], errors="coerce")
            df = df.sort_values("date").set_index("date")
            pct = df["close"].pct_change() * 100
            all_returns[code] = pct
            print(f"  [{name}] {len(pct)}일 완료")
            time.sleep(0.2)
        except Exception as e:
            print(f"  [{name}({code})] 오류: {e}")

    if not all_returns:
        return pd.DataFrame()
    return pd.DataFrame(all_returns).dropna(how="all")


def fetch_market_close(market: str, fromdate: str, todate: str) -> pd.Series:
    code = MARKET_IDX.get(market, "0001")
    rows = _fetch_period(code, fromdate, todate)
    df = pd.DataFrame(rows)
    date_col  = next(c for c in df.columns if "date" in c.lower() or "bsop" in c.lower())
    close_col = [c for c in df.columns if "prpr" in c.lower()][0]
    df = df[[date_col, close_col]].copy()
    df.columns = ["date", "close"]
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.sort_values("date").set_index("date")
    return df["close"]
