"""
KOSPI/KOSDAQ SIO (Strength Index Oscillator) Calculator
카페라떼 엑셀 SIO 수식 재현

확인된 수식:
  SIO = IF(D > E, D, -E) * 100
  D   = (J + K) / 2
  E   = 1 - D
  J   = F / (F + G)   ← 상승종목 거래대금 / 전체(상승+하락) 거래대금
  K   = H / (H + I)   ← 상승종목 등락폭합 / 전체 등락폭합  (등락폭 = 전일종가×등락률/100)

  F = 상승종목 거래대금 합
  G = 하락종목 거래대금 합
  H = 상승종목 등락폭 합  (양수)
  I = 하락종목 등락폭 절대값 합  (양수)

참고:
  - D > 0.5 → 상승장, SIO = D*100  (최소 +50)
  - D ≤ 0.5 → 하락장, SIO = -E*100 (최대 -50)
  - 전일종가가 없을 때 등락폭 근사치: 종가 × 등락률 / (100 + 등락률)
"""

import os
import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# 데이터 취득
# ---------------------------------------------------------------------------

def get_market_data(market: str, date: str) -> pd.DataFrame:
    """
    특정 날짜의 시장 전 종목 OHLCV + 등락률 일괄 반환.
    market : 'KOSPI' 또는 'KOSDAQ'
    date   : 'YYYYMMDD'
    """
    from pykrx import stock
    return stock.get_market_ohlcv(date, market=market)


def get_prev_close(market: str, date: str) -> pd.Series:
    """
    date 직전 거래일의 종가를 반환 (등락폭 정밀 계산용).
    반환: ticker → 전일종가 Series
    """
    from pykrx import stock
    # 당일 포함 2일치 조회 → 전일 데이터 추출
    df2 = stock.get_market_ohlcv(date, market=market)
    # pykrx에서 전전일 종가를 직접 얻는 API가 없으므로
    # 종가와 등락률로 역산: 전일종가 = 종가 / (1 + 등락률/100)
    close_col  = _find_column(df2, ['종가', 'Close', 'close'])
    change_col = _find_column(df2, ['등락률', '변동률', 'change'])
    if close_col is None or change_col is None:
        return pd.Series(dtype=float)
    close  = df2[close_col].fillna(0)
    pct    = df2[change_col].fillna(0)
    prev   = close / (1 + pct / 100)
    return prev


# ---------------------------------------------------------------------------
# SIO 계산
# ---------------------------------------------------------------------------

def calc_sio_from_raw(
    df: pd.DataFrame,
    prev_close: pd.Series | None = None,
) -> dict:
    """
    종목별 데이터프레임으로부터 SIO 계산.

    Parameters
    ----------
    df         : get_market_data() 반환값
    prev_close : 전일종가 Series (없으면 근사치 사용)

    Returns
    -------
    dict: J, K, D, E, sio, F, G, H, I, advancing, declining, unchanged
    """
    change_col = _find_column(df, ['등락률', '변동률', 'change', 'Change'])
    val_col    = _find_column(df, ['거래대금', 'Turnover', 'turnover'])
    close_col  = _find_column(df, ['종가', 'Close', 'close'])

    if change_col is None:
        raise KeyError(f"등락률 컬럼 없음. 컬럼: {df.columns.tolist()}")
    if val_col is None:
        raise KeyError(f"거래대금 컬럼 없음. 컬럼: {df.columns.tolist()}")
    if close_col is None:
        raise KeyError(f"종가 컬럼 없음. 컬럼: {df.columns.tolist()}")

    pct   = df[change_col].fillna(0)
    val   = df[val_col].fillna(0)
    close = df[close_col].fillna(0)

    up = pct > 0
    dn = pct < 0

    # ── F, G : 거래대금 ──────────────────────────────────────────────────
    F = val[up].sum()
    G = val[dn].sum()

    # ── H, I : 등락폭(포인트) 합산 ───────────────────────────────────────
    # 전일종가가 있으면 정확히, 없으면 근사치 사용
    # 정확: 등락폭 = 전일종가 × 등락률/100
    # 근사: 등락폭 = 종가 × 등락률 / (100 + 등락률)  ← 전일종가 역산
    if prev_close is not None and not prev_close.empty:
        aligned = prev_close.reindex(df.index).fillna(0)
        pt = aligned * pct / 100
    else:
        # 종가 / (1 + pct/100) = 전일종가 → 등락폭 = 전일종가 × pct/100
        prev_approx = close / (1 + pct / 100)
        pt = prev_approx * pct / 100

    H = pt[up].sum()
    I = pt[dn].abs().sum()

    # ── J, K, D, E ────────────────────────────────────────────────────────
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

def calc_sio_range(
    market: str,
    fromdate: str,
    todate: str,
) -> pd.DataFrame:
    """
    fromdate~todate 기간의 일별 SIO 계산.
    반환: DatetimeIndex DataFrame
    """
    from pykrx import stock

    trading_days = stock.get_index_ohlcv_by_date(
        fromdate, todate, '1001' if market == 'KOSPI' else '2001'
    ).index

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
# 단일 날짜 디버그 출력
# ---------------------------------------------------------------------------

def debug_sio(market: str, date: str):
    df = get_market_data(market, date)
    r  = calc_sio_from_raw(df)

    print(f"\n{'='*55}")
    print(f"{market} SIO [{date}]")
    print(f"{'='*55}")
    print(f"  상승/하락/보합 : {r['advancing']} / {r['declining']} / {r['unchanged']}")
    print(f"  F (상승 거래대금): {r['F']:,.0f}")
    print(f"  G (하락 거래대금): {r['G']:,.0f}")
    print(f"  H (상승 등락폭합): {r['H']:,.2f}")
    print(f"  I (하락 등락폭합): {r['I']:,.2f}")
    print(f"  J = F/(F+G)     : {r['J']:.6f}")
    print(f"  K = H/(H+I)     : {r['K']:.6f}")
    print(f"  D = (J+K)/2     : {r['D']:.6f}")
    print(f"  E = 1-D         : {r['E']:.6f}")
    print(f"  SIO             : {r['sio']:.4f}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='KOSPI/KOSDAQ SIO Calculator')
    parser.add_argument('market', choices=['KOSPI', 'KOSDAQ'])
    parser.add_argument('date',   help='YYYYMMDD (단일) 또는 시작날짜')
    parser.add_argument('--end',  default=None, help='종료날짜 (기간 조회)')
    parser.add_argument('--debug', action='store_true', help='상세 출력')
    args = parser.parse_args()

    os.environ.setdefault('KRX_ID', 'syj6718')
    os.environ.setdefault('KRX_PW', 'song135!')

    if args.debug or args.end is None:
        debug_sio(args.market, args.date)
    else:
        df = calc_sio_range(args.market, args.date, args.end)
        print(df[['sio', 'D', 'J', 'K', 'advancing', 'declining']].to_string())
