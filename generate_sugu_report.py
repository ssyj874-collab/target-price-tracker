"""
수급오실레이터 HTML 리포트 생성기
sugu_result.json을 읽어서 sugu_report.html을 생성합니다.
"""

import json
import webbrowser
from pathlib import Path
from datetime import datetime

RESULT_FILE = Path(__file__).parent / 'sugu_result.json'
OUTPUT_FILE = Path(__file__).parent / 'sugu_report.html'

# 종목명 조회 (universe_700.json 캐시 기반)
def load_names() -> dict:
    cache_dir = Path(__file__).parent / '.cache'
    names = {}
    for f in sorted(cache_dir.glob('universe_kis_*.json'), reverse=True):
        try:
            data = json.loads(f.read_text())
            if isinstance(data, list) and data and isinstance(data[0], dict):
                for d in data:
                    if d.get('ticker') and d.get('name'):
                        names[d['ticker']] = d['name']
        except Exception:
            pass
        if names:
            break
    return names


def generate():
    if not RESULT_FILE.exists():
        print(f"결과 파일 없음: {RESULT_FILE}")
        print("먼저 python3 sugu_calculator.py 를 실행하세요.")
        return

    result = json.loads(RESULT_FILE.read_text())
    updated_at = result.get('updated_at', '')
    ref_date   = result.get('ref_date', '')
    data       = result.get('data', [])

    names = load_names()

    # 데이터 정렬: oscillator 기준 내림차순
    data_sorted = sorted(data, key=lambda x: x.get('oscillator', 0), reverse=True)

    # 테이블 행 생성
    rows_html = []
    for i, row in enumerate(data_sorted, 1):
        ticker = row.get('ticker', '')
        name   = names.get(ticker, ticker)
        net20  = row.get('net20', 0)
        macd   = row.get('macd', 0)
        signal = row.get('signal', 0)
        osc    = row.get('oscillator', 0)
        date   = row.get('date', '')

        osc_color  = '#c0392b' if osc > 0 else '#2980b9'
        net20_disp = f"{net20:,.1f}" if net20 is not None else '-'

        rows_html.append(f"""
        <tr>
          <td class="rank">{i}</td>
          <td class="ticker">{ticker}</td>
          <td class="name">{name}</td>
          <td class="num">{net20_disp}</td>
          <td class="num" style="color:{osc_color};font-weight:bold">{osc:+.4f}%</td>
          <td class="num">{macd:+.4f}%</td>
          <td class="num">{signal:+.4f}%</td>
          <td class="date">{date}</td>
        </tr>""")

    rows_str = '\n'.join(rows_html)

    # 차트 데이터 (f-string 밖에서 미리 직렬화)
    chart_data_json = json.dumps([
        {'l': names.get(r.get('ticker',''), r.get('ticker','')), 'v': r.get('oscillator', 0)}
        for r in data_sorted
    ], ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>수급오실레이터 리포트</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Apple SD Gothic Neo', 'Nanum Gothic', sans-serif; background: #0d1117; color: #e6edf3; }}
    header {{ padding: 20px 24px; border-bottom: 1px solid #21262d; }}
    header h1 {{ font-size: 1.4rem; color: #58a6ff; }}
    header p  {{ font-size: 0.85rem; color: #8b949e; margin-top: 4px; }}
    .container {{ padding: 20px 24px; max-width: 1400px; margin: 0 auto; }}

    /* 탭 */
    .tabs {{ display: flex; gap: 8px; margin-bottom: 20px; }}
    .tab {{ padding: 8px 18px; border-radius: 6px; cursor: pointer; font-size: 0.9rem;
            background: #21262d; color: #8b949e; border: 1px solid #30363d; }}
    .tab.active {{ background: #1f6feb; color: #fff; border-color: #1f6feb; }}

    /* 필터/검색 */
    .toolbar {{ display: flex; gap: 12px; margin-bottom: 16px; align-items: center; flex-wrap: wrap; }}
    input[type=text] {{ padding: 6px 12px; border-radius: 6px; border: 1px solid #30363d;
                        background: #161b22; color: #e6edf3; font-size: 0.9rem; width: 200px; }}
    select {{ padding: 6px 10px; border-radius: 6px; border: 1px solid #30363d;
              background: #161b22; color: #e6edf3; font-size: 0.9rem; }}
    .stat {{ margin-left: auto; font-size: 0.85rem; color: #8b949e; }}

    /* 테이블 */
    .table-wrap {{ overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}
    thead tr {{ background: #161b22; }}
    th {{ padding: 10px 12px; text-align: right; color: #8b949e; font-weight: 600;
          border-bottom: 1px solid #21262d; white-space: nowrap; cursor: pointer; user-select: none; }}
    th:hover {{ color: #58a6ff; }}
    th.left {{ text-align: left; }}
    td {{ padding: 8px 12px; border-bottom: 1px solid #21262d; text-align: right; }}
    td.rank {{ color: #8b949e; font-size: 0.8rem; }}
    td.ticker {{ font-family: monospace; color: #79c0ff; text-align: left; }}
    td.name {{ text-align: left; white-space: nowrap; }}
    td.num  {{ font-family: monospace; }}
    td.date {{ color: #8b949e; font-size: 0.8rem; }}
    tr:hover td {{ background: #1c2128; }}
    tr.hidden {{ display: none; }}

    /* 차트 */
    .chart-section {{ margin-bottom: 28px; }}
    .chart-section h2 {{ font-size: 1rem; color: #8b949e; margin-bottom: 12px; }}
    .chart-wrap {{ background: #161b22; border: 1px solid #21262d; border-radius: 8px; padding: 16px; }}
    canvas {{ max-height: 280px; }}
  </style>
</head>
<body>
<header>
  <h1>📊 수급오실레이터 리포트</h1>
  <p>기준일: {ref_date[:4]}-{ref_date[4:6]}-{ref_date[6:]} &nbsp;|&nbsp; 업데이트: {updated_at} &nbsp;|&nbsp; {len(data)}종목</p>
</header>

<div class="container">

  <!-- 차트 -->
  <div class="chart-section">
    <h2>수급오실레이터 분포 (상위/하위 50종목)</h2>
    <div class="chart-wrap">
      <canvas id="oscChart"></canvas>
    </div>
  </div>

  <!-- 툴바 -->
  <div class="toolbar">
    <input type="text" id="searchInput" placeholder="종목코드 / 종목명 검색" oninput="filterTable()">
    <select id="oscFilter" onchange="filterTable()">
      <option value="all">전체</option>
      <option value="pos">오실레이터 양수 (매수세)</option>
      <option value="neg">오실레이터 음수 (매도세)</option>
    </select>
    <span class="stat" id="statText"></span>
  </div>

  <!-- 테이블 -->
  <div class="table-wrap">
    <table id="dataTable">
      <thead>
        <tr>
          <th class="left" onclick="sortTable(0)">#</th>
          <th class="left" onclick="sortTable(1)">코드</th>
          <th class="left" onclick="sortTable(2)">종목명</th>
          <th onclick="sortTable(3)">20일누적합산(억)</th>
          <th onclick="sortTable(4)">오실레이터(%)</th>
          <th onclick="sortTable(5)">MACD(%)</th>
          <th onclick="sortTable(6)">시그널(%)</th>
          <th onclick="sortTable(7)">기준일</th>
        </tr>
      </thead>
      <tbody>
        {rows_str}
      </tbody>
    </table>
  </div>
</div>

<script>
// 차트 (상위 25 + 하위 25)
const allData = {chart_data_json};
const top25  = allData.slice(0, 25);
const bot25  = allData.slice(-25).reverse();
const chartData = [...top25, ...bot25];

new Chart(document.getElementById('oscChart'), {{
  type: 'bar',
  data: {{
    labels: chartData.map(d => d.l),
    datasets: [{{
      data: chartData.map(d => d.v),
      backgroundColor: chartData.map(d => d.v > 0 ? 'rgba(192,57,43,0.75)' : 'rgba(41,128,185,0.75)'),
      borderWidth: 0,
    }}]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ display: false }}, tooltip: {{
      callbacks: {{ label: ctx => ctx.parsed.y.toFixed(4) + '%' }}
    }} }},
    scales: {{
      x: {{ ticks: {{ color: '#8b949e', font: {{ size: 10 }} }}, grid: {{ color: '#21262d' }} }},
      y: {{ ticks: {{ color: '#8b949e', callback: v => v.toFixed(2)+'%' }}, grid: {{ color: '#21262d' }} }}
    }}
  }}
}});

// 테이블 필터
function filterTable() {{
  const q   = document.getElementById('searchInput').value.toLowerCase();
  const flt = document.getElementById('oscFilter').value;
  const rows = document.querySelectorAll('#dataTable tbody tr');
  let visible = 0;
  rows.forEach(tr => {{
    const ticker = tr.querySelector('td.ticker')?.textContent.toLowerCase() || '';
    const name   = tr.querySelector('td.name')?.textContent.toLowerCase() || '';
    const oscEl  = tr.querySelectorAll('td')[4];
    const oscVal = parseFloat(oscEl?.textContent) || 0;
    const matchQ   = !q || ticker.includes(q) || name.includes(q);
    const matchFlt = flt === 'all' || (flt === 'pos' && oscVal > 0) || (flt === 'neg' && oscVal < 0);
    tr.classList.toggle('hidden', !(matchQ && matchFlt));
    if (matchQ && matchFlt) visible++;
  }});
  document.getElementById('statText').textContent = `${{visible}}종목 표시 중`;
}}

// 테이블 정렬
let sortDir = {{}};
function sortTable(col) {{
  const tbody = document.querySelector('#dataTable tbody');
  const rows  = Array.from(tbody.querySelectorAll('tr'));
  const asc   = (sortDir[col] = !sortDir[col]);
  rows.sort((a, b) => {{
    const av = a.querySelectorAll('td')[col]?.textContent.replace(/[,%+]/g,'').trim() || '';
    const bv = b.querySelectorAll('td')[col]?.textContent.replace(/[,%+]/g,'').trim() || '';
    const an = parseFloat(av), bn = parseFloat(bv);
    if (!isNaN(an) && !isNaN(bn)) return asc ? an - bn : bn - an;
    return asc ? av.localeCompare(bv) : bv.localeCompare(av);
  }});
  rows.forEach(r => tbody.appendChild(r));
}}

filterTable();
</script>
</body>
</html>"""

    OUTPUT_FILE.write_text(html, encoding='utf-8')
    print(f"리포트 생성 완료: {OUTPUT_FILE}")
    print(f"  {len(data)}종목, 기준일: {ref_date}")
    webbrowser.open(f'file://{OUTPUT_FILE.resolve()}')


if __name__ == '__main__':
    generate()
