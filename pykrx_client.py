import time
import requests
import pandas as pd

HEADERS = {
    "Referer": "https://data.krx.co.kr/",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
}
URL = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"

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
MARKET_MID  = {"KOSPI": "02",           "KOSDAQ": "03"}
MARKET_IDX  = {"KOSPI": "1001",         "KOSDAQ": "2001"}


def _fetch(mid_cls: str, idx_code: str, from_date: str, to_date: str) -> list[dict]:
    data = {
        "bld": "dbms/MDC/STAT/standard/MDCSTAT01001",
        "locale": "ko_KR",
        "idxIndMidclssCd": mid_cls,
        "indIdx": idx_code,
        "indIdx2": idx_code,
        "strtDd": from_date,
        "endDd": to_date,
        "share": "1",
        "money": "1",
        "csvxls_isNo": "false",
    }
    resp = requests.post(URL, headers=HEADERS, data=data, timeout=15)
    resp.raise_for_status()
    return resp.json().get("output", [])


def fetch_all_sector_returns(market: str, fromdate: str, todate: str) -> pd.DataFrame:
    sectors = SECTOR_MAP.get(market, KOSPI_SECTORS)
    mid = MARKET_MID.get(market, "02")
    all_returns = {}

    for code, name in sectors.items():
        try:
            rows = _fetch(mid, code, fromdate, todate)
            if not rows:
                print(f"  [{name}] 데이터 없음")
                continue
            # KRX 응답: 날짜 역순 → 오름차순 정렬
            df = pd.DataFrame(rows)
            date_col  = [c for c in df.columns if "일자" in c or "TRD_DD" in c][0]
            close_col = [c for c in df.columns if "종가" in c or "CLSPRC_IDX" in c][0]
            df = df[[date_col, close_col]].rename(columns={date_col: "date", close_col: "close"})
            df["close"] = pd.to_numeric(df["close"].str.replace(",", ""), errors="coerce")
            df = df.sort_values("date").set_index("date")
            pct = df["close"].pct_change() * 100
            all_returns[code] = pct
            print(f"  [{name}] {len(df)}일 완료")
            time.sleep(0.3)
        except Exception as e:
            print(f"  [{name}({code})] 오류: {e}")

    if not all_returns:
        return pd.DataFrame()
    return pd.DataFrame(all_returns).dropna(how="all")


def fetch_market_close(market: str, fromdate: str, todate: str) -> pd.Series:
    mid  = MARKET_MID.get(market, "02")
    code = MARKET_IDX.get(market, "1001")
    rows = _fetch(mid, code, fromdate, todate)
    df = pd.DataFrame(rows)
    date_col  = [c for c in df.columns if "일자" in c or "TRD_DD" in c][0]
    close_col = [c for c in df.columns if "종가" in c or "CLSPRC_IDX" in c][0]
    df = df[[date_col, close_col]].rename(columns={date_col: "date", close_col: "close"})
    df["close"] = pd.to_numeric(df["close"].str.replace(",", ""), errors="coerce")
    df = df.sort_values("date").set_index("date")
    return df["close"]
