"""
SIO 리포트 웹 서버
실행: python3 server.py
브라우저: http://localhost:5000
"""

import os
import subprocess
import threading
from datetime import datetime
from flask import Flask, jsonify, send_file, Response

os.environ.setdefault('KRX_ID', 'syj6718')
os.environ.setdefault('KRX_PW', 'song135!')

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORT_PATH = os.path.join(BASE_DIR, 'sio_report.html')

_status = {'running': False, 'message': '대기 중'}


def run_update():
    _status['running'] = True
    _status['message'] = '데이터 수집 중...'
    try:
        env = os.environ.copy()
        result = subprocess.run(
            ['python3', os.path.join(BASE_DIR, 'generate_report.py'), '--no-open', '--publish'],
            capture_output=True, text=True, env=env, cwd=BASE_DIR
        )
        if result.returncode == 0:
            _status['message'] = f"완료: {datetime.now().strftime('%H:%M:%S')}"
        else:
            _status['message'] = f"오류: {result.stderr[-200:]}"
    except Exception as e:
        _status['message'] = f"실패: {e}"
    finally:
        _status['running'] = False


@app.route('/')
def index():
    if os.path.exists(REPORT_PATH):
        with open(REPORT_PATH, encoding='utf-8') as f:
            html = f.read()
        # 업데이트 버튼 삽입
        button = """
<div id="ctrl" style="position:fixed;bottom:20px;right:20px;z-index:9999;
  background:#1a1a2e;padding:12px 16px;border-radius:10px;
  box-shadow:0 4px 12px rgba(0,0,0,.4);display:flex;align-items:center;gap:10px;">
  <span id="msg" style="color:#aaa;font-size:0.8rem;font-family:sans-serif"></span>
  <button id="btn" onclick="doUpdate()" style="background:#4a9eff;color:#fff;
    border:none;padding:8px 16px;border-radius:6px;cursor:pointer;
    font-size:0.85rem;font-weight:600;">🔄 업데이트</button>
</div>
<script>
function doUpdate(){
  document.getElementById('btn').disabled=true;
  document.getElementById('msg').textContent='수집 중...';
  fetch('/update',{method:'POST'});
  poll();
}
function poll(){
  fetch('/status').then(r=>r.json()).then(d=>{
    document.getElementById('msg').textContent=d.message;
    if(d.running){setTimeout(poll,2000);}
    else{
      document.getElementById('btn').disabled=false;
      if(d.message.startsWith('완료')) setTimeout(()=>location.reload(),1000);
    }
  });
}
poll();
</script>
"""
        html = html.replace('</body>', button + '</body>')
        return html
    return '<p>리포트 없음. 업데이트 버튼을 누르세요.</p><button onclick="fetch(\'/update\',{method:\'POST\'})">업데이트</button>'


@app.route('/update', methods=['POST'])
def update():
    if not _status['running']:
        threading.Thread(target=run_update, daemon=True).start()
    return jsonify({'ok': True})


@app.route('/status')
def status():
    return jsonify(_status)


if __name__ == '__main__':
    print("SIO 서버 시작: http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
