"""순수 Python으로 구현한 업종쏠림지수 계산 (numpy/pandas 없음)."""
import statistics as _stat

TOP_N = 5
CORR_WINDOW = 30


def _pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def compute_concentration(returns_by_date: dict) -> dict:
    """
    returns_by_date: {date_obj: {sector_code: pct_float}}
    반환: {date_obj: {"long_short": float, "index_value": float}}
    """
    results = {}
    prev_idx = 1000.0
    first = True

    for dt in sorted(returns_by_date.keys()):
        rates = {k: v for k, v in returns_by_date[dt].items()
                 if v is not None and isinstance(v, (int, float))}
        if len(rates) < TOP_N + 1:
            continue
        sorted_vals = sorted(rates.values(), reverse=True)
        top = sorted_vals[:TOP_N]
        bottom = sorted_vals[TOP_N:]
        long_short = _stat.mean(top) - _stat.mean(bottom)

        if first:
            idx_val = 1000.0
            first = False
        else:
            idx_val = prev_idx * (1 + long_short / 100)

        results[dt] = {"long_short": long_short, "index_value": idx_val}
        prev_idx = idx_val

    return results


def build_chart_data(market_close: dict, returns_by_date: dict) -> dict:
    """
    market_close: {date_obj: float}
    returns_by_date: {date_obj: {sector: pct}}
    """
    conc = compute_concentration(returns_by_date)
    if not conc:
        return {"dates": [], "market": [], "concentration": [], "correlation": []}

    common = sorted(set(conc.keys()) & set(market_close.keys()))
    if not common:
        return {"dates": [], "market": [], "concentration": [], "correlation": []}

    mkt = [float(market_close[d]) for d in common]
    idx = [conc[d]["index_value"] for d in common]

    # 일별 수익률
    mkt_r = [None] + [
        (mkt[i] / mkt[i - 1] - 1) * 100 if mkt[i - 1] else None
        for i in range(1, len(mkt))
    ]
    idx_r = [None] + [
        (idx[i] / idx[i - 1] - 1) * 100 if idx[i - 1] else None
        for i in range(1, len(idx))
    ]

    # 롤링 상관계수
    corr = []
    for i in range(len(common)):
        if i < CORR_WINDOW - 1:
            corr.append(None)
            continue
        xs = [v for v in mkt_r[i - CORR_WINDOW + 1: i + 1] if v is not None]
        ys = [v for v in idx_r[i - CORR_WINDOW + 1: i + 1] if v is not None]
        if len(xs) < 5 or len(xs) != len(ys):
            corr.append(None)
        else:
            c = _pearson(xs, ys)
            corr.append(round(c, 4) if c is not None else None)

    def fmt_date(d):
        return d.isoformat() if hasattr(d, "isoformat") else str(d)

    return {
        "dates": [fmt_date(d) for d in common],
        "market": mkt,
        "concentration": idx,
        "correlation": corr,
    }
