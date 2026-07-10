"""이익률·증분이익률·주가 비교 인터랙티브 HTML 리포트 생성.

리포트는 자체 완결형 단일 HTML이며, 분기 실적표가 그 자리에서 편집된다:
행 추가/삭제, 매출·영업이익·주가 수정, 컨센서스(E) 체크 — 바꾸는 즉시
차트·KPI·시그널이 재계산된다. 수정 내용은 브라우저 localStorage에
자동 저장된다(제목 기준 키). 따라서 계산 로직은 파이썬(터미널 출력용,
incremental_margin.py)과 템플릿 안의 JS에 같은 규칙으로 두 벌 존재한다 —
임계값이나 판정 규칙을 바꿀 때는 양쪽을 함께 고칠 것.

차트 구성:
- 주가와 이익률은 스케일이 달라 한 축에 얹지 않는다(듀얼축 금지).
  같은 분기 x축을 공유하는 위(주가)/아래(이익률) 두 패널로 정렬.
- 대신 "주가 겹쳐보기" 토글이 이익률 패널 위에 주가를 min-max 상대
  스케일로 겹쳐 그린다 — 축 없이 모양(꺾이는 시점) 비교 전용이고,
  정확한 값은 툴팁과 주가 패널이 담당한다.
- 컨센서스(E) 분기는 점선·빈 마커·배경 워시로 구분되며 추세·KPI·
  손익분기 판정에서 제외된다.
"""

from __future__ import annotations

import html
import json

from incremental_margin import Analysis


def render_html(analysis: Analysis, title: str = "증분 영업이익률 리포트") -> str:
    data = {
        "title": title,
        "quarters": [
            {
                "label": q.label,
                "revenue": q.revenue,
                "op": q.operating_profit,
                "price": q.price,
                "estimate": q.estimate,
            }
            for q in analysis.quarters
        ],
    }
    page = HTML_TEMPLATE
    page = page.replace("__TITLE__", html.escape(title))
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
    --surface-1: #1a1a19; --page: #0d0d0d;
    --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #898781;
    --grid: #2c2c2a; --baseline: #383835; --border: rgba(255,255,255,0.10);
    --series-price: #3987e5; --series-overall: #199e70; --series-inc: #c98500;
    --delta-good: #0ca30c; --delta-bad: #e66767;
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
  background: var(--page); color: var(--text-primary);
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  padding: 24px 16px 48px;
}
.wrap { max-width: 980px; margin: 0 auto; display: grid; gap: 16px; }
header h1 { font-size: 20px; font-weight: 650; }
header p { color: var(--text-secondary); font-size: 13px; margin-top: 4px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
.tile { background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px; }
.tile-label { font-size: 12px; color: var(--text-secondary); }
.tile-value { font-size: 26px; font-weight: 600; margin-top: 2px; }
.tile-delta { font-size: 12px; margin-top: 2px; }
.delta-good { color: var(--delta-good); }
.delta-bad { color: var(--delta-bad); }
.panel { background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; padding: 16px; }
.panel h2 { font-size: 14px; font-weight: 600; margin-bottom: 4px; }
.legend-row { display: flex; flex-wrap: wrap; align-items: center; gap: 16px; font-size: 12px; color: var(--text-secondary); margin: 4px 0 8px; }
.legend-row .key { display: inline-block; width: 14px; height: 3px; border-radius: 2px; vertical-align: middle; margin-right: 6px; }
.legend-row label { display: inline-flex; align-items: center; gap: 6px; cursor: pointer; margin-left: auto; }
.chart svg { display: block; width: 100%; height: auto; }
#charts { outline: none; }
#charts:focus-visible { box-shadow: 0 0 0 2px var(--series-price); border-radius: 10px; }
.signals h2 { font-size: 14px; font-weight: 600; margin-bottom: 8px; }
.signals ul { padding-left: 18px; display: grid; gap: 6px; }
.signals li { font-size: 13px; color: var(--text-secondary); line-height: 1.5; }
.grid-head { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.grid-head h2 { flex: 1; }
.btn {
  font: inherit; font-size: 12px; color: var(--text-primary);
  background: transparent; border: 1px solid var(--border);
  border-radius: 7px; padding: 5px 12px; cursor: pointer;
}
.btn:hover { background: var(--page); }
.table-wrap { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { padding: 6px 8px; white-space: nowrap; }
th { color: var(--text-secondary); font-weight: 600; text-align: right; border-bottom: 1px solid var(--baseline); }
th:first-child { text-align: left; }
td.num, td.derived { text-align: right; font-variant-numeric: tabular-nums; }
td.derived { color: var(--text-secondary); }
tbody tr { border-bottom: 1px solid var(--grid); }
tbody tr:last-child { border-bottom: none; }
td input[type=text] {
  font: inherit; color: inherit; background: transparent;
  border: none; border-bottom: 1px dashed transparent;
  width: 88px; text-align: right; padding: 2px 0;
  font-variant-numeric: tabular-nums;
}
td input.label-input { width: 74px; text-align: left; }
td input[type=text]:hover { border-bottom-color: var(--grid); }
td input[type=text]:focus { outline: none; border-bottom-color: var(--series-price); }
td.center { text-align: center; }
button.del {
  font: inherit; background: none; border: none; cursor: pointer;
  color: var(--text-muted); font-size: 14px; padding: 0 4px;
}
button.del:hover { color: var(--delta-bad); }
.hint { font-size: 12px; color: var(--text-muted); margin-top: 8px; }
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
    <p>증분 이익률 추세: <strong id="trend-label">-</strong> ·
       전체 이익률의 기울기는 (증분 − 전체) 격차에 비례 —
       격차가 0에 닿는 분기가 전체 이익률의 고점</p>
  </header>

  <div class="tiles" id="kpis"></div>

  <div id="charts" tabindex="0" aria-label="분기별 주가·이익률 차트. 좌우 화살표로 분기 이동">
    <section class="panel" id="price-panel" hidden>
      <h2>주가</h2>
      <div class="chart" id="price-chart"></div>
    </section>
    <section class="panel" style="margin-top:12px">
      <h2>영업이익률 vs 증분 영업이익률</h2>
      <div class="legend-row">
        <span><span class="key" style="background:var(--series-overall)"></span>전체 영업이익률</span>
        <span><span class="key" style="background:var(--series-inc)"></span>증분 영업이익률</span>
        <span id="overlay-key" hidden><span class="key" style="background:var(--series-price);opacity:.55"></span>주가 (상대 스케일)</span>
        <label id="overlay-label" hidden>
          <input type="checkbox" id="overlay-toggle" checked> 주가 겹쳐보기
        </label>
      </div>
      <div class="chart" id="margin-chart"></div>
    </section>
  </div>

  <section class="panel signals">
    <h2>시그널</h2>
    <ul id="signals"></ul>
  </section>

  <section class="panel">
    <div class="grid-head">
      <h2>분기 실적표</h2>
      <button class="btn" id="add-row">+ 분기 추가</button>
      <button class="btn" id="reset">초기화</button>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr>
          <th>분기</th><th>매출</th><th>영업이익</th><th>주가</th><th>E</th>
          <th>전체이익률</th><th>Δ매출</th><th>Δ영업이익</th><th>증분이익률</th><th></th>
        </tr></thead>
        <tbody id="grid"></tbody>
      </table>
    </div>
    <p class="hint">셀을 클릭해 바로 수정 — 차트·KPI·시그널이 즉시 재계산됩니다.
       E = 컨센서스 추정치(추세 판정에서 제외). 수정 내용은 이 브라우저에
       자동 저장되며, 초기화를 누르면 리포트 생성 시점 데이터로 돌아갑니다.</p>
  </section>

  <footer>
    당기순이익이 아니라 영업이익 기준. 증분 영업이익률 = Δ영업이익 ÷ Δ매출 —
    새로 붙는 매출이 몇 %짜리인지를 본다. 매출 변화가 0인 분기의 증분값은
    표시하지 않음. "주가 겹쳐보기"는 min-max 상대 스케일이라 모양(꺾이는
    시점) 비교 전용 — 값은 툴팁과 주가 패널에서 확인.
  </footer>
</div>

<div id="tooltip" role="status"></div>

<script>
"use strict";
const INITIAL = __DATA__;
const STORE_KEY = "ipm:" + INITIAL.title;
// 판정 임계값 — incremental_margin.py와 동일하게 유지할 것
const TREND_PP = 2.0, SPIKE_PP = 15.0;
const NS = "http://www.w3.org/2000/svg";
const W = 920, PAD = { l: 58, r: 96, t: 16, b: 30 };

// ---------- 상태 ----------
function cloneRows(rows) { return rows.map(r => ({ ...r })); }
function loadState() {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (!raw) return null;
    const rows = JSON.parse(raw);
    return Array.isArray(rows) && rows.length ? rows : null;
  } catch (e) { return null; }
}
let state = loadState() || cloneRows(INITIAL.quarters);
function saveState() {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(state)); } catch (e) {}
}

// ---------- 계산 (incremental_margin.py의 규칙을 그대로 옮김) ----------
function validRows() { return state.filter(r => r.revenue != null && r.op != null); }

function computeAll() {
  const v = validRows();
  const n = v.length;
  const overall = v.map(q => q.revenue !== 0 ? q.op / q.revenue * 100 : null);
  const incremental = [null], dRev = [null], dOp = [null];
  for (let i = 1; i < n; i++) {
    const dr = v[i].revenue - v[i - 1].revenue;
    const dp = v[i].op - v[i - 1].op;
    dRev.push(dr); dOp.push(dp);
    incremental.push(dr !== 0 ? dp / dr * 100 : null);
  }
  // 실적치만으로 판정 (실적이 2개 미만이면 전체 사용)
  const actualIdx = [];
  v.forEach((q, i) => { if (!q.estimate) actualIdx.push(i); });
  const basisIdx = actualIdx.length >= 2 ? actualIdx : v.map((_, i) => i);
  const basisIncs = [];
  for (let k = 1; k < basisIdx.length; k++) {
    const i = basisIdx[k], j = basisIdx[k - 1];
    // 판정용 증분은 연속 실적 분기 기준이지만, 표시는 전체 시퀀스 기준을
    // 쓰므로 연속(j == i-1)일 때만 위 배열을 재사용한다.
    const dr = v[i].revenue - v[j].revenue, dp = v[i].op - v[j].op;
    if (dr > 0) basisIncs.push(dp / dr * 100);
  }
  let trend = "판단불가";
  if (basisIncs.length >= 2) {
    const diff = basisIncs[basisIncs.length - 1] - basisIncs[basisIncs.length - 2];
    trend = diff > TREND_PP ? "상승" : diff < -TREND_PP ? "하락" : "정체";
  }
  // 손익분기: basis 점들의 최소제곱 직선
  let breakEven = null;
  if (basisIdx.length >= 2) {
    const xs = basisIdx.map(i => v[i].revenue), ys = basisIdx.map(i => v[i].op);
    const mx = xs.reduce((a, b) => a + b, 0) / xs.length;
    const my = ys.reduce((a, b) => a + b, 0) / ys.length;
    let sxx = 0, sxy = 0;
    xs.forEach((x, k) => { sxx += (x - mx) ** 2; sxy += (x - mx) * (ys[k] - my); });
    if (sxx > 0) {
      const slope = sxy / sxx;
      if (slope > 0) breakEven = -(my - slope * mx) / slope;
    }
  }
  // 증분−전체 격차 (마지막 실적 구간이 매출 증가일 때만)
  let gap = null;
  const bLast = basisIdx[basisIdx.length - 1], bPrev = basisIdx[basisIdx.length - 2];
  if (bPrev != null) {
    const dr = v[bLast].revenue - v[bPrev].revenue;
    const dp = v[bLast].op - v[bPrev].op;
    if (dr > 0 && overall[bLast] != null) gap = dp / dr * 100 - overall[bLast];
  }
  return { v, n, overall, incremental, dRev, dOp, basisIdx, basisIncs,
           trend, breakEven, gap, bLast, bPrev };
}

function buildSignals(c) {
  const s = [];
  if (c.trend === "상승") s.push(
    "증분 이익률 상승 추세 — 새로 붙는 매출의 수익성이 계속 좋아지는 중. 이런 회사가 이익 성장이 폭발하는 회사.");
  else if (c.trend === "정체") s.push(
    "증분 이익률 정체 — 가격 인상(P)이 실적에 다 반영됐다는 신호. 이제부터는 물량(Q)이 늘어야만 성장 가능. 가동률·출하량 확인 필요.");
  else if (c.trend === "하락") s.push(
    "증분 이익률 하락 — 영업이익률 추세가 꺾이는 시점은 항상 위험. 단, 사이클이 긴 업종은 꺾여도 주가가 버틸 수 있음.");
  const bi = c.basisIncs;
  if (bi.length >= 2 && bi[bi.length - 1] - bi[bi.length - 2] >= SPIKE_PP) s.push(
    "증분 이익률 급등 — 사업보고서에서 원인을 찾을 것. 신사업·독점 등 시장이 좋아할 만한 이유면 강한 매수 시그널.");
  if (c.bPrev != null && c.v[c.bPrev].op <= 0 && c.v[c.bLast].op > 0) s.push(
    "영업이익 흑자 전환 — 손익분기점을 막 넘어선 자리. 판관비 축소(구조조정)로 분기점이 낮아진 경우라면 특히 주목.");
  if (c.gap != null) {
    const g = c.gap;
    if (g > 0.5) s.push(`증분−전체 이익률 격차 +${g.toFixed(1)}%p — 격차가 양수인 동안 전체 이익률은 계속 오름. 이 격차가 0에 닿는 순간이 전체 이익률 고점.`);
    else if (g < -0.5) s.push(`증분−전체 이익률 격차 ${g.toFixed(1)}%p — 증분이 평균 밑으로 내려왔으므로 전체 영업이익률은 하락 국면.`);
    else s.push(`증분−전체 이익률 격차 ${(g >= 0 ? "+" : "") + g.toFixed(1)}%p — 증분이 평균과 만나는 자리, 즉 전체 영업이익률의 고점 부근.`);
  }
  // 컨센서스가 반영하는 증분 이익률
  const est = [];
  for (let i = 1; i < c.n; i++) {
    if (c.v[i].estimate && c.dRev[i] > 0 && c.incremental[i] != null)
      est.push(`${c.v[i].label} ${c.incremental[i].toFixed(1)}%`);
  }
  if (est.length) {
    const last = bi.length ? ` (최근 실적 증분 ${bi[bi.length - 1].toFixed(1)}%와 비교)` : "";
    s.push("컨센서스 반영 증분 이익률: " + est.join(" · ") + last);
  }
  if (c.breakEven != null) {
    const latest = c.v[c.bLast];
    if (latest.revenue > c.breakEven) {
      const head = (latest.revenue - c.breakEven) / latest.revenue * 100;
      s.push(`손익분기 매출(빵원 자리) 추정 ≈ ${fmt(c.breakEven, 1)} — 현재 매출이 분기점보다 ${head.toFixed(0)}% 위에 있음.`);
    } else {
      s.push(`손익분기 매출(빵원 자리) 추정 ≈ ${fmt(c.breakEven, 1)} — 현재 매출이 아직 분기점 아래. 판관비(고정비) 축소 여부 확인.`);
    }
  }
  if (!s.length) s.push("특이 시그널 없음");
  return s;
}

// ---------- 렌더 공통 ----------
function fmt(v, digits) {
  return v == null || !isFinite(v) ? "–" : v.toLocaleString("ko-KR",
    { minimumFractionDigits: digits, maximumFractionDigits: digits });
}
function el(name, attrs, parent) {
  const node = document.createElementNS(NS, name);
  for (const k in attrs) node.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(node);
  return node;
}
function div(cls, parent, text) {
  const d = document.createElement("div");
  if (cls) d.className = cls;
  if (text != null) d.textContent = text;
  if (parent) parent.appendChild(d);
  return d;
}
function niceTicks(min, max, count) {
  const span = max - min || 1;
  const step0 = span / Math.max(1, count);
  const mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => span / s <= count) || 10 * mag;
  const ticks = [];
  for (let t = Math.ceil(min / step) * step; t <= max + 1e-9; t += step)
    ticks.push((Math.round(t * 1e6) / 1e6) || 0);
  return ticks;
}

// ---------- KPI ----------
function tile(parent, label, value, delta, goodWhenUp, suffix) {
  const t = div("tile", parent);
  div("tile-label", t, label);
  div("tile-value", t, value);
  if (delta != null) {
    const good = (delta >= 0) === goodWhenUp;
    const d = div("tile-delta " + (good ? "delta-good" : "delta-bad"), t);
    d.textContent = (delta >= 0 ? "+" : "") + fmt(delta, 1) + suffix + " vs 직전 분기";
  }
}

function renderKpis(c) {
  const box = document.getElementById("kpis");
  box.textContent = "";
  if (c.bPrev == null) { tile(box, "분기 수 부족", "–"); return; }
  const latest = c.v[c.bLast], prev = c.v[c.bPrev];
  const mNow = c.overall[c.bLast], mPrev = c.overall[c.bPrev];
  tile(box, "전체 영업이익률", fmt(mNow, 1) + "%",
    mNow != null && mPrev != null ? mNow - mPrev : null, true, "%p");
  const drLast = latest.revenue - prev.revenue;
  const incNow = drLast !== 0 ? (latest.op - prev.op) / drLast * 100 : null;
  const incLabel = drLast < 0 ? "증분 영업이익률 (매출 감소 구간)" : "증분 영업이익률";
  const bi = c.basisIncs;
  const incDelta = drLast > 0 && bi.length >= 2 ? bi[bi.length - 1] - bi[bi.length - 2] : null;
  tile(box, incLabel, fmt(incNow, 1) + "%", incDelta, true, "%p");
  tile(box, "증분−전체 격차", c.gap == null ? "–" : fmt(c.gap, 1) + "%p");
  tile(box, "손익분기 매출 추정", fmt(c.breakEven, 1));
  if (latest.price != null) {
    const chg = prev.price ? (latest.price - prev.price) / prev.price * 100 : null;
    tile(box, "주가", fmt(latest.price, 0), chg, true, "%");
  }
}

// ---------- 차트 ----------
let panels = [], ttSeries = [], chartLabels = [], chartEst = [];

function drawPanel(containerId, series, labels, est, opts) {
  const container = document.getElementById(containerId);
  container.textContent = "";
  const H = opts.height, n = labels.length;
  if (n < 2) return null;
  const all = series.flatMap(s => s.values).filter(x => x != null);
  if (!all.length) return null;
  let lo = Math.min(...all), hi = Math.max(...all);
  if (opts.includeZero) { lo = Math.min(lo, 0); hi = Math.max(hi, 0); }
  const padY = (hi - lo || 1) * 0.08;
  lo -= padY; hi += padY;
  const x = i => PAD.l + (W - PAD.l - PAD.r) * i / (n - 1);
  const y = v => PAD.t + (H - PAD.t - PAD.b) * (1 - (v - lo) / (hi - lo));
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img" });
  container.appendChild(svg);

  const firstEst = est.indexOf(true);
  if (firstEst >= 0) {
    const startX = firstEst > 0 ? (x(firstEst - 1) + x(firstEst)) / 2 : PAD.l;
    el("rect", { x: startX, y: PAD.t, width: W - PAD.r - startX,
      height: H - PAD.t - PAD.b, fill: "var(--text-muted)", "fill-opacity": 0.07 }, svg);
    const tag = el("text", { x: W - PAD.r - 6, y: PAD.t + 12, "text-anchor": "end",
      "font-size": 10, fill: "var(--text-muted)" }, svg);
    tag.textContent = "컨센서스(E)";
  }
  for (const t of niceTicks(lo, hi, 4)) {
    el("line", { x1: PAD.l, x2: W - PAD.r, y1: y(t), y2: y(t),
      stroke: t === 0 ? "var(--baseline)" : "var(--grid)", "stroke-width": 1 }, svg);
    const lbl = el("text", { x: PAD.l - 8, y: y(t) + 4, "text-anchor": "end",
      "font-size": 11, fill: "var(--text-muted)",
      style: "font-variant-numeric: tabular-nums" }, svg);
    lbl.textContent = fmt(t, 0) + (opts.axisSuffix || "");
  }
  const stride = Math.ceil(n / 10);
  labels.forEach((label, i) => {
    if (i % stride !== 0 && i !== n - 1) return;
    if (i !== n - 1 && n - 1 - i < stride && stride > 1) return;
    const lbl = el("text", { x: x(i), y: H - 8, "text-anchor": "middle",
      "font-size": 11, fill: "var(--text-muted)" }, svg);
    lbl.textContent = label + (est[i] ? "(E)" : "");
  });

  // 주가 오버레이 (상대 스케일 — 모양 비교 전용, 자체 축 없음)
  if (opts.overlay) {
    const pv = opts.overlay.filter(x => x != null);
    if (pv.length >= 2) {
      const pLo = Math.min(...pv), pHi = Math.max(...pv);
      const py = p => pHi === pLo ? (y(lo) + y(hi)) / 2
        : y(lo) + (y(hi) - y(lo)) * (p - pLo) / (pHi - pLo);
      let dSolid = "", dDash = "", prev = null;
      opts.overlay.forEach((p, i) => {
        if (p == null) { prev = null; return; }
        if (prev) {
          const seg = "M" + x(prev.i).toFixed(1) + " " + py(prev.p).toFixed(1)
            + "L" + x(i).toFixed(1) + " " + py(p).toFixed(1);
          if (est[i] || est[prev.i]) dDash += seg; else dSolid += seg;
        }
        prev = { i, p };
      });
      const ob = { fill: "none", stroke: "var(--series-price)", "stroke-width": 2,
        opacity: 0.55, "stroke-linejoin": "round", "stroke-linecap": "round" };
      if (dSolid) el("path", { ...ob, d: dSolid }, svg);
      if (dDash) el("path", { ...ob, d: dDash, "stroke-dasharray": "5 5",
        "stroke-linecap": "butt" }, svg);
      for (let i = opts.overlay.length - 1; i >= 0; i--) {
        if (opts.overlay[i] != null) {
          const lbl = el("text", { x: x(i) + 8, y: py(opts.overlay[i]) + 4,
            "font-size": 10, fill: "var(--text-muted)" }, svg);
          lbl.textContent = "주가(상대)";
          break;
        }
      }
    }
  }

  const cross = el("line", { y1: PAD.t, y2: H - PAD.b,
    stroke: "var(--baseline)", "stroke-width": 1, visibility: "hidden" }, svg);

  const endLabels = [];
  for (const s of series) {
    let solid = "", dashed = "", prev = null;
    s.values.forEach((val, i) => {
      if (val == null) { prev = null; return; }
      if (prev) {
        const seg = "M" + x(prev.i).toFixed(1) + " " + y(prev.v).toFixed(1)
          + "L" + x(i).toFixed(1) + " " + y(val).toFixed(1);
        if (est[i] || est[prev.i]) dashed += seg; else solid += seg;
      }
      prev = { i, v: val };
    });
    const base = { fill: "none", stroke: `var(${s.colorVar})`, "stroke-width": 2,
      "stroke-linejoin": "round", "stroke-linecap": "round" };
    if (solid) el("path", { ...base, d: solid }, svg);
    if (dashed) el("path", { ...base, d: dashed, "stroke-dasharray": "5 5",
      "stroke-linecap": "butt" }, svg);
    s.values.forEach((val, i) => {
      if (val == null) return;
      el("circle", { cx: x(i), cy: y(val), r: 4,
        fill: est[i] ? "var(--surface-1)" : `var(${s.colorVar})`,
        stroke: est[i] ? `var(${s.colorVar})` : "var(--surface-1)",
        "stroke-width": 2 }, svg);
    });
    for (let i = n - 1; i >= 0; i--) {
      if (s.values[i] != null) {
        endLabels.push({ y: y(s.values[i]),
          text: fmt(s.values[i], s.digits) + (s.suffix || "") });
        break;
      }
    }
  }
  const sorted = endLabels.slice().sort((a, b) => a.y - b.y);
  const collide = sorted.some((l, i) => i && l.y - sorted[i - 1].y < 16);
  (collide ? endLabels.slice(-1) : endLabels).forEach(l => {
    const t = el("text", { x: W - PAD.r + 10, y: l.y + 4, "font-size": 12,
      "font-weight": 600, fill: "var(--text-primary)",
      style: "font-variant-numeric: tabular-nums" }, svg);
    t.textContent = l.text;
  });
  return { svg, x, cross };
}

function renderCharts(c) {
  chartLabels = c.v.map(q => q.label);
  chartEst = c.v.map(q => !!q.estimate);
  const price = c.v.map(q => q.price);
  const hasPrice = price.some(p => p != null);
  panels = [];
  document.getElementById("price-panel").hidden = !hasPrice;
  document.getElementById("overlay-label").hidden = !hasPrice;
  const overlayOn = hasPrice && document.getElementById("overlay-toggle").checked;
  document.getElementById("overlay-key").hidden = !overlayOn;
  if (hasPrice) {
    const p = drawPanel("price-chart", [
      { values: price, colorVar: "--series-price", digits: 0 },
    ], chartLabels, chartEst, { height: 230 });
    if (p) panels.push(p);
  } else {
    document.getElementById("price-chart").textContent = "";
  }
  const m = drawPanel("margin-chart", [
    { values: c.overall, colorVar: "--series-overall", digits: 1, suffix: "%" },
    { values: c.incremental, colorVar: "--series-inc", digits: 1, suffix: "%" },
  ], chartLabels, chartEst, { height: 280, includeZero: true, axisSuffix: "%",
    overlay: overlayOn ? price : null });
  if (m) panels.push(m);

  ttSeries = [];
  if (hasPrice) ttSeries.push({ values: price, colorVar: "--series-price", name: "주가", digits: 0, suffix: "" });
  ttSeries.push(
    { values: c.overall, colorVar: "--series-overall", name: "전체 이익률", digits: 1, suffix: "%" },
    { values: c.incremental, colorVar: "--series-inc", name: "증분 이익률", digits: 1, suffix: "%" });
}

// ---------- 시그널 ----------
function renderSignals(c) {
  const ul = document.getElementById("signals");
  ul.textContent = "";
  for (const s of buildSignals(c)) {
    const li = document.createElement("li");
    li.textContent = s;
    ul.appendChild(li);
  }
  document.getElementById("trend-label").textContent = c.trend;
}

// ---------- 편집 테이블 ----------
function parseNum(s) {
  const t = String(s).replace(/,/g, "").trim();
  if (!t || t === "-") return null;
  const v = Number(t);
  return isFinite(v) ? v : null;
}

function numInput(row, key, refreshFn) {
  const inp = document.createElement("input");
  inp.type = "text";
  inp.value = row[key] == null ? "" : row[key].toLocaleString("ko-KR", { maximumFractionDigits: 4 });
  inp.addEventListener("input", () => { row[key] = parseNum(inp.value); refreshFn(); });
  inp.addEventListener("blur", () => {
    if (row[key] != null) inp.value = row[key].toLocaleString("ko-KR", { maximumFractionDigits: 4 });
  });
  return inp;
}

function nextLabel(prev) {
  let m = /^(\d{4})[./\-](\d{1,2})$/.exec(prev || "");
  if (m) {
    let yy = +m[1], mm = +m[2] + 3;
    if (mm > 12) { mm -= 12; yy += 1; }
    return `${yy}/${String(mm).padStart(2, "0")}`;
  }
  m = /^(\d{4})Q([1-4])$/i.exec(prev || "");
  if (m) {
    const q = +m[2];
    return q === 4 ? `${+m[1] + 1}Q1` : `${m[1]}Q${q + 1}`;
  }
  return "";
}

function renderTable() {
  const tbody = document.getElementById("grid");
  tbody.textContent = "";
  state.forEach((row, ri) => {
    const tr = document.createElement("tr");
    const tdL = document.createElement("td");
    const lab = document.createElement("input");
    lab.type = "text"; lab.className = "label-input"; lab.value = row.label || "";
    lab.addEventListener("input", () => { row.label = lab.value.trim(); refresh(false); });
    tdL.appendChild(lab); tr.appendChild(tdL);

    for (const key of ["revenue", "op", "price"]) {
      const td = document.createElement("td");
      td.className = "num";
      td.appendChild(numInput(row, key, () => refresh(false)));
      tr.appendChild(td);
    }
    const tdE = document.createElement("td");
    tdE.className = "center";
    const chk = document.createElement("input");
    chk.type = "checkbox"; chk.checked = !!row.estimate;
    chk.title = "컨센서스 추정치";
    chk.addEventListener("change", () => { row.estimate = chk.checked; refresh(false); });
    tdE.appendChild(chk); tr.appendChild(tdE);

    for (let k = 0; k < 4; k++) {
      const td = document.createElement("td");
      td.className = "derived";
      td.dataset.slot = `d${ri}-${k}`;
      tr.appendChild(td);
    }
    const tdX = document.createElement("td");
    const del = document.createElement("button");
    del.className = "del"; del.textContent = "×"; del.title = "행 삭제";
    del.addEventListener("click", () => { state.splice(ri, 1); refresh(true); });
    tdX.appendChild(del); tr.appendChild(tdX);
    tbody.appendChild(tr);
  });
  updateDerived();
}

function updateDerived() {
  const c = computeAll();
  // state 행 → valid 인덱스 매핑
  let vi = -1;
  state.forEach((row, ri) => {
    const ok = row.revenue != null && row.op != null;
    if (ok) vi += 1;
    const get = k => document.querySelector(`[data-slot="d${ri}-${k}"]`);
    if (!ok) { for (let k = 0; k < 4; k++) get(k).textContent = "–"; return; }
    get(0).textContent = fmt(c.overall[vi], 1) + "%";
    if (vi === 0) { for (let k = 1; k < 4; k++) get(k).textContent = "–"; return; }
    const sign = x => (x >= 0 ? "+" : "") + fmt(x, 1);
    get(1).textContent = sign(c.dRev[vi]);
    get(2).textContent = sign(c.dOp[vi]);
    get(3).textContent = c.incremental[vi] == null ? "–" : fmt(c.incremental[vi], 1) + "%";
  });
  return c;
}

// ---------- 전체 갱신 ----------
function refresh(rebuildTable) {
  if (rebuildTable) renderTable();
  const c = updateDerived();
  renderKpis(c);
  renderCharts(c);
  renderSignals(c);
  saveState();
}

document.getElementById("add-row").addEventListener("click", () => {
  const last = state[state.length - 1];
  state.push({ label: nextLabel(last && last.label), revenue: null, op: null,
    price: null, estimate: false });
  refresh(true);
  const rows = document.querySelectorAll("#grid tr");
  const inp = rows[rows.length - 1].querySelector("input");
  if (inp) inp.focus();
});
document.getElementById("reset").addEventListener("click", () => {
  try { localStorage.removeItem(STORE_KEY); } catch (e) {}
  state = cloneRows(INITIAL.quarters);
  refresh(true);
});
document.getElementById("overlay-toggle").addEventListener("change", () => refresh(false));

// ---------- 크로스헤어 + 툴팁 ----------
const tooltip = document.getElementById("tooltip");
const chartsBox = document.getElementById("charts");

function showIndex(i, clientX, clientY) {
  const n = chartLabels.length;
  if (!n || !panels.length) return;
  i = Math.max(0, Math.min(n - 1, i));
  for (const p of panels) {
    const px = p.x(i);
    p.cross.setAttribute("x1", px);
    p.cross.setAttribute("x2", px);
    p.cross.setAttribute("visibility", "visible");
  }
  tooltip.textContent = "";
  div("tt-title", tooltip, chartLabels[i] + (chartEst[i] ? " (E · 컨센서스)" : ""));
  for (const s of ttSeries) {
    const row = div("tt-row", tooltip);
    const key = document.createElement("span");
    key.className = "tt-key";
    key.style.background = `var(${s.colorVar})`;
    row.appendChild(key);
    const val = document.createElement("span");
    val.className = "tt-val";
    val.textContent = fmt(s.values[i], s.digits) + s.suffix;
    const name = document.createElement("span");
    name.className = "tt-name";
    name.textContent = s.name;
    row.append(val, name);
  }
  tooltip.style.display = "block";
  const r = tooltip.getBoundingClientRect();
  let tx = clientX + 14, ty = clientY + 14;
  if (tx + r.width > window.innerWidth - 8) tx = clientX - r.width - 14;
  if (ty + r.height > window.innerHeight - 8) ty = clientY - r.height - 14;
  tooltip.style.left = tx + "px";
  tooltip.style.top = ty + "px";
}
function hideTip() {
  tooltip.style.display = "none";
  for (const p of panels) p.cross.setAttribute("visibility", "hidden");
}
let focusIndex = -1;
chartsBox.addEventListener("pointermove", e => {
  if (!panels.length) return;
  const rect = panels[0].svg.getBoundingClientRect();
  const relX = (e.clientX - rect.left) / rect.width * W;
  const n = chartLabels.length;
  const step = (W - PAD.l - PAD.r) / Math.max(1, n - 1);
  showIndex(Math.round((relX - PAD.l) / step), e.clientX, e.clientY);
});
chartsBox.addEventListener("pointerleave", hideTip);
chartsBox.addEventListener("keydown", e => {
  const n = chartLabels.length;
  if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
    e.preventDefault();
    if (focusIndex < 0) focusIndex = n - 1;
    else focusIndex = e.key === "ArrowRight"
      ? Math.min(n - 1, focusIndex + 1) : Math.max(0, focusIndex - 1);
    const rect = chartsBox.getBoundingClientRect();
    showIndex(focusIndex, rect.left + 80, rect.top + 60);
  } else if (e.key === "Escape") { focusIndex = -1; hideTip(); }
});
chartsBox.addEventListener("blur", () => { focusIndex = -1; hideTip(); });

refresh(true);
</script>
</body>
</html>
"""
