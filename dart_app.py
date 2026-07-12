"""다트 재무 데이터 수집기 — 버튼으로 종목 추가/업데이트하는 로컬 앱.

실행:
    python3 dart_app.py            # http://127.0.0.1:8899 브라우저 자동 오픈
    python3 dart_app.py --port 8899 --dir data

화면에서:
- 종목명(또는 6자리 코드) 입력 → [종목 추가]: 최근 3년 + 올해 진행분의
  분기·연간 매출액/영업이익/판관비/재고자산을 다트에서 수집해 저장
- 종목별 [업데이트]: 작년~올해 보고서를 다시 받아 새 분기만 병합(멱등)
  — 분기·반기·사업보고서가 새로 공시될 때마다 누르면 쌓인다
- [전체 업데이트]: 저장된 모든 종목 일괄 업데이트

데이터는 data/ 디렉토리에 종목별 JSON으로 보관된다(단위 백만원).
DART 인증키는 dart_fetch.py와 동일하게 DART_API_KEY 환경변수 또는
dart_api_key.txt에서 읽는다. 서버는 127.0.0.1에만 바인딩된다.
"""

from __future__ import annotations

import datetime as dt
import glob
import json
import os
import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import dart_store
from dart_fetch import load_corp_map, lookup_corp, resolve_key

DATA_DIR = "data"
_LOCK = threading.Lock()  # 다트 호출·파일 쓰기 직렬화


def list_stores() -> list[dict]:
    out = []
    for path in sorted(glob.glob(os.path.join(DATA_DIR, "*.json"))):
        store = dart_store.load_store(path)
        if not store:
            continue
        out.append({
            "stock_code": store.get("stock_code"),
            "corp_name": store.get("corp_name"),
            "updated": store.get("updated"),
            "quarters": len(store.get("quarterly", [])),
            "years": len(store.get("annual", [])),
            "latest": (store.get("quarterly") or [{}])[-1].get("label"),
        })
    return out


def find_store(stock_code: str) -> dict | None:
    for path in glob.glob(os.path.join(DATA_DIR, f"{stock_code}_*.json")):
        store = dart_store.load_store(path)
        if store:
            return store
    return None


def do_add(key: str, query: str) -> dict:
    corp = lookup_corp(load_corp_map(key), query)
    this_year = dt.date.today().year
    with _LOCK:
        return dart_store.update_stock(key, corp, DATA_DIR,
                                       this_year - 3, this_year)


def do_update(key: str, stock_code: str) -> dict:
    store = find_store(stock_code)
    if not store:
        raise SystemExit(f"저장된 종목이 아닙니다: {stock_code}")
    corp = {"corp_code": store["corp_code"], "corp_name": store["corp_name"],
            "stock_code": store["stock_code"]}
    this_year = dt.date.today().year
    with _LOCK:
        return dart_store.update_stock(key, corp, DATA_DIR,
                                       this_year - 1, this_year)


class Handler(BaseHTTPRequestHandler):
    server_version = "DartCollector/1.0"

    def log_message(self, fmt, *args):  # 조용히
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
            key = resolve_key(None)
            if url.path == "/api/add":
                store = do_add(key, str(payload.get("query", "")).strip())
                self._json({"ok": True, "stock_code": store["stock_code"],
                            "corp_name": store["corp_name"],
                            "quarters": len(store["quarterly"])})
            elif url.path == "/api/update":
                store = do_update(key, str(payload.get("code", "")).strip())
                self._json({"ok": True, "stock_code": store["stock_code"],
                            "quarters": len(store["quarterly"])})
            elif url.path == "/api/update-all":
                results = []
                for s in list_stores():
                    store = do_update(key, s["stock_code"])
                    results.append({"stock_code": store["stock_code"],
                                    "quarters": len(store["quarterly"])})
                self._json({"ok": True, "results": results})
            else:
                self._json({"error": "not found"}, 404)
        except SystemExit as e:  # lookup 실패, 키 없음 등 사용자 오류
            self._json({"ok": False, "error": str(e)}, 400)
        except Exception as e:  # noqa: BLE001 — 화면에 사유를 보여준다
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
button:disabled { opacity: .5; cursor: wait; }
#status { font-size: 13px; color: var(--ink2); min-height: 18px; }
#status.err { color: var(--bad); white-space: pre-wrap; }
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
.table-wrap { overflow-x: auto; }
.neg { color: var(--bad); }
.tabs { display: flex; gap: 8px; margin-bottom: 10px; }
.tabs button.on { border-color: var(--accent); color: var(--accent); font-weight: 600; }
.hint { font-size: 12px; color: var(--muted); margin-top: 8px; line-height: 1.6; }
</style>
</head>
<body>
<div class="wrap">
  <h1>다트 재무 데이터 수집기<small>매출액 · 영업이익 · 판관비 · 재고자산 (단위: 백만원)</small></h1>

  <section class="panel">
    <div class="row">
      <input type="text" id="query" placeholder="종목명 또는 종목코드 (예: 효성중공업)">
      <button class="primary" id="btn-add">종목 추가 (3년치 수집)</button>
      <button id="btn-update-all">전체 업데이트</button>
    </div>
    <p id="status"></p>
  </section>

  <section class="panel">
    <h2>종목</h2>
    <div class="table-wrap">
      <table>
        <thead><tr><th>종목</th><th>코드</th><th>분기 수</th><th>최근 분기</th>
          <th>마지막 수집</th><th></th></tr></thead>
        <tbody id="stock-list"></tbody>
      </table>
    </div>
    <p class="hint">새 분기·반기·사업보고서가 공시되면 [업데이트]를 누르세요 —
      작년~올해 보고서를 다시 받아 새로 나온 분기만 저장소에 쌓입니다(중복 안전).
      데이터는 data/ 폴더의 종목별 JSON에 보관됩니다.</p>
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
      재고자산은 분기말 잔액. 판관비율 = 판관비 ÷ 매출, 재고/매출 = 재고자산 ÷ 매출(분기).
      연결(CFS) 재무제표 기준(없으면 별도).</p>
  </section>
</div>

<script>
"use strict";
const $ = id => document.getElementById(id);
let currentCode = null, currentTab = "q", cache = {};

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
function setStatus(msg, isErr) {
  $("status").textContent = msg || "";
  $("status").className = isErr ? "err" : "";
}
async function api(path, body) {
  const opt = body ? { method: "POST", body: JSON.stringify(body) } : {};
  const res = await fetch(path, opt);
  const data = await res.json();
  if (body && !data.ok) throw new Error(data.error || "실패");
  return data;
}

async function refreshList() {
  const stocks = await api("/api/stocks");
  const tbody = $("stock-list");
  tbody.innerHTML = "";
  for (const s of stocks) {
    const tr = document.createElement("tr");
    if (s.stock_code === currentCode) tr.className = "active";
    tr.innerHTML = `<td>${s.corp_name}</td><td>${s.stock_code}</td>` +
      `<td>${s.quarters}</td><td>${s.latest || "–"}</td>` +
      `<td>${(s.updated || "").replace("T", " ")}</td><td></td>`;
    const btn = document.createElement("button");
    btn.textContent = "업데이트";
    btn.addEventListener("click", e => { e.stopPropagation(); update(s.stock_code); });
    tr.lastChild.appendChild(btn);
    tr.addEventListener("click", () => showDetail(s.stock_code));
    tbody.appendChild(tr);
  }
}

async function showDetail(code) {
  currentCode = code;
  delete cache[code];
  const store = cache[code] || (cache[code] = await api("/api/stock/" + code));
  $("detail").hidden = false;
  $("detail-title").textContent = `${store.corp_name} (${store.stock_code})`;
  renderDetail(store);
  refreshList();
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

function busy(on, msg) {
  for (const b of document.querySelectorAll("button")) b.disabled = on;
  if (msg !== undefined) setStatus(msg);
}

async function run(msg, fn) {
  busy(true, msg);
  try {
    await fn();
    setStatus("완료");
  } catch (e) {
    setStatus(String(e.message || e), true);
  } finally {
    busy(false);
    refreshList();
  }
}

function update(code) {
  run(`${code} 업데이트 중... (다트 조회, 수십 초 걸릴 수 있음)`, async () => {
    await api("/api/update", { code });
    if (currentCode === code) await showDetail(code);
  });
}

$("btn-add").addEventListener("click", () => {
  const q = $("query").value.trim();
  if (!q) { setStatus("종목명이나 종목코드를 입력하세요.", true); return; }
  run(`'${q}' 수집 중... (3년치 보고서 조회 — 최초 실행은 1~2분 걸릴 수 있음)`,
    async () => {
      const r = await api("/api/add", { query: q });
      $("query").value = "";
      await showDetail(r.stock_code);
    });
});
$("query").addEventListener("keydown", e => {
  if (e.key === "Enter") $("btn-add").click();
});
$("btn-update-all").addEventListener("click", () => {
  run("전체 종목 업데이트 중...", async () => {
    await api("/api/update-all", {});
    if (currentCode) await showDetail(currentCode);
  });
});
$("tab-q").addEventListener("click", () => {
  currentTab = "q";
  if (currentCode && cache[currentCode]) renderDetail(cache[currentCode]);
});
$("tab-a").addEventListener("click", () => {
  currentTab = "a";
  if (currentCode && cache[currentCode]) renderDetail(cache[currentCode]);
});

refreshList();
</script>
</body>
</html>
"""


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    port = 8899
    if "--port" in argv:
        i = argv.index("--port")
        port = int(argv[i + 1])
    if "--dir" in argv:
        i = argv.index("--dir")
        global DATA_DIR
        DATA_DIR = argv[i + 1]

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
