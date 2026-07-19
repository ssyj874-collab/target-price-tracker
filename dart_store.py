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

# 계정 매칭: account_id(표준 태그) 우선, 없으면 account_nm(정규화) 비교.
# 손익 항목은 IS뿐 아니라 CIS(단일 포괄손익계산서)에도 온다 — 이걸 안
# 받으면 포괄손익 단일 표를 쓰는 회사가 통째로 빈다.
_MATCHERS = {
    "revenue": {
        "ids": {"ifrs-full_Revenue", "ifrs_Revenue"},
        "names": {"매출액", "수익(매출액)", "매출액(수익)", "영업수익", "매출"},
        "sj": {"IS", "CIS"}, "cumulative": True,
    },
    "op": {
        "ids": {"dart_OperatingIncomeLoss"},
        "names": {"영업이익", "영업이익(손실)", "영업손실", "영업손실(이익)",
                  "영업손익"},
        "sj": {"IS", "CIS"}, "cumulative": True,
    },
    "sga": {
        "ids": {"dart_TotalSellingGeneralAdministrativeExpenses"},
        "names": {"판매비와관리비", "판매비및관리비"},
        "sj": {"IS", "CIS"}, "cumulative": True,
    },
    "inventory": {
        "ids": {"ifrs-full_Inventories", "ifrs_Inventories"},
        "names": {"재고자산"},
        "sj": {"BS"}, "cumulative": False,
    },
}
_METRICS = tuple(_MATCHERS)

# "Ⅰ. 매출액", "1.매출액" 같은 순번 접두어 제거용
_ORDINAL_PREFIX = re.compile(r"^[0-9IVXⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+\.")

# 계정 미매칭 진단용 — 보고서 행은 있는데 매출·영업이익을 못 찾은 경우
# 그 보고서의 계정명 샘플을 남긴다 (다음 매칭 개선의 근거)
LAST_MISS: Optional[list] = None

# 한국표준산업분류(KSIC) 대분류(2자리) 이름 — 업종 필터용
KSIC_DIVISIONS = {
    "01": "농업", "02": "임업", "03": "어업",
    "05": "석탄·석유광업", "06": "원유·가스채굴", "07": "금속광업",
    "08": "비금속광물광업", "10": "식료품", "11": "음료", "12": "담배",
    "13": "섬유", "14": "의복", "15": "가죽·신발", "16": "목재",
    "17": "펄프·종이", "18": "인쇄", "19": "석유정제", "20": "화학",
    "21": "의약품", "22": "고무·플라스틱", "23": "비금속광물제품",
    "24": "1차금속", "25": "금속가공", "26": "전자부품·통신장비",
    "27": "의료·정밀기기", "28": "전기장비", "29": "기계·장비",
    "30": "자동차", "31": "기타운송장비", "32": "가구", "33": "기타제품",
    "34": "기계수리", "35": "전기·가스", "36": "수도", "37": "하수처리",
    "38": "폐기물처리", "39": "환경정화", "41": "종합건설", "42": "전문건설",
    "45": "자동차판매", "46": "도매·상품중개", "47": "소매",
    "49": "육상운송", "50": "수상운송", "51": "항공운송", "52": "물류·창고",
    "55": "숙박", "56": "음식점", "58": "출판·게임SW", "59": "영상·음반",
    "60": "방송", "61": "통신", "62": "IT서비스·SW개발", "63": "정보서비스",
    "64": "금융", "65": "보험·연금", "66": "금융지원서비스", "68": "부동산",
    "70": "연구개발", "71": "전문서비스", "72": "엔지니어링",
    "73": "과학기술서비스", "74": "사업시설관리", "75": "사업지원서비스",
    "76": "임대", "85": "교육", "86": "보건업", "87": "사회복지",
    "90": "예술·스포츠", "91": "여가서비스",
}


def industry_name(code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    return KSIC_DIVISIONS.get(str(code).strip()[:2])


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
        name = _ORDINAL_PREFIX.sub("", name)
        for metric, m in _MATCHERS.items():
            if out[metric] is not None or sj not in m["sj"]:
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
    global LAST_MISS
    order = ["CFS", "OFS"]
    if fs_hint in order:
        order.remove(fs_hint)
        order.insert(0, fs_hint)
    miss_sample = None
    for fs in order:
        data = _call_api("fnlttSinglAcntAll.json", crtfc_key=key,
                         corp_code=corp_code, bsns_year=str(year),
                         reprt_code=_REPRT[q], fs_div=fs)
        rows = data.get("list", [])
        if not rows:
            continue
        metrics = extract_metrics(rows)
        # 은행·지주 등 금융사는 매출액 계정이 없다 — 영업이익만 있어도
        # 저장한다(매출 칸은 비움). 둘 다 없으면 이 재무제표는 불채택.
        if metrics["op"] is not None or metrics["revenue"] is not None:
            return metrics, fs
        miss_sample = sorted({
            (r.get("account_nm") or "").strip()
            for r in rows if (r.get("sj_div") or "") in ("IS", "CIS")
        })[:20]
    if miss_sample:
        LAST_MISS = miss_sample
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
    global LAST_MISS
    path = store_path(data_dir, corp)
    store = load_store(path) or new_store(corp)
    store.setdefault("cums", {})
    todo = missing_periods(store, periods)
    added = 0
    LAST_MISS = None
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
        # 여전히 빈 종목이면 왜 비는지 계정명 샘플을 남긴다(매칭 개선 근거)
        if not store["cums"] and LAST_MISS:
            store["diag_accounts"] = LAST_MISS
        if added or not os.path.exists(path) or store.get("diag_accounts"):
            rebuild(store)
            store["updated"] = dt.datetime.now().isoformat(timespec="seconds")
            save_store(path, store)
    return store, added


_CORP_CLS = {"Y": "유가", "K": "코스닥", "N": "코넥스", "E": "기타"}


def ensure_industry(key: str, corp: dict, data_dir: str) -> Optional[str]:
    """표준산업분류코드·시장구분이 없으면 다트 기업개요에서 받아 저장.

    corp_cls(Y=유가/K=코스닥/N=코넥스/E=기타)가 공식 시장구분이라
    상장폐지·코넥스·기타법인을 정확히 걸러낼 수 있다.
    """
    path = store_path(data_dir, corp)
    store = load_store(path) or new_store(corp)
    if "industry_code" in store and "market" in store:
        return store.get("industry_code")
    data = _call_api("company.json", crtfc_key=key, corp_code=corp["corp_code"])
    code = (data.get("induty_code") or "").strip()
    cls = (data.get("corp_cls") or "").strip()
    store["industry_code"] = code
    store["industry_name"] = industry_name(code)
    store["corp_cls"] = cls
    store["market"] = _CORP_CLS.get(cls, "")
    save_store(path, store)
    return code


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
