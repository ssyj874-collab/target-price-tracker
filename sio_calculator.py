"""
KOSPI/KOSDAQ SIO (Strength Index Oscillator) Calculator
카페라떼 엑셀 SIO 수식 재현

확정 수식 (원본 엑셀 xlsm 역공학):
  SIO = D×100        (D > 0.5, 상승장)
  SIO = -(1-D)×100   (D ≤ 0.5, 하락장)

  D = (J + K) / 2
  J = F / (F + G)   ← 상승종목 거래량 / (상승+하락 거래량)
  K = H / (H + I)   ← 상승종목 등락률%합 / (상승+하락 등락률%합)

  F = 상승종목 거래량 합 (ETF/스팩/관리종목 제외)
  G = 하락종목 거래량 합
  H = 상승종목 등락률(%) 합  (양수)
  I = 하락종목 등락률(%) 절대값 합  (양수)

주의:
  - pykrx는 ETF·스팩 포함 → 엑셀 대비 J 값 약 0.05~0.07 차이
  - 완전 재현을 위해 ETF 티커를 제외한 주권(주식)만 사용
"""

import os
import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# 데이터 취득
# ---------------------------------------------------------------------------

# 날짜별 티커 캐시 (같은 날짜 반복 호출 방지)
_ticker_cache: dict = {}


def get_stock_only_tickers(date: str, market: str) -> set:
    """ETF·스팩 제외 순수 주권 티커 목록 반환 (캐시됨)."""
    from pykrx import stock

    key = (date, market)
    if key not in _ticker_cache:
        all_tickers = set(stock.get_market_ticker_list(date, market=market))
        etf_tickers = set(stock.get_etf_ticker_list(date))
        _ticker_cache[key] = all_tickers - etf_tickers
    return _ticker_cache[key]


def get_market_data(market: str, date: str, exclude_etf: bool = True) -> pd.DataFrame:
    """
    특정 날짜의 시장 전 종목 OHLCV + 등락률 + 시가총액 반환.
    exclude_etf=True 이면 ETF 제외 (엑셀과 동일 기준).
    """
    from pykrx import stock

    df = stock.get_market_ohlcv(date, market=market)
    if df.empty:
        return df

    # 시가총액 merge (market-cap weighted K 계산에 필요)
    try:
        cap = stock.get_market_cap(date, market=market)
        if not cap.empty and '시가총액' in cap.columns:
            df = df.join(cap[['시가총액']], how='left')
    except Exception:
        pass

    if exclude_etf:
        valid = get_stock_only_tickers(date, market)
        df = df[df.index.isin(valid)]

    return df


# ---------------------------------------------------------------------------
# SIO 계산
# ---------------------------------------------------------------------------

def calc_sio_from_raw(df: pd.DataFrame) -> dict:
    """
    종목별 데이터프레임으로부터 SIO 계산.

    F/G = 거래량 기준
    H/I = 시가총액 가중 등락률 (index contribution)
          H = Σ(시총_i / 총시총 × 등락률_i) for rising  [%단위]
          I = Σ(시총_i / 총시총 × |등락률_i|) for falling

    Returns dict: J, K, D, E, sio, F, G, H, I, advancing, declining, unchanged
    """
    change_col = _find_column(df, ['등락률', '변동률', 'change', 'Change'])
    vol_col    = _find_column(df, ['거래량', 'Volume', 'volume'])
    cap_col    = _find_column(df, ['시가총액', 'Marcap', 'marcap'])

    if change_col is None:
        raise KeyError(f"등락률 컬럼 없음. 컬럼: {df.columns.tolist()}")
    if vol_col is None:
        raise KeyError(f"거래량 컬럼 없음. 컬럼: {df.columns.tolist()}")

    pct = df[change_col].fillna(0)
    vol = df[vol_col].fillna(0)

    up = pct > 0
    dn = pct < 0

    # F, G : 거래량
    F = vol[up].sum()
    G = vol[dn].sum()

    # H, I : 시가총액 가중 등락률 (지수기여도 근사)
    # NaN 시총이 많으면 가중치가 왜곡되므로 커버리지 70% 미만 시 단순합으로 fallback
    def _use_cap_weight():
        if cap_col is None:
            return False
        valid = df[cap_col].notna() & (df[cap_col] > 0)
        coverage = valid.sum() / max(len(df), 1)
        return coverage >= 0.7

    if _use_cap_weight():
        cap        = df[cap_col].fillna(0)
        total_cap  = cap.sum()
        weight     = cap / total_cap
        H = (weight * pct)[up].sum()
        I = (weight * pct.abs())[dn].sum()
    else:
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
