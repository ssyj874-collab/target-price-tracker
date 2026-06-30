"""
수급오실레이터 HTML 리포트 생성기
sugu_result.json을 읽어서 sugu_report.html을 생성합니다.
"""

import json
import webbrowser
from pathlib import Path

RESULT_FILE   = Path(__file__).parent / 'sugu_result.json'
SECTOR_FILE   = Path(__file__).parent / 'sector_result.json'
OUTPUT_FILE   = Path(__file__).parent / 'sugu_report.html'
UNIVERSE_FILE = Path(__file__).parent / 'universe_700.json'


def load_name_map() -> dict:
    """universe_700.json에서 ticker→한글명 매핑 로드"""
    if not UNIVERSE_FILE.exists():
        return {}
    data = json.loads(UNIVERSE_FILE.read_text())
    if data and isinstance(data[0], dict):
        return {d['ticker']: d.get('name', d['ticker']) for d in data}
    return {}


def load_sector_data() -> dict:
    """sector_result.json 로드 (없으면 빈 dict)"""
    if not SECTOR_FILE.exists():
        return {}
    return json.loads(SECTOR_FILE.read_text())


def generate():
    if not RESULT_FILE.exists():
        print(f"결과 파일 없음: {RESULT_FILE}")
        print("먼저 python3 sugu_calculator.py 를 실행하세요.")
        return

    result   = json.loads(RESULT_FILE.read_text())
    updated  = result.get('updated_at', '')
    ref_date = result.get('ref_date', '')
    data     = result.get('data', [])

    # universe_700.json 한글명으로 덮어쓰기
    name_map = load_name_map()
    for row in data:
        t = row.get('ticker', '')
        if t in name_map:
            row['name'] = name_map[t]

    # 테이블 행 (오실레이터 내림차순)
    data_by_osc = sorted(data, key=lambda x: x.get('oscillator', 0), reverse=True)

    rows_html = []
    for i, row in enumerate(data_by_osc, 1):
        ticker = row.get('ticker', '')
        name   = row.get('name', ticker)
        net20  = row.get('net20', 0) or 0
        net20_disp = f"{-net20:+,.1f}"
        macd   = row.get('macd', 0) or 0
        signal = row.get('signal', 0) or 0
        osc    = row.get('oscillator', 0) or 0
        date   = row.get('date', '')
        osc_color = '#e74c3c' if osc > 0 else '#3498db'

        rows_html.append(f"""<tr data-ticker="{ticker}" onclick="showChart('{ticker}')">
          <td class="rank">{i}</td>
          <td class="ticker">{ticker}</td>
          <td class="name">{name}</td>
          <td class="num">{net20_disp}</td>
          <td class="num osc" style="color:{osc_color};font-weight:bold">{osc:+.4f}%</td>
          <td class="num">{macd:+.4f}%</td>
          <td class="num">{signal:+.4f}%</td>
          <td class="date">{date}</td>
        </tr>""")

    rows_str = '\n'.join(rows_html)

    # 전체 데이터 JSON (히스토리 포함) - JS에서 사용
    all_data_json = json.dumps(
        {row['ticker']: row for row in data if 'ticker' in row},
        ensure_ascii=False
    )

    rd = ref_date
    ref_fmt = f"{rd[:4]}-{rd[4:6]}-{rd[6:]}" if len(rd) == 8 else rd

    # ── 업종별 탭 ──────────────────────────────────────────────────────────
    sector_data = load_sector_data()
    sector_rows_html = []
    sector_all_json = '{}'
    has_sector = bool(sector_data and sector_data.get('data'))
    if has_sector:
        sec_list = sector_data['data']
        for i, row in enumerate(sec_list, 1):
            code  = row.get('sector_code', '')
            name  = row.get('name', code)
            net20 = row.get('net20', 0) or 0
            osc   = row.get('oscillator', 0) or 0
            macd  = row.get('macd', 0) or 0
            sig   = row.get('signal', 0) or 0
            cnt   = row.get('member_count', 0)
            date  = row.get('date', '')
            net20_disp = f"{-net20:+,.1f}"
            osc_color = '#e74c3c' if osc > 0 else '#3498db'
            sector_rows_html.append(
                f"""<tr data-code="{code}" onclick="showSectorChart('{code}')">
              <td class="rank">{i}</td>
              <td class="ticker">{code}</td>
              <td class="name">{name}</td>
              <td class="num">{cnt}</td>
              <td class="num">{net20_disp}</td>
              <td class="num osc" style="color:{osc_color};font-weight:bold">{osc:+.4f}%</td>
              <td class="num">{macd:+.4f}%</td>
              <td class="num">{sig:+.4f}%</td>
              <td class="date">{date}</td>
            </tr>"""
            )
        sector_all_json = json.dumps(
            {row['sector_code']: row for row in sec_list if 'sector_code' in row},
            ensure_ascii=False
        )
    sector_rows_str = '\n'.join(sector_rows_html)

    sector_tab_display = 'inline-block' if has_sector else 'none'

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>수급오실레이터 리포트</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Apple SD Gothic Neo','Nanum Gothic',sans-serif;background:#0d1117;color:#e6edf3;}}
header{{padding:16px 24px;border-bottom:1px solid #21262d;display:flex;align-items:center;gap:16px;flex-wrap:wrap;}}
header h1{{font-size:1.3rem;color:#58a6ff;}}
header p{{font-size:0.82rem;color:#8b949e;margin-top:3px;}}

/* 탭 */
.tabs{{padding:0 24px;border-bottom:1px solid #21262d;display:flex;gap:0;}}
.tab-btn{{padding:10px 20px;background:none;border:none;border-bottom:2px solid transparent;
          color:#8b949e;font-size:0.9rem;cursor:pointer;font-family:inherit;transition:color 0.2s;}}
.tab-btn:hover{{color:#e6edf3;}}
.tab-btn.active{{color:#58a6ff;border-bottom-color:#58a6ff;}}
.tab-content{{display:none;}}
.tab-content.active{{display:block;}}

/* 차트 패널 */
.chart-panel{{background:#161b22;border-bottom:1px solid #21262d;padding:16px 24px;display:none;}}
.chart-panel.visible{{display:block;}}
.chart-panel h2{{font-size:0.95rem;color:#8b949e;margin-bottom:12px;}}
.chart-grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;}}
.chart-box{{background:#0d1117;border:1px solid #21262d;border-radius:8px;padding:12px;}}
.chart-box h3{{font-size:0.82rem;color:#8b949e;margin-bottom:8px;}}
canvas{{max-height:220px;}}

.container{{padding:16px 24px;}}
.toolbar{{display:flex;gap:10px;margin-bottom:14px;align-items:center;flex-wrap:wrap;}}
input[type=text]{{padding:6px 12px;border-radius:6px;border:1px solid #30363d;
                  background:#161b22;color:#e6edf3;font-size:0.88rem;width:220px;}}
select{{padding:6px 10px;border-radius:6px;border:1px solid #30363d;
        background:#161b22;color:#e6edf3;font-size:0.88rem;}}
.stat{{margin-left:auto;font-size:0.82rem;color:#8b949e;}}

/* 검색 자동완성 */
.search-wrap{{position:relative;}}
.autocomplete-list{{
  position:absolute;top:100%;left:0;z-index:1000;
  background:#1c2128;border:1px solid #30363d;border-radius:6px;
  width:320px;max-height:280px;overflow-y:auto;
  box-shadow:0 8px 24px rgba(0,0,0,0.5);display:none;margin-top:3px;
}}
.autocomplete-list.open{{display:block;}}
.ac-item{{
  display:flex;align-items:center;gap:10px;padding:8px 12px;
  cursor:pointer;border-bottom:1px solid #21262d;
}}
.ac-item:last-child{{border-bottom:none;}}
.ac-item:hover,.ac-item.focused{{background:#2d333b;}}
.ac-ticker{{font-family:monospace;color:#79c0ff;font-size:0.82rem;min-width:52px;}}
.ac-name{{color:#e6edf3;font-size:0.88rem;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
.ac-osc{{font-family:monospace;font-size:0.82rem;min-width:72px;text-align:right;}}

.table-wrap{{overflow-x:auto;}}
table{{width:100%;border-collapse:collapse;font-size:0.87rem;}}
thead tr{{background:#161b22;position:sticky;top:0;z-index:10;}}
th{{padding:9px 12px;text-align:right;color:#8b949e;font-weight:600;
    border-bottom:1px solid #21262d;white-space:nowrap;cursor:pointer;user-select:none;}}
th:hover{{color:#58a6ff;}}
th.left{{text-align:left;}}
td{{padding:7px 12px;border-bottom:1px solid #161b22;text-align:right;}}
td.rank{{color:#8b949e;font-size:0.78rem;}}
td.ticker{{font-family:monospace;color:#79c0ff;text-align:left;}}
td.name{{text-align:left;white-space:nowrap;max-width:200px;overflow:hidden;text-overflow:ellipsis;}}
td.num{{font-family:monospace;}}
td.date{{color:#8b949e;font-size:0.78rem;}}
tr:hover td{{background:#1c2128;cursor:pointer;}}
tr.active td{{background:#1f2937;}}
tr.hidden{{display:none;}}
</style>
</head>
<body>
<header>
  <div>
    <h1>📊 수급오실레이터 리포트</h1>
    <p>기준일: {ref_fmt} &nbsp;|&nbsp; 업데이트: {updated} &nbsp;|&nbsp; {len(data)}종목</p>
  </div>
</header>

<!-- 탭 -->
<div class="tabs">
  <button class="tab-btn active" onclick="switchTab('stock')">종목별</button>
  <button class="tab-btn" onclick="switchTab('sector')"
          style="display:{sector_tab_display}">업종별</button>
</div>

<!-- ══════════ 종목별 탭 ══════════ -->
<div id="tab-stock" class="tab-content active">

<!-- 종목별 차트 패널 -->
<div class="chart-panel" id="chartPanel">
  <h2 id="chartTitle">종목 차트</h2>
  <div class="chart-grid">
    <div class="chart-box">
      <h3>시가총액 + 기관/외국인 20일 누적합산(억원)</h3>
      <canvas id="chart1"></canvas>
    </div>
    <div class="chart-box">
      <h3>시가총액 + 수급오실레이터(%)</h3>
      <canvas id="chart2"></canvas>
    </div>
  </div>
</div>

<div class="container">
  <div class="toolbar">
    <div class="search-wrap">
      <input type="text" id="searchInput" placeholder="종목코드 / 종목명 검색"
             oninput="onSearchInput()" onkeydown="onSearchKey(event)" autocomplete="off">
      <div class="autocomplete-list" id="acList"></div>
    </div>
    <select id="oscFilter" onchange="filterTable()">
      <option value="all">전체</option>
      <option value="pos">오실레이터 양수</option>
      <option value="neg">오실레이터 음수</option>
    </select>
    <span class="stat" id="statText"></span>
  </div>
  <div class="table-wrap">
    <table id="dataTable">
      <thead><tr>
        <th class="left" onclick="sortTable('dataTable',0)">#</th>
        <th class="left" onclick="sortTable('dataTable',1)">코드</th>
        <th class="left" onclick="sortTable('dataTable',2)">종목명</th>
        <th onclick="sortTable('dataTable',3)">20일순매도합산(억)</th>
        <th onclick="sortTable('dataTable',4)">오실레이터(%)</th>
        <th onclick="sortTable('dataTable',5)">MACD(%)</th>
        <th onclick="sortTable('dataTable',6)">시그널(%)</th>
        <th onclick="sortTable('dataTable',7)">기준일</th>
      </tr></thead>
      <tbody>{rows_str}</tbody>
    </table>
  </div>
</div>

</div><!-- /tab-stock -->

<!-- ══════════ 업종별 탭 ══════════ -->
<div id="tab-sector" class="tab-content">

<!-- 업종별 차트 패널 -->
<div class="chart-panel" id="sectorChartPanel">
  <h2 id="sectorChartTitle">업종 차트</h2>
  <div class="chart-grid">
    <div class="chart-box">
      <h3>시가총액 + 기관/외국인 20일 누적합산(억원)</h3>
      <canvas id="secChart1"></canvas>
    </div>
    <div class="chart-box">
      <h3>시가총액 + 수급오실레이터(%)</h3>
      <canvas id="secChart2"></canvas>
    </div>
  </div>
</div>

<div class="container">
  <div class="toolbar">
    <input type="text" id="secSearch" placeholder="업종코드 / 업종명 검색"
           oninput="filterSectorTable()" autocomplete="off">
    <select id="secOscFilter" onchange="filterSectorTable()">
      <option value="all">전체</option>
      <option value="pos">오실레이터 양수 (매수세)</option>
      <option value="neg">오실레이터 음수 (매도세)</option>
    </select>
    <span class="stat" id="secStatText"></span>
  </div>
  <div class="table-wrap">
    <table id="sectorTable">
      <thead><tr>
        <th class="left" onclick="sortTable('sectorTable',0)">#</th>
        <th class="left" onclick="sortTable('sectorTable',1)">업종코드</th>
        <th class="left" onclick="sortTable('sectorTable',2)">업종명</th>
        <th onclick="sortTable('sectorTable',3)">구성종목수</th>
        <th onclick="sortTable('sectorTable',4)">20일순매도합산(억)</th>
        <th onclick="sortTable('sectorTable',5)">오실레이터(%)</th>
        <th onclick="sortTable('sectorTable',6)">MACD(%)</th>
        <th onclick="sortTable('sectorTable',7)">시그널(%)</th>
        <th onclick="sortTable('sectorTable',8)">기준일</th>
      </tr></thead>
      <tbody>{sector_rows_str}</tbody>
    </table>
  </div>
</div>

</div><!-- /tab-sector -->

<script>
const ALL_DATA    = {all_data_json};
const SECTOR_DATA = {sector_all_json};

// ── 탭 전환 ──────────────────────────────────────────────────────────────
function switchTab(name) {{
  document.querySelectorAll('.tab-content').forEach(el =>
    el.classList.toggle('active', el.id === 'tab-' + name));
  document.querySelectorAll('.tab-btn').forEach((btn, i) => {{
    const names = ['stock','sector'];
    btn.classList.toggle('active', names[i] === name);
  }});
}}

// ── 종목 차트 ─────────────────────────────────────────────────────────────
let chart1 = null, chart2 = null;

function showChart(ticker) {{
  const d = ALL_DATA[ticker];
  if (!d || !d.history) return;

  document.querySelectorAll('#tab-stock tr.active').forEach(r => r.classList.remove('active'));
  const row = document.querySelector(`#dataTable tr[data-ticker="${{ticker}}"]`);
  if (row) row.classList.add('active');

  const hist   = d.history;
  const labels = hist.map(h => h.date);
  const mktcap = hist.map(h => h.mktcap);
  const net20  = hist.map(h => h.net20 !== null ? -h.net20 : null);
  const osc    = hist.map(h => h.osc);

  document.getElementById('chartTitle').textContent =
    `${{d.name || ticker}} (${{ticker}}) — 기준일 ${{d.date}}`;
  document.getElementById('chartPanel').classList.add('visible');

  const gridColor = '#21262d', tickColor = '#8b949e';

  if (chart1) chart1.destroy();
  chart1 = new Chart(document.getElementById('chart1'), {{
    data: {{ labels, datasets: [
      {{ type:'line', label:'시가총액(억)', data:mktcap, yAxisID:'y1',
         borderColor:'#3498db', backgroundColor:'transparent', borderWidth:1.5, pointRadius:0, tension:0.3 }},
      {{ type:'line', label:'20일순매도합산(억)', data:net20, yAxisID:'y2',
         borderColor:'#e74c3c', backgroundColor:'transparent', borderWidth:1.5, pointRadius:0, tension:0.3 }},
    ]}},
    options: {{ responsive:true, interaction:{{mode:'index',intersect:false}},
      plugins:{{ legend:{{ labels:{{ color:tickColor, font:{{size:11}} }} }} }},
      scales:{{
        x:{{ ticks:{{ color:tickColor, maxTicksLimit:8, font:{{size:10}} }}, grid:{{ color:gridColor }} }},
        y1:{{ position:'left',  ticks:{{ color:'#3498db', font:{{size:10}} }}, grid:{{ color:gridColor }} }},
        y2:{{ position:'right', ticks:{{ color:'#e74c3c', font:{{size:10}} }}, grid:{{ drawOnChartArea:false }} }},
      }}
    }}
  }});

  if (chart2) chart2.destroy();
  chart2 = new Chart(document.getElementById('chart2'), {{
    data: {{ labels, datasets: [
      {{ type:'line', label:'시가총액(억)', data:mktcap, yAxisID:'y1',
         borderColor:'#2ecc71', backgroundColor:'transparent', borderWidth:1.5, pointRadius:0, tension:0.3 }},
      {{ type:'line', label:'수급오실레이터(%)', data:osc, yAxisID:'y2',
         borderColor:'#e74c3c', backgroundColor:'transparent', borderWidth:1.5, pointRadius:0, tension:0.3 }},
    ]}},
    options: {{ responsive:true, interaction:{{mode:'index',intersect:false}},
      plugins:{{ legend:{{ labels:{{ color:tickColor, font:{{size:11}} }} }} }},
      scales:{{
        x:{{ ticks:{{ color:tickColor, maxTicksLimit:8, font:{{size:10}} }}, grid:{{ color:gridColor }} }},
        y1:{{ position:'left',  ticks:{{ color:'#2ecc71', font:{{size:10}} }}, grid:{{ color:gridColor }} }},
        y2:{{ position:'right', ticks:{{ color:'#e74c3c', callback:v=>v.toFixed(2)+'%', font:{{size:10}} }},
              grid:{{ drawOnChartArea:false }} }},
      }}
    }}
  }});

  document.getElementById('chartPanel').scrollIntoView({{behavior:'smooth',block:'start'}});
}}

// ── 업종 차트 ─────────────────────────────────────────────────────────────
let secChart1 = null, secChart2 = null;

function showSectorChart(code) {{
  const d = SECTOR_DATA[code];
  if (!d || !d.history || !d.history.length) return;

  document.querySelectorAll('#sectorTable tr.active').forEach(r => r.classList.remove('active'));
  const row = document.querySelector(`#sectorTable tr[data-code="${{code}}"]`);
  if (row) row.classList.add('active');

  const hist   = d.history;
  const labels = hist.map(h => h.date);
  const mktcap = hist.map(h => h.mktcap);
  const net20  = hist.map(h => h.net20 !== null ? -h.net20 : null);
  const osc    = hist.map(h => h.osc);

  document.getElementById('sectorChartTitle').textContent =
    `${{d.name || code}} (${{code}}) — 기준일 ${{d.date}}`;
  document.getElementById('sectorChartPanel').classList.add('visible');

  const gridColor = '#21262d', tickColor = '#8b949e';

  if (secChart1) secChart1.destroy();
  secChart1 = new Chart(document.getElementById('secChart1'), {{
    data: {{ labels, datasets: [
      {{ type:'line', label:'업종시총합(억)', data:mktcap, yAxisID:'y1',
         borderColor:'#3498db', backgroundColor:'transparent', borderWidth:1.5, pointRadius:0, tension:0.3 }},
      {{ type:'line', label:'업종20일순매도합산(억)', data:net20, yAxisID:'y2',
         borderColor:'#e74c3c', backgroundColor:'transparent', borderWidth:1.5, pointRadius:0, tension:0.3 }},
    ]}},
    options: {{ responsive:true, interaction:{{mode:'index',intersect:false}},
      plugins:{{ legend:{{ labels:{{ color:tickColor, font:{{size:11}} }} }} }},
      scales:{{
        x:{{ ticks:{{ color:tickColor, maxTicksLimit:8, font:{{size:10}} }}, grid:{{ color:gridColor }} }},
        y1:{{ position:'left',  ticks:{{ color:'#3498db', font:{{size:10}} }}, grid:{{ color:gridColor }} }},
        y2:{{ position:'right', ticks:{{ color:'#e74c3c', font:{{size:10}} }}, grid:{{ drawOnChartArea:false }} }},
      }}
    }}
  }});

  if (secChart2) secChart2.destroy();
  secChart2 = new Chart(document.getElementById('secChart2'), {{
    data: {{ labels, datasets: [
      {{ type:'line', label:'업종시총합(억)', data:mktcap, yAxisID:'y1',
         borderColor:'#2ecc71', backgroundColor:'transparent', borderWidth:1.5, pointRadius:0, tension:0.3 }},
      {{ type:'line', label:'업종오실레이터(%)', data:osc, yAxisID:'y2',
         borderColor:'#e74c3c', backgroundColor:'transparent', borderWidth:1.5, pointRadius:0, tension:0.3 }},
    ]}},
    options: {{ responsive:true, interaction:{{mode:'index',intersect:false}},
      plugins:{{ legend:{{ labels:{{ color:tickColor, font:{{size:11}} }} }} }},
      scales:{{
        x:{{ ticks:{{ color:tickColor, maxTicksLimit:8, font:{{size:10}} }}, grid:{{ color:gridColor }} }},
        y1:{{ position:'left',  ticks:{{ color:'#2ecc71', font:{{size:10}} }}, grid:{{ color:gridColor }} }},
        y2:{{ position:'right', ticks:{{ color:'#e74c3c', callback:v=>v.toFixed(2)+'%', font:{{size:10}} }},
              grid:{{ drawOnChartArea:false }} }},
      }}
    }}
  }});

  document.getElementById('sectorChartPanel').scrollIntoView({{behavior:'smooth',block:'start'}});
}}

// ── 종목 자동완성 ─────────────────────────────────────────────────────────
const STOCK_LIST = Object.values(ALL_DATA).map(d => ({{
  ticker: d.ticker, name: d.name || d.ticker, osc: d.oscillator || 0,
}}));

let acFocus = -1;

function onSearchInput() {{
  filterTable();
  const q = document.getElementById('searchInput').value.trim().toLowerCase();
  const list = document.getElementById('acList');
  if (!q) {{ list.classList.remove('open'); return; }}

  const matches = STOCK_LIST.filter(s =>
    s.ticker.toLowerCase().includes(q) || s.name.toLowerCase().includes(q)
  ).slice(0, 15);

  if (!matches.length) {{ list.classList.remove('open'); return; }}

  list.innerHTML = matches.map((s, i) => {{
    const color = s.osc > 0 ? '#e74c3c' : '#3498db';
    return `<div class="ac-item" data-ticker="${{s.ticker}}" data-idx="${{i}}"
                 onmousedown="selectAc('${{s.ticker}}')" onmouseover="setFocus(${{i}})">
      <span class="ac-ticker">${{s.ticker}}</span>
      <span class="ac-name">${{s.name}}</span>
      <span class="ac-osc" style="color:${{color}}">${{s.osc >= 0 ? '+' : ''}}${{s.osc.toFixed(4)}}%</span>
    </div>`;
  }}).join('');
  acFocus = -1;
  list.classList.add('open');
}}

function setFocus(idx) {{
  acFocus = idx;
  document.querySelectorAll('.ac-item').forEach((el, i) =>
    el.classList.toggle('focused', i === idx));
}}

function onSearchKey(e) {{
  const items = document.querySelectorAll('.ac-item');
  if (e.key === 'ArrowDown') {{
    e.preventDefault();
    acFocus = Math.min(acFocus + 1, items.length - 1);
    items.forEach((el, i) => el.classList.toggle('focused', i === acFocus));
    if (items[acFocus]) items[acFocus].scrollIntoView({{block:'nearest'}});
  }} else if (e.key === 'ArrowUp') {{
    e.preventDefault();
    acFocus = Math.max(acFocus - 1, 0);
    items.forEach((el, i) => el.classList.toggle('focused', i === acFocus));
    if (items[acFocus]) items[acFocus].scrollIntoView({{block:'nearest'}});
  }} else if (e.key === 'Enter') {{
    if (acFocus >= 0 && items[acFocus]) {{
      selectAc(items[acFocus].dataset.ticker);
    }} else if (items.length > 0) {{
      selectAc(items[0].dataset.ticker);
    }}
  }} else if (e.key === 'Escape') {{
    document.getElementById('acList').classList.remove('open');
  }}
}}

function selectAc(ticker) {{
  const d = ALL_DATA[ticker];
  if (!d) return;
  document.getElementById('searchInput').value = d.name || ticker;
  document.getElementById('acList').classList.remove('open');
  filterTable();
  showChart(ticker);
  const row = document.querySelector(`#dataTable tr[data-ticker="${{ticker}}"]`);
  if (row) setTimeout(() => row.scrollIntoView({{behavior:'smooth', block:'center'}}), 300);
}}

document.addEventListener('click', e => {{
  if (!e.target.closest('.search-wrap'))
    document.getElementById('acList').classList.remove('open');
}});

// ── 테이블 필터 ───────────────────────────────────────────────────────────
function filterTable() {{
  const q   = document.getElementById('searchInput').value.toLowerCase();
  const flt = document.getElementById('oscFilter').value;
  const rows = document.querySelectorAll('#dataTable tbody tr');
  let visible = 0;
  rows.forEach(tr => {{
    const ticker = tr.querySelector('td.ticker')?.textContent.toLowerCase() || '';
    const name   = tr.querySelector('td.name')?.textContent.toLowerCase() || '';
    const oscVal = parseFloat(tr.querySelector('td.osc')?.textContent) || 0;
    const zone   = tr.dataset.zone || '';
    const matchQ   = !q || ticker.includes(q) || name.includes(q);
    const matchFlt = flt==='all'
      || (flt==='pos' && oscVal>0)
      || (flt==='neg' && oscVal<0);
    tr.classList.toggle('hidden', !(matchQ && matchFlt));
    if (matchQ && matchFlt) visible++;
  }});
  document.getElementById('statText').textContent = `${{visible}}종목 표시 중`;
}}

function filterSectorTable() {{
  const q   = document.getElementById('secSearch').value.toLowerCase();
  const flt = document.getElementById('secOscFilter').value;
  const rows = document.querySelectorAll('#sectorTable tbody tr');
  let visible = 0;
  rows.forEach(tr => {{
    const code = tr.querySelector('td.ticker')?.textContent.toLowerCase() || '';
    const name = tr.querySelector('td.name')?.textContent.toLowerCase() || '';
    const oscVal = parseFloat(tr.querySelector('td.osc')?.textContent) || 0;
    const matchQ   = !q || code.includes(q) || name.includes(q);
    const matchFlt = flt==='all'||(flt==='pos'&&oscVal>0)||(flt==='neg'&&oscVal<0);
    tr.classList.toggle('hidden', !(matchQ && matchFlt));
    if (matchQ && matchFlt) visible++;
  }});
  document.getElementById('secStatText').textContent = `${{visible}}업종 표시 중`;
}}

// ── 테이블 정렬 ───────────────────────────────────────────────────────────
const sortDir = {{}};
function sortTable(tableId, col) {{
  const tbody = document.querySelector(`#${{tableId}} tbody`);
  const rows  = Array.from(tbody.querySelectorAll('tr'));
  const key   = tableId + '_' + col;
  const asc   = (sortDir[key] = !sortDir[key]);
  rows.sort((a, b) => {{
    const av = a.querySelectorAll('td')[col]?.textContent.replace(/[,%+]/g,'').trim()||'';
    const bv = b.querySelectorAll('td')[col]?.textContent.replace(/[,%+]/g,'').trim()||'';
    const an = parseFloat(av), bn = parseFloat(bv);
    if (!isNaN(an)&&!isNaN(bn)) return asc?an-bn:bn-an;
    return asc?av.localeCompare(bv,'ko'):bv.localeCompare(av,'ko');
  }});
  rows.forEach(r => tbody.appendChild(r));
}}

filterTable();
filterSectorTable();
</script>
</body>
</html>"""

    OUTPUT_FILE.write_text(html, encoding='utf-8')
    print(f"리포트 생성 완료: {OUTPUT_FILE} ({len(data)}종목)")
    webbrowser.open(f'file://{OUTPUT_FILE.resolve()}')


if __name__ == '__main__':
    generate()
