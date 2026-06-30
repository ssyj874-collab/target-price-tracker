import time
import pandas as pd
from pykrx import stock

# KRX 공식 업종 티커 코드
KOSPI_SECTORS = {
    "1005": "음식료품", "1006": "섬유의복", "1007": "종이목재",
    "1008": "화학",    "1009": "의약품",   "1010": "비금속광물",
    "1011": "철강금속", "1012": "기계",     "1013": "전기전자",
    "1014": "의료정밀", "1015": "운수장비", "1016": "유통업",
    "1017": "전기가스업","1018": "건설업",  "1019": "운수창고업",
    "1020": "통신업",  "1021": "금융업",   "1022": "은행",
    "1023": "증권",    "1024": "보험",     "1025": "서비스업",
}

KOSDAQ_SECTORS = {
    "2006": "음식료·담배", "2007": "섬유·의류", "2008": "종이·목재",
    "2010": "화학",       "2011": "제약",      "2012": "비금속",
    "2013": "금속",       "2014": "기계·장비", "2015": "IT부품",
    "2016": "반도체",     "2017": "전자부품",  "2018": "기타전자",
    "2019": "통신장비",   "2020": "정보기기",  "2021": "방송서비스",
    "2022": "인터넷",     "2023": "소프트웨어","2024": "컴퓨터서비스",
    "2025": "통신서비스",
}

SECTOR_MAP = {"KOSPI": KOSPI_SECTORS, "KOSDAQ": KOSDAQ_SECTORS}
MARKET_INDEX = {"KOSPI": "1001", "KOSDAQ": "2001"}


def fetch_all_sector_returns(market: str, fromdate: str, todate: str) -> pd.DataFrame:
    """
    모든 업종의 일별 수익률 DataFrame
    index=날짜, columns=업종코드, values=등락률(%)
    """
    sectors = SECTOR_MAP.get(market, KOSPI_SECTORS)
    all_returns = {}

    for ticker, name in sectors.items():
        try:
            df = stock.get_index_ohlcv_by_date(fromdate, todate, ticker)
            if df is None or df.empty:
                print(f"  [{name}] 데이터 없음")
                continue
            pct = df["종가"].pct_change() * 100
            all_returns[ticker] = pct
            print(f"  [{name}] {len(df)}일 수집 완료")
            time.sleep(0.3)
        except Exception as e:
            print(f"  [{name}({ticker})] 오류: {e}")

    if not all_returns:
        return pd.DataFrame()

    return pd.DataFrame(all_returns).dropna(how="all")


def fetch_market_close(market: str, fromdate: str, todate: str) -> pd.Series:
    """코스피(1001) 또는 코스닥(2001) 종가 시리즈"""
    ticker = MARKET_INDEX.get(market, "1001")
    df = stock.get_index_ohlcv_by_date(fromdate, todate, ticker)
    return df["종가"]
