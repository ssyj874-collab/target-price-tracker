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
  "fs_div": "CFS"|"OFS",              # 이 회사가 쓰는 재무제표 (호출 절약용)
  "cums": {"2024": {"1": {revenue, op, sga, inventory}, ...}},  # 보고서 원본(누적, 원)
  "quarterly": [{"label": "2024.3분기", "revenue", "op", "sga", "inventory"}...],
  "annual":    [{"year": 2024, "revenue", "op", "sga", "inventory"}...]
}
cums가 원본이고 quarterly/annual은 cums에서 재계산된다. 이미 저장된
(연도, 분기)는 API를 다시 부르지 않으므로 업데이트를 몇 번 돌려도
호출이 낭비되지 않는다 — 전 상장사 정기 갱신이 가능한 이유.

API_HOOK: 호출 직전에 불리는 훅(페이싱·쿼터 계산용). 전체 수집 잡이
여기에 속도 제한과 일일 한도 체크를 끼워 넣는다.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
from typing import Callable, Optional

from dart_fetch import _api_json, _REPRT

# 호출 직전 훅 — 잡 러너가 페이싱/쿼터/진행 카운트에 사용
API_HOOK: Optional[Callable[[], None]] = None


class BudgetExceeded(Exception):
    """일일 호출 한도 도달 — 잡을 중단하고 다음 날 이어서."""


def _call_api(path: str, **params) -> dict:
    if API_HOOK is not None:
        API_HOOK()
    return _api_json(path, **params)

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


def fetch_period(key: str, corp_code: str, year: int, q: int,
                 fs_hint: Optional[str] = None) -> tuple[Optional[dict], Optional[str]]:
    """(연도, 분기) 보고서의 metrics(누적/시점, 원)와 사용한 fs_div.

    fs_hint(이 회사가 지난번에 쓴 재무제표 구분)를 먼저 시도해 호출을
    절약한다. 공시가 없거나 매출·영업이익을 못 찾으면 (None, None).
    """
    order = ["CFS", "OFS"]
    if fs_hint in order:
        order.remove(fs_hint)
        order.insert(0, fs_hint)
    for fs in order:
        data = _call_api("fnlttSinglAcntAll.json", crtfc_key=key,
                         corp_code=corp_code, bsns_year=str(year),
                         reprt_code=_REPRT[q], fs_div=fs)
        rows = data.get("list", [])
        if not rows:
            continue
        metrics = extract_metrics(rows)
        if metrics["revenue"] is not None and metrics["op"] is not None:
            return metrics, fs
    return None, None


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


def new_store(corp: dict) -> dict:
    return {"corp_code": corp["corp_code"], "corp_name": corp["corp_name"],
            "stock_code": corp["stock_code"], "cums": {},
            "quarterly": [], "annual": []}


def rebuild(store: dict) -> dict:
    """cums(원본 누적치)에서 quarterly/annual을 다시 만든다."""
    year_data = {
        int(y): {int(q): m for q, m in qs.items()}
        for y, qs in store.get("cums", {}).items()
    }
    store["quarterly"] = build_quarters(year_data)
    store["annual"] = build_annual(year_data)
    return store


def missing_periods(store: dict, periods: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """periods 중 아직 cums에 없는 (연도, 분기)만 남긴다."""
    cums = store.get("cums", {})
    return [(y, q) for y, q in periods
            if str(q) not in cums.get(str(y), {})]


def ensure_periods(key: str, corp: dict, data_dir: str,
                   periods: list[tuple[int, int]]) -> tuple[dict, int]:
    """지정한 (연도, 분기)들 중 없는 것만 수집해 저장. (store, 새로 받은 수).

    이미 저장된 기간은 API를 부르지 않으므로 멱등이면서 싸다.
    BudgetExceeded가 나면 그때까지 받은 것을 저장하고 그대로 올린다.
    """
    path = store_path(data_dir, corp)
    store = load_store(path) or new_store(corp)
    store.setdefault("cums", {})
    todo = missing_periods(store, periods)
    added = 0
    try:
        for year, q in todo:
            metrics, fs = fetch_period(key, corp["corp_code"], year, q,
                                       fs_hint=store.get("fs_div"))
            if metrics is None:
                continue  # 미공시 — 다음 갱신 때 다시 시도
            store["cums"].setdefault(str(year), {})[str(q)] = metrics
            store["fs_div"] = fs
            added += 1
    finally:
        if added or not os.path.exists(path):
            rebuild(store)
            store["updated"] = dt.datetime.now().isoformat(timespec="seconds")
            save_store(path, store)
    return store, added


def year_range_periods(start_year: int, end_year: int) -> list[tuple[int, int]]:
    return [(y, q) for y in range(start_year, end_year + 1) for q in (1, 2, 3, 4)]


def rolling_periods(today: Optional[dt.date] = None, count: int = 4) -> list[tuple[int, int]]:
    """오늘 기준 직전 count개 분기 (진행 중인 분기 제외) — 실적시즌 갱신 대상."""
    today = today or dt.date.today()
    year, q = today.year, (today.month - 1) // 3 + 1
    out = []
    for _ in range(count):
        q -= 1
        if q < 1:
            q = 4
            year -= 1
        out.append((year, q))
    return sorted(out)


def update_stock(key: str, corp: dict, data_dir: str,
                 start_year: int, end_year: int) -> dict:
    """start~end년 중 빠진 보고서를 수집해 저장(하위호환 API)."""
    store, _added = ensure_periods(key, corp, data_dir,
                                   year_range_periods(start_year, end_year))
    return store
