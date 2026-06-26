"""
KOSPI/KOSDAQ SIO (Strength Index Oscillator) Calculator
카페라떼 엑셀 SIO 수식 재현

수식:
  SIO = IF(D > E, D, -E) * 100
  D   = AVERAGE(J, K)
  E   = AVERAGE(1-J, 1-K)  = 1 - D  (대칭)
  J   = F / (F + G)   # 상승거래량 비율
  K   = H / (H + I)   # 상승포인트 비율
  F   = 상승종목 거래량 (또는 거래대금)
  G   = 하락종목 거래량 (또는 거래대금)
  H   = 상승종목 등락폭 합산 (절대값)
  I   = 하락종목 등락폭 합산 (절대값)

참고: D > 0.5 이면 상승장, D <= 0.5 이면 하락장
  → SIO = D*100 (상승) 또는 -E*100 (하락, E = 1-D)
"""

import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


# ---------------------------------------------------------------------------
# pykrx 데이터 취득
# ---------------------------------------------------------------------------

def get_market_data(market: str, date: str) -> pd.DataFrame:
    """
    특정 날짜의 시장 전 종목 OHLCV + 등락률 반환.
    market: 'KOSPI' 또는 'KOSDAQ'
    date  : 'YYYYMMDD'

    반환 컬럼: 시가, 고가, 저가, 종가, 거래량, 거래대금, 등락률
    """
    from pykrx import stock

    tickers = stock.get_market_ticker_list(date, market=market)
    rows = []
    for ticker in tickers:
        df = stock.get_market_ohlcv(date, date, ticker)
        if df.empty:
            continue
        row = df.iloc[0].to_dict()
        row['ticker'] = ticker
        rows.append(row)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).set_index('ticker')
    return df


def calc_sio_from_raw(df: pd.DataFrame, use_value: bool = False) -> dict:
    """
    종목별 데이터프레임으로부터 SIO 계산.

    Parameters
    ----------
    df        : get_market_data() 반환값
    use_value : True → 거래대금으로 F/G 계산, False → 거래량

    Returns
    -------
    dict with keys: J, K, D, E, sio, F, G, H, I,
                    advancing, declining, unchanged
    """
    # 등락률 컬럼명 탐색 (pykrx 버전마다 다름)
    change_col = _find_column(df, ['등락률', '변동률', 'change', 'Change'])
    vol_col    = _find_column(df, ['거래량', 'Volume', 'volume'])
    val_col    = _find_column(df, ['거래대금', 'Turnover', 'turnover'])

    if change_col is None:
        raise KeyError(f"등락률 컬럼을 찾을 수 없습니다. 컬럼: {df.columns.tolist()}")

    pct = df[change_col].fillna(0)

    up_mask   = pct > 0
    down_mask = pct < 0

    # ── F, G : 거래량 또는 거래대금 ──────────────────────────────────────
    base_col = val_col if use_value else vol_col
    if base_col is None:
        raise KeyError(f"거래량/거래대금 컬럼을 찾을 수 없습니다. 컬럼: {df.columns.tolist()}")

    volume = df[base_col].fillna(0)
    F = volume[up_mask].sum()    # 상승종목 거래량
    G = volume[down_mask].sum()  # 하락종목 거래량

    # ── H, I : 상승/하락 포인트 합산 (절대값) ────────────────────────────
    # 주의: H = 상승종목 등락률 합산, I = |하락종목 등락률| 합산
    H = pct[up_mask].sum()           # 양수
    I = pct[down_mask].abs().sum()   # 절대값으로 변환 (양수)

    # ── J, K, D, E ────────────────────────────────────────────────────────
    J = F / (F + G) if (F + G) > 0 else 0.5
    K = H / (H + I) if (H + I) > 0 else 0.5
    D = (J + K) / 2
    E = 1 - D   # AVERAGE(1-J, 1-K) = 1 - AVERAGE(J,K) = 1 - D

    # ── SIO ──────────────────────────────────────────────────────────────
    sio = D * 100 if D > E else -E * 100

    return {
        'F': F, 'G': G, 'H': H, 'I': I,
        'J': J, 'K': K, 'D': D, 'E': E,
        'sio': sio,
        'advancing': int(up_mask.sum()),
        'declining': int(down_mask.sum()),
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
    use_value: bool = False,
) -> pd.DataFrame:
    """
    fromdate~todate 기간의 일별 SIO 계산.
    반환: DatetimeIndex DataFrame (sio, J, K, D, E, F, G, H, I, advancing, declining)
    """
    from pykrx import stock

    # 거래일 목록
    trading_days = stock.get_index_ohlcv_by_date(fromdate, todate, '1001').index
    results = []

    for dt in trading_days:
        date_str = dt.strftime('%Y%m%d')
        try:
            df = get_market_data(market, date_str)
            if df.empty:
                continue
            row = calc_sio_from_raw(df, use_value=use_value)
            row['date'] = dt
            results.append(row)
        except Exception as e:
            print(f"[WARN] {date_str}: {e}")

    if not results:
        return pd.DataFrame()

    result_df = pd.DataFrame(results).set_index('date')
    return result_df


# ---------------------------------------------------------------------------
# 부호 반전 진단
# ---------------------------------------------------------------------------

def diagnose_sign_reversal(
    sio_computed: pd.Series,
    sio_reference: pd.Series,
    label: str = "SIO",
) -> pd.DataFrame:
    """
    계산값 vs 레퍼런스(엑셀) 부호 불일치 날짜 탐색.

    Parameters
    ----------
    sio_computed  : 직접 계산한 SIO 시리즈
    sio_reference : 엑셀에서 복사한 SIO 시리즈
    """
    df = pd.DataFrame({
        'computed': sio_computed,
        'reference': sio_reference,
    }).dropna()

    df['sign_computed']  = np.sign(df['computed'])
    df['sign_reference'] = np.sign(df['reference'])
    df['sign_match'] = df['sign_computed'] == df['sign_reference']
    df['abs_diff']   = (df['computed'] - df['reference']).abs()

    mismatch = df[~df['sign_match']]
    print(f"\n[{label}] 총 {len(df)}일 중 부호 불일치: {len(mismatch)}일")
    if not mismatch.empty:
        print(mismatch[['computed', 'reference', 'abs_diff']].to_string())

    return df


# ---------------------------------------------------------------------------
# 단일 날짜 디버그 출력
# ---------------------------------------------------------------------------

def debug_sio(market: str, date: str, use_value: bool = False):
    """단일 날짜 SIO 계산 과정 출력 (진단용)."""
    df = get_market_data(market, date)
    r  = calc_sio_from_raw(df, use_value=use_value)

    mode = '거래대금' if use_value else '거래량'
    print(f"\n{'='*50}")
    print(f"{market} SIO [{date}] (F/G 기준: {mode})")
    print(f"{'='*50}")
    print(f"  상승/하락/보합 종목수: {r['advancing']} / {r['declining']} / {r['unchanged']}")
    print(f"  F (상승 {mode}): {r['F']:,.0f}")
    print(f"  G (하락 {mode}): {r['G']:,.0f}")
    print(f"  H (상승 등락폭 합): {r['H']:.4f}")
    print(f"  I (하락 등락폭 합): {r['I']:.4f}")
    print(f"  J = F/(F+G)  : {r['J']:.6f}")
    print(f"  K = H/(H+I)  : {r['K']:.6f}")
    print(f"  D = (J+K)/2  : {r['D']:.6f}")
    print(f"  E = 1-D      : {r['E']:.6f}")
    print(f"  D > E?       : {r['D'] > r['E']}")
    print(f"  SIO          : {r['sio']:.4f}")


# ---------------------------------------------------------------------------
# CLI 진입점
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='KOSPI/KOSDAQ SIO Calculator')
    parser.add_argument('market', choices=['KOSPI', 'KOSDAQ'], help='시장 구분')
    parser.add_argument('date',   help='조회 날짜 (YYYYMMDD) 또는 시작날짜')
    parser.add_argument('--end',  default=None, help='종료 날짜 (YYYYMMDD, 기간 조회 시)')
    parser.add_argument('--value', action='store_true',
                        help='F/G를 거래대금 기준으로 계산 (기본: 거래량)')
    parser.add_argument('--debug', action='store_true',
                        help='단일 날짜 상세 출력')
    args = parser.parse_args()

    os.environ.setdefault('KRX_ID', 'syj6718')
    os.environ.setdefault('KRX_PW', 'song135!')

    if args.debug or args.end is None:
        debug_sio(args.market, args.date, use_value=args.value)
    else:
        df = calc_sio_range(args.market, args.date, args.end, use_value=args.value)
        print(df[['sio', 'D', 'E', 'J', 'K', 'advancing', 'declining']].to_string())
