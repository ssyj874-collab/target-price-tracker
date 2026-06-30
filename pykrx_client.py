import time
import pandas as pd
import FinanceDataReader as fdr

# KRX 코스피 업종 지수 코드
KOSPI_SECTORS = {
    "1005": "음식료품",  "1006": "섬유의복",   "1007": "종이목재",
    "1008": "화학",      "1009": "의약품",      "1010": "비금속광물",
    "1011": "철강금속",  "1012": "기계",        "1013": "전기전자",
    "1014": "의료정밀",  "1015": "운수장비",    "1016": "유통업",
    "1017": "전기가스업","1018": "건설업",      "1019": "운수창고업",
    "1020": "통신업",    "1021": "금융업",      "1022": "은행",
    "1023": "증권",      "1024": "보험",        "1025": "서비스업",
}

# KRX 코스닥 업종 지수 코드
KOSDAQ_SECTORS = {
    "2006": "음식료·담배", "2007": "섬유·의류",  "2008": "종이·목재",
    "2010": "화학",        "2011": "제약",        "2012": "비금속",
    "2013": "금속",        "2014": "기계·장비",   "2015": "IT부품",
    "2016": "반도체",      "2017": "전자부품",    "2018": "기타전자",
    "2019": "통신장비",    "2020": "정보기기",    "2023": "소프트웨어",
    "2025": "통신서비스",
}

SECTOR_MAP  = {"KOSPI": KOSPI_SECTORS,  "KOSDAQ": KOSDAQ_SECTORS}
MARKET_CODE = {"KOSPI": "KS11",         "KOSDAQ": "KQ11"}


def fetch_all_sector_returns(market: str, fromdate: str, todate: str) -> pd.DataFrame:
    sectors = SECTOR_MAP.get(market, KOSPI_SECTORS)
    all_returns = {}

    # fromdate/todate: "20240101" → "2024-01-01"
    fd = f"{fromdate[:4]}-{fromdate[4:6]}-{fromdate[6:]}"
    td = f"{todate[:4]}-{todate[4:6]}-{todate[6:]}"

    for code, name in sectors.items():
        try:
            df = fdr.DataReader(code, fd, td)
            if df is None or df.empty:
                print(f"  [{name}] 데이터 없음")
                continue
            close_col = "Close" if "Close" in df.columns else df.columns[3]
            pct = df[close_col].pct_change() * 100
            all_returns[code] = pct
            print(f"  [{name}] {len(df)}일 완료")
            time.sleep(0.2)
        except Exception as e:
            print(f"  [{name}({code})] 오류: {e}")

    if not all_returns:
        return pd.DataFrame()
    return pd.DataFrame(all_returns).dropna(how="all")


def fetch_market_close(market: str, fromdate: str, todate: str) -> pd.Series:
    code = MARKET_CODE.get(market, "KS11")
    fd = f"{fromdate[:4]}-{fromdate[4:6]}-{fromdate[6:]}"
    td = f"{todate[:4]}-{todate[4:6]}-{todate[6:]}"
    df = fdr.DataReader(code, fd, td)
    close_col = "Close" if "Close" in df.columns else df.columns[3]
    return df[close_col]
