import pandas as pd
import numpy as np

TOP_N = 5
CORR_WINDOW = 30


def compute_concentration_index(returns_df: pd.DataFrame) -> pd.DataFrame:
    """
    returns_df: index=날짜, columns=업종티커, values=일별수익률(%)
    반환: DataFrame with index_value (지수화된 쏠림지수)
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

    idx_vals = [1000.0]
    for ls in df["long_short"].iloc[1:]:
        idx_vals.append(idx_vals[-1] * (1 + ls / 100))
    df["index_value"] = idx_vals

    return df


def build_chart_data(market_close: pd.Series, returns_df: pd.DataFrame) -> dict:
    """최종 차트 데이터 계산"""
    conc_df = compute_concentration_index(returns_df)
    if conc_df.empty:
        return {"dates": [], "market": [], "concentration": [], "correlation": []}

    market_close = market_close.sort_index()
    common = conc_df.index.intersection(market_close.index)
    conc_aligned = conc_df.loc[common, "index_value"]
    market_aligned = market_close.loc[common]

    corr = (
        market_aligned.pct_change()
        .rolling(CORR_WINDOW)
        .corr(conc_aligned.pct_change())
    )

    return {
        "dates": [d.strftime("%Y-%m-%d") for d in common],
        "market": market_aligned.tolist(),
        "concentration": conc_aligned.tolist(),
        "correlation": [None if np.isnan(v) else round(v, 4) for v in corr.tolist()],
    }
