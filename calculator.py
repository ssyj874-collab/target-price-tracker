import pandas as pd
import numpy as np

TOP_N = 5  # 상위 N개 업종을 "쏠린 업종"으로 정의
CORR_WINDOW = 30  # 상관계수 롤링 윈도우 (일)

KOSPI_SECTORS = {
    "WI100": "에너지", "WI110": "화학", "WI200": "비철/목재",
    "WI210": "철강", "WI220": "건설", "WI230": "기계",
    "WI240": "조선", "WI250": "상사/자본재", "WI260": "운송",
    "WI300": "자동차", "WI310": "화장품/의류", "WI320": "호텔/레저",
    "WI330": "미디어/교육", "WI340": "소매(유통)", "WI400": "필수소비재",
    "WI410": "건강관리", "WI500": "은행", "WI510": "증권",
    "WI520": "보험", "WI600": "소프트웨어", "WI610": "IT하드웨어",
    "WI620": "반도체", "WI630": "IT가전", "WI640": "디스플레이",
    "WI650": "통신서비스", "WI660": "유틸리티",
}

KOSDAQ_SECTORS = {
    "WI210": "철강", "WI220": "건설", "WI230": "기계",
    "WI240": "조선", "WI260": "운송", "WI310": "화장품/의류",
    "WI320": "호텔/레저", "WI330": "미디어/교육", "WI340": "소매(유통)",
    "WI400": "필수소비재", "WI410": "건강관리", "WI510": "증권",
    "WI600": "소프트웨어", "WI610": "IT하드웨어", "WI620": "반도체",
    "WI630": "IT가전", "WI640": "디스플레이", "WI650": "통신서비스",
}


def compute_concentration_index(returns_df: pd.DataFrame) -> pd.DataFrame:
    """
    returns_df: index=날짜, columns=업종코드, values=일별수익률(%)
    반환: index=날짜, columns=[long_short, index_value]
    """
    results = []
    for date, row in returns_df.iterrows():
        rates = row.dropna()
        if len(rates) < TOP_N + 1:
            continue
        ranked = rates.rank(ascending=False)
        top_rates = rates[ranked <= TOP_N]
        bottom_rates = rates[ranked > TOP_N]
        long_short = top_rates.mean() - bottom_rates.mean()
        results.append({"date": date, "long_short": long_short})

    if not results:
        return pd.DataFrame(columns=["date", "long_short", "index_value"])

    df = pd.DataFrame(results).set_index("date").sort_index()

    # 지수화: 1000 시작, 누적 복리
    idx_vals = [1000.0]
    for ls in df["long_short"].iloc[1:]:
        idx_vals.append(idx_vals[-1] * (1 + ls / 100))
    df["index_value"] = idx_vals

    return df


def compute_correlation(market_series: pd.Series, concentration_series: pd.Series) -> pd.Series:
    """30일 롤링 상관계수"""
    combined = pd.DataFrame({
        "market": market_series,
        "concentration": concentration_series,
    }).dropna()
    return combined["market"].rolling(CORR_WINDOW).corr(combined["concentration"])


def build_chart_data(
    market_df: pd.DataFrame,      # columns: date(index), close
    sector_returns: dict,          # {code: [{date, change_rate}, ...]}
    sectors: dict,                 # {code: name}
) -> dict:
    """최종 차트 데이터를 계산해서 반환"""
    # 수익률 DataFrame 구성
    returns_map = {}
    for code, rows in sector_returns.items():
        for r in rows:
            date = r["date"]
            if date not in returns_map:
                returns_map[date] = {}
            returns_map[date][code] = r["change_rate"]

    returns_df = pd.DataFrame.from_dict(returns_map, orient="index")
    returns_df.index = pd.to_datetime(returns_df.index)
    returns_df = returns_df.sort_index()

    conc_df = compute_concentration_index(returns_df)
    if conc_df.empty:
        return {"dates": [], "market": [], "concentration": [], "correlation": []}

    # 시장 지수 정렬
    market_df = market_df.copy()
    market_df.index = pd.to_datetime(market_df.index)
    market_df = market_df.sort_index()

    # 공통 날짜만
    common_dates = conc_df.index.intersection(market_df.index)
    conc_aligned = conc_df.loc[common_dates, "index_value"]
    market_aligned = market_df.loc[common_dates, "close"]

    corr = compute_correlation(market_aligned.pct_change(), conc_aligned.pct_change())

    dates = [d.strftime("%Y-%m-%d") for d in common_dates]
    return {
        "dates": dates,
        "market": market_aligned.tolist(),
        "concentration": conc_aligned.tolist(),
        "correlation": corr.tolist(),
    }
