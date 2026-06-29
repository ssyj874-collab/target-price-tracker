"""
통합 리포트 웹 서버 (SIO + 수급오실레이터)
실행: python3 server.py
브라우저:
  http://localhost:5000        → SIO 목표가 리포트
  http://localhost:5000/sugu   → 수급오실레이터 리포트
"""

import os
import subprocess
import threading
from datetime import datetime
from flask import Flask, jsonify

os.environ.setdefault('KRX_ID', 'syj6718')
os.environ.setdefault('KRX_PW', 'song135!')

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 각 리포트별 상태
_st = {
    'sio':  {'running': False, 'message': '대기 중'},
    'sugu': {'running': False, 'message': '대기 중'},
}


def _inject_button(html: str, update_url: str, status_url: str) -> str:
    """HTML에 우하단 업데이트 버튼 삽입"""
    button = f"""
<div id="ctrl" style="position:fixed;bottom:20px;right:20px;z-index:9999;
  background:#161b22;padding:12px 16px;border-radius:10px;
  box-shadow:0 4px 20px rgba(0,0,0,.6);display:flex;align-items:center;gap:10px;
  border:1px solid #30363d;">
  <span id="upd-msg" style="color:#8b949e;font-size:0.8rem;font-family:sans-serif;max-width:200px;"></span>
  <button id="upd-btn" onclick="doUpdate()" style="background:#238636;color:#fff;
    border:none;padding:8px 18px;border-radius:6px;cursor:pointer;
    font-size:0.85rem;font-weight:600;white-space:nowrap;">🔄 지금 업데이트</button>
</div>
<script>
(function(){{
  const UPDATE_URL='{update_url}', STATUS_URL='{status_url}';
  function doUpdate(){{
    document.getElementById('upd-btn').disabled=true;
    document.getElementById('upd-btn').textContent='업데이트 중...';
    document.getElementById('upd-msg').textContent='데이터 수집 시작...';
    fetch(UPDATE_URL,{{method:'POST'}}).then(poll);
  }}
  function poll(){{
    fetch(STATUS_URL).then(r=>r.json()).then(d=>{{
      document.getElementById('upd-msg').textContent=d.message;
      if(d.running){{
        setTimeout(poll,2000);
      }} else {{
        document.getElementById('upd-btn').disabled=false;
        document.getElementById('upd-btn').textContent='🔄 지금 업데이트';
        if(d.message.startsWith('완료')){{
          document.getElementById('upd-msg').style.color='#3fb950';
          setTimeout(()=>location.reload(),1200);
        }} else if(d.message.startsWith('오류')||d.message.startsWith('실패')){{
          document.getElementById('upd-msg').style.color='#f85149';
        }}
      }}
    }});
  }}
  window.doUpdate=doUpdate;
  poll();
}})();
</script>
"""
    if '</body>' in html:
        return html.replace('</body>', button + '</body>')
    elif '</html>' in html:
        return html.replace('</html>', button + '</html>')
    else:
        return html + button


# ── SIO 리포트 ─────────────────────────────────────────────────────────────

def _run_sio():
    _st['sio']['running'] = True
    _st['sio']['message'] = 'SIO 데이터 수집 중...'
    try:
        r = subprocess.run(
            ['python3', os.path.join(BASE_DIR, 'generate_report.py'), '--no-open', '--publish'],
            capture_output=True, text=True, env=os.environ.copy(), cwd=BASE_DIR
        )
        if r.returncode == 0:
            _st['sio']['message'] = f"완료: {datetime.now().strftime('%H:%M')}"
        else:
            _st['sio']['message'] = f"오류: {r.stderr[-300:]}"
    except Exception as e:
        _st['sio']['message'] = f"실패: {e}"
    finally:
        _st['sio']['running'] = False


@app.route('/')
def index():
    path = os.path.join(BASE_DIR, 'sio_report.html')
    if os.path.exists(path):
        html = open(path, encoding='utf-8').read()
    else:
        html = '<html><body><p>SIO 리포트 없음. 업데이트 버튼을 누르세요.</p></body></html>'
    return _inject_button(html, '/update', '/status')


@app.route('/update', methods=['POST'])
def update_sio():
    if not _st['sio']['running']:
        threading.Thread(target=_run_sio, daemon=True).start()
    return jsonify({'ok': True})


@app.route('/status')
def status_sio():
    return jsonify(_st['sio'])


# ── 수급오실레이터 리포트 ──────────────────────────────────────────────────

def _run_sugu():
    _st['sugu']['running'] = True
    _st['sugu']['message'] = '수급 데이터 수집 중...'
    try:
        python = 'python3'
        # 1. 데이터 수집
        r1 = subprocess.run(
            [python, os.path.join(BASE_DIR, 'sugu_calculator.py')],
            capture_output=True, text=True, env=os.environ.copy(), cwd=BASE_DIR
        )
        if r1.returncode != 0:
            _st['sugu']['message'] = f"오류(수집): {r1.stderr[-300:]}"
            return

        _st['sugu']['message'] = '리포트 생성 중...'
        # 2. 리포트 생성
        r2 = subprocess.run(
            [python, os.path.join(BASE_DIR, 'generate_sugu_report.py')],
            capture_output=True, text=True, env=os.environ.copy(), cwd=BASE_DIR
        )
        if r2.returncode != 0:
            _st['sugu']['message'] = f"오류(리포트): {r2.stderr[-300:]}"
            return

        _st['sugu']['message'] = 'GitHub 배포 중...'
        # 3. 배포
        r3 = subprocess.run(
            ['bash', os.path.join(BASE_DIR, 'publish_sugu.sh')],
            capture_output=True, text=True, env=os.environ.copy(), cwd=BASE_DIR
        )
        if r3.returncode == 0:
            _st['sugu']['message'] = f"완료: {datetime.now().strftime('%H:%M')}"
        else:
            _st['sugu']['message'] = f"오류(배포): {r3.stderr[-300:]}"
    except Exception as e:
        _st['sugu']['message'] = f"실패: {e}"
    finally:
        _st['sugu']['running'] = False


@app.route('/sugu')
def sugu():
    path = os.path.join(BASE_DIR, 'sugu_report.html')
    if os.path.exists(path):
        html = open(path, encoding='utf-8').read()
    else:
        html = '<html><body><p>수급오실레이터 리포트 없음. 업데이트 버튼을 누르세요.</p></body></html>'
    return _inject_button(html, '/update-sugu', '/status-sugu')


@app.route('/update-sugu', methods=['POST'])
def update_sugu():
    if not _st['sugu']['running']:
        threading.Thread(target=_run_sugu, daemon=True).start()
    return jsonify({'ok': True})


@app.route('/status-sugu')
def status_sugu():
    return jsonify(_st['sugu'])


# ── 실행 ──────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("=" * 50)
    print("리포트 서버 시작")
    print("  SIO 목표가:      http://localhost:8888")
    print("  수급오실레이터:   http://localhost:8888/sugu")
    print("=" * 50)
    app.run(host='0.0.0.0', port=8888, debug=False)
