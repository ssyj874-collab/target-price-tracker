"""
SIO 부호 반전 원인 진단 스크립트

pykrx로 계산 시 부호가 반대로 나오는 날이 다수 발생하는 이유를
단계별로 검증합니다.

가설 목록:
  A. H/I 계산 시 등락률이 아닌 등락(포인트)을 써야 하는가?
  B. K = H/(H+I)에서 I가 abs()없이 음수로 들어가고 있는가?
  C. F/G를 거래량 대신 거래대금으로 써야 하는가?
  D. J와 K 역할이 뒤바뀌어 있는가? (K=볼륨, J=포인트)
  E. D와 E 비교 방향이 반대인가? (IF(E>D, ...) 가 맞는가?)
  F. 등락률 계산 기준 (전일 대비 vs 52주 대비 등)이 다른가?
"""

import os
import pandas as pd
import numpy as np

os.environ.setdefault('KRX_ID', 'syj6718')
os.environ.setdefault('KRX_PW', 'song135!')


def get_raw_df(market: str, date: str) -> pd.DataFrame:
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
    return pd.DataFrame(rows).set_index('ticker') if rows else pd.DataFrame()


def try_all_hypotheses(df: pd.DataFrame) -> pd.DataFrame:
    """
    동일 데이터에 대해 모든 가설 조합으로 SIO를 계산해 비교표 반환.
    """
    results = {}

    # 컬럼 탐색
    change_col = next((c for c in ['등락률', '변동률', 'change'] if c in df.columns), None)
    vol_col    = next((c for c in ['거래량', 'Volume', 'volume'] if c in df.columns), None)
    val_col    = next((c for c in ['거래대금', 'Turnover', 'turnover'] if c in df.columns), None)

    pct    = df[change_col].fillna(0)
    up     = pct > 0
    dn     = pct < 0

    for use_val in [False, True]:
        base_col = val_col if use_val else vol_col
        vol      = df[base_col].fillna(0)
        F = vol[up].sum()
        G = vol[dn].sum()
        J = F / (F + G) if (F + G) > 0 else 0.5

        # 가설 B: I를 abs()하느냐 마느냐
        for abs_i in [True, False]:
            H = pct[up].sum()
            I = pct[dn].abs().sum() if abs_i else pct[dn].sum()
            K = H / (H + I) if (H + I) != 0 else 0.5

            # 가설 D: J/K 순서 뒤집기
            for swap_jk in [False, True]:
                j_eff, k_eff = (K, J) if swap_jk else (J, K)
                D = (j_eff + k_eff) / 2  # 교환해도 평균은 같으므로 의미 없음
                # → 실제 의미 있는 뒤집기: J를 볼륨비율이 아닌 포인트로
                pass

            D = (J + K) / 2
            E = 1 - D

            # 가설 E: 비교 방향 반전
            for flip_cmp in [False, True]:
                cond = (D > E) if not flip_cmp else (E > D)
                sio  = D * 100 if cond else -E * 100

                label = (
                    f"vol={'val' if use_val else 'qty'}"
                    f"_abs_i={abs_i}"
                    f"_flip={flip_cmp}"
                )
                results[label] = {
                    'F': F, 'G': G, 'H': H, 'I': I,
                    'J': round(J, 4), 'K': round(K, 4),
                    'D': round(D, 4), 'E': round(E, 4),
                    'SIO': round(sio, 4),
                }

    return pd.DataFrame(results).T


def compare_with_excel(
    market: str,
    dates_and_sio: list[tuple[str, float]],
    use_value: bool = False,
) -> pd.DataFrame:
    """
    엑셀 SIO 값과 계산값 비교.

    Parameters
    ----------
    dates_and_sio : [(날짜문자열, 엑셀SIO값), ...]  예: [('20250603', 12.34), ...]
    """
    from sio_calculator import get_market_data, calc_sio_from_raw

    rows = []
    for date_str, excel_sio in dates_and_sio:
        try:
            df  = get_market_data(market, date_str)
            r   = calc_sio_from_raw(df, use_value=use_value)
            computed = r['sio']
        except Exception as e:
            print(f"[WARN] {date_str}: {e}")
            computed = float('nan')

        rows.append({
            'date':          date_str,
            'excel_sio':     excel_sio,
            'computed_sio':  round(computed, 4),
            'diff':          round(computed - excel_sio, 4),
            'sign_match':    np.sign(computed) == np.sign(excel_sio),
        })

    result = pd.DataFrame(rows).set_index('date')
    n_mismatch = (~result['sign_match']).sum()
    print(f"\n부호 불일치: {n_mismatch}/{len(result)} 일")
    print(result.to_string())
    return result


# ---------------------------------------------------------------------------
# 단일 날짜 전체 가설 테스트
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 3:
        print("Usage: python diagnose_sign_bug.py KOSPI 20250603")
        sys.exit(1)

    market = sys.argv[1]
    date   = sys.argv[2]

    print(f"\n[전체 가설 테스트] {market} {date}")
    df_raw = get_raw_df(market, date)
    if df_raw.empty:
        print("데이터 없음")
        sys.exit(1)

    print(f"총 종목수: {len(df_raw)}")
    print(f"컬럼: {df_raw.columns.tolist()}")

    result = try_all_hypotheses(df_raw)
    print("\n=== 가설별 SIO 계산 결과 ===")
    print(result[['J', 'K', 'D', 'E', 'SIO']].to_string())
    print("\n─ 엑셀값과 비교하려면 compare_with_excel() 함수 직접 호출 ─")
