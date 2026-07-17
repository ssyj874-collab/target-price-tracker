"""다트 재무 데이터 수집기 — 전 상장사 커버, 실적시즌 버튼 갱신.

실행:
    python3 dart_app.py            # http://127.0.0.1:8899 브라우저 자동 오픈
    python3 dart_app.py --port 8899 --dir data --budget 19000

화면 버튼:
- [전체 수집 시작/이어하기]: 상장사 전체(~2,600개)의 최근 3년 + 올해
  진행분 매출액/영업이익/판관비/재고자산을 수집. 다트 일일 한도(2만 건)
  때문에 첫 수집은 며칠에 나뉠 수 있다 — 한도에 닿으면 자동으로 멈추고,
  다음 날 같은 버튼을 누르면 이어서 진행한다(이미 받은 보고서는 호출 안 함).
- [실적시즌 업데이트]: 직전 4개 분기 중 아직 저장 안 된 보고서만 전
  종목에 대해 조회. 시즌 중 며칠 간격으로 눌러주면 새 공시가 차곡차곡
  쌓인다. 매일 돌릴 필요 없음.
- [중지]: 진행 중인 잡을 멈춘다(받은 데이터는 저장돼 있음).

데이터: data/ 디렉토리에 종목별 JSON(연간/분기 분리, 단위 백만원).
호출 속도는 분당 ~600건으로 제한하고, 일일 사용량은 data/_quota.json에
기록해 한도를 넘지 않게 한다. 서버는 127.0.0.1에만 바인딩.
"""

from __future__ import annotations

import datetime as dt
import glob
import json
import os
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import dart_store
from dart_fetch import fetch_listed_codes, load_corp_map, resolve_key

DATA_DIR = "data"
DAILY_BUDGET = 19000       # 다트 일일 한도(20,000)보다 여유 있게
CALL_INTERVAL = 0.1        # 초당 10건 = 분당 600건

_LOCK = threading.Lock()

JOB = {
    "running": False, "mode": None, "total": 0, "done": 0,
    "current": "", "added": 0, "calls_today": 0,
    "message": "", "errors": [],
}


# ---------------------------------------------------------------------------
# 일일 쿼터 + 페이싱
# ---------------------------------------------------------------------------

def _quota_path() -> str:
    return os.path.join(DATA_DIR, "_quota.json")


def load_quota() -> dict:
    try:
        with open(_quota_path(), encoding="utf-8") as f:
            q = json.load(f)
        if q.get("date") == dt.date.today().isoformat():
            return q
    except (OSError, ValueError):
        pass
    return {"date": dt.date.today().isoformat(), "used": 0}


def save_quota(q: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(_quota_path(), "w", encoding="utf-8") as f:
        json.dump(q, f)


class _Pacer:
    """호출 훅: 속도 제한 + 일일 한도 + 진행 카운트."""

    def __init__(self):
        self.quota = load_quota()
        self.stop = False

    def __call__(self):
        if self.stop:
            raise dart_store.BudgetExceeded("사용자 중지")
        if self.quota["used"] >= DAILY_BUDGET:
            raise dart_store.BudgetExceeded(
                f"오늘 호출 한도({DAILY_BUDGET:,}건) 도달 — 내일 [이어하기]를 누르세요.")
        self.quota["used"] += 1
        JOB["calls_today"] = self.quota["used"]
        if self.quota["used"] % 50 == 0:
            save_quota(self.quota)
        time.sleep(CALL_INTERVAL)


# ---------------------------------------------------------------------------
# 잡 러너
# ---------------------------------------------------------------------------

def _job_state_path() -> str:
    return os.path.join(DATA_DIR, "_job_state.json")


def _load_job_state() -> dict:
    try:
        with open(_job_state_path(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_job_state(state: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(_job_state_path(), "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


_PACER: _Pacer | None = None


def job_universe(key: str) -> list[dict]:
    """수집 대상: 유가증권 + 코스닥 상장사만 (코넥스·기타법인 제외).

    KRX 상장법인 목록을 못 받으면 필터 없이 전체를 쓴다(폴백).
    """
    corps = sorted(load_corp_map(key)["entries"], key=lambda e: e["corp_name"])
    listed = fetch_listed_codes()
    if listed:
        corps = [c for c in corps if c["stock_code"] in listed]
    return corps


def resume_index(corps: list[dict], state: dict, key: str) -> int:
    """저장된 진행 위치 → 현재 목록에서의 시작 인덱스.

    새 형식은 종목명(last_name) 기준이라 목록이 필터로 바뀌어도 정확하다.
    옛 형식(index)은 필터 전 전체 목록에서 이름을 복원해 변환한다.
    """
    import bisect

    if state.get("mode") != "backfill":
        return 0
    last_name = state.get("last_name")
    if not last_name and "index" in state:
        all_sorted = sorted(load_corp_map(key)["entries"],
                            key=lambda e: e["corp_name"])
        i = state["index"]
        if 0 <= i < len(all_sorted):
            last_name = all_sorted[i]["corp_name"]
    if not last_name:
        return 0
    names = [c["corp_name"] for c in corps]
    return bisect.bisect_left(names, last_name)


def run_job(mode: str) -> None:
    """mode: 'backfill'(3년치 전체) | 'season'(직전 4개 분기만)."""
    global _PACER
    key = resolve_key(None)
    corps = job_universe(key)
    this_year = dt.date.today().year
    if mode == "backfill":
        periods = dart_store.year_range_periods(this_year - 3, this_year)
    else:
        periods = dart_store.rolling_periods()

    # 이어하기: backfill은 마지막 진행 지점(종목명 기준)부터
    start_idx = resume_index(corps, _load_job_state(), key) if mode == "backfill" else 0

    _PACER = _Pacer()
    dart_store.API_HOOK = _PACER
    JOB.update(running=True, mode=mode, total=len(corps), done=start_idx,
               added=0, current="", message="", errors=[],
               calls_today=_PACER.quota["used"])
    try:
        for i in range(start_idx, len(corps)):
            corp = corps[i]
            JOB["current"] = f"{corp['corp_name']} ({corp['stock_code']})"
            try:
                _store, added = dart_store.ensure_periods(key, corp, DATA_DIR, periods)
                JOB["added"] += added
            except dart_store.BudgetExceeded as e:
                JOB["message"] = str(e)
                if mode == "backfill":
                    _save_job_state({"mode": "backfill",
                                     "last_name": corp["corp_name"]})
                return
            except Exception as e:  # noqa: BLE001 — 한 종목 실패는 건너뛴다
                JOB["errors"].append(f"{corp['corp_name']}: {e}")
                if len(JOB["errors"]) > 20:
                    JOB["message"] = "오류가 너무 많아 중단 (인증키/네트워크 확인)"
                    return
            JOB["done"] = i + 1
        if mode == "backfill":
            _save_job_state({})  # 완주 — 다음 backfill은 처음부터(스킵이 빨라서 무방)
        JOB["message"] = f"완료 — 새로 받은 보고서 {JOB['added']:,}건"
    finally:
        if _PACER:
            save_quota(_PACER.quota)
        dart_store.API_HOOK = None
        # 수집이 끝날 때마다(한도 중단 포함) 자동으로 GitHub 백업
        if JOB["added"]:
            JOB["current"] = "GitHub 백업 중..."
            JOB["message"] = (JOB["message"] + " · " if JOB["message"] else "") + git_backup()
        JOB["running"] = False
        JOB["current"] = ""


def git_backup() -> str:
    """data/ 폴더를 커밋하고 GitHub로 푸시. 결과를 한 줄로 반환.

    push는 커밋 유무와 무관하게 항상 시도한다 — 이전에 커밋까지 되고
    push만 실패(타임아웃 등)한 경우를 재시도로 살리기 위해.
    """
    root = os.path.dirname(os.path.abspath(__file__))
    if not os.path.isdir(os.path.join(root, ".git")):
        return "git 저장소가 아니라 백업 생략"

    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")  # 로그인 입력 대기로 멈추지 않게

    def run(*args, timeout=120):
        return subprocess.run(args, cwd=root, capture_output=True,
                              text=True, timeout=timeout, env=env)

    try:
        run("git", "add", DATA_DIR)
        committed = False
        if run("git", "diff", "--cached", "--quiet").returncode != 0:
            stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
            commit = run("git", "commit", "-m", f"재무 데이터 백업 {stamp}")
            if commit.returncode != 0:
                return f"GitHub 백업 실패(commit): {commit.stderr.strip()[:200]}"
            committed = True
        # 첫 백업은 파일이 수천 개라 오래 걸릴 수 있다 — 여유 있게
        push = run("git", "push", timeout=900)
        if push.returncode != 0:
            err = (push.stderr or push.stdout).strip()
            if "terminal prompts disabled" in err or "Username" in err \
                    or "Authentication" in err or "403" in err:
                return ("GitHub 백업 실패: GitHub 로그인 정보가 없습니다 — "
                        "이 메시지를 Claude에게 보여주세요. (데이터는 컴퓨터에 안전하게 저장돼 있음)")
            return f"GitHub 백업 실패(push): {err[:200]}"
        if committed:
            return "GitHub 백업 완료"
        return "GitHub 백업: 새 변경 없음 (밀린 업로드가 있었다면 마저 올림)"
    except subprocess.TimeoutExpired:
        return ("GitHub 백업 실패: 업로드 시간 초과 — 인터넷이 느리거나 파일이 많습니다. "
                "[GitHub 백업]을 다시 누르면 이어서 시도합니다. (데이터는 컴퓨터에 안전)")
    except OSError as e:
        return f"GitHub 백업 실패: {e}"


def start_job(mode: str) -> bool:
    with _LOCK:
        if JOB["running"]:
            return False
        # 스레드 시작 전에 상태를 리셋해야 이전 잡의 완료 메시지가
        # 새 잡 것으로 오인되지 않는다
        JOB.update(running=True, mode=mode, total=0, done=0, current="",
                   added=0, message="", errors=[])
        threading.Thread(target=run_job, args=(mode,), daemon=True).start()
        return True


# ---------------------------------------------------------------------------
# 조회
# ---------------------------------------------------------------------------

def list_stores() -> list[dict]:
    out = []
    for path in sorted(glob.glob(os.path.join(DATA_DIR, "[0-9]*.json"))):
        store = dart_store.load_store(path)
        if not store:
            continue
        out.append({
            "stock_code": store.get("stock_code"),
            "corp_name": store.get("corp_name"),
            "updated": store.get("updated"),
            "quarters": len(store.get("quarterly", [])),
            "latest": (store.get("quarterly") or [{}])[-1].get("label"),
        })
    return out


def find_store(stock_code: str) -> dict | None:
    for path in glob.glob(os.path.join(DATA_DIR, f"{stock_code}_*.json")):
        store = dart_store.load_store(path)
        if store:
            return store
    return None


class Handler(BaseHTTPRequestHandler):
    server_version = "DartCollector/2.0"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        if url.path == "/":
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif url.path == "/api/stocks":
            self._json(list_stores())
        elif url.path == "/api/job":
            self._json(JOB)
        elif url.path.startswith("/api/stock/"):
            code = url.path.rsplit("/", 1)[-1]
            store = find_store(code)
            if store:
                self._json(store)
            else:
                self._json({"error": "not found"}, 404)
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
            if url.path == "/api/job/start":
                mode = payload.get("mode")
                if mode not in ("backfill", "season"):
                    self._json({"ok": False, "error": "mode?"}, 400)
                    return
                resolve_key(None)  # 키 확인
                started = start_job(mode)
                self._json({"ok": started,
                            "error": None if started else "이미 실행 중"})
            elif url.path == "/api/job/stop":
                if _PACER:
                    _PACER.stop = True
                self._json({"ok": True})
            elif url.path == "/api/backup":
                if JOB["running"]:
                    self._json({"ok": False,
                                "error": "수집 진행 중에는 백업할 수 없습니다 — 완료 후 자동 백업됩니다."},
                               409)
                    return
                self._json({"ok": True, "result": git_backup()})
            elif url.path == "/api/update-one":
                if JOB["running"]:
                    self._json({"ok": False,
                                "error": "전체 수집이 진행 중입니다 — 완료(또는 중지) 후 다시 시도하세요."},
                               409)
                    return
                key = resolve_key(None)
                code = str(payload.get("code", "")).strip()
                store = find_store(code)
                if not store:
                    self._json({"ok": False, "error": "저장된 종목 아님"}, 404)
                    return
                corp = {"corp_code": store["corp_code"],
                        "corp_name": store["corp_name"],
                        "stock_code": store["stock_code"]}
                # 단일 종목은 호출 부담이 없으므로 3년치 전체 범위를 채운다
                # (빠진 보고서만 조회 — 이미 있으면 호출 0건).
                # 일일 한도는 여기서도 지킨다.
                this_year = dt.date.today().year
                pacer = _Pacer()
                with _LOCK:
                    dart_store.API_HOOK = pacer
                    try:
                        _s, added = dart_store.ensure_periods(
                            key, corp, DATA_DIR,
                            dart_store.year_range_periods(this_year - 3, this_year))
                    except dart_store.BudgetExceeded as e:
                        self._json({"ok": False, "error": str(e)}, 429)
                        return
                    finally:
                        save_quota(pacer.quota)
                        dart_store.API_HOOK = None
                self._json({"ok": True, "added": added,
                            "quarters": len(_s.get("quarterly", []))})
            else:
                self._json({"error": "not found"}, 404)
        except SystemExit as e:
            self._json({"ok": False, "error": str(e)}, 400)
        except Exception as e:  # noqa: BLE001
            self._json({"ok": False, "error": f"{type(e).__name__}: {e}"}, 500)


PAGE = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>다트 재무 데이터 수집기</title>
<style>
:root {
  --surface: #fcfcfb; --page: #f9f9f7; --ink: #0b0b0b; --ink2: #52514e;
  --muted: #898781; --grid: #e1e0d9; --line: #c3c2b7;
  --border: rgba(11,11,11,0.10); --accent: #2a78d6;
  --good: #006300; --bad: #d03b3b;
}
@media (prefers-color-scheme: dark) {
  :root {
    --surface: #1a1a19; --page: #0d0d0d; --ink: #fff; --ink2: #c3c2b7;
    --muted: #898781; --grid: #2c2c2a; --line: #383835;
    --border: rgba(255,255,255,0.10); --accent: #3987e5;
    --good: #0ca30c; --bad: #e66767;
  }
}
* { box-sizing: border-box; margin: 0; }
body { background: var(--page); color: var(--ink);
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  padding: 24px 16px 48px; }
.wrap { max-width: 980px; margin: 0 auto; display: grid; gap: 16px; }
h1 { font-size: 20px; font-weight: 650; }
h1 small { font-size: 13px; font-weight: 400; color: var(--ink2); margin-left: 8px; }
.panel { background: var(--surface); border: 1px solid var(--border);
  border-radius: 10px; padding: 16px; }
.panel h2 { font-size: 14px; font-weight: 600; margin-bottom: 8px; }
.row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
input[type=text] { font: inherit; color: inherit; background: var(--page);
  border: 1px solid var(--border); border-radius: 7px; padding: 7px 10px; width: 220px; }
button { font: inherit; font-size: 13px; color: var(--ink);
  background: transparent; border: 1px solid var(--border);
  border-radius: 7px; padding: 6px 14px; cursor: pointer; }
button:hover { background: var(--page); }
button.primary { border-color: var(--accent); color: var(--accent); font-weight: 600; }
button:disabled { opacity: .5; cursor: not-allowed; }
#progress-wrap { margin-top: 10px; display: none; }
#progress-bar { height: 6px; background: var(--grid); border-radius: 999px; overflow: hidden; }
#progress-fill { height: 100%; width: 0; background: var(--accent); transition: width .5s; }
#job-line { font-size: 13px; color: var(--ink2); margin-top: 6px; }
#job-msg { font-size: 13px; margin-top: 4px; }
#job-msg.err { color: var(--bad); }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { padding: 6px 8px; white-space: nowrap; text-align: right;
  font-variant-numeric: tabular-nums; }
th { color: var(--ink2); font-weight: 600; border-bottom: 1px solid var(--line); }
th:first-child, td:first-child { text-align: left; }
tbody tr { border-bottom: 1px solid var(--grid); }
tbody tr:last-child { border-bottom: none; }
#stock-list tr { cursor: pointer; }
#stock-list tr:hover { background: var(--page); }
#stock-list tr.active td:first-child { color: var(--accent); font-weight: 650; }
.table-wrap { overflow-x: auto; max-height: 420px; overflow-y: auto; }
.neg { color: var(--bad); }
.tabs { display: flex; gap: 8px; margin-bottom: 10px; }
.tabs button.on { border-color: var(--accent); color: var(--accent); font-weight: 600; }
.hint { font-size: 12px; color: var(--muted); margin-top: 8px; line-height: 1.6; }
</style>
</head>
<body>
<div class="wrap">
  <h1>다트 재무 데이터 수집기<small>유가증권+코스닥 전 종목 · 매출액 · 영업이익 · 판관비 · 재고자산 (단위: 백만원)</small></h1>

  <section class="panel">
    <div class="row">
      <button class="primary" id="btn-backfill">전체 수집 시작/이어하기 (3년치)</button>
      <button class="primary" id="btn-season">실적시즌 업데이트 (직전 4개 분기)</button>
      <button id="btn-stop" disabled>중지</button>
      <button id="btn-backup">GitHub 백업</button>
    </div>
    <div id="progress-wrap">
      <div id="progress-bar"><div id="progress-fill"></div></div>
      <div id="job-line"></div>
    </div>
    <div id="job-msg"></div>
    <p class="hint">전체 수집은 다트 일일 한도(2만 건) 때문에 첫 회는 2~3일에
      나뉠 수 있습니다 — 한도에 닿으면 자동으로 멈추고, 다음 날 같은 버튼을
      누르면 이어서 받습니다(이미 받은 보고서는 건너뜀). 실적시즌 업데이트는
      새로 공시된 보고서만 조회하므로 시즌 중 몇 번을 눌러도 가볍습니다.
      수집이 끝나면(한도로 멈춘 경우 포함) data/ 폴더가 <b>자동으로 GitHub에
      백업</b>됩니다 — 수동으로 하려면 [GitHub 백업] 버튼.</p>
  </section>

  <section class="panel">
    <div class="row" style="justify-content: space-between">
      <h2 style="margin:0">종목 <span id="count" style="font-weight:400;color:var(--muted)"></span></h2>
      <input type="text" id="filter" placeholder="종목명/코드 검색">
    </div>
    <div class="table-wrap" style="margin-top:8px">
      <table>
        <thead><tr><th>종목</th><th>코드</th><th>분기 수</th><th>최근 분기</th>
          <th>마지막 수집</th><th></th></tr></thead>
        <tbody id="stock-list"></tbody>
      </table>
    </div>
  </section>

  <section class="panel" id="detail" hidden>
    <h2 id="detail-title"></h2>
    <div class="tabs">
      <button id="tab-q" class="on">분기별</button>
      <button id="tab-a">연간</button>
    </div>
    <div class="table-wrap">
      <table>
        <thead id="detail-head"></thead>
        <tbody id="detail-body"></tbody>
      </table>
    </div>
    <p class="hint">손익 항목(매출·영업이익·판관비)은 보고서 누적치의 분기 차분,
      재고자산은 분기말 잔액. 판관비율 = 판관비 ÷ 매출, 재고/매출 = 재고자산 ÷
      매출(분기). 연결(CFS) 재무제표 기준(없으면 별도).</p>
  </section>
</div>

<script>
"use strict";
const $ = id => document.getElementById(id);
let currentCode = null, currentTab = "q", cache = {}, stocks = [], poller = null;

function fmt(v) {
  if (v == null) return "–";
  const s = Math.abs(v).toLocaleString("ko-KR");
  return v < 0 ? `<span class="neg">-${s}</span>` : s;
}
function pct(a, b) {
  if (a == null || !b) return "–";
  const v = a / b * 100;
  const s = v.toFixed(1) + "%";
  return v < 0 ? `<span class="neg">${s}</span>` : s;
}
async function api(path, body) {
  const opt = body ? { method: "POST", body: JSON.stringify(body) } : {};
  const res = await fetch(path, opt);
  return res.json();
}

function renderList() {
  const q = $("filter").value.trim().toLowerCase();
  const tbody = $("stock-list");
  tbody.innerHTML = "";
  let shown = 0;
  for (const s of stocks) {
    if (q && !(s.corp_name.toLowerCase().includes(q) || s.stock_code.includes(q))) continue;
    shown += 1;
    if (shown > 500) break;  // 필터로 좁혀 쓰세요
    const tr = document.createElement("tr");
    if (s.stock_code === currentCode) tr.className = "active";
    tr.innerHTML = `<td>${s.corp_name}</td><td>${s.stock_code}</td>` +
      `<td>${s.quarters}</td><td>${s.latest || "–"}</td>` +
      `<td>${(s.updated || "").replace("T", " ")}</td><td></td>`;
    const btn = document.createElement("button");
    btn.textContent = "업데이트";
    btn.addEventListener("click", async e => {
      e.stopPropagation();
      btn.disabled = true;
      btn.textContent = "수집중…";
      const msg = $("job-msg");
      try {
        const r = await api("/api/update-one", { code: s.stock_code });
        if (!r.ok) throw new Error(r.error || "실패");
        msg.textContent = `${s.corp_name}: 새 보고서 ${r.added}건 (분기 ${r.quarters}개 보유)`;
        msg.className = "";
      } catch (err) {
        const detail = String(err.message || err);
        msg.textContent = `${s.corp_name} 업데이트 실패: ` +
          (detail.includes("Failed to fetch")
            ? "서버가 꺼져 있습니다 — 수집기실행.command(또는 python3 dart_app.py)를 먼저 실행하세요."
            : detail);
        msg.className = "err";
      } finally {
        await refreshList().catch(() => {});
        if (currentCode === s.stock_code) showDetail(s.stock_code).catch(() => {});
      }
    });
    tr.lastChild.appendChild(btn);
    tr.addEventListener("click", () => showDetail(s.stock_code));
    tbody.appendChild(tr);
  }
  $("count").textContent = `수집됨 ${stocks.length.toLocaleString()}개` +
    (q ? ` · 표시 ${Math.min(shown, 500)}` : "");
}

async function refreshList() {
  stocks = await api("/api/stocks");
  renderList();
}

async function showDetail(code) {
  currentCode = code;
  delete cache[code];
  const store = await api("/api/stock/" + code);
  cache[code] = store;
  $("detail").hidden = false;
  $("detail-title").textContent = `${store.corp_name} (${store.stock_code})`;
  renderDetail(store);
  renderList();
}

function renderDetail(store) {
  const isQ = currentTab === "q";
  $("tab-q").className = isQ ? "on" : "";
  $("tab-a").className = isQ ? "" : "on";
  $("detail-head").innerHTML = "<tr>" +
    `<th>${isQ ? "분기" : "연도"}</th><th>매출</th><th>영업이익</th><th>영업이익률</th>` +
    "<th>판관비</th><th>판관비율</th><th>재고자산</th><th>재고/매출</th></tr>";
  const rows = isQ ? store.quarterly : store.annual;
  const tbody = $("detail-body");
  tbody.innerHTML = "";
  for (const r of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${isQ ? r.label : r.year}</td>` +
      `<td>${fmt(r.revenue)}</td><td>${fmt(r.op)}</td><td>${pct(r.op, r.revenue)}</td>` +
      `<td>${fmt(r.sga)}</td><td>${pct(r.sga, r.revenue)}</td>` +
      `<td>${fmt(r.inventory)}</td><td>${pct(r.inventory, r.revenue)}</td>`;
    tbody.appendChild(tr);
  }
}

// ---- 잡 상태 ----
function setJobUi(job) {
  const running = job.running;
  $("btn-backfill").disabled = running;
  $("btn-season").disabled = running;
  $("btn-backup").disabled = running;
  $("btn-stop").disabled = !running;
  $("progress-wrap").style.display = running || job.done ? "block" : "none";
  const pctDone = job.total ? (job.done / job.total * 100) : 0;
  $("progress-fill").style.width = pctDone.toFixed(1) + "%";
  $("job-line").textContent = running || job.done
    ? `${job.done.toLocaleString()}/${job.total.toLocaleString()} 종목` +
      ` · 오늘 API ${job.calls_today.toLocaleString()}건` +
      ` · 새 보고서 ${job.added.toLocaleString()}건` +
      (job.current ? ` · ${job.current}` : "")
    : "";
  $("job-msg").textContent = job.message ||
    (job.errors && job.errors.length ? `오류 ${job.errors.length}건: ${job.errors[0]}` : "");
  $("job-msg").className = (job.errors && job.errors.length) ? "err" : "";
}

async function pollJob() {
  let job;
  try {
    job = await api("/api/job");
  } catch (e) {
    $("job-msg").textContent = "서버 연결 안 됨 — 수집기실행.command(또는 python3 dart_app.py)를 실행한 뒤 이 페이지를 새로고침하세요.";
    $("job-msg").className = "err";
    if (poller) { clearInterval(poller); poller = null; }
    return;
  }
  setJobUi(job);
  if (job.running) {
    if (!poller) poller = setInterval(pollJob, 2000);
  } else if (poller) {
    clearInterval(poller);
    poller = null;
    refreshList();
  }
}

async function startJob(mode) {
  const r = await api("/api/job/start", { mode });
  if (r.error) { $("job-msg").textContent = r.error; $("job-msg").className = "err"; }
  pollJob();
  if (!poller) poller = setInterval(pollJob, 2000);
}

$("btn-backfill").addEventListener("click", () => startJob("backfill"));
$("btn-season").addEventListener("click", () => startJob("season"));
$("btn-stop").addEventListener("click", () => api("/api/job/stop", {}));
$("btn-backup").addEventListener("click", async () => {
  const btn = $("btn-backup");
  btn.disabled = true; btn.textContent = "백업 중…";
  try {
    const r = await api("/api/backup", {});
    $("job-msg").textContent = r.ok ? r.result : (r.error || "실패");
    $("job-msg").className = r.ok && r.result.includes("완료") ? "" :
      (r.ok ? "" : "err");
  } catch (e) {
    $("job-msg").textContent = "백업 실패: 서버 연결 안 됨";
    $("job-msg").className = "err";
  } finally {
    btn.disabled = false; btn.textContent = "GitHub 백업";
  }
});
$("filter").addEventListener("input", renderList);
$("tab-q").addEventListener("click", () => {
  currentTab = "q";
  if (currentCode && cache[currentCode]) renderDetail(cache[currentCode]);
});
$("tab-a").addEventListener("click", () => {
  currentTab = "a";
  if (currentCode && cache[currentCode]) renderDetail(cache[currentCode]);
});

refreshList();
pollJob();
</script>
</body>
</html>
"""


def main(argv=None) -> int:
    global DATA_DIR, DAILY_BUDGET
    argv = list(sys.argv[1:] if argv is None else argv)
    port = 8899
    if "--port" in argv:
        port = int(argv[argv.index("--port") + 1])
    if "--dir" in argv:
        DATA_DIR = argv[argv.index("--dir") + 1]
    if "--budget" in argv:
        DAILY_BUDGET = int(argv[argv.index("--budget") + 1])

    resolve_key(None)  # 키 없으면 안내 후 종료
    os.makedirs(DATA_DIR, exist_ok=True)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    print(f"다트 재무 데이터 수집기: {url}  (종료: Ctrl+C)")
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n종료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
