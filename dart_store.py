"""DART 전체 재무제표에서 매출·영업이익·판관비·재고자산을 수집해 보관.

fnlttSinglAcntAll(단일회사 전체 재무제표) API를 쓴다 — 주요계정 API에는
판관비·재고자산이 없기 때문. 연결(CFS) 우선, 없으면 별도(OFS).

수집 항목과 처리:
- 매출액 / 영업이익 / 판매비와관리비(판관비): 손익 항목 — 보고서의
  누적치를 받아 분기끼리 차분해 분기 단독 값을 만든다.
- 재고자산: 재무상태표 시점값 — 각 보고서의 분기말 잔액을 그대로 쓴다.
- 연간 값: 사업보고서(11011)의 누적치(=연간)와 연말 재고.
- 금액은 원 단위로 내려오므로 백만원으로 환산(반올림).

보관: data/ 디렉토리에 종목별 JSON 하나.
{
  "corp_code", "corp_name", "stock_code", "updated": ISO시각,
  "quarterly": [{"label": "2024.3분기", "revenue", "op", "sga", "inventory"}...],
  "annual":    [{"year": 2024, "revenue", "op", "sga", "inventory"}...]
}
업데이트는 라벨/연도 기준 upsert라 몇 번을 눌러도 안전하다(멱등).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
from typing import Optional

from dart_fetch import _api_json, _REPRT

# 계정 매칭: account_id(표준 태그) 우선, 없으면 account_nm(공백 제거) 비교
_MATCHERS = {
    "revenue": {
        "ids": {"ifrs-full_Revenue", "ifrs_Revenue"},
        "names": {"매출액", "수익(매출액)", "영업수익", "매출"},
        "sj": "IS", "cumulative": True,
    },
    "op": {
        "ids": {"dart_OperatingIncomeLoss"},
        "names": {"영업이익", "영업이익(손실)"},
        "sj": "IS", "cumulative": True,
    },
    "sga": {
        "ids": {"dart_TotalSellingGeneralAdministrativeExpenses"},
        "names": {"판매비와관리비", "판매비및관리비", "판매비와 관리비"},
        "sj": "IS", "cumulative": True,
    },
    "inventory": {
        "ids": {"ifrs-full_Inventories", "ifrs_Inventories"},
        "names": {"재고자산"},
        "sj": "BS", "cumulative": False,
    },
}
_METRICS = tuple(_MATCHERS)


def _amount(row: dict, cumulative: bool) -> Optional[int]:
    """원 단위 금액. 손익 항목은 당기누적(thstrm_add_amount) 우선."""
    fields = ("thstrm_add_amount", "thstrm_amount") if cumulative else ("thstrm_amount",)
    for f in fields:
        raw = (row.get(f) or "").replace(",", "").strip()
        if raw and raw != "-":
            try:
                return int(raw)
            except ValueError:
                continue
    return None


def extract_metrics(rows: list[dict]) -> dict[str, Optional[int]]:
    """보고서 응답에서 {revenue, op, sga, inventory} (원, 누적/시점)."""
    out: dict[str, Optional[int]] = {m: None for m in _METRICS}
    for r in rows:
        sj = (r.get("sj_div") or "").strip()
        acc_id = (r.get("account_id") or "").strip()
        name = re.sub(r"\s+", "", r.get("account_nm") or "")
        for metric, m in _MATCHERS.items():
            if out[metric] is not None or sj != m["sj"]:
                continue
            if acc_id in m["ids"] or name in m["names"]:
                out[metric] = _amount(r, m["cumulative"])
    return out


def fetch_report(key: str, corp_code: str, year: int, reprt: str) -> list[dict]:
    """전체 재무제표 행. 연결(CFS) 우선, 비면 별도(OFS). 없으면 []."""
    for fs in ("CFS", "OFS"):
        data = _api_json("fnlttSinglAcntAll.json", crtfc_key=key,
                         corp_code=corp_code, bsns_year=str(year),
                         reprt_code=reprt, fs_div=fs)
        rows = data.get("list", [])
        if rows:
            return rows
    return []


def collect_year(key: str, corp_code: str, year: int) -> dict[int, dict]:
    """{분기번호: metrics(누적/시점, 원)} — 공시된 보고서만."""
    out = {}
    for q, reprt in _REPRT.items():
        rows = fetch_report(key, corp_code, year, reprt)
        if not rows:
            continue
        metrics = extract_metrics(rows)
        if metrics["revenue"] is not None and metrics["op"] is not None:
            out[q] = metrics
    return out


def _mil(x: Optional[int]) -> Optional[int]:
    return None if x is None else round(x / 1e6)


def build_quarters(year_data: dict[int, dict[int, dict]]) -> list[dict]:
    """연도별 누적치 → 분기 단독 값(백만원). 재고자산은 시점값 그대로."""
    out = []
    for year in sorted(year_data):
        cums = year_data[year]
        prev = None
        for q in (1, 2, 3, 4):
            cur = cums.get(q)
            if cur is None:
                prev = None  # 중간 보고서 누락 → 다음 분기 손익 차분 불가
                continue
            row = {"label": f"{year}.{q}분기", "inventory": _mil(cur["inventory"])}
            for m in ("revenue", "op", "sga"):
                if q == 1:
                    row[m] = _mil(cur[m])
                elif prev is not None and prev.get(m) is not None and cur.get(m) is not None:
                    row[m] = _mil(cur[m] - prev[m])
                else:
                    row[m] = None  # 차분 기준 없음 — 재고(시점값)만 남긴다
            out.append(row)
            prev = cur
    return out


def build_annual(year_data: dict[int, dict[int, dict]]) -> list[dict]:
    """사업보고서(4분기 보고서)의 누적치 = 연간. 재고는 연말 잔액."""
    out = []
    for year in sorted(year_data):
        q4 = year_data[year].get(4)
        if not q4:
            continue
        out.append({
            "year": year,
            "revenue": _mil(q4["revenue"]),
            "op": _mil(q4["op"]),
            "sga": _mil(q4["sga"]),
            "inventory": _mil(q4["inventory"]),
        })
    return out


# ---------------------------------------------------------------------------
# 저장소
# ---------------------------------------------------------------------------

def store_path(data_dir: str, corp: dict) -> str:
    safe = re.sub(r"[^\w가-힣]", "_", corp["corp_name"])
    return os.path.join(data_dir, f"{corp['stock_code']}_{safe}.json")


def load_store(path: str) -> Optional[dict]:
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save_store(path: str, store: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _label_key(label: str) -> tuple:
    m = re.match(r"^(\d{4})\.([1-4])분기$", label)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def upsert(store: dict, quarters: list[dict], annual: list[dict]) -> dict:
    """라벨/연도 기준으로 새 값을 덮어쓰며 병합(멱등)."""
    q_map = {r["label"]: r for r in store.get("quarterly", [])}
    for r in quarters:
        q_map[r["label"]] = r
    a_map = {r["year"]: r for r in store.get("annual", [])}
    for r in annual:
        a_map[r["year"]] = r
    store["quarterly"] = sorted(q_map.values(), key=lambda r: _label_key(r["label"]))
    store["annual"] = sorted(a_map.values(), key=lambda r: r["year"])
    return store


def update_stock(key: str, corp: dict, data_dir: str,
                 start_year: int, end_year: int) -> dict:
    """start~end년 보고서를 수집해 저장소에 병합하고 파일로 저장."""
    path = store_path(data_dir, corp)
    store = load_store(path) or {
        "corp_code": corp["corp_code"],
        "corp_name": corp["corp_name"],
        "stock_code": corp["stock_code"],
        "quarterly": [], "annual": [],
    }
    year_data = {}
    for year in range(start_year, end_year + 1):
        cums = collect_year(key, corp["corp_code"], year)
        if cums:
            year_data[year] = cums
    upsert(store, build_quarters(year_data), build_annual(year_data))
    store["updated"] = dt.datetime.now().isoformat(timespec="seconds")
    save_store(path, store)
    return store
