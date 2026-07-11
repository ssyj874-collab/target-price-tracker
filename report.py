"""워치리스트(종목 n개) 인터랙티브 HTML 리포트 생성.

리포트는 자체 완결형 단일 HTML이며 2뎁스 구조다:
워치리스트(종목 요약 테이블, 클릭으로 전환) → 종목 상세(차트·KPI·시그널·실적표).

브라우저 안에서 되는 것:
- 종목 추가/삭제, 종목명 수정(제목 클릭), FnGuide 표 붙여넣기로 분기 채우기
- 분기 실적표 편집(과거/최신 분기 추가, 행 삭제, 매출·영업이익 수정, E 체크)
  → 차트·KPI·시그널·워치리스트 요약 즉시 재계산
- 모든 상태는 localStorage에 저장. 리포트를 다시 생성해 열면 같은 종목
  (이름 기준 id)의 주가 시계열은 새 임베드로 갱신되고, 분기 데이터는
  사용자 수정본이 유지된다(초기화 버튼으로 임베드 데이터 복귀).

주가 그래프는 없다(사용자 요청으로 제거). 주가 시계열(--fetch-price /
--price-csv / watchlist.py)이 주입되어 있으면 KPI의 '최근 종가' 타일에만
쓰인다. 분기 라벨은 "23.1분기" 형식이 기본이고 2025/03·2025Q1도 허용.

계산 로직은 파이썬(incremental_margin.py)과 템플릿 JS에 같은 규칙으로
두 벌 존재한다 — 임계값·판정 규칙을 바꿀 때 양쪽을 함께 고칠 것.
차트 규칙(날짜 축, 컨센서스 점선·빈 마커·워시)은 이전과 동일하다.
"""

from __future__ import annotations

import html
import json

from incremental_margin import Analysis
from price_fetch import quarter_end


def _stock_payload(analysis: Analysis, name: str, price_series: list | None) -> dict:
    if price_series is None:
        price_series = []
        for q in analysis.quarters:
            if q.price is not None:
                end = quarter_end(q.label)
                if end:
                    price_series.append([end.isoformat(), q.price])
    return {
        "id": name,
        "name": name,
        "quarters": [
            {
                "label": q.label,
                "revenue": q.revenue,
                "op": q.operating_profit,
                "estimate": q.estimate,
            }
            for q in analysis.quarters
        ],
        "priceSeries": price_series,
    }


def render_watchlist(
    stocks: list[dict],
    page_title: str = "증분 이익률 워치리스트",
    unit: str = "백만원",
) -> str:
    """stocks: [{"name": str, "analysis": Analysis, "price_series": list|None}]

    unit: 매출·영업이익 금액 단위 표기 (기본 백만원 — DART 사업보고서 기준.
    FnGuide 표는 억원이므로 붙여넣기 시 ×100 변환 체크박스를 쓸 것)."""
    data = {
        "unit": unit,
        "stocks": [
            _stock_payload(s["analysis"], s["name"], s.get("price_series"))
            for s in stocks
        ],
    }
    page = HTML_TEMPLATE
    page = page.replace("__TITLE__", html.escape(page_title))
    page = page.replace("__UNIT__", html.escape(unit))
    page = page.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    return page


def render_html(
    analysis: Analysis,
    title: str = "증분 영업이익률 리포트",
    price_series: list | None = None,
    unit: str = "백만원",
) -> str:
    """단일 종목 리포트 (워치리스트에 종목 1개)."""
    return render_watchlist(
        [{"name": title, "analysis": analysis, "price_series": price_series}],
        page_title=title,
        unit=unit,
    )


# raw 문자열 필수: 템플릿 JS의 정규식(\r?\n 등)이 파이썬 이스케이프로
# 손상되지 않도록.
HTML_TEMPLATE = r"""<!doctype html>
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
.panel { background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; padding: 16px; }
.panel h2 { font-size: 14px; font-weight: 600; margin-bottom: 4px; }
.grid-head { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; flex-wrap: wrap; }
.grid-head h2 { flex: 1; margin-bottom: 0; }
.btn {
  font: inherit; font-size: 12px; color: var(--text-primary);
  background: transparent; border: 1px solid var(--border);
  border-radius: 7px; padding: 5px 12px; cursor: pointer;
}
.btn:hover { background: var(--page); }
/* 워치리스트 */
#watch-table tr { cursor: pointer; }
#watch-table tr.active td { font-weight: 650; }
#watch-table tr.active td:first-child { color: var(--series-price); }
#watch-table tr:hover { background: var(--page); }
.trend-chip { font-size: 12px; padding: 1px 8px; border-radius: 999px; border: 1px solid var(--border); color: var(--text-secondary); }
/* 종목 헤더 */
#stock-name {
  font-size: 20px; font-weight: 650; color: inherit; background: transparent;
  border: none; border-bottom: 1px dashed transparent; padding: 0; width: 100%;
  font-family: inherit;
}
#stock-name:hover { border-bottom-color: var(--grid); }
#stock-name:focus { outline: none; border-bottom-color: var(--series-price); }
header p { color: var(--text-secondary); font-size: 13px; margin-top: 4px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
.tile { background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px; }
.tile-label { font-size: 12px; color: var(--text-secondary); }
.tile-value { font-size: 26px; font-weight: 600; margin-top: 2px; }
.tile-delta { font-size: 12px; margin-top: 2px; }
.delta-good { color: var(--delta-good); }
.delta-bad { color: var(--delta-bad); }
.legend-row { display: flex; flex-wrap: wrap; align-items: center; gap: 16px; font-size: 12px; color: var(--text-secondary); margin: 4px 0 8px; }
.legend-row .key { display: inline-block; width: 14px; height: 3px; border-radius: 2px; vertical-align: middle; margin-right: 6px; }
.legend-row label { display: inline-flex; align-items: center; gap: 6px; cursor: pointer; margin-left: auto; }
.chart svg { display: block; width: 100%; height: auto; }
#charts { outline: none; }
#charts:focus-visible { box-shadow: 0 0 0 2px var(--series-price); border-radius: 10px; }
.signals h2 { font-size: 14px; font-weight: 600; margin-bottom: 8px; }
.signals ul { padding-left: 18px; display: grid; gap: 6px; }
.signals li { font-size: 13px; color: var(--text-secondary); line-height: 1.5; }
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
.hint { font-size: 12px; color: var(--text-muted); margin-top: 8px; line-height: 1.6; }
details.paste { margin-top: 10px; }
details.paste summary { font-size: 12px; color: var(--text-secondary); cursor: pointer; }
details.paste textarea {
  width: 100%; min-height: 110px; margin-top: 8px; font: 12px/1.5 ui-monospace, monospace;
  color: inherit; background: var(--page); border: 1px solid var(--border);
  border-radius: 7px; padding: 8px;
}
#paste-status { font-size: 12px; margin-left: 8px; color: var(--text-muted); }
#tooltip {
  position: fixed; pointer-events: none; z-index: 10; display: none;
  background: var(--surface-1); border: 1px solid var(--border);
  border-radius: 8px; padding: 8px 10px; font-size: 12px;
  box-shadow: 0 4px 14px rgba(0,0,0,0.14); min-width: 165px;
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
  <section class="panel">
    <div class="grid-head">
      <h2>워치리스트</h2>
      <button class="btn" id="add-stock">+ 종목 추가</button>
      <button class="btn" id="del-stock">현재 종목 삭제</button>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr>
          <th>종목</th><th>최신 분기</th><th>전체이익률</th><th>증분이익률</th>
          <th>격차</th><th style="text-align:center">추세</th><th>최근 종가</th>
        </tr></thead>
        <tbody id="watch-table"></tbody>
      </table>
    </div>
  </section>

  <header>
    <input id="stock-name" aria-label="종목명 (클릭해서 수정)" title="클릭해서 종목명 수정">
    <p>증분 이익률 추세: <strong id="trend-label">-</strong> ·
       전체 이익률의 기울기는 (증분 − 전체) 격차에 비례 —
       격차가 0에 닿는 분기가 전체 이익률의 고점</p>
  </header>

  <div class="tiles" id="kpis"></div>

  <div id="charts" tabindex="0" aria-label="분기별 이익률 차트. 좌우 화살표로 분기 이동">
    <section class="panel">
      <h2>영업이익률 vs 증분 영업이익률</h2>
      <div class="legend-row">
        <span><span class="key" style="background:var(--series-overall)"></span>전체 영업이익률</span>
        <span><span class="key" style="background:var(--series-inc)"></span>증분 영업이익률</span>
        <label title="계절성(분기마다 매출이 오르내리는) 종목은 전년 동기 대비가 깨끗합니다">
          <input type="checkbox" id="yoy-toggle"> 증분 전년 동기(YoY) 기준
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
      <button class="btn" id="add-past">+ 과거 분기</button>
      <button class="btn" id="add-recent">+ 최신 분기</button>
      <button class="btn" id="reset">초기화</button>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr>
          <th>분기</th><th>매출 (__UNIT__)</th><th>영업이익 (__UNIT__)</th><th>E</th>
          <th>전체이익률</th><th id="th-drev">Δ매출</th><th id="th-dop">Δ영업이익</th>
          <th id="th-inc">증분이익률</th><th></th>
        </tr></thead>
        <tbody id="grid"></tbody>
      </table>
    </div>
    <details class="paste">
      <summary>FnGuide 표 붙여넣기로 채우기</summary>
      <textarea id="paste-box" placeholder="FnGuide Financial Highlight에서 복사한 표를 여기에 붙여넣기&#10;(헤더: 2025/03 2025/06 ... 2026/06(E), 행: 매출액 / 영업이익 / 영업이익(발표기준))"></textarea>
      <div style="margin-top:6px">
        <button class="btn" id="paste-apply">적용 (현재 종목 분기 교체)</button>
        <label style="font-size:12px;color:var(--text-secondary);margin-left:8px">
          <input type="checkbox" id="paste-eok" checked> 억원 단위 표(FnGuide) — ×100 하여 __UNIT__ 변환
        </label>
        <span id="paste-status"></span>
      </div>
    </details>
    <p class="hint">금액 단위: __UNIT__ (다트 사업보고서 기준. FnGuide 표는
       억원이므로 붙여넣기 시 ×100 변환 체크를 켤 것). 분기 라벨은
       "2024.3분기" 형식으로 표준화됩니다(2024/09, 24.3분기, 2024Q3으로
       입력해도 자동 변환). 셀을 클릭해 바로 수정 —
       차트·KPI·시그널·워치리스트가 즉시 재계산됩니다. "+ 과거 분기"는 표
       맨 위에 이전 분기를(다트에서 긁은 옛 실적 입력용), "+ 최신 분기"는
       맨 아래에 다음 분기를 추가합니다. E = 컨센서스 추정치(추세 판정에서
       제외). 수정 내용은 이 브라우저에 자동 저장되고, 초기화를 누르면
       생성 시점 데이터로 돌아갑니다.</p>
  </section>

  <footer>
    당기순이익이 아니라 영업이익 기준, 금액 단위 __UNIT__. 증분 영업이익률
    = Δ영업이익 ÷ Δ매출 — 새로 붙는 매출이 몇 %짜리인지를 본다. 매출이
    줄어든 분기의 증분값은 부호가 반전된 노이즈라 차트에서 제외하고
    그 자리에서 선이 끊긴다(전후의 유효한 값은 점으로 표시, 값은
    표·툴팁에서 확인). 추세 판정에서도 제외한다. 분기마다 매출이
    오르내리는 계절성 종목은 "증분 전년 동기(YoY) 기준"을 켜면 이
    노이즈가 근본적으로 사라져 선이 이어진다. 분기 지표는 분기 말일
    위치에 찍힌다.
  </footer>
</div>

<div id="tooltip" role="status"></div>

<script>
"use strict";
const INITIAL = __DATA__;
const STORE_KEY = "ipt:watchlist:v2";
// 판정 임계값 — incremental_margin.py와 동일하게 유지할 것
const TREND_PP = 2.0, SPIKE_PP = 15.0;
const NS = "http://www.w3.org/2000/svg";
const W = 920, PAD = { l: 58, r: 96, t: 16, b: 30 };
const DAY = 86400000;

// ---------- 워치리스트 DB ----------
function clone(x) { return JSON.parse(JSON.stringify(x)); }
function loadDb() {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (raw) {
      const db = JSON.parse(raw);
      if (db && Array.isArray(db.stocks)) return db;
    }
  } catch (e) {}
  return { stocks: [], active: null };
}
let db = loadDb();
// 임베드 병합: 새 종목은 추가. 기존 종목(id 일치)은 임베드 데이터가
// 바뀌었으면(리포트 재생성) 임베드로 교체 — 재생성이 곧 데이터 원본이다.
// 임베드가 그대로면 브라우저에서의 수정본을 유지한다.
for (const s of INITIAL.stocks) {
  const hash = JSON.stringify(s.quarters);
  const found = db.stocks.find(x => x.id === s.id);
  if (!found) {
    const c = clone(s);
    c.seedHash = hash;
    db.stocks.push(c);
  } else {
    if (found.seedHash !== hash) {
      found.quarters = clone(s.quarters);
      found.name = s.name;
      found.seedHash = hash;
    }
    if (s.priceSeries && s.priceSeries.length) found.priceSeries = clone(s.priceSeries);
  }
}
if (!db.stocks.length) db.stocks.push({ id: "새 종목", name: "새 종목", quarters: [], priceSeries: [] });
if (!db.active || !db.stocks.some(s => s.id === db.active)) db.active = db.stocks[0].id;
// 분기 라벨을 표준형(YYYY.N분기)으로 정규화 — 과거에 2024/09 식으로
// 저장된 라벨도 열 때 자동 변환된다.
for (const s of db.stocks) {
  (s.quarters || []).forEach(r => { r.label = normalizeLabel(r.label); });
}

function saveDb() {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(db)); } catch (e) {}
}
function activeStock() { return db.stocks.find(s => s.id === db.active); }

let stock = activeStock();
let PRICE = [];
function rebuildPrice() {
  PRICE = (stock.priceSeries || [])
    .map(([d, c]) => ({ t: Date.parse(d), c }))
    .filter(p => isFinite(p.t) && p.c != null)
    .sort((a, b) => a.t - b.t);
}
rebuildPrice();

// ---------- 분기 라벨 ↔ 날짜 ----------
// 표준형 'YYYY.N분기'로 정규화 (2024/09 → 2024.3분기, 24.3분기 → 2024.3분기)
function normalizeLabel(label) {
  const s = String(label || "").trim();
  let m = /^(\d{2,4})\.([1-4])분기$/.exec(s);
  if (m) {
    let y = +m[1]; if (y < 100) y += 2000;
    return `${y}.${m[2]}분기`;
  }
  m = /^(\d{4})[./\-](\d{1,2})$/.exec(s);
  if (m && +m[2] >= 1 && +m[2] <= 12) return `${m[1]}.${Math.ceil(+m[2] / 3)}분기`;
  m = /^(\d{4})Q([1-4])$/i.exec(s);
  if (m) return `${m[1]}.${m[2]}분기`;
  return s;
}

function qEndMs(label) {
  let y = null, mo = null, m;
  if ((m = /^(\d{2,4})\.([1-4])분기$/.exec(label || ""))) {
    y = +m[1]; if (y < 100) y += 2000; mo = +m[2] * 3;
  }
  else if ((m = /^(\d{4})[./\-](\d{1,2})$/.exec(label || ""))) { y = +m[1]; mo = +m[2]; }
  else if ((m = /^(\d{4})Q([1-4])$/i.exec(label || ""))) { y = +m[1]; mo = +m[2] * 3; }
  if (y == null || mo < 1 || mo > 12) return null;
  return Date.UTC(y, mo, 0);
}
function dateStr(t) { return new Date(t).toISOString().slice(0, 10); }
function prevLabel(label) {
  const m = /^(\d{4})\.([1-4])분기$/.exec(normalizeLabel(label));
  if (!m) return "";
  let y = +m[1], q = +m[2] - 1;
  if (q < 1) { q = 4; y -= 1; }
  return `${y}.${q}분기`;
}
function nextLabel(label) {
  const m = /^(\d{4})\.([1-4])분기$/.exec(normalizeLabel(label));
  if (!m) return "";
  let y = +m[1], q = +m[2] + 1;
  if (q > 4) { q = 1; y += 1; }
  return `${y}.${q}분기`;
}

// ---------- 계산 (incremental_margin.py의 규칙을 그대로 옮김) ----------
// mode: "qoq"(전분기 대비, 기본) | "yoy"(전년 동기 대비 — 계절성 종목용.
// 매출이 거의 항상 증가라 부호 반전 노이즈가 사라지고 선이 이어진다)
function computeAll(quarters, mode) {
  const lag = mode === "yoy" ? 4 : 1;
  const v = quarters.filter(r => r.revenue != null && r.op != null);
  const n = v.length;
  const overall = v.map(q => q.revenue !== 0 ? q.op / q.revenue * 100 : null);
  const incremental = Array(n).fill(null);
  const dRev = Array(n).fill(null), dOp = Array(n).fill(null);
  for (let i = lag; i < n; i++) {
    const dr = v[i].revenue - v[i - lag].revenue;
    const dp = v[i].op - v[i - lag].op;
    dRev[i] = dr; dOp[i] = dp;
    incremental[i] = dr !== 0 ? dp / dr * 100 : null;
  }
  const actualIdx = [];
  v.forEach((q, i) => { if (!q.estimate) actualIdx.push(i); });
  const basisIdx = actualIdx.length >= 2 ? actualIdx : v.map((_, i) => i);
  // 판정용 증분: 실적 분기 & 매출 증가 구간만
  const basisIncs = [];
  v.forEach((q, i) => {
    if (!q.estimate && incremental[i] != null && dRev[i] > 0)
      basisIncs.push(incremental[i]);
  });
  let trend = "판단불가";
  if (basisIncs.length >= 2) {
    const diff = basisIncs[basisIncs.length - 1] - basisIncs[basisIncs.length - 2];
    trend = diff > TREND_PP ? "상승" : diff < -TREND_PP ? "하락" : "정체";
  }
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
  const bLast = basisIdx[basisIdx.length - 1], bPrev = basisIdx[basisIdx.length - 2];
  let gap = null;
  if (bLast != null && dRev[bLast] > 0 && overall[bLast] != null
      && incremental[bLast] != null) {
    gap = incremental[bLast] - overall[bLast];
  }
  let dates = v.map(q => qEndMs(q.label));
  const datesOK = n >= 2 && dates.every(d => d != null)
    && dates.every((d, i) => !i || d > dates[i - 1]);
  if (!datesOK) dates = v.map((_, i) => i);
  return { v, n, lag, mode: mode || "qoq", overall, incremental, dRev, dOp,
           basisIdx, basisIncs, trend, breakEven, gap, bLast, bPrev,
           dates, datesOK };
}

function buildSignals(c) {
  const s = [];
  if (c.mode === "yoy") s.push(
    "증분 기준: 전년 동기(YoY) — 계절성 제거를 위해 4분기 전과 비교해 계산.");
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
      s.push(`손익분기 매출(빵원 자리) 추정 ≈ ${fmt(c.breakEven, 0)} — 현재 매출이 분기점보다 ${head.toFixed(0)}% 위에 있음.`);
    } else {
      s.push(`손익분기 매출(빵원 자리) 추정 ≈ ${fmt(c.breakEven, 0)} — 현재 매출이 아직 분기점 아래. 판관비(고정비) 축소 여부 확인.`);
    }
  }
  if (!s.length) s.push("특이 시그널 없음");
  return s;
}

// ---------- FnGuide 붙여넣기 파서 (incremental_margin.parse_paste 이식) ----------
function parsePasteText(text) {
  const QTOKEN = /^(?:\d{2,4}\.[1-4]분기|\d{4}[./\-]\d{1,2}|\d{4}Q[1-4])(?:\(E\))?$/i;
  let labels = null, est = null;
  const fields = {};
  for (const line of (text || "").split(/\r?\n/)) {
    const cells = line.includes("\t")
      ? line.split("\t").map(s => s.trim())
      : line.trim().split(/\s+/);
    if (!cells.length || !cells.join("")) continue;
    const qcells = cells.filter(c => QTOKEN.test(c));
    if (!labels && qcells.length >= 2) {
      labels = []; est = [];
      qcells.forEach(c => {
        const e = /\(E\)$/i.test(c);
        labels.push(e ? c.slice(0, -3) : c);
        est.push(e);
      });
      continue;
    }
    const name = cells[0].replace(/\s+/g, "");
    let key = null;
    if (["매출액", "매출"].includes(name) || name.toLowerCase() === "revenue") key = "revenue";
    else if (name === "영업이익") key = "op";
    else if (name.startsWith("영업이익(발표")) key = "opA";
    else continue;
    let vals = cells.slice(1).map(c => {
      const t = c.replace(/,/g, "");
      if (!t || t === "-") return null;
      const v = Number(t);
      return isFinite(v) ? v : null;
    });
    if (labels) vals = vals.concat(Array(labels.length).fill(null)).slice(0, labels.length);
    fields[key] = vals;
  }
  if (!labels || !fields.revenue) return null;
  const op = fields.op || [], opA = fields.opA || [];
  const rows = [];
  labels.forEach((lb, i) => {
    const o = op[i] != null ? op[i] : opA[i];
    if (fields.revenue[i] == null || o == null) return;
    rows.push({ label: normalizeLabel(lb), revenue: fields.revenue[i], op: o,
      estimate: !!est[i] });
  });
  return rows.length ? rows : null;
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

// ---------- 워치리스트 요약 테이블 ----------
function lastCloseOf(s) {
  const ps = s.priceSeries || [];
  return ps.length ? ps[ps.length - 1][1] : null;
}
function renderWatchlist() {
  const tbody = document.getElementById("watch-table");
  tbody.textContent = "";
  for (const s of db.stocks) {
    const c = computeAll(s.quarters || [], db.incMode);
    const tr = document.createElement("tr");
    if (s.id === db.active) tr.className = "active";
    const cells = [];
    cells.push([s.name || s.id, "left"]);
    if (c.bLast != null) {
      cells.push([c.v[c.bLast].label, "num"]);
      cells.push([fmt(c.overall[c.bLast], 1) + "%", "num"]);
      const dr = c.dRev[c.bLast], inc = c.incremental[c.bLast];
      cells.push([fmt(inc, 1) + "%" + (dr != null && dr < 0 ? " (Δ매출<0)" : ""), "num"]);
      cells.push([c.gap == null ? "–" : fmt(c.gap, 1) + "%p", "num"]);
    } else {
      cells.push(["–", "num"], ["–", "num"], ["–", "num"], ["–", "num"]);
    }
    cells.push([c.trend, "chip"]);
    cells.push([fmt(lastCloseOf(s), 0), "num"]);
    for (const [text, kind] of cells) {
      const td = document.createElement("td");
      if (kind === "num") td.className = "num";
      if (kind === "chip") {
        td.style.textAlign = "center";
        const chip = document.createElement("span");
        chip.className = "trend-chip";
        chip.textContent = text;
        td.appendChild(chip);
      } else td.textContent = text;
      tr.appendChild(td);
    }
    tr.addEventListener("click", () => switchStock(s.id));
    tbody.appendChild(tr);
  }
}

function switchStock(id) {
  if (!db.stocks.some(s => s.id === id)) return;
  db.active = id;
  stock = activeStock();
  rebuildPrice();
  document.getElementById("stock-name").value = stock.name || stock.id;
  refresh(true);
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
function closeAtOrBefore(t, maxGapDays) {
  let best = null;
  for (const p of PRICE) {
    if (p.t <= t) best = p; else break;
  }
  if (best && maxGapDays != null && t - best.t > maxGapDays * DAY) return null;
  return best;
}
function renderKpis(c) {
  const box = document.getElementById("kpis");
  box.textContent = "";
  if (c.bPrev == null) { tile(box, "분기 수 부족 (2개 이상 입력)", "–"); return; }
  const prev = c.v[c.bPrev];
  const mNow = c.overall[c.bLast], mPrev = c.overall[c.bPrev];
  tile(box, "전체 영업이익률", fmt(mNow, 1) + "%",
    mNow != null && mPrev != null ? mNow - mPrev : null, true, "%p");
  const drLast = c.dRev[c.bLast];
  const incNow = c.incremental[c.bLast];
  let incLabel = "증분 영업이익률" + (c.mode === "yoy" ? " (YoY)" : "");
  if (drLast != null && drLast < 0) incLabel += " (매출 감소 구간)";
  const bi = c.basisIncs;
  const incDelta = drLast != null && drLast > 0 && bi.length >= 2
    ? bi[bi.length - 1] - bi[bi.length - 2] : null;
  tile(box, incLabel, fmt(incNow, 1) + "%", incDelta, true, "%p");
  tile(box, "증분−전체 격차", c.gap == null ? "–" : fmt(c.gap, 1) + "%p");
  tile(box, `손익분기 매출 추정 (${INITIAL.unit})`, fmt(c.breakEven, 0));
  if (PRICE.length && c.datesOK) {
    const last = PRICE[PRICE.length - 1];
    const prevEnd = closeAtOrBefore(qEndMs(prev.label), 15);
    const chg = prevEnd ? (last.c - prevEnd.c) / prevEnd.c * 100 : null;
    tile(box, `주가 (${dateStr(last.t)} 종가)`, fmt(last.c, 0), chg, true, "%");
  }
}

// ---------- 차트 ----------
let panels = [], chartCtx = null;

function drawPanel(containerId, opts) {
  const container = document.getElementById(containerId);
  container.textContent = "";
  const { H, xOf, dates, est, labels, washX } = opts;
  const n = labels.length;

  const pool = [];
  (opts.qSeries || []).forEach(s => s.values.forEach(v => { if (v != null) pool.push(v); }));
  if (!pool.length) return null;
  let lo = Math.min(...pool), hi = Math.max(...pool);
  if (opts.includeZero) { lo = Math.min(lo, 0); hi = Math.max(hi, 0); }
  const padY = (hi - lo || 1) * 0.08;
  lo -= padY; hi += padY;
  const y = v => PAD.t + (H - PAD.t - PAD.b) * (1 - (v - lo) / (hi - lo));

  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img" });
  container.appendChild(svg);

  if (washX != null) {
    el("rect", { x: washX, y: PAD.t, width: Math.max(0, W - PAD.r - washX),
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
    const lbl = el("text", { x: xOf(dates[i]), y: H - 8, "text-anchor": "middle",
      "font-size": 11, fill: "var(--text-muted)" }, svg);
    lbl.textContent = label + (est[i] ? "(E)" : "");
  });

  const cross = el("line", { y1: PAD.t, y2: H - PAD.b,
    stroke: "var(--baseline)", "stroke-width": 1, visibility: "hidden" }, svg);

  const endLabels = [];
  for (const s of opts.qSeries || []) {
    // null(값 없음/제외) 지점에서는 선을 끊는다 — 그 구간의 유효한 값은
    // 고립점(마커)으로만 표시. (계절성 종목은 YoY 토글이 정답)
    let solid = "", dashed = "", prev = null;
    s.values.forEach((val, i) => {
      if (val == null) { prev = null; return; }
      if (prev) {
        const seg = "M" + xOf(dates[prev.i]).toFixed(1) + " " + y(prev.v).toFixed(1)
          + "L" + xOf(dates[i]).toFixed(1) + " " + y(val).toFixed(1);
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
      el("circle", { cx: xOf(dates[i]), cy: y(val), r: 4,
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
  return { svg, cross };
}

function renderCharts(c) {
  const labels = c.v.map(q => q.label);
  const est = c.v.map(q => !!q.estimate);

  if (c.n < 2) {
    panels = []; chartCtx = null;
    document.getElementById("margin-chart").textContent = "";
    return;
  }

  let t0 = c.dates[0], t1 = c.dates[c.n - 1];
  const span = t1 - t0 || 1;
  t0 -= span * 0.03; t1 += span * 0.03;
  const xOf = t => PAD.l + (W - PAD.l - PAD.r) * (t - t0) / (t1 - t0);

  const firstEst = est.indexOf(true);
  const washX = firstEst < 0 ? null
    : xOf(firstEst > 0 ? (c.dates[firstEst - 1] + c.dates[firstEst]) / 2 : c.dates[firstEst]);

  // 매출 감소 분기의 증분값은 부호가 반전된 노이즈라 차트에서는 끊고
  // (추세 판정 제외와 동일한 규칙) 표·툴팁에만 남긴다.
  const incForChart = c.incremental.map((v, i) => (i > 0 && c.dRev[i] > 0 ? v : null));

  panels = [];
  const m = drawPanel("margin-chart", {
    xOf, dates: c.dates, est, labels, washX, H: 300,
    includeZero: true, axisSuffix: "%",
    qSeries: [
      { values: c.overall, colorVar: "--series-overall", digits: 1, suffix: "%" },
      { values: incForChart, colorVar: "--series-inc", digits: 1, suffix: "%" },
    ] });
  if (m) panels.push(m);

  chartCtx = { c, labels, est, t0, t1, xOf };
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

function renderTable() {
  const tbody = document.getElementById("grid");
  tbody.textContent = "";
  stock.quarters.forEach((row, ri) => {
    const tr = document.createElement("tr");
    const tdL = document.createElement("td");
    const lab = document.createElement("input");
    lab.type = "text"; lab.className = "label-input"; lab.value = row.label || "";
    lab.addEventListener("input", () => { row.label = lab.value.trim(); refresh(false); });
    tdL.appendChild(lab); tr.appendChild(tdL);

    for (const key of ["revenue", "op"]) {
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
    del.addEventListener("click", () => { stock.quarters.splice(ri, 1); refresh(true); });
    tdX.appendChild(del); tr.appendChild(tdX);
    tbody.appendChild(tr);
  });
  updateDerived();
}

function updateDerived() {
  const c = computeAll(stock.quarters, db.incMode);
  const yoy = db.incMode === "yoy";
  document.getElementById("th-drev").textContent = "Δ매출" + (yoy ? " (YoY)" : "");
  document.getElementById("th-dop").textContent = "Δ영업이익" + (yoy ? " (YoY)" : "");
  document.getElementById("th-inc").textContent = "증분이익률" + (yoy ? " (YoY)" : "");
  let vi = -1;
  stock.quarters.forEach((row, ri) => {
    const ok = row.revenue != null && row.op != null;
    if (ok) vi += 1;
    const get = k => document.querySelector(`[data-slot="d${ri}-${k}"]`);
    if (!get(0)) return;
    if (!ok) { for (let k = 0; k < 4; k++) get(k).textContent = "–"; return; }
    get(0).textContent = fmt(c.overall[vi], 1) + "%";
    if (c.dRev[vi] == null) {
      for (let k = 1; k < 4; k++) get(k).textContent = "–";
      return;
    }
    const sign = x => (x >= 0 ? "+" : "") + fmt(x, 0);
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
  renderWatchlist();
  saveDb();
}

// ---------- 이벤트 ----------
document.getElementById("stock-name").addEventListener("input", e => {
  stock.name = e.target.value.trim() || stock.id;
  renderWatchlist();
  saveDb();
});
document.getElementById("add-stock").addEventListener("click", () => {
  const name = (window.prompt("추가할 종목명:") || "").trim();
  if (!name) return;
  let id = name, k = 2;
  while (db.stocks.some(s => s.id === id)) id = `${name} (${k++})`;
  db.stocks.push({ id, name: id, quarters: [], priceSeries: [] });
  switchStock(id);
  document.querySelector("details.paste").open = true;
});
document.getElementById("del-stock").addEventListener("click", () => {
  if (!window.confirm(`'${stock.name}' 종목을 워치리스트에서 삭제할까요?`)) return;
  db.stocks = db.stocks.filter(s => s.id !== db.active);
  if (!db.stocks.length) db.stocks.push({ id: "새 종목", name: "새 종목", quarters: [], priceSeries: [] });
  switchStock(db.stocks[0].id);
});
document.getElementById("add-past").addEventListener("click", () => {
  const first = stock.quarters[0];
  stock.quarters.unshift({ label: prevLabel(first && first.label), revenue: null, op: null,
    estimate: false });
  refresh(true);
  const inp = document.querySelector("#grid tr td input");
  if (inp) inp.focus();
});
document.getElementById("add-recent").addEventListener("click", () => {
  const last = stock.quarters[stock.quarters.length - 1];
  stock.quarters.push({ label: nextLabel(last && last.label), revenue: null, op: null,
    estimate: false });
  refresh(true);
  const rows = document.querySelectorAll("#grid tr");
  const inp = rows[rows.length - 1].querySelector("input");
  if (inp) inp.focus();
});
document.getElementById("reset").addEventListener("click", () => {
  const embedded = INITIAL.stocks.find(s => s.id === db.active);
  if (embedded) {
    stock.quarters = clone(embedded.quarters);
    stock.priceSeries = clone(embedded.priceSeries || []);
    stock.name = embedded.name;
  } else {
    stock.quarters = [];
  }
  document.getElementById("stock-name").value = stock.name;
  rebuildPrice();
  refresh(true);
});
document.getElementById("yoy-toggle").addEventListener("change", e => {
  db.incMode = e.target.checked ? "yoy" : "qoq";
  refresh(false);
});
document.getElementById("paste-apply").addEventListener("click", () => {
  const status = document.getElementById("paste-status");
  const rows = parsePasteText(document.getElementById("paste-box").value);
  if (!rows) {
    status.textContent = "파싱 실패 — 분기 라벨 헤더와 매출액/영업이익 행이 있는지 확인";
    return;
  }
  // FnGuide 표는 억원 단위 → ×100 하여 백만원으로 통일
  if (document.getElementById("paste-eok").checked) {
    for (const r of rows) { r.revenue *= 100; r.op *= 100; }
  }
  stock.quarters = rows;
  status.textContent = `${rows.length}개 분기 적용됨`;
  document.getElementById("paste-box").value = "";
  refresh(true);
});

// ---------- 크로스헤어 + 툴팁 ----------
const tooltip = document.getElementById("tooltip");
const chartsBox = document.getElementById("charts");

function nearestQuarter(t) {
  const { c } = chartCtx;
  let best = 0, bd = Infinity;
  c.dates.forEach((d, i) => {
    const dist = Math.abs(d - t);
    if (dist < bd) { bd = dist; best = i; }
  });
  return best;
}
function showAt(t, clientX, clientY) {
  if (!chartCtx || !panels.length || !chartCtx.c.n) return;
  const { c, labels, est, xOf } = chartCtx;
  const qi = nearestQuarter(t);
  const snapT = c.dates[qi];
  const px = xOf(snapT);
  for (const p of panels) {
    p.cross.setAttribute("x1", px);
    p.cross.setAttribute("x2", px);
    p.cross.setAttribute("visibility", "visible");
  }
  tooltip.textContent = "";
  div("tt-title", tooltip, labels[qi] + (est[qi] ? " (E · 컨센서스)" : ""));
  const rows = [
    { colorVar: "--series-overall", name: "전체 이익률", val: fmt(c.overall[qi], 1) + "%" },
    { colorVar: "--series-inc", name: "증분 이익률", val: fmt(c.incremental[qi], 1) + "%" }];
  for (const r of rows) {
    const row = div("tt-row", tooltip);
    const key = document.createElement("span");
    key.className = "tt-key";
    key.style.background = `var(${r.colorVar})`;
    row.appendChild(key);
    const val = document.createElement("span");
    val.className = "tt-val";
    val.textContent = r.val;
    const name = document.createElement("span");
    name.className = "tt-name";
    name.textContent = r.name;
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
  if (!panels.length || !chartCtx) return;
  const rect = panels[0].svg.getBoundingClientRect();
  const relX = (e.clientX - rect.left) / rect.width * W;
  const { t0, t1 } = chartCtx;
  const t = t0 + (relX - PAD.l) / (W - PAD.l - PAD.r) * (t1 - t0);
  showAt(t, e.clientX, e.clientY);
});
chartsBox.addEventListener("pointerleave", hideTip);
chartsBox.addEventListener("keydown", e => {
  if (!chartCtx) return;
  const n = chartCtx.c.n;
  if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
    e.preventDefault();
    if (focusIndex < 0) focusIndex = n - 1;
    else focusIndex = e.key === "ArrowRight"
      ? Math.min(n - 1, focusIndex + 1) : Math.max(0, focusIndex - 1);
    const rect = chartsBox.getBoundingClientRect();
    showAt(chartCtx.c.dates[focusIndex], rect.left + 80, rect.top + 60);
  } else if (e.key === "Escape") { focusIndex = -1; hideTip(); }
});
chartsBox.addEventListener("blur", () => { focusIndex = -1; hideTip(); });

// ---------- 시작 ----------
if (!db.incMode) db.incMode = "qoq";
document.getElementById("yoy-toggle").checked = db.incMode === "yoy";
document.getElementById("stock-name").value = stock.name || stock.id;
refresh(true);
</script>
</body>
</html>
"""
