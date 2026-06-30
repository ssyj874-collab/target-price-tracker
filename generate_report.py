"""
SIO 리포트 생성기
실행하면 sio_report.html 파일을 만들고 브라우저에서 자동으로 엽니다.

사용법:
  python3 generate_report.py          # 오늘 기준 1년치
  python3 generate_report.py --days 60  # 최근 60일
"""

import os
import sys
import argparse
import webbrowser
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

os.environ.setdefault('KRX_ID', 'syj6718')
os.environ.setdefault('KRX_PW', 'song135!')

PANIC_BUY  =  80
PANIC_SELL = -80


def fetch_sio_range(market: str, fromdate: str, todate: str) -> pd.DataFrame:
    from pykrx import stock
    from sio_calculator import get_market_data, calc_sio_from_raw

    index_ticker = '1001' if market == 'KOSPI' else '2001'
    try:
        trading_days = stock.get_index_ohlcv_by_date(fromdate, todate, index_ticker).index
    except Exception as e:
        print(f"[{market}] 거래일 조회 실패: {e}")
        return pd.DataFrame()

    rows = []
    total = len(trading_days)
    for i, dt in enumerate(trading_days, 1):
        date_str = dt.strftime('%Y%m%d')
        print(f"\r  [{market}] {i:3d}/{total} {date_str}...", end='', flush=True)
        try:
            df = get_market_data(market, date_str)
            if df.empty:
                continue
            r = calc_sio_from_raw(df)
            rows.append({
                'date': date_str,
                'sio':  round(r['sio'], 2),
                'J':    round(r['J'], 4),
                'K':    round(r['K'], 4),
                'D':    round(r['D'], 4),
                'advancing': r['advancing'],
                'declining': r['declining'],
            })
        except Exception as e:
            print(f"\n  [WARN] {date_str}: {e}")
    print()

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values('date', ascending=False).set_index('date')


def signal_label(sio: float) -> str:
    if sio >= PANIC_BUY:
        return '패닉 바잉 🔴'
    if sio <= PANIC_SELL:
        return '패닉 셀링 🔵'
    if sio > 0:
        return '과매수'
    return '과매도'


def make_html(kospi: pd.DataFrame, kosdaq: pd.DataFrame, generated_at: str) -> str:
    def rows_html(df: pd.DataFrame) -> str:
        html = ''
        for dt, row in df.iterrows():
            sio = row['sio']
            if sio >= PANIC_BUY:
                cls = 'panic-buy'
            elif sio <= PANIC_SELL:
                cls = 'panic-sell'
            elif sio > 0:
                cls = 'up'
            else:
                cls = 'down'

            sig = signal_label(sio)
            html += f"""
            <tr class="{cls}">
              <td>{dt[:4]}-{dt[4:6]}-{dt[6:]}</td>
              <td class="num">{sio:+.2f}</td>
              <td>{sig}</td>
              <td class="num">{row['advancing']}</td>
              <td class="num">{row['declining']}</td>
              <td class="num">{row['J']:.4f}</td>
              <td class="num">{row['K']:.4f}</td>
            </tr>"""
        return html

    kospi_rows  = rows_html(kospi)  if not kospi.empty  else '<tr><td colspan="7">데이터 없음</td></tr>'
    kosdaq_rows = rows_html(kosdaq) if not kosdaq.empty else '<tr><td colspan="7">데이터 없음</td></tr>'

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>KOSPI / KOSDAQ 매매과열</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, 'Malgun Gothic', sans-serif; background: #f5f5f5; color: #222; }}

  header {{ background: #1a1a2e; color: #fff; padding: 18px 24px; }}
  header h1 {{ font-size: 1.3rem; font-weight: 700; }}
  header p  {{ font-size: 0.8rem; opacity: .7; margin-top: 4px; }}

  .legend {{ display: flex; gap: 16px; padding: 12px 24px; background: #fff;
             border-bottom: 1px solid #ddd; flex-wrap: wrap; font-size: 0.82rem; }}
  .legend span {{ display: flex; align-items: center; gap: 6px; }}
  .dot {{ width: 12px; height: 12px; border-radius: 2px; }}
  .dot.pb {{ background: #ff4757; }}
  .dot.ps {{ background: #1e90ff; }}
  .dot.up {{ background: #ffecea; border: 1px solid #f8bdc2; }}
  .dot.dn {{ background: #eaf0ff; border: 1px solid #b8cef0; }}

  .tabs {{ display: flex; gap: 0; padding: 16px 24px 0; }}
  .tab {{ padding: 8px 20px; cursor: pointer; border-radius: 6px 6px 0 0;
          background: #ddd; font-size: 0.9rem; font-weight: 600; user-select: none; }}
  .tab.active {{ background: #1a1a2e; border: 1px solid #1a1a2e; border-bottom: 1px solid #1a1a2e; color: #fff; }}

  .panel {{ display: none; padding: 0 24px 24px; }}
  .panel.active {{ display: block; }}

  .scroll-wrap {{ overflow-y: auto; max-height: 70vh; border: 1px solid #ddd;
                  border-radius: 0 6px 6px 6px; background: #fff; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}
  thead th {{ position: sticky; top: 0; background: #1a1a2e; color: #fff;
              padding: 10px 12px; text-align: center; font-weight: 600; white-space: nowrap; }}
  tbody td {{ padding: 8px 12px; border-bottom: 1px solid #f0f0f0;
              text-align: center; white-space: nowrap; }}
  tbody tr:hover td {{ filter: brightness(0.95); }}
  .num {{ font-variant-numeric: tabular-nums; }}

  tr.panic-buy  td {{ background: #ff4757; color: #fff; font-weight: 700; }}
  tr.panic-sell td {{ background: #1e90ff; color: #fff; font-weight: 700; }}
  tr.up  td {{ background: #fff5f5; }}
  tr.down td {{ background: #f0f5ff; }}
</style>
</head>
<body>

<header>
  <h1>📊 KOSPI / KOSDAQ 매매과열</h1>
  <p>생성: {generated_at} &nbsp;|&nbsp; 수식: J=거래량비율, K=등락률비율 (KOSPI200/KOSDAQ150 기준), D=(J+K)/2</p>
</header>

<div class="legend">
  <span><div class="dot pb"></div> 패닉 바잉 (SIO ≥ +80)</span>
  <span><div class="dot ps"></div> 패닉 셀링 (SIO ≤ −80)</span>
  <span><div class="dot up"></div> 과매수 (0 ~ +80)</span>
  <span><div class="dot dn"></div> 과매도 (−80 ~ 0)</span>
</div>

<div class="tabs">
  <div class="tab active" onclick="showTab('kospi', this)">KOSPI</div>
  <div class="tab"        onclick="showTab('kosdaq', this)">KOSDAQ</div>
</div>

<div id="kospi" class="panel active">
  <div class="scroll-wrap">
    <table>
      <thead><tr>
        <th>날짜</th><th>SIO (%)</th><th>신호</th>
        <th>상승<br>종목수</th><th>하락<br>종목수</th>
        <th>J<br>(거래량)</th><th>K<br>(등락률)</th>
      </tr></thead>
      <tbody>{kospi_rows}</tbody>
    </table>
  </div>
</div>

<div id="kosdaq" class="panel">
  <div class="scroll-wrap">
    <table>
      <thead><tr>
        <th>날짜</th><th>SIO (%)</th><th>신호</th>
        <th>상승<br>종목수</th><th>하락<br>종목수</th>
        <th>J<br>(거래량)</th><th>K<br>(등락률)</th>
      </tr></thead>
      <tbody>{kosdaq_rows}</tbody>
    </table>
  </div>
</div>

<script>
function showTab(id, el) {{
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  el.classList.add('active');
}}
</script>
</body>
</html>"""


def is_already_updated(out_path: str) -> bool:
    """오늘 날짜로 이미 리포트가 생성됐으면 True."""
    if not os.path.exists(out_path):
        return False
    mtime = datetime.fromtimestamp(os.path.getmtime(out_path))
    today = datetime.today()
    # 오늘 오후 3시 30분(장 마감) 이후에 생성된 파일이면 최신으로 간주
    cutoff = today.replace(hour=15, minute=30, second=0, microsecond=0)
    return mtime >= cutoff


def publish_to_github_pages(html_path: str):
    """생성된 HTML을 gh-pages 브랜치에 push → GitHub Pages로 서빙."""
    import subprocess, shutil, tempfile

    repo_dir = os.path.dirname(html_path)

    def git(cmd, cwd=repo_dir):
        result = subprocess.run(
            ['git'] + cmd, cwd=cwd,
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"git {' '.join(cmd)} 실패:\n{result.stderr}")
        return result.stdout.strip()

    print("\n📤 GitHub Pages에 업로드 중...")
    try:
        # 현재 브랜치 저장
        original_branch = git(['rev-parse', '--abbrev-ref', 'HEAD'])

        # 로컬/원격 gh-pages 브랜치 존재 여부 확인
        local_branches  = git(['branch'])
        remote_branches = git(['branch', '-r'])
        has_local  = 'gh-pages' in local_branches
        has_remote = 'origin/gh-pages' in remote_branches

        if has_local:
            git(['checkout', 'gh-pages'])
            if has_remote:
                git(['reset', '--hard', 'origin/gh-pages'])
        elif has_remote:
            git(['fetch', 'origin', 'gh-pages'])
            git(['checkout', '-b', 'gh-pages', 'origin/gh-pages'])
        else:
            git(['checkout', '--orphan', 'gh-pages'])
            git(['rm', '-rf', '.'])

        # index.html 복사
        dest = os.path.join(repo_dir, 'index.html')
        shutil.copy2(html_path, dest)

        git(['add', 'index.html'])
        git(['commit', '-m', f'Update SIO report {datetime.today().strftime("%Y-%m-%d %H:%M")}'])
        git(['push', 'origin', 'gh-pages'])

        # 원래 브랜치로 복귀
        git(['checkout', original_branch])

        print("✅ GitHub Pages 업로드 완료!")
        print("   URL: https://ssyj874-collab.github.io/target-price-tracker/")
        print("   (첫 등록 시 GitHub 설정에서 Pages를 활성화해야 합니다)")
    except Exception as e:
        print(f"⚠️  GitHub 업로드 실패: {e}")
        # 실패해도 원래 브랜치로 복귀 시도
        try:
            git(['checkout', original_branch])
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--days',      type=int, default=60, help='최근 N일 (기본 60)')
    parser.add_argument('--out',       default='sio_report.html', help='출력 파일명')
    parser.add_argument('--no-open',   action='store_true', help='브라우저 자동 열기 안 함')
    parser.add_argument('--skip-if-fresh', action='store_true',
                        help='오늘 이미 업데이트됐으면 건너뜀 (자동실행용)')
    parser.add_argument('--publish',   action='store_true',
                        help='생성 후 GitHub Pages(gh-pages 브랜치)에 자동 push')
    args = parser.parse_args()

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), args.out)

    if args.skip_if_fresh and is_already_updated(out_path):
        print(f"✅ 오늘 리포트가 이미 최신입니다. 건너뜁니다. ({out_path})")
        return

    today    = datetime.today()
    fromdate = (today - timedelta(days=args.days + 60)).strftime('%Y%m%d')
    todate   = today.strftime('%Y%m%d')

    print(f"기간: {fromdate} ~ {todate} (거래일 기준 약 {args.days}일)")
    print("KOSPI 데이터 수집 중...")
    kospi = fetch_sio_range('KOSPI', fromdate, todate)
    print("KOSDAQ 데이터 수집 중...")
    kosdaq = fetch_sio_range('KOSDAQ', fromdate, todate)

    # 최근 N 거래일만 유지
    if len(kospi) > args.days:
        kospi = kospi.head(args.days)
    if len(kosdaq) > args.days:
        kosdaq = kosdaq.head(args.days)

    generated_at = today.strftime('%Y-%m-%d %H:%M')
    html = make_html(kospi, kosdaq, generated_at)

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), args.out)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"\n✅ 리포트 생성 완료: {out_path}")

    if args.publish:
        publish_to_github_pages(out_path)

    if not args.no_open:
        webbrowser.open(f'file://{out_path}')


if __name__ == '__main__':
    main()
