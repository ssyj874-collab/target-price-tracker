"""
KOSPI/KOSDAQ SIO (Strength Index Oscillator) Calculator
카페라떼 엑셀 SIO 수식 재현

확정 수식 (원본 엑셀 xlsm 역공학):
  SIO = D×100        (D > 0.5, 상승장)
  SIO = -(1-D)×100   (D ≤ 0.5, 하락장)

  D = (J + K) / 2
  J = F / (F + G)   ← 상승종목 거래량 / (상승+하락 거래량)
  K = H / (H + I)   ← 상승종목 등락률(%)합 / (상승+하락 등락률(%)합)

  대상 종목: KOSPI → KOSPI 200 구성종목 (엑셀 B:GS = 200열)
             KOSDAQ → KOSDAQ 150 구성종목
  F = 상승종목 거래량 합
  G = 하락종목 거래량 합
  H = 상승종목 등락률(%) 합  (양수)
  I = 하락종목 등락률(%) 절대값 합  (양수)
"""

import os
import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# 데이터 취득
# ---------------------------------------------------------------------------

# 날짜별 티커 캐시 (같은 날짜 반복 호출 방지)
_ticker_cache: dict = {}


# 지수별 구성종목 인덱스 티커
_INDEX_TICKER = {
    'KOSPI':  '1028',  # KOSPI 200
    'KOSDAQ': '2203',  # KOSDAQ 150
}


def get_index_tickers(date: str, market: str) -> set:
    """KOSPI 200 / KOSDAQ 150 구성종목 티커 반환 (캐시됨)."""
    from pykrx import stock

    key = (date, market)
    if key not in _ticker_cache:
        idx = _INDEX_TICKER.get(market)
        try:
            tickers = stock.get_index_portfolio_deposit_file(idx, date)
            _ticker_cache[key] = set(tickers)
        except Exception as e:
            print(f"[WARN] {market} 지수 구성종목 조회 실패({e}), 전체 종목으로 대체")
            all_t = set(stock.get_market_ticker_list(date, market=market))
            etf_t = set(stock.get_etf_ticker_list(date))
            _ticker_cache[key] = all_t - etf_t
    return _ticker_cache[key]


# 하위 호환을 위해 유지
def get_stock_only_tickers(date: str, market: str) -> set:
    return get_index_tickers(date, market)


def get_market_data(market: str, date: str, exclude_etf: bool = True) -> pd.DataFrame:
    """
    KOSPI 200 / KOSDAQ 150 구성종목의 OHLCV + 등락률 반환.
    엑셀 원본: '코스피 SIO(태린이아빠).xlsx' B:GS(200열) = KOSPI 200
    """
    from pykrx import stock

    df = stock.get_market_ohlcv(date, market=market)
    if df.empty:
        return df

    valid = get_index_tickers(date, market)
    return df[df.index.isin(valid)]


# ---------------------------------------------------------------------------
# SIO 계산
# ---------------------------------------------------------------------------

def calc_sio_from_raw(df: pd.DataFrame) -> dict:
    """
    종목별 데이터프레임으로부터 SIO 계산.

    F/G = 거래량 기준 (엑셀 UPSIDE/DOWNSIDE 거래량 시트, KOSPI200/KOSDAQ150)
    H/I = 등락률(%) 단순합 기준
          H = 상승종목 등락률(%) 합  (양수)
          I = 하락종목 등락률(%) 절대값 합  (양수)

    Returns dict: J, K, D, E, sio, F, G, H, I, advancing, declining, unchanged
    """
    change_col = _find_column(df, ['등락률', '변동률', 'change', 'Change'])
    vol_col    = _find_column(df, ['거래량', 'Volume', 'volume'])

    if change_col is None:
        raise KeyError(f"등락률 컬럼 없음. 컬럼: {df.columns.tolist()}")
    if vol_col is None:
        raise KeyError(f"거래량 컬럼 없음. 컬럼: {df.columns.tolist()}")

    pct = df[change_col].fillna(0)
    vol = df[vol_col].fillna(0)

    up = pct > 0
    dn = pct < 0

    # F, G : 거래량 (KOSPI 200 / KOSDAQ 150 기준)
    F = vol[up].sum()
    G = vol[dn].sum()

    # H, I : 등락률(%) 단순합
    H = pct[up].sum()
    I = pct[dn].abs().sum()

    J = F / (F + G) if (F + G) > 0 else 0.5
    K = H / (H + I) if (H + I) > 0 else 0.5
    D = (J + K) / 2
    E = 1 - D

    sio = D * 100 if D > E else -E * 100

    return {
        'F': F, 'G': G, 'H': H, 'I': I,
        'J': J, 'K': K, 'D': D, 'E': E,
        'sio': sio,
        'advancing': int(up.sum()),
        'declining': int(dn.sum()),
        'unchanged': int((pct == 0).sum()),
    }


def _find_column(df: pd.DataFrame, candidates: list) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None


# ---------------------------------------------------------------------------
# 날짜 범위 일괄 계산
# ---------------------------------------------------------------------------

def calc_sio_range(market: str, fromdate: str, todate: str) -> pd.DataFrame:
    from pykrx import stock

    index_ticker = '1001' if market == 'KOSPI' else '2001'
    trading_days = stock.get_index_ohlcv_by_date(fromdate, todate, index_ticker).index

    results = []
    total = len(trading_days)
    for i, dt in enumerate(trading_days, 1):
        date_str = dt.strftime('%Y%m%d')
        print(f"\r[{i:3d}/{total}] {date_str}...", end='', flush=True)
        try:
            df = get_market_data(market, date_str)
            if df.empty:
                continue
            row = calc_sio_from_raw(df)
            row['date'] = dt
            results.append(row)
        except Exception as e:
            print(f"\n[WARN] {date_str}: {e}")

    print()
    if not results:
        return pd.DataFrame()
    return pd.DataFrame(results).set_index('date')


# ---------------------------------------------------------------------------
# 단일 날짜 디버그
# ---------------------------------------------------------------------------

def debug_sio(market: str, date: str):
    df  = get_market_data(market, date)
    r   = calc_sio_from_raw(df)
    xls = _load_excel_ref(market, date)

    print(f"\n{'='*60}")
    print(f"{market} SIO [{date}]  (ETF 제외)")
    print(f"{'='*60}")
    print(f"  종목수  상승:{r['advancing']} / 하락:{r['declining']} / 보합:{r['unchanged']}")
    print(f"  {'항목':12s}  {'pykrx':>14s}  {'엑셀':>14s}  {'차이':>10s}")
    print(f"  {'-'*54}")
    fields = [
        ('F (상승거래량)', r['F'],   xls.get('F')),
        ('G (하락거래량)', r['G'],   xls.get('G')),
        ('H (상승등락률%)', r['H'],  xls.get('H')),
        ('I (하락등락률%)', r['I'],  xls.get('I')),
        ('J',              r['J'],  xls.get('J')),
        ('K',              r['K'],  xls.get('K')),
        ('D',              r['D'],  xls.get('D')),
        ('SIO(%)',         r['sio'], xls.get('sio')),
    ]
    for name, computed, excel in fields:
        if excel is not None:
            diff = f"{computed - excel:+.4f}"
            print(f"  {name:12s}  {computed:>14.4f}  {excel:>14.4f}  {diff:>10s}")
        else:
            print(f"  {name:12s}  {computed:>14.4f}  {'(없음)':>14s}")


def _load_excel_ref(market: str, date: str) -> dict:
    """xlsm 레퍼런스에서 해당 날짜 값 로드."""
    fname = f"{'kospi' if market=='KOSPI' else 'kosdaq'}_sio_reference.csv"
    path  = os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)
    if not os.path.exists(path):
        return {}
    ref = pd.read_csv(path, dtype={'date': str})
    row = ref[ref['date'] == date]
    if row.empty:
        return {}
    r = row.iloc[0]
    return {k: float(r[k]) for k in ['sio','D','E','F','G','H','I','J','K'] if k in r}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='KOSPI/KOSDAQ SIO Calculator')
    parser.add_argument('market', choices=['KOSPI', 'KOSDAQ'])
    parser.add_argument('date',   help='YYYYMMDD')
    parser.add_argument('--end',  default=None, help='종료날짜 (기간 조회)')
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--include-etf', action='store_true', help='ETF 포함 (기본: 제외)')
    args = parser.parse_args()

    os.environ.setdefault('KRX_ID', 'syj6718')
    os.environ.setdefault('KRX_PW', 'song135!')

    if args.debug or args.end is None:
        debug_sio(args.market, args.date)
    else:
        df = calc_sio_range(args.market, args.date, args.end)
        print(df[['sio','D','J','K','advancing','declining']].to_string())
