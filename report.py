"""이익률·증분이익률·주가 비교 HTML 리포트 생성.

주가와 이익률은 스케일이 달라 한 축에 못 얹으므로(듀얼축 금지),
같은 분기 x축을 공유하는 위아래 두 패널로 정렬한다:

- 위 패널: 주가 (단일 시리즈)
- 아래 패널: 전체 영업이익률 vs 증분 영업이익률 (%, 같은 축)

마우스를 올리면 두 패널을 관통하는 크로스헤어가 분기에 스냅되고,
그 분기의 주가·전체이익률·증분이익률이 툴팁 하나에 함께 뜬다.
차트 아래에는 같은 데이터의 전체 테이블을 둔다(접근성 겸 원본 확인용).
"""

from __future__ import annotations

import html
import json

from incremental_margin import Analysis, price_change_pct


def _fmt_num(value, digits=1, suffix=""):
    return "–" if value is None else f"{value:,.{digits}f}{suffix}"


def _kpi_tile(label, value, delta_html=""):
    return (
        '<div class="tile">'
        f'<div class="tile-label">{html.escape(label)}</div>'
        f'<div class="tile-value">{html.escape(value)}</div>'
        f"{delta_html}"
        "</div>"
    )


def _delta_html(delta, suffix="%p", up_is_good=True):
    if delta is None:
        return ""
    good = (delta >= 0) == up_is_good
    cls = "delta-good" if good else "delta-bad"
    return f'<div class="tile-delta {cls}">{delta:+,.1f}{suffix} vs 직전 분기</div>'


def _build_kpis(analysis: Analysis) -> str:
    quarters = analysis.quarters
    latest, prev = quarters[-1], quarters[-2]
    rows = analysis.rows

    tiles = []
    m_delta = None
    if latest.operating_margin is not None and prev.operating_margin is not None:
        m_delta = latest.operating_margin - prev.operating_margin
    tiles.append(
        _kpi_tile(
            "전체 영업이익률",
            _fmt_num(latest.operating_margin, suffix="%"),
            _delta_html(m_delta),
        )
    )

    inc_now = rows[-1].incremental_margin
    inc_prev = rows[-2].incremental_margin if len(rows) >= 2 else None
    inc_delta = (
        inc_now - inc_prev if inc_now is not None and inc_prev is not None else None
    )
    tiles.append(
        _kpi_tile(
            "증분 영업이익률",
            _fmt_num(inc_now, suffix="%"),
            _delta_html(inc_delta),
        )
    )

    gap = analysis.margin_gap
    tiles.append(
        _kpi_tile(
            "증분−전체 격차",
            _fmt_num(gap, suffix="%p"),
        )
    )

    tiles.append(
        _kpi_tile(
            "손익분기 매출 추정",
            _fmt_num(analysis.break_even_revenue),
        )
    )

    if any(q.price is not None for q in quarters):
        chg = price_change_pct(prev, latest)
        tiles.append(
            _kpi_tile(
                "주가",
                _fmt_num(latest.price, digits=0),
                _delta_html(chg, suffix="%"),
            )
        )
    return "".join(tiles)


def _build_table(analysis: Analysis) -> str:
    has_price = any(q.price is not None for q in analysis.quarters)
    heads = ["분기", "매출", "영업이익", "전체이익률", "Δ매출", "Δ영업이익", "증분이익률"]
    if has_price:
        heads += ["주가", "주가등락"]
    thead = "".join(
        f"<th{' class=num' if i else ''}>{html.escape(h)}</th>"
        for i, h in enumerate(heads)
    )

    body_rows = []

    def row(q, d_rev=None, d_op=None, inc=None, chg=None):
        cells = [
            f"<td>{html.escape(q.label)}</td>",
            f"<td class=num>{_fmt_num(q.revenue)}</td>",
            f"<td class=num>{_fmt_num(q.operating_profit)}</td>",
            f"<td class=num>{_fmt_num(q.operating_margin, suffix='%')}</td>",
            f"<td class=num>{'–' if d_rev is None else f'{d_rev:+,.1f}'}</td>",
            f"<td class=num>{'–' if d_op is None else f'{d_op:+,.1f}'}</td>",
            f"<td class=num>{_fmt_num(inc, suffix='%')}</td>",
        ]
        if has_price:
            cells.append(f"<td class=num>{_fmt_num(q.price, digits=0)}</td>")
            cells.append(
                f"<td class=num>{'–' if chg is None else f'{chg:+.1f}%'}</td>"
            )
        body_rows.append("<tr>" + "".join(cells) + "</tr>")

    row(analysis.quarters[0])
    for r in analysis.rows:
        row(
            r.curr,
            r.delta_revenue,
            r.delta_profit,
            r.incremental_margin,
            price_change_pct(r.prev, r.curr),
        )
    return (
        '<div class="table-wrap"><table>'
        f"<thead><tr>{thead}</tr></thead><tbody>{''.join(body_rows)}</tbody>"
        "</table></div>"
    )


def render_html(analysis: Analysis, title: str = "증분 영업이익률 리포트") -> str:
    quarters = analysis.quarters
    has_price = any(q.price is not None for q in quarters)

    data = {
        "labels": [q.label for q in quarters],
        "price": [q.price for q in quarters],
        "overall": [q.operating_margin for q in quarters],
        "incremental": [None]
        + [
            r.incremental_margin if r.delta_revenue != 0 else None
            for r in analysis.rows
        ],
        "hasPrice": has_price,
    }

    signals = "".join(
        f"<li>{html.escape(s)}</li>" for s in analysis.signals
    ) or "<li>특이 시그널 없음</li>"

    price_panel = (
        '<section class="panel">'
        "<h2>주가</h2>"
        '<div class="chart" id="price-chart"></div>'
        "</section>"
        if has_price
        else ""
    )

    page = HTML_TEMPLATE
    page = page.replace("__TITLE__", html.escape(title))
    page = page.replace("__TREND__", html.escape(analysis.trend.value))
    page = page.replace("__KPIS__", _build_kpis(analysis))
    page = page.replace("__PRICE_PANEL__", price_panel)
    page = page.replace("__SIGNALS__", signals)
    page = page.replace("__TABLE__", _build_table(analysis))
    page = page.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    return page


HTML_TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root {
  --surface-1: #fcfcfb;
  --page: #f9f9f7;
  --text-primary: #0b0b0b;
  --text-secondary: #52514e;
  --text-muted: #898781;
  --grid: #e1e0d9;
  --baseline: #c3c2b7;
  --border: rgba(11,11,11,0.10);
  --series-price: #2a78d6;   /* 주가 */
  --series-overall: #1baf7a; /* 전체 이익률 */
  --series-inc: #eda100;     /* 증분 이익률 */
  --delta-good: #006300;
  --delta-bad: #d03b3b;
}
@media (prefers-color-scheme: dark) {
  :root {
    --surface-1: #1a1a19;
    --page: #0d0d0d;
    --text-primary: #ffffff;
    --text-secondary: #c3c2b7;
    --text-muted: #898781;
    --grid: #2c2c2a;
    --baseline: #383835;
    --border: rgba(255,255,255,0.10);
    --series-price: #3987e5;
    --series-overall: #199e70;
    --series-inc: #c98500;
    --delta-good: #0ca30c;
    --delta-bad: #e66767;
  }
}
:root[data-theme="light"] {
  --surface-1: #fcfcfb; --page: #f9f9f7;
  --text-primary: #0b0b0b; --text-secondary: #52514e; --text-muted: #898781;
  --grid: #e1e0d9; --baseline: #c3c2b7; --border: rgba(11,11,11,0.10);
  --series-price: #2a78d6; --series-overall: #1baf7a; --series-inc: #eda100;
  --delta-good: #006300; --delta-bad: #d03b3b;
}
:root[data-theme="dark"] {
  --surface-1: #1a1a19; --page: #0d0d0d;
  --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #898781;
  --grid: #2c2c2a; --baseline: #383835; --border: rgba(255,255,255,0.10);
  --series-price: #3987e5; --series-overall: #199e70; --series-inc: #c98500;
  --delta-good: #0ca30c; --delta-bad: #e66767;
}
* { box-sizing: border-box; margin: 0; }
body {
  background: var(--page);
  color: var(--text-primary);
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  padding: 24px 16px 48px;
}
.wrap { max-width: 960px; margin: 0 auto; display: grid; gap: 16px; }
header h1 { font-size: 20px; font-weight: 650; }
header p { color: var(--text-secondary); font-size: 13px; margin-top: 4px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
.tile {
  background: var(--surface-1); border: 1px solid var(--border);
  border-radius: 10px; padding: 12px 14px;
}
.tile-label { font-size: 12px; color: var(--text-secondary); }
.tile-value { font-size: 26px; font-weight: 600; margin-top: 2px; }
.tile-delta { font-size: 12px; margin-top: 2px; }
.delta-good { color: var(--delta-good); }
.delta-bad { color: var(--delta-bad); }
.panel {
  background: var(--surface-1); border: 1px solid var(--border);
  border-radius: 10px; padding: 16px;
}
.panel h2 { font-size: 14px; font-weight: 600; margin-bottom: 4px; }
.legend { display: flex; gap: 16px; font-size: 12px; color: var(--text-secondary); margin: 4px 0 8px; }
.legend .key { display: inline-block; width: 14px; height: 3px; border-radius: 2px; vertical-align: middle; margin-right: 6px; }
.chart svg { display: block; width: 100%; height: auto; }
#charts { outline: none; }
#charts:focus-visible { box-shadow: 0 0 0 2px var(--series-price); border-radius: 10px; }
.signals { background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; padding: 16px; }
.signals h2 { font-size: 14px; font-weight: 600; margin-bottom: 8px; }
.signals ul { padding-left: 18px; display: grid; gap: 6px; }
.signals li { font-size: 13px; color: var(--text-secondary); line-height: 1.5; }
.table-wrap { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { padding: 7px 10px; white-space: nowrap; }
th { color: var(--text-secondary); font-weight: 600; text-align: left; border-bottom: 1px solid var(--baseline); }
th.num, td.num { text-align: right; font-variant-numeric: tabular-nums; }
tbody tr { border-bottom: 1px solid var(--grid); }
tbody tr:last-child { border-bottom: none; }
#tooltip {
  position: fixed; pointer-events: none; z-index: 10; display: none;
  background: var(--surface-1); border: 1px solid var(--border);
  border-radius: 8px; padding: 8px 10px; font-size: 12px;
  box-shadow: 0 4px 14px rgba(0,0,0,0.14); min-width: 150px;
}
#tooltip .tt-title { color: var(--text-muted); margin-bottom: 4px; }
#tooltip .tt-row { display: flex; align-items: center; gap: 6px; margin-top: 3px; }
#tooltip .tt-key { width: 12px; height: 3px; border-radius: 2px; flex: none; }
#tooltip .tt-val { font-weight: 650; font-variant-numeric: tabular-nums; }
#tooltip .tt-name { color: var(--text-secondary); }
footer { font-size: 12px; color: var(--text-muted); line-height: 1.6; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>__TITLE__</h1>
    <p>증분 이익률 추세: <strong>__TREND__</strong> · 전체 이익률의 기울기는 (증분 − 전체) 격차에 비례 — 격차가 0에 닿는 분기가 전체 이익률의 고점</p>
  </header>

  <div class="tiles">__KPIS__</div>

  <div id="charts" tabindex="0" aria-label="분기별 주가·이익률 차트. 좌우 화살표로 분기 이동">
    __PRICE_PANEL__
    <section class="panel" style="margin-top:12px">
      <h2>영업이익률 vs 증분 영업이익률</h2>
      <div class="legend">
        <span><span class="key" style="background:var(--series-overall)"></span>전체 영업이익률</span>
        <span><span class="key" style="background:var(--series-inc)"></span>증분 영업이익률</span>
      </div>
      <div class="chart" id="margin-chart"></div>
    </section>
  </div>

  <section class="signals">
    <h2>시그널</h2>
    <ul>__SIGNALS__</ul>
  </section>

  <section class="panel">
    <h2>분기 실적표</h2>
    __TABLE__
  </section>

  <footer>
    당기순이익이 아니라 영업이익 기준. 증분 영업이익률 = Δ영업이익 ÷ Δ매출 —
    새로 붙는 매출이 몇 %짜리인지를 본다. 매출 변화가 0인 분기의 증분값은 표시하지 않음.
  </footer>
</div>

<div id="tooltip" role="status"></div>

<script>
const DATA = __DATA__;
const NS = "http://www.w3.org/2000/svg";
const W = 920, PAD = { l: 58, r: 96, t: 16, b: 30 };

function el(name, attrs, parent) {
  const node = document.createElementNS(NS, name);
  for (const k in attrs) node.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(node);
  return node;
}

function niceTicks(min, max, count) {
  const span = max - min || 1;
  const step0 = span / Math.max(1, count);
  const mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => span / s <= count) || 10 * mag;
  const ticks = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step)
    ticks.push((Math.round(v * 1e6) / 1e6) || 0); // -0 → 0
  return ticks;
}

function fmt(v, digits) {
  return v == null ? "–" : v.toLocaleString("ko-KR",
    { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

// 패널 하나를 그린다. series: [{ values, colorVar, name, digits, suffix }]
function drawPanel(containerId, series, opts) {
  const H = opts.height;
  const n = DATA.labels.length;
  const all = series.flatMap(s => s.values).filter(v => v != null);
  let lo = Math.min(...all), hi = Math.max(...all);
  if (opts.includeZero) { lo = Math.min(lo, 0); hi = Math.max(hi, 0); }
  const padY = (hi - lo || 1) * 0.08;
  lo -= padY; hi += padY;
  const ticks = niceTicks(lo, hi, 4);

  const x = i => PAD.l + (n === 1 ? 0 : (W - PAD.l - PAD.r) * i / (n - 1));
  const y = v => PAD.t + (H - PAD.t - PAD.b) * (1 - (v - lo) / (hi - lo));

  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img" });
  document.getElementById(containerId).appendChild(svg);

  // 그리드 + y축 눈금
  for (const t of ticks) {
    el("line", { x1: PAD.l, x2: W - PAD.r, y1: y(t), y2: y(t),
      stroke: t === 0 ? "var(--baseline)" : "var(--grid)", "stroke-width": 1 }, svg);
    const lbl = el("text", { x: PAD.l - 8, y: y(t) + 4, "text-anchor": "end",
      "font-size": 11, fill: "var(--text-muted)",
      style: "font-variant-numeric: tabular-nums" }, svg);
    lbl.textContent = fmt(t, 0) + (opts.axisSuffix || "");
  }
  // x축 라벨
  DATA.labels.forEach((label, i) => {
    const lbl = el("text", { x: x(i), y: H - 8, "text-anchor": "middle",
      "font-size": 11, fill: "var(--text-muted)" }, svg);
    lbl.textContent = label;
  });

  // 크로스헤어 (분기에 스냅, 기본 숨김)
  const cross = el("line", { y1: PAD.t, y2: H - PAD.b,
    stroke: "var(--baseline)", "stroke-width": 1, visibility: "hidden" }, svg);

  // 시리즈 라인 + 마커 (null은 선을 끊는다)
  const endLabels = [];
  for (const s of series) {
    let d = "", pen = false;
    s.values.forEach((v, i) => {
      if (v == null) { pen = false; return; }
      d += (pen ? "L" : "M") + x(i).toFixed(1) + " " + y(v).toFixed(1);
      pen = true;
    });
    el("path", { d, fill: "none", stroke: `var(${s.colorVar})`,
      "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }, svg);
    s.values.forEach((v, i) => {
      if (v == null) return;
      el("circle", { cx: x(i), cy: y(v), r: 4, fill: `var(${s.colorVar})`,
        stroke: "var(--surface-1)", "stroke-width": 2 }, svg);
    });
    for (let i = n - 1; i >= 0; i--) {
      if (s.values[i] != null) {
        endLabels.push({ y: y(s.values[i]),
          text: fmt(s.values[i], s.digits) + (s.suffix || ""), colorVar: s.colorVar });
        break;
      }
    }
  }
  // 끝점 직접 라벨 — 겹치면(16px 미만) 마지막 시리즈 것만 남긴다(범례+툴팁이 보완)
  const sorted = endLabels.slice().sort((a, b) => a.y - b.y);
  const collide = sorted.some((l, i) => i && l.y - sorted[i - 1].y < 16);
  (collide ? endLabels.slice(-1) : endLabels).forEach(l => {
    const t = el("text", { x: W - PAD.r + 10, y: l.y + 4, "font-size": 12,
      "font-weight": 600, fill: "var(--text-primary)",
      style: "font-variant-numeric: tabular-nums" }, svg);
    t.textContent = l.text;
  });

  return { svg, x, cross, n };
}

const panels = [];
if (DATA.hasPrice) {
  panels.push(drawPanel("price-chart", [
    { values: DATA.price, colorVar: "--series-price", name: "주가", digits: 0 },
  ], { height: 230 }));
}
panels.push(drawPanel("margin-chart", [
  { values: DATA.overall, colorVar: "--series-overall", name: "전체 영업이익률", digits: 1, suffix: "%" },
  { values: DATA.incremental, colorVar: "--series-inc", name: "증분 영업이익률", digits: 1, suffix: "%" },
], { height: 260, includeZero: true, axisSuffix: "%" }));

// ---- 공유 크로스헤어 + 툴팁 -------------------------------------------
const tooltip = document.getElementById("tooltip");
const chartsBox = document.getElementById("charts");

const TT_SERIES = [];
if (DATA.hasPrice) TT_SERIES.push({ values: DATA.price, colorVar: "--series-price", name: "주가", digits: 0 });
TT_SERIES.push(
  { values: DATA.overall, colorVar: "--series-overall", name: "전체 이익률", digits: 1, suffix: "%" },
  { values: DATA.incremental, colorVar: "--series-inc", name: "증분 이익률", digits: 1, suffix: "%" });

function showIndex(i, clientX, clientY) {
  for (const p of panels) {
    const px = p.x(i);
    p.cross.setAttribute("x1", px);
    p.cross.setAttribute("x2", px);
    p.cross.setAttribute("visibility", "visible");
  }
  tooltip.textContent = "";
  const title = document.createElement("div");
  title.className = "tt-title";
  title.textContent = DATA.labels[i];
  tooltip.appendChild(title);
  for (const s of TT_SERIES) {
    const row = document.createElement("div");
    row.className = "tt-row";
    const key = document.createElement("span");
    key.className = "tt-key";
    key.style.background = `var(${s.colorVar})`;
    const val = document.createElement("span");
    val.className = "tt-val";
    val.textContent = fmt(s.values[i], s.digits) + (s.suffix || "");
    const name = document.createElement("span");
    name.className = "tt-name";
    name.textContent = s.name;
    row.append(key, val, name);
    tooltip.appendChild(row);
  }
  tooltip.style.display = "block";
  const r = tooltip.getBoundingClientRect();
  let tx = clientX + 14, ty = clientY + 14;
  if (tx + r.width > window.innerWidth - 8) tx = clientX - r.width - 14;
  if (ty + r.height > window.innerHeight - 8) ty = clientY - r.height - 14;
  tooltip.style.left = tx + "px";
  tooltip.style.top = ty + "px";
}

function hide() {
  tooltip.style.display = "none";
  for (const p of panels) p.cross.setAttribute("visibility", "hidden");
}

let focusIndex = -1;
chartsBox.addEventListener("pointermove", e => {
  const svg = panels[0].svg;
  const rect = svg.getBoundingClientRect();
  const relX = (e.clientX - rect.left) / rect.width * W;
  const n = DATA.labels.length;
  const step = (W - PAD.l - PAD.r) / Math.max(1, n - 1);
  const i = Math.max(0, Math.min(n - 1, Math.round((relX - PAD.l) / step)));
  showIndex(i, e.clientX, e.clientY);
});
chartsBox.addEventListener("pointerleave", hide);
chartsBox.addEventListener("keydown", e => {
  const n = DATA.labels.length;
  if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
    e.preventDefault();
    if (focusIndex < 0) focusIndex = n - 1;
    else focusIndex = e.key === "ArrowRight"
      ? Math.min(n - 1, focusIndex + 1) : Math.max(0, focusIndex - 1);
    const rect = chartsBox.getBoundingClientRect();
    showIndex(focusIndex, rect.left + 80, rect.top + 60);
  } else if (e.key === "Escape") { focusIndex = -1; hide(); }
});
chartsBox.addEventListener("blur", () => { focusIndex = -1; hide(); });
</script>
</body>
</html>
"""
