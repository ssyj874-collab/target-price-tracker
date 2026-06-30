import datetime
import time
import pandas as pd
from pykrx import stock


def get_sector_tickers(market: str) -> list[str]:
    """오늘 기준 업종 티커 목록 (KOSPI / KOSDAQ)"""
    date = datetime.date.today().strftime("%Y%m%d")
    tickers = stock.get_index_ticker_list(date, market=market)
    # 전체지수(종합) 제외하고 업종만 반환
    names = {t: stock.get_index_ticker_name(t) for t in tickers}
    # 코스피/코스닥 종합·대형·중형·소형 제외
    exclude_keywords = ["종합", "대형주", "중형주", "소형주", "100", "200", "배당"]
    return [
        t for t, n in names.items()
        if not any(kw in n for kw in exclude_keywords)
    ]


def get_sector_ohlcv(ticker: str, fromdate: str, todate: str) -> pd.DataFrame:
    """업종 일별 시세 (종가 포함)"""
    df = stock.get_index_ohlcv_by_date(fromdate, todate, ticker)
    return df


def fetch_all_sector_returns(market: str, fromdate: str, todate: str) -> pd.DataFrame:
    """
    모든 업종의 일별 수익률 DataFrame 반환
    index=날짜, columns=업종티커, values=등락률(%)
    """
    tickers = get_sector_tickers(market)
    all_returns = {}

    for ticker in tickers:
        try:
            df = get_sector_ohlcv(ticker, fromdate, todate)
            if df.empty:
                continue
            pct = df["종가"].pct_change() * 100
            all_returns[ticker] = pct
            time.sleep(0.1)
        except Exception as e:
            print(f"  [{ticker}] 오류: {e}")

    if not all_returns:
        return pd.DataFrame()

    return pd.DataFrame(all_returns).dropna(how="all")


def fetch_market_close(market: str, fromdate: str, todate: str) -> pd.Series:
    """코스피(1001) 또는 코스닥(2001) 종가 시리즈"""
    ticker = "1001" if market == "KOSPI" else "2001"
    df = stock.get_index_ohlcv_by_date(fromdate, todate, ticker)
    return df["종가"]
