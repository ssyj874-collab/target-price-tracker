"""
엑셀 레퍼런스 vs pykrx 계산 SIO 전수 비교 스크립트

실행 방법:
  python verify_sio.py KOSPI
  python verify_sio.py KOSDAQ
  python verify_sio.py KOSPI --value   # 거래대금 기준

레퍼런스: kospi_sio_reference.csv / kosdaq_sio_reference.csv
"""

import os
import sys
import argparse
import pandas as pd
import numpy as np

os.environ.setdefault('KRX_ID', 'syj6718')
os.environ.setdefault('KRX_PW', 'song135!')

REFERENCE_FILES = {
    'KOSPI':  'kospi_sio_reference.csv',
    'KOSDAQ': 'kosdaq_sio_reference.csv',
}


def load_reference(market: str) -> pd.DataFrame:
    path = os.path.join(os.path.dirname(__file__), REFERENCE_FILES[market])
    df = pd.read_csv(path, dtype={'date': str})
    df['date'] = df['date'].str.strip()
    return df.set_index('date')


def compute_sio_for_dates(market: str, dates: list[str], use_value: bool) -> pd.DataFrame:
    """dates 리스트에 대해 SIO 일괄 계산."""
    from sio_calculator import get_market_data, calc_sio_from_raw

    rows = []
    total = len(dates)
    for i, date_str in enumerate(dates, 1):
        print(f"\r[{i:3d}/{total}] {date_str}...", end='', flush=True)
        try:
            df = get_market_data(market, date_str)
            if df.empty:
                raise ValueError("빈 데이터")
            r = calc_sio_from_raw(df, use_value=use_value)
            rows.append({'date': date_str, **r})
        except Exception as e:
            rows.append({'date': date_str, 'sio': float('nan'), 'error': str(e)})
    print()
    return pd.DataFrame(rows).set_index('date')


def summarize_diff(ref: pd.Series, calc: pd.Series, label: str):
    """부호 불일치 및 오차 통계 출력."""
    both = pd.DataFrame({'ref': ref, 'calc': calc}).dropna()
    if both.empty:
        print(f"[{label}] 비교 가능한 데이터 없음")
        return

    both['sign_match'] = np.sign(both['ref']) == np.sign(both['calc'])
    both['abs_err']    = (both['ref'] - both['calc']).abs()
    mismatch = both[~both['sign_match']]

    print(f"\n{'='*60}")
    print(f"{label} 비교 결과 ({len(both)}일)")
    print(f"  부호 일치: {both['sign_match'].sum()}일  "
          f"불일치: {len(mismatch)}일 ({len(mismatch)/len(both)*100:.1f}%)")
    print(f"  평균 오차: {both['abs_err'].mean():.2f}  "
          f"최대 오차: {both['abs_err'].max():.2f}")
    if not mismatch.empty:
        print(f"\n  ── 부호 불일치 날짜 ──")
        print(mismatch[['ref','calc','abs_err']].rename(
            columns={'ref':'엑셀','calc':'계산','abs_err':'오차'}
        ).to_string())
    return both


# ---------------------------------------------------------------------------
# 가설별 일괄 테스트 (로컬 실행용)
# ---------------------------------------------------------------------------

def test_hypothesis(market: str, date_str: str, ref_sio: float):
    """
    단일 날짜에 대해 여러 파라미터 조합으로 SIO를 계산해
    어느 조합이 엑셀값과 일치하는지 출력.

    J 계산 방식:
      count  : 상승/하락 종목 수 비율  (F=상승수, G=하락수)
      volume : 상승/하락 거래량 비율
      value  : 상승/하락 거래대금 비율

    K 계산 방식:
      pct    : 등락률(%) 합산
      pt     : 등락폭(포인트=종가×등락률/100) 합산
    """
    from pykrx import stock
    from sio_calculator import _find_column

    raw = stock.get_market_ohlcv(date_str, market=market)

    change_col = _find_column(raw, ['등락률', '변동률', 'change'])
    vol_col    = _find_column(raw, ['거래량', 'Volume', 'volume'])
    val_col    = _find_column(raw, ['거래대금', 'Turnover', 'turnover'])
    close_col  = _find_column(raw, ['종가', 'Close', 'close'])

    pct = raw[change_col].fillna(0)
    up  = pct > 0
    dn  = pct < 0

    print(f"\n[가설 테스트] {market} {date_str}  엑셀SIO={ref_sio}")
    print(f"컬럼: {raw.columns.tolist()}")
    print(f"상승: {up.sum()}  하락: {dn.sum()}  보합: {(pct==0).sum()}")

    # 역산: 엑셀 SIO에서 D값 추정
    ref_D = ref_sio / 100 if ref_sio > 0 else 1 + ref_sio / 100
    print(f"엑셀 역산 D = {ref_D:.4f}\n")

    # ── J 후보 ────────────────────────────────────────────────────────────
    j_candidates = {}
    j_candidates['count'] = (int(up.sum()), int(dn.sum()))  # (F, G) = 종목수

    if vol_col:
        vol = raw[vol_col].fillna(0)
        j_candidates['volume'] = (vol[up].sum(), vol[dn].sum())
    if val_col:
        val = raw[val_col].fillna(0)
        j_candidates['value'] = (val[up].sum(), val[dn].sum())

    # ── K 후보 ────────────────────────────────────────────────────────────
    k_candidates = {}
    H_pct = pct[up].sum()
    I_pct = pct[dn].abs().sum()
    k_candidates['pct'] = (H_pct, I_pct)

    if close_col:
        close = raw[close_col].fillna(0)
        # 등락폭(pt) = 종가 × 등락률/100  (근사치, 전일종가 불필요)
        pt    = close * pct / 100
        H_pt  = pt[up].sum()
        I_pt  = pt[dn].abs().sum()
        k_candidates['pt'] = (H_pt, I_pt)

    # ── 전체 조합 출력 ────────────────────────────────────────────────────
    best = None
    for j_name, (F, G) in j_candidates.items():
        J = F / (F + G) if (F + G) > 0 else 0.5
        for k_name, (H, I) in k_candidates.items():
            K = H / (H + I) if (H + I) > 0 else 0.5
            D = (J + K) / 2
            E = 1 - D
            sio = D * 100 if D > E else -E * 100

            sign_ok  = np.sign(sio) == np.sign(ref_sio)
            val_close = abs(sio - ref_sio) < 5   # 5% 이내 근사
            mark = ""
            if sign_ok and val_close: mark = "★★ 부호+값 근사"
            elif sign_ok:             mark = "★  부호일치"
            label = f"J={j_name:6s} K={k_name:3s}"
            print(f"  {label}: J={J:.4f} K={K:.4f} D={D:.4f} SIO={sio:+.2f}  {mark}")
            if sign_ok and best is None:
                best = label

    print(f"\n→ 첫 번째 부호 일치 조합: {best}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('market', choices=['KOSPI', 'KOSDAQ'])
    parser.add_argument('--value', action='store_true')
    parser.add_argument('--hypothesis', metavar='YYYYMMDD',
                        help='단일 날짜 가설 전수 테스트')
    args = parser.parse_args()

    ref = load_reference(args.market)

    if args.hypothesis:
        date = args.hypothesis
        ref_sio = float(ref.loc[date, 'sio'])
        test_hypothesis(args.market, date, ref_sio)
        sys.exit(0)

    print(f"레퍼런스: {len(ref)}일 로드 완료 ({ref.index[0]} ~ {ref.index[-1]})")
    print("pykrx로 계산 중...")

    calc = compute_sio_for_dates(args.market, ref.index.tolist(), args.value)
    result = summarize_diff(ref['sio'], calc['sio'], args.market)

    if result is not None:
        out = f"{args.market.lower()}_sio_comparison.csv"
        result.to_csv(out)
        print(f"\n결과 저장: {out}")
