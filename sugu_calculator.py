"""
수급오실레이터 계산기
공식:
  수급비율(t) = (기관5일누적순매수대금 + 외인5일누적순매수대금) / 시가총액
  EMA12      = EMA(수급비율, 12)
  EMA26      = EMA(수급비율, 26)
  MACD       = EMA12 - EMA26
  시그널      = EMA(MACD, 9)
  오실레이터  = MACD - 시그널
"""

import os
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
from pykrx import stock

load_dotenv()
os.environ.setdefault('KRX_ID', 'syj6718')
os.environ.setdefault('KRX_PW', 'song135!')

CACHE_DIR = Path(__file__).parent / '.cache'
CACHE_DIR.mkdir(exist_ok=True)


# ── 마지막 거래일 ──────────────────────────────────────────────────────────

def last_trading_day() -> str:
    """오늘 기준 가장 최근 거래일 반환 (YYYYMMDD)"""
    dt = datetime.today()
    for _ in range(10):
        candidate = dt.strftime('%Y%m%d')
        try:
            idx = stock.get_index_ohlcv_by_date(candidate, candidate, '1001')
            if not idx.empty:
                return candidate
        except Exception:
            pass
        dt -= timedelta(days=1)
    return datetime.today().strftime('%Y%m%d')


# ── 유니버스: 시가총액 상위 N종목 ───────────────────────────────────────────

def get_top_n_by_marketcap(ref_date: str, n: int) -> list[str]:
    """
    시가총액 상위 N종목 티커 반환.
    결과를 캐시 파일에 저장하므로 같은 날짜 재실행 시 즉시 반환.
    """
    cache_file = CACHE_DIR / f'universe_{ref_date}.json'
    if cache_file.exists():
        tickers = json.loads(cache_file.read_text())
        print(f"  (캐시 로드: {ref_date}, {len(tickers)}종목)")
        return tickers[:n]

    print(f"  시가총액 조회 중 (최초 1회, 약 10~20분 소요)...")
    all_tickers = []
    for mkt in ('KOSPI', 'KOSDAQ'):
        try:
            t_list = stock.get_market_ticker_list(ref_date, market=mkt)
            all_tickers += list(t_list)
        except Exception as e:
            print(f"  [WARN] {mkt} 종목 목록 조회 실패: {e}")

    print(f"  전체 {len(all_tickers)}종목 시가총액 수집 중...")
    caps = {}
    total = len(all_tickers)
    for i, ticker in enumerate(all_tickers, 1):
        if i % 100 == 0:
            print(f"\r  {i}/{total}...", end='', flush=True)
        try:
            df = stock.get_market_cap_by_date(ref_date, ref_date, ticker)
            if not df.empty and '시가총액' in df.columns:
                caps[ticker] = int(df['시가총액'].iloc[0])
            else:
                caps[ticker] = 0
        except Exception:
            caps[ticker] = 0

    print()
    sorted_tickers = sorted(caps, key=lambda t: caps[t], reverse=True)
    cache_file.write_text(json.dumps(sorted_tickers))
    print(f"  캐시 저장 완료: {cache_file}")
    return sorted_tickers[:n]


# ── 데이터 수집 ────────────────────────────────────────────────────────────

def fetch_investor_data(tickers: list[str], fromdate: str, todate: str,
                        verbose: bool = True) -> pd.DataFrame:
    """
    종목별 일자별 외인/기관 순매수대금 + 시가총액 수집
    컬럼: ticker, date, foreign_net, institution_net, market_cap (단위: 원)
    """
    rows = []
    total = len(tickers)
    for i, ticker in enumerate(tickers, 1):
        if verbose and i % 50 == 0:
            print(f"\r  {i}/{total} 수집 중...", end='', flush=True)
        try:
            inv     = stock.get_market_trading_value_by_date(fromdate, todate, ticker)
            cap_map = stock.get_market_cap_by_date(fromdate, todate, ticker)[['시가총액']]
        except Exception:
            continue

        if inv.empty or cap_map.empty:
            continue

        for dt in inv.index:
            if dt not in cap_map.index:
                continue
            r = inv.loc[dt]
            rows.append({
                'ticker':          ticker,
                'date':            dt,
                'foreign_net':     r.get('외국인합계', 0),
                'institution_net': r.get('기관합계', 0),
                'market_cap':      cap_map.loc[dt, '시가총액'],
            })

    if verbose:
        print()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df['date'] = pd.to_datetime(df['date'])
    return df.sort_values(['ticker', 'date'])


# ── EMA / 오실레이터 계산 ─────────────────────────────────────────────────

def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


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

        roll5  = (grp['foreign_net'] + grp['institution_net']).rolling(5).sum()
        mktcap = grp['market_cap'].replace(0, np.nan)
        ratio  = roll5 / mktcap

        valid = ratio.dropna()
        if len(valid) < 26:
            continue

        ema12  = _ema(valid, 12)
        ema26  = _ema(valid, 26)
        macd   = ema12 - ema26
        signal = _ema(macd, 9)
        osc    = macd - signal

        results.append({
            'ticker':     ticker,
            'date':       grp.index[-1],
            'macd':       round(macd.iloc[-1] * 100, 4),
            'signal':     round(signal.iloc[-1] * 100, 4),
            'oscillator': round(osc.iloc[-1] * 100, 4),
            'ratio':      round(ratio.iloc[-1] * 100, 4) if not pd.isna(ratio.iloc[-1]) else None,
        })

    if not results:
        return pd.DataFrame()

    return (pd.DataFrame(results)
            .set_index('ticker')
            .sort_values('oscillator', ascending=False))


# ── 종목명 조회 ───────────────────────────────────────────────────────────

def get_ticker_names(tickers: list[str]) -> dict:
    return {t: stock.get_market_ticker_name(t) for t in tickers}


# ── 메인 ─────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    today    = datetime.today()
    todate   = today.strftime('%Y%m%d')
    fromdate = (today - timedelta(days=120)).strftime('%Y%m%d')

    ref_date = last_trading_day()
    print(f"기준일: {ref_date}, 기간: {fromdate} ~ {todate}")

    print("시가총액 상위 700 종목 선정 중...")
    tickers = get_top_n_by_marketcap(ref_date, 700)
    print(f"  → {len(tickers)}개 종목 선정")
    print(f"  상위 10개: {tickers[:10]}")

    # 상위 10개 이름 확인
    names = get_ticker_names(tickers[:10])
    for t, n in names.items():
        print(f"    {t}: {n}")

    # 테스트: 상위 5개만
    test_tickers = tickers[:5]
    print(f"\n데이터 수집 중 (테스트 5개)...")
    raw = fetch_investor_data(test_tickers, fromdate, todate)
    print(f"수집된 데이터: {len(raw)}행")

    if not raw.empty:
        result = calc_sugu_oscillator(raw)
        result['종목명'] = result.index.map(lambda t: stock.get_market_ticker_name(t))
        print("\n[수급오실레이터 결과]")
        print(result[['종목명', 'ratio', 'macd', 'signal', 'oscillator']].to_string())
