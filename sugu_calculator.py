"""
수급오실레이터 계산기
공식:
  수급비율(t) = (기관5일누적순매수대금 + 외인5일누적순매수대금) / 시가총액
  EMA12      = EMA(수급비율, 12)
  EMA26      = EMA(수급비율, 26)
  MACD       = EMA12 - EMA26
  시그널      = EMA(MACD, 9)
  오실레이터  = MACD - 시그널
  20일매도합산 = 기관20일매도대금 + 외인20일매도대금
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pykrx import stock


# ── 유니버스 ──────────────────────────────────────────────────────────────

def get_top_n_by_marketcap(date: str, n: int, markets=('KOSPI', 'KOSDAQ')) -> list[str]:
    """시가총액 상위 N개 종목 티커 반환"""
    frames = []
    for mkt in markets:
        try:
            df = stock.get_market_cap_by_ticker(date, market=mkt)
            frames.append(df[['시가총액']])
        except Exception as e:
            print(f"[WARN] {mkt} 시가총액 조회 실패: {e}")
    if not frames:
        return []
    combined = pd.concat(frames).sort_values('시가총액', ascending=False)
    return list(combined.index[:n])


# ── 원시 데이터 수집 ───────────────────────────────────────────────────────

def fetch_investor_data(tickers: list[str], fromdate: str, todate: str,
                        verbose: bool = True) -> pd.DataFrame:
    """
    종목별 일자별 외인/기관 순매수대금 + 시가총액 수집
    반환 컬럼: ticker, date, foreign_net, institution_net,
               foreign_sell, institution_sell, market_cap
    단위: 순매수/매도대금 → 원(KRX 기준), 시가총액 → 원
    """
    rows = []
    total = len(tickers)
    for i, ticker in enumerate(tickers, 1):
        if verbose and i % 50 == 0:
            print(f"\r  {i}/{total} 수집 중...", end='', flush=True)
        try:
            # 투자자별 순매수 (단위: 주)
            inv = stock.get_market_net_purchases_of_investor(
                fromdate, todate, ticker
            )
            # 시가총액 일별
            cap = stock.get_market_ohlcv_by_date(fromdate, todate, ticker)[['종가']]
            cap_map = stock.get_market_cap_by_date(fromdate, todate, ticker)[['시가총액']]
        except Exception:
            continue

        if inv.empty or cap_map.empty:
            continue

        for dt in inv.index:
            if dt not in cap_map.index:
                continue
            row_inv = inv.loc[dt]
            mktcap  = cap_map.loc[dt, '시가총액']
            rows.append({
                'ticker':           ticker,
                'date':             dt,
                'foreign_net':      row_inv.get('외국인', 0),
                'institution_net':  row_inv.get('기관합계', 0),
                'market_cap':       mktcap,
            })

    if verbose:
        print()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df['date'] = pd.to_datetime(df['date'])
    return df.sort_values(['ticker', 'date'])


def fetch_investor_sell_data(tickers: list[str], fromdate: str, todate: str,
                             verbose: bool = True) -> pd.DataFrame:
    """
    종목별 일자별 외인/기관 매도대금 수집 (20일 누적 매도합산용)
    """
    rows = []
    total = len(tickers)
    for i, ticker in enumerate(tickers, 1):
        if verbose and i % 50 == 0:
            print(f"\r  {i}/{total} 매도데이터 수집 중...", end='', flush=True)
        try:
            df_trade = stock.get_market_trading_value_by_investor(
                fromdate, todate, ticker
            )
        except Exception:
            continue

        if df_trade.empty:
            continue

        for dt, row in df_trade.iterrows():
            rows.append({
                'ticker':              ticker,
                'date':                dt,
                'foreign_sell':        abs(row.get('외국인', {}).get('매도', 0) if isinstance(row.get('외국인'), dict) else 0),
                'institution_sell':    abs(row.get('기관합계', {}).get('매도', 0) if isinstance(row.get('기관합계'), dict) else 0),
            })

    if verbose:
        print()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df['date'] = pd.to_datetime(df['date'])
    return df.sort_values(['ticker', 'date'])


# ── EMA 계산 ──────────────────────────────────────────────────────────────

def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


# ── 수급오실레이터 계산 ────────────────────────────────────────────────────

def calc_sugu_oscillator(raw: pd.DataFrame) -> pd.DataFrame:
    """
    raw: fetch_investor_data() 반환값
    반환: ticker별 수급오실레이터 최신값 DataFrame
    """
    results = []

    for ticker, grp in raw.groupby('ticker'):
        grp = grp.set_index('date').sort_index()

        if len(grp) < 30:
            continue

        # 5일 누적 순매수 (rolling sum)
        roll5_foreign      = grp['foreign_net'].rolling(5).sum()
        roll5_institution  = grp['institution_net'].rolling(5).sum()

        # 수급비율
        mktcap = grp['market_cap'].replace(0, np.nan)
        sugu_ratio = (roll5_foreign + roll5_institution) / mktcap

        # MACD
        ema12  = ema(sugu_ratio.dropna(), 12)
        ema26  = ema(sugu_ratio.dropna(), 26)
        macd   = ema12 - ema26
        signal = ema(macd, 9)
        osc    = macd - signal

        latest_date = grp.index[-1]
        results.append({
            'ticker':     ticker,
            'date':       latest_date,
            'sugu_ratio': round(sugu_ratio.iloc[-1] * 100, 4) if not pd.isna(sugu_ratio.iloc[-1]) else None,
            'macd':       round(macd.iloc[-1] * 100, 4) if len(macd) > 0 else None,
            'signal':     round(signal.iloc[-1] * 100, 4) if len(signal) > 0 else None,
            'oscillator': round(osc.iloc[-1] * 100, 4) if len(osc) > 0 else None,
        })

    if not results:
        return pd.DataFrame()

    result_df = pd.DataFrame(results).set_index('ticker')
    return result_df.sort_values('oscillator', ascending=False)


# ── 종목명 조회 ───────────────────────────────────────────────────────────

def get_ticker_names(tickers: list[str], date: str) -> dict:
    names = {}
    for mkt in ('KOSPI', 'KOSDAQ'):
        try:
            tlist = stock.get_market_ticker_list(date, market=mkt)
            for t in tlist:
                if t in tickers:
                    names[t] = stock.get_market_ticker_name(t)
        except Exception:
            pass
    return names


# ── 메인 ─────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    today    = datetime.today()
    todate   = today.strftime('%Y%m%d')
    # EMA 계산에 충분한 기간 필요 (26+9+5 = 40일 + 여유)
    fromdate = (today - timedelta(days=120)).strftime('%Y%m%d')

    print(f"기간: {fromdate} ~ {todate}")
    print("시가총액 상위 700 종목 조회 중...")

    ref_date = today.strftime('%Y%m%d')
    tickers  = get_top_n_by_marketcap(ref_date, 700)
    print(f"  → {len(tickers)}개 종목 선정")

    # 테스트: 처음 5개만
    test_tickers = tickers[:5]
    print(f"\n[테스트] 상위 5개 종목: {test_tickers}")

    print("데이터 수집 중...")
    raw = fetch_investor_data(test_tickers, fromdate, todate)
    print(f"수집된 데이터: {len(raw)}행")

    if not raw.empty:
        result = calc_sugu_oscillator(raw)
        names  = get_ticker_names(test_tickers, ref_date)

        result['종목명'] = result.index.map(lambda t: names.get(t, t))
        print("\n[수급오실레이터 결과]")
        print(result[['종목명', 'sugu_ratio', 'macd', 'signal', 'oscillator']].to_string())
