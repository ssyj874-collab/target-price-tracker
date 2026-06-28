"""
수급오실레이터 HTML 리포트 생성기
sugu_result.json을 읽어서 sugu_report.html을 생성합니다.
"""

import json
import webbrowser
from pathlib import Path

RESULT_FILE = Path(__file__).parent / 'sugu_result.json'
OUTPUT_FILE = Path(__file__).parent / 'sugu_report.html'


def generate():
    if not RESULT_FILE.exists():
        print(f"결과 파일 없음: {RESULT_FILE}")
        print("먼저 python3 sugu_calculator.py 를 실행하세요.")
        return

    result   = json.loads(RESULT_FILE.read_text())
    updated  = result.get('updated_at', '')
    ref_date = result.get('ref_date', '')
    data     = result.get('data', [])

    # 테이블 행 (net20 순매도 기준 정렬: 원본 net20이 음수=순매수, 양수=순매도)
    data_by_net = sorted(data, key=lambda x: x.get('net20', 0))  # 가장 많이 순매도한 것이 앞
    data_by_osc = sorted(data, key=lambda x: x.get('oscillator', 0), reverse=True)

    rows_html = []
    for i, row in enumerate(data_by_osc, 1):
        ticker = row.get('ticker', '')
        name   = row.get('name', ticker)
        net20  = row.get('net20', 0) or 0
        net20_disp = f"{-net20:+,.1f}"  # 순매도 양수로 표시
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
header{{padding:16px 24px;border-bottom:1px solid #21262d;display:flex;align-items:center;gap:16px;}}
header h1{{font-size:1.3rem;color:#58a6ff;}}
header p{{font-size:0.82rem;color:#8b949e;margin-top:3px;}}

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
td.name{{text-align:left;white-space:nowrap;max-width:160px;overflow:hidden;text-overflow:ellipsis;}}
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
    <input type="text" id="searchInput" placeholder="종목코드 / 종목명 검색" oninput="filterTable()">
    <select id="oscFilter" onchange="filterTable()">
      <option value="all">전체</option>
      <option value="pos">오실레이터 양수 (매수세)</option>
      <option value="neg">오실레이터 음수 (매도세)</option>
    </select>
    <span class="stat" id="statText"></span>
  </div>
  <div class="table-wrap">
    <table id="dataTable">
      <thead><tr>
        <th class="left" onclick="sortTable(0)">#</th>
        <th class="left" onclick="sortTable(1)">코드</th>
        <th class="left" onclick="sortTable(2)">종목명</th>
        <th onclick="sortTable(3)">20일순매도합산(억)</th>
        <th onclick="sortTable(4)">오실레이터(%)</th>
        <th onclick="sortTable(5)">MACD(%)</th>
        <th onclick="sortTable(6)">시그널(%)</th>
        <th onclick="sortTable(7)">기준일</th>
      </tr></thead>
      <tbody>{rows_str}</tbody>
    </table>
  </div>
</div>

<script>
const ALL_DATA = {all_data_json};

let chart1 = null, chart2 = null;

function showChart(ticker) {{
  const d = ALL_DATA[ticker];
  if (!d || !d.history) return;

  // 행 하이라이트
  document.querySelectorAll('tr.active').forEach(r => r.classList.remove('active'));
  const row = document.querySelector(`tr[data-ticker="${{ticker}}"]`);
  if (row) row.classList.add('active');

  const hist    = d.history;
  const labels  = hist.map(h => h.date);
  const mktcap  = hist.map(h => h.mktcap);
  const net20   = hist.map(h => h.net20 !== null ? -h.net20 : null); // 순매도 양수
  const osc     = hist.map(h => h.osc);

  document.getElementById('chartTitle').textContent =
    `${{d.name || ticker}} (${{ticker}}) — 기준일 ${{d.date}}`;
  document.getElementById('chartPanel').classList.add('visible');

  const gridColor = '#21262d';
  const tickColor = '#8b949e';

  // 차트1: 시가총액 + 20일 누적합산
  if (chart1) chart1.destroy();
  chart1 = new Chart(document.getElementById('chart1'), {{
    data: {{
      labels,
      datasets: [
        {{ type:'line', label:'시가총액(억)', data:mktcap, yAxisID:'y1',
           borderColor:'#3498db', backgroundColor:'transparent', borderWidth:1.5,
           pointRadius:0, tension:0.3 }},
        {{ type:'bar',  label:'20일순매도합산(억)', data:net20, yAxisID:'y2',
           backgroundColor: net20.map(v => v > 0 ? 'rgba(231,76,60,0.6)' : 'rgba(52,152,219,0.6)'),
           borderWidth:0 }},
      ]
    }},
    options: {{
      responsive:true, interaction:{{mode:'index',intersect:false}},
      plugins:{{ legend:{{ labels:{{ color:tickColor, font:{{size:11}} }} }} }},
      scales:{{
        x:{{ ticks:{{ color:tickColor, maxTicksLimit:8, font:{{size:10}} }}, grid:{{ color:gridColor }} }},
        y1:{{ position:'left',  ticks:{{ color:'#3498db', font:{{size:10}} }}, grid:{{ color:gridColor }} }},
        y2:{{ position:'right', ticks:{{ color:'#e74c3c', font:{{size:10}} }}, grid:{{ drawOnChartArea:false }} }},
      }}
    }}
  }});

  // 차트2: 시가총액 + 오실레이터
  if (chart2) chart2.destroy();
  chart2 = new Chart(document.getElementById('chart2'), {{
    data: {{
      labels,
      datasets: [
        {{ type:'line', label:'시가총액(억)', data:mktcap, yAxisID:'y1',
           borderColor:'#2ecc71', backgroundColor:'transparent', borderWidth:1.5,
           pointRadius:0, tension:0.3 }},
        {{ type:'line', label:'수급오실레이터(%)', data:osc, yAxisID:'y2',
           borderColor:'#e74c3c', backgroundColor:'transparent', borderWidth:1.5,
           pointRadius:0, tension:0.3 }},
      ]
    }},
    options: {{
      responsive:true, interaction:{{mode:'index',intersect:false}},
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

function filterTable() {{
  const q   = document.getElementById('searchInput').value.toLowerCase();
  const flt = document.getElementById('oscFilter').value;
  const rows = document.querySelectorAll('#dataTable tbody tr');
  let visible = 0;
  rows.forEach(tr => {{
    const ticker = tr.querySelector('td.ticker')?.textContent.toLowerCase() || '';
    const name   = tr.querySelector('td.name')?.textContent.toLowerCase() || '';
    const oscVal = parseFloat(tr.querySelector('td.osc')?.textContent) || 0;
    const matchQ   = !q || ticker.includes(q) || name.includes(q);
    const matchFlt = flt==='all'||(flt==='pos'&&oscVal>0)||(flt==='neg'&&oscVal<0);
    tr.classList.toggle('hidden', !(matchQ && matchFlt));
    if (matchQ && matchFlt) visible++;
  }});
  document.getElementById('statText').textContent = `${{visible}}종목 표시 중`;
}}

let sortDir = {{}};
function sortTable(col) {{
  const tbody = document.querySelector('#dataTable tbody');
  const rows  = Array.from(tbody.querySelectorAll('tr'));
  const asc   = (sortDir[col] = !sortDir[col]);
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
</script>
</body>
</html>"""

    OUTPUT_FILE.write_text(html, encoding='utf-8')
    print(f"리포트 생성 완료: {OUTPUT_FILE} ({len(data)}종목)")
    webbrowser.open(f'file://{OUTPUT_FILE.resolve()}')


if __name__ == '__main__':
    generate()
