"""증분 영업이익률(incremental operating margin) 분석기.

전체 영업이익률("10% → 20%로 개선") 대신, 늘어난 매출과 늘어난
영업이익만 따로 떼어내서(증분끼리) 계산한다.

    증분 영업이익률 = (이번 분기 영업이익 − 이전 분기 영업이익)
                    ÷ (이번 분기 매출 − 이전 분기 매출)

예: 매출 100조/영업이익 10조 → 매출 150조/영업이익 30조 이면
전체 이익률은 10% → 20%지만, 증분 이익률은 20 ÷ 50 = 40%.
기존 매출은 10%짜리, 새로 붙는 매출은 40%짜리라는 뜻("10, 40, 40").

왜 이렇게 보는가: 전체 이익률 평균은 둔하게 움직여서 꺾이는 시점을
늦게 알려준다. 증분 이익률이 정체되면 가격 인상(P)이 실적에 다
반영됐다는 신호이고, 이때부터는 물량(Q)이 늘어야만 성장이 가능하다.

함께 계산하는 것:
- 손익분기 매출("빵원 되는 자리"): 영업이익 = 0 이 되는 매출 수준.
  분기 실적들을 (매출, 영업이익) 직선으로 적합해서 추정한다.
  판관비(고정비)가 줄면 이 자리가 낮아지고, 플러스로 돌아서는
  시점부터 주가가 크게 오른다.
- 당기순이익은 쓰지 않는다. 주식평가이익·전환사채 평가 등이 섞여서
  의미가 없다. 오직 매출과 영업이익만 입력받는다.

데이터는 분기 실적표(매출, 영업이익)만 있으면 된다 — 4개 분기면 충분.
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Sequence

# 추세 판정 임계값(퍼센트포인트). 직전 대비 증분 이익률 변화가
# 이 범위 안이면 "정체"로 본다.
TREND_THRESHOLD_PP = 2.0

# 급등 판정 임계값(퍼센트포인트). 증분 이익률이 직전보다 이만큼
# 이상 튀면 사업보고서에서 원인을 찾아보라는 시그널을 낸다.
SPIKE_THRESHOLD_PP = 15.0


class Trend(Enum):
    RISING = "상승"
    PLATEAU = "정체"
    FALLING = "하락"
    UNKNOWN = "판단불가"


@dataclass(frozen=True)
class Quarter:
    """분기 실적 한 줄. 금액 단위는 자유(조원, 억원, ...) — 일관되기만 하면 된다.

    price는 그 분기 시점의 주가(예: 분기말 종가). 선택 입력이며,
    있으면 이익률-주가 비교 테이블·차트에 함께 표시된다.
    """

    label: str
    revenue: float
    operating_profit: float
    price: Optional[float] = None

    @property
    def operating_margin(self) -> Optional[float]:
        """전체 영업이익률(%). 매출이 0이면 None."""
        if self.revenue == 0:
            return None
        return self.operating_profit / self.revenue * 100


@dataclass(frozen=True)
class IncrementalRow:
    """연속된 두 분기 사이의 증분 계산 결과."""

    prev: Quarter
    curr: Quarter
    delta_revenue: float
    delta_profit: float
    incremental_margin: Optional[float]  # %, 매출 변화가 0이면 None


@dataclass
class Analysis:
    quarters: Sequence[Quarter]
    rows: Sequence[IncrementalRow]
    trend: Trend
    break_even_revenue: Optional[float]
    # 최신 분기의 (증분 이익률 − 전체 이익률) 격차(%p).
    # Δm = (ΔR/R_new) × (m_inc − m_old) 이므로, 이 격차가 양수인 동안
    # 전체 이익률은 오르고, 0에 닿는 순간이 전체 이익률의 고점이다.
    margin_gap: Optional[float] = None
    signals: list[str] = field(default_factory=list)


def incremental_rows(quarters: Sequence[Quarter]) -> list[IncrementalRow]:
    rows = []
    for prev, curr in zip(quarters, quarters[1:]):
        d_rev = curr.revenue - prev.revenue
        d_op = curr.operating_profit - prev.operating_profit
        margin = (d_op / d_rev * 100) if d_rev != 0 else None
        rows.append(IncrementalRow(prev, curr, d_rev, d_op, margin))
    return rows


def classify_trend(rows: Sequence[IncrementalRow]) -> Trend:
    """가장 최근 두 증분 이익률을 비교해 추세를 판정한다.

    매출이 줄어든 구간(delta_revenue < 0)의 증분 이익률은 부호가
    뒤집혀 의미가 다르므로 추세 비교에서 제외한다.
    """
    margins = [
        r.incremental_margin
        for r in rows
        if r.incremental_margin is not None and r.delta_revenue > 0
    ]
    if len(margins) < 2:
        return Trend.UNKNOWN
    diff = margins[-1] - margins[-2]
    if diff > TREND_THRESHOLD_PP:
        return Trend.RISING
    if diff < -TREND_THRESHOLD_PP:
        return Trend.FALLING
    return Trend.PLATEAU


def break_even_revenue(quarters: Sequence[Quarter]) -> Optional[float]:
    """손익분기 매출("빵원 되는 자리") 추정.

    영업이익 ≈ 증분이익률 × 매출 − 고정비(판관비) 라는 선형 관계를
    가정하고 (매출, 영업이익) 점들을 최소제곱 직선으로 적합한 뒤,
    영업이익이 0이 되는 매출을 돌려준다. 기울기가 0 이하이거나
    매출이 전부 같아 직선을 그을 수 없으면 None.
    """
    if len(quarters) < 2:
        return None
    xs = [q.revenue for q in quarters]
    ys = [q.operating_profit for q in quarters]
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx == 0:
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / sxx
    if slope <= 0:
        return None
    intercept = mean_y - slope * mean_x
    return -intercept / slope


def analyze(quarters: Sequence[Quarter]) -> Analysis:
    if len(quarters) < 2:
        raise ValueError("최소 2개 분기 실적이 필요합니다 (4개 분기 권장).")

    rows = incremental_rows(quarters)
    trend = classify_trend(rows)
    be = break_even_revenue(quarters)
    signals: list[str] = []

    if trend is Trend.RISING:
        signals.append(
            "증분 이익률 상승 추세 — 새로 붙는 매출의 수익성이 계속 좋아지는 중. "
            "이런 회사가 이익 성장이 폭발하는 회사."
        )
    elif trend is Trend.PLATEAU:
        signals.append(
            "증분 이익률 정체 — 가격 인상(P)이 실적에 다 반영됐다는 신호. "
            "이제부터는 물량(Q)이 늘어야만 성장 가능. 가동률·출하량 확인 필요."
        )
    elif trend is Trend.FALLING:
        signals.append(
            "증분 이익률 하락 — 영업이익률 추세가 꺾이는 시점은 항상 위험. "
            "단, 사이클이 긴 업종은 꺾여도 주가가 버틸 수 있음."
        )

    # 급등 감지: 직전 증분 이익률 대비 크게 튀면 사업보고서에서 원인 확인.
    valid = [
        r.incremental_margin
        for r in rows
        if r.incremental_margin is not None and r.delta_revenue > 0
    ]
    if len(valid) >= 2 and valid[-1] - valid[-2] >= SPIKE_THRESHOLD_PP:
        signals.append(
            "증분 이익률 급등 — 사업보고서에서 원인을 찾을 것. "
            "신사업·독점 등 시장이 좋아할 만한 이유면 강한 매수 시그널."
        )

    # 흑자 전환 감지: 플러스로 돌아서는 시점부터 주가가 크게 오른다.
    if (
        quarters[-2].operating_profit <= 0 < quarters[-1].operating_profit
    ):
        signals.append(
            "영업이익 흑자 전환 — 손익분기점을 막 넘어선 자리. "
            "판관비 축소(구조조정)로 분기점이 낮아진 경우라면 특히 주목."
        )

    # 증분 − 전체 이익률 격차. 전체 이익률의 기울기는 이 격차에
    # 비례하므로(Δm ∝ m_inc − m), 격차가 좁혀지는 것 자체가
    # 전체 이익률 상승 둔화의 선행 신호다.
    margin_gap = None
    last_row = rows[-1]
    latest_margin = quarters[-1].operating_margin
    if (
        last_row.incremental_margin is not None
        and last_row.delta_revenue > 0
        and latest_margin is not None
    ):
        margin_gap = last_row.incremental_margin - latest_margin
        if margin_gap > 0.5:
            signals.append(
                f"증분−전체 이익률 격차 +{margin_gap:.1f}%p — 격차가 양수인 동안 "
                "전체 이익률은 계속 오름. 이 격차가 0에 닿는 순간이 전체 이익률 고점."
            )
        elif margin_gap < -0.5:
            signals.append(
                f"증분−전체 이익률 격차 {margin_gap:.1f}%p — 증분이 평균 밑으로 "
                "내려왔으므로 전체 영업이익률은 하락 국면."
            )
        else:
            signals.append(
                f"증분−전체 이익률 격차 {margin_gap:+.1f}%p — 증분이 평균과 "
                "만나는 자리, 즉 전체 영업이익률의 고점 부근."
            )

    if be is not None:
        latest = quarters[-1]
        if latest.revenue > be:
            headroom = (latest.revenue - be) / latest.revenue * 100
            signals.append(
                f"손익분기 매출(빵원 자리) 추정 ≈ {be:,.1f} — "
                f"현재 매출이 분기점보다 {headroom:.0f}% 위에 있음."
            )
        else:
            signals.append(
                f"손익분기 매출(빵원 자리) 추정 ≈ {be:,.1f} — "
                f"현재 매출이 아직 분기점 아래. 판관비(고정비) 축소 여부 확인."
            )

    return Analysis(quarters, rows, trend, be, margin_gap, signals)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def load_csv(path: str) -> list[Quarter]:
    """CSV 로드. 헤더: quarter,revenue,operating_profit (한글 헤더도 허용)."""
    aliases = {
        "quarter": "quarter", "분기": "quarter",
        "revenue": "revenue", "매출": "revenue", "매출액": "revenue",
        "operating_profit": "operating_profit", "영업이익": "operating_profit",
        "price": "price", "주가": "price", "종가": "price", "close": "price",
    }
    quarters = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"{path}: 헤더가 없습니다.")
        colmap = {}
        for name in reader.fieldnames:
            key = aliases.get(name.strip().lower(), aliases.get(name.strip()))
            if key:
                colmap[key] = name
        missing = {"quarter", "revenue", "operating_profit"} - set(colmap)
        if missing:
            raise ValueError(
                f"{path}: 필요한 열이 없습니다: {', '.join(sorted(missing))} "
                "(헤더는 quarter,revenue,operating_profit 또는 분기,매출,영업이익)"
            )
        for line in reader:
            price = None
            if "price" in colmap:
                raw = (line[colmap["price"]] or "").replace(",", "").strip()
                price = float(raw) if raw else None
            quarters.append(
                Quarter(
                    label=line[colmap["quarter"]].strip(),
                    revenue=float(line[colmap["revenue"]].replace(",", "")),
                    operating_profit=float(
                        line[colmap["operating_profit"]].replace(",", "")
                    ),
                    price=price,
                )
            )
    return quarters


def _fmt(value: Optional[float], suffix: str = "") -> str:
    return "-" if value is None else f"{value:,.1f}{suffix}"


def price_change_pct(prev: Quarter, curr: Quarter) -> Optional[float]:
    """직전 분기 대비 주가 등락률(%). 주가가 없으면 None."""
    if prev.price is None or curr.price is None or prev.price == 0:
        return None
    return (curr.price - prev.price) / prev.price * 100


def render(analysis: Analysis) -> str:
    has_price = any(q.price is not None for q in analysis.quarters)
    lines = []
    header = (
        f"{'분기':<8} {'매출':>12} {'영업이익':>12} {'전체이익률':>10} "
        f"{'Δ매출':>12} {'Δ영업이익':>12} {'증분이익률':>10}"
    )
    if has_price:
        header += f" {'주가':>12} {'주가등락':>8}"
    lines.append(header)
    lines.append("-" * len(header))

    def price_cols(q: Quarter, change: Optional[float]) -> str:
        if not has_price:
            return ""
        price = "-" if q.price is None else f"{q.price:,.0f}"
        chg = "-" if change is None else f"{change:+.1f}%"
        return f" {price:>13} {chg:>10}"

    first = analysis.quarters[0]
    lines.append(
        f"{first.label:<8} {first.revenue:>14,.1f} {first.operating_profit:>14,.1f} "
        f"{_fmt(first.operating_margin, '%'):>12} {'-':>13} {'-':>15} {'-':>13}"
        + price_cols(first, None)
    )
    for row in analysis.rows:
        q = row.curr
        lines.append(
            f"{q.label:<8} {q.revenue:>14,.1f} {q.operating_profit:>14,.1f} "
            f"{_fmt(q.operating_margin, '%'):>12} {row.delta_revenue:>+13,.1f} "
            f"{row.delta_profit:>+15,.1f} {_fmt(row.incremental_margin, '%'):>13}"
            + price_cols(q, price_change_pct(row.prev, q))
        )

    lines.append("")
    lines.append(f"증분 이익률 추세: {analysis.trend.value}")
    for signal in analysis.signals:
        lines.append(f"  • {signal}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    html_out = None
    if "--html" in argv:
        i = argv.index("--html")
        try:
            html_out = argv[i + 1]
        except IndexError:
            print("--html 뒤에 출력 파일 경로를 지정하세요.", file=sys.stderr)
            return 2
        del argv[i : i + 2]
    if len(argv) != 1 or argv[0] in ("-h", "--help"):
        print(
            "사용법: python incremental_margin.py <분기실적.csv> [--html 리포트.html]\n"
            "CSV 헤더: quarter,revenue,operating_profit[,price]\n"
            "          (분기,매출,영업이익[,주가]도 가능)\n"
            "--html: 이익률·증분이익률·주가를 비교하는 테이블+차트 리포트 생성\n"
            "※ 당기순이익이 아니라 영업이익을 넣을 것.",
            file=sys.stderr,
        )
        return 2
    quarters = load_csv(argv[0])
    analysis = analyze(quarters)
    print(render(analysis))
    if html_out:
        from report import render_html

        with open(html_out, "w", encoding="utf-8") as f:
            f.write(render_html(analysis))
        print(f"\nHTML 리포트 생성: {html_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
