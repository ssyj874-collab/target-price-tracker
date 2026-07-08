#!/usr/bin/env python3
"""DART 분기실적 기반 영업레버리지(증분 영업이익률) 계산기.

전체 영업이익률 대신 "추가된 매출에서 얼마가 남았는가"를 본다:

    증분 영업이익률 = (이번 분기 영업이익 - 비교 분기 영업이익)
                    / (이번 분기 매출 - 비교 분기 매출)

이 기울기가 커지는 동안이 이익 성장 구간이고, 정체/하락하는 시점이
가격(P) 반영이 끝났다는 경고 신호다. QoQ와 YoY(계절성 제거) 둘 다 계산한다.

사용법:
    export DART_API_KEY=발급받은키          # https://opendart.fss.or.kr 무료 발급
    python3 operating_leverage.py --name 삼성전자 --quarters 8
    python3 operating_leverage.py --name 효성중공업 --csv out.csv
    python3 operating_leverage.py --demo    # API 키 없이 예시 데이터로 확인

표준 라이브러리만 사용한다 (requests 불필요).
"""

import argparse
import csv
import io
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

DART_BASE = "https://opendart.fss.or.kr/api"
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "dart")

# 보고서 코드: 분기 순서대로 (1분기, 반기, 3분기, 사업보고서)
REPORT_CODES = ["11013", "11012", "11014", "11011"]
REPORT_LABEL = {"11013": "Q1", "11012": "Q2", "11014": "Q3", "11011": "Q4"}

REVENUE_NAMES = {"매출액", "수익(매출액)", "영업수익", "매출"}


@dataclass
class Quarter:
    year: int
    q: int  # 1..4
    revenue: float  # 원
    op: float  # 영업이익, 원

    @property
    def label(self) -> str:
        return f"{self.year}Q{self.q}"


def http_get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "operating-leverage/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def parse_amount(raw: Optional[str]) -> Optional[float]:
    if raw is None:
        return None
    s = str(raw).strip().replace(",", "")
    if s in ("", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def load_corp_codes(api_key: str) -> List[Tuple[str, str, str]]:
    """(corp_code, corp_name, stock_code) 목록. 상장사만. 하루 단위 캐시."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = os.path.join(CACHE_DIR, "corp_codes.json")
    if os.path.exists(cache):
        with open(cache, encoding="utf-8") as f:
            return [tuple(row) for row in json.load(f)]

    url = f"{DART_BASE}/corpCode.xml?crtfc_key={urllib.parse.quote(api_key)}"
    blob = http_get(url, timeout=60)
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        xml_bytes = zf.read(zf.namelist()[0])
    root = ET.fromstring(xml_bytes)
    rows = []
    for el in root.iter("list"):
        stock = (el.findtext("stock_code") or "").strip()
        if not stock:  # 비상장 제외
            continue
        rows.append(((el.findtext("corp_code") or "").strip(),
                     (el.findtext("corp_name") or "").strip(), stock))
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False)
    return rows


def find_corp(api_key: str, name: str) -> Tuple[str, str, str]:
    rows = load_corp_codes(api_key)
    exact = [r for r in rows if r[1] == name]
    if len(exact) == 1:
        return exact[0]
    partial = [r for r in rows if name in r[1]]
    if len(partial) == 1:
        return partial[0]
    if not partial:
        raise SystemExit(f"'{name}' 에 해당하는 상장사를 찾지 못했습니다.")
    listing = "\n".join(f"  {r[1]} (종목코드 {r[2]})" for r in partial[:15])
    raise SystemExit(f"'{name}' 후보가 여러 개입니다. 정확한 사명을 지정하세요:\n{listing}")


def fetch_report(api_key: str, corp_code: str, year: int, reprt_code: str) -> Optional[dict]:
    """fnlttSinglAcnt 호출. 보고서가 없으면 None."""
    params = urllib.parse.urlencode({
        "crtfc_key": api_key, "corp_code": corp_code,
        "bsns_year": str(year), "reprt_code": reprt_code,
    })
    data = json.loads(http_get(f"{DART_BASE}/fnlttSinglAcnt.json?{params}"))
    status = data.get("status")
    if status == "013":  # 조회 데이터 없음
        return None
    if status != "000":
        raise SystemExit(f"DART API 오류 (status={status}): {data.get('message')}")
    return data


def extract_cumulative(data: dict, fs_div: str) -> Optional[Tuple[float, float]]:
    """보고서 시점까지의 누적 (매출, 영업이익). fs_div: CFS(연결)/OFS(별도)."""
    revenue = op = None
    for item in data.get("list", []):
        if item.get("fs_div") != fs_div or item.get("sj_div") != "IS":
            continue
        name = (item.get("account_nm") or "").strip()
        # 분/반기 보고서의 손익계산서는 thstrm_amount가 3개월치,
        # thstrm_add_amount가 누적치. 사업보고서(연간)는 add가 없고 amount가 연간치.
        cum = parse_amount(item.get("thstrm_add_amount"))
        if cum is None:
            cum = parse_amount(item.get("thstrm_amount"))
        if cum is None:
            continue
        if name in REVENUE_NAMES:
            revenue = cum
        elif re.sub(r"[\s()]", "", name).startswith("영업이익"):
            op = cum
    if revenue is None or op is None:
        return None
    return revenue, op


def fetch_quarters(api_key: str, corp_code: str, quarters: int, fs_pref: str) -> Tuple[List[Quarter], str]:
    """최근 N개 분기의 (비누적) 실적. 누적치를 분기별로 분해한다."""
    from datetime import date
    this_year = date.today().year
    years = range(this_year - (quarters // 4) - 2, this_year + 1)

    fs_used = ""
    cumulative: Dict[Tuple[int, int], Tuple[float, float]] = {}
    for year in years:
        for code in REPORT_CODES:
            data = fetch_report(api_key, corp_code, year, code)
            if data is None:
                continue
            if not fs_used:
                for candidate in (["CFS", "OFS"] if fs_pref == "auto" else [fs_pref]):
                    if extract_cumulative(data, candidate):
                        fs_used = candidate
                        break
            if not fs_used:
                continue
            vals = extract_cumulative(data, fs_used)
            if vals:
                q = REPORT_CODES.index(code) + 1
                cumulative[(year, q)] = vals

    result: List[Quarter] = []
    for (year, q) in sorted(cumulative):
        rev_c, op_c = cumulative[(year, q)]
        if q == 1:
            result.append(Quarter(year, 1, rev_c, op_c))
        else:
            prev = cumulative.get((year, q - 1))
            if prev is None:
                continue  # 직전 누적이 없으면 분해 불가
            result.append(Quarter(year, q, rev_c - prev[0], op_c - prev[1]))
    return result[-quarters:], fs_used or fs_pref


@dataclass
class Row:
    quarter: Quarter
    opm: float
    qoq_drev: Optional[float] = None
    qoq_dop: Optional[float] = None
    qoq_incr: Optional[float] = None  # 증분 영업이익률 (QoQ)
    yoy_incr: Optional[float] = None  # 증분 영업이익률 (YoY)


def incremental(cur: Quarter, base: Optional[Quarter]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    if base is None:
        return None, None, None
    drev = cur.revenue - base.revenue
    dop = cur.op - base.op
    ratio = dop / drev if drev > 0 else None  # 매출이 줄면 기울기 해석 무의미
    return drev, dop, ratio


def analyze(quarters: List[Quarter]) -> List[Row]:
    by_key = {(q.year, q.q): q for q in quarters}
    rows = []
    for i, q in enumerate(quarters):
        row = Row(q, opm=(q.op / q.revenue if q.revenue else 0.0))
        prev = quarters[i - 1] if i > 0 else None
        row.qoq_drev, row.qoq_dop, row.qoq_incr = incremental(q, prev)
        _, _, row.yoy_incr = incremental(q, by_key.get((q.year - 1, q.q)))
        rows.append(row)
    return rows


def fmt_won(v: Optional[float]) -> str:
    """원 단위 금액을 조/억 단위로 표시."""
    if v is None:
        return "-"
    eok = v / 1e8
    if abs(eok) >= 10000:
        return f"{eok / 10000:,.1f}조"
    return f"{eok:,.0f}억"


def fmt_pct(v: Optional[float]) -> str:
    return "-" if v is None else f"{v * 100:.1f}%"


def render_table(rows: List[Row]) -> str:
    headers = ["분기", "매출", "영업이익", "OPM",
               "Δ매출(QoQ)", "ΔOP(QoQ)", "증분OPM(QoQ)", "증분OPM(YoY)"]
    body = [[r.quarter.label, fmt_won(r.quarter.revenue), fmt_won(r.quarter.op),
             fmt_pct(r.opm), fmt_won(r.qoq_drev), fmt_won(r.qoq_dop),
             fmt_pct(r.qoq_incr), fmt_pct(r.yoy_incr)] for r in rows]
    widths = [max(display_width(x) for x in [h] + [b[i] for b in body])
              for i, h in enumerate(headers)]

    def line(cells):
        return "  ".join(pad(c, w) for c, w in zip(cells, widths))

    out = [line(headers), line(["-" * w for w in widths])]
    out += [line(b) for b in body]
    return "\n".join(out)


def display_width(s: str) -> int:
    return sum(2 if ord(ch) > 0x2E7F else 1 for ch in s)


def pad(s: str, width: int) -> str:
    return " " * (width - display_width(s)) + s


def summarize(rows: List[Row]) -> str:
    usable = [r for r in rows if r.yoy_incr is not None or r.qoq_incr is not None]
    if len(usable) < 2:
        return "증분 이익률을 비교할 분기가 부족합니다."
    series = [(r.quarter.label, r.yoy_incr if r.yoy_incr is not None else r.qoq_incr)
              for r in usable]
    last_label, last = series[-1]
    prev_label, prev = series[-2]
    msg = [f"최근 증분 영업이익률: {prev_label} {fmt_pct(prev)} → {last_label} {fmt_pct(last)}"]
    if last is None or prev is None:
        msg.append("→ 매출 감소 구간이 있어 기울기 해석에 주의가 필요합니다.")
    elif last > prev:
        msg.append("→ 추가 매출의 수익성이 개선 중 (레버리지 확대 구간).")
    elif last < prev:
        msg.append("→ 증분 이익률 둔화. 가격(P) 반영이 끝나가는지, 물량(Q) 여력이 있는지 확인 필요.")
    else:
        msg.append("→ 증분 이익률 정체. 예측 가능하지만 폭발 구간은 지난 상태일 수 있음.")
    return "\n".join(msg)


def write_csv(rows: List[Row], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["quarter", "revenue_krw", "op_krw", "opm",
                    "qoq_delta_revenue", "qoq_delta_op",
                    "incremental_opm_qoq", "incremental_opm_yoy"])
        for r in rows:
            w.writerow([r.quarter.label, r.quarter.revenue, r.quarter.op,
                        round(r.opm, 6),
                        r.qoq_drev if r.qoq_drev is not None else "",
                        r.qoq_dop if r.qoq_dop is not None else "",
                        round(r.qoq_incr, 6) if r.qoq_incr is not None else "",
                        round(r.yoy_incr, 6) if r.yoy_incr is not None else ""])


def demo_quarters() -> List[Quarter]:
    """통화 예시: 매출 100조→150조→200조, 영업이익 10조→30조→50조.
    전체 OPM은 10%→20%→25%로 계속 좋아 보이지만 증분 OPM은 40%에서 정체."""
    jo = 1e12
    return [
        Quarter(2025, 3, 100 * jo, 10 * jo),
        Quarter(2025, 4, 150 * jo, 30 * jo),
        Quarter(2026, 1, 200 * jo, 50 * jo),
    ]


def main() -> None:
    ap = argparse.ArgumentParser(description="DART 분기실적으로 증분 영업이익률(영업레버리지) 계산")
    ap.add_argument("--name", help="상장사 이름 (예: 삼성전자)")
    ap.add_argument("--corp-code", help="DART 고유번호 8자리 (이름 대신 직접 지정)")
    ap.add_argument("--key", default=os.environ.get("DART_API_KEY"),
                    help="DART API 키 (기본: DART_API_KEY 환경변수)")
    ap.add_argument("--quarters", type=int, default=8, help="분석할 최근 분기 수 (기본 8)")
    ap.add_argument("--fs", choices=["auto", "CFS", "OFS"], default="auto",
                    help="재무제표 구분: 연결(CFS)/별도(OFS), 기본 auto=연결 우선")
    ap.add_argument("--csv", help="결과를 CSV 파일로도 저장")
    ap.add_argument("--demo", action="store_true", help="API 키 없이 예시 숫자로 계산 확인")
    args = ap.parse_args()

    if args.demo:
        quarters, fs_used, title = demo_quarters(), "DEMO", "예시 데이터 (통화 속 숫자)"
    else:
        if not args.key:
            ap.error("API 키가 필요합니다. --key 또는 DART_API_KEY 환경변수를 설정하세요. "
                     "(무료 발급: https://opendart.fss.or.kr)")
        if args.corp_code:
            corp_code, corp_name = args.corp_code, args.corp_code
        elif args.name:
            corp_code, corp_name, stock = find_corp(args.key, args.name)
            corp_name = f"{corp_name} ({stock})"
        else:
            ap.error("--name 또는 --corp-code 를 지정하세요.")
        quarters, fs_used = fetch_quarters(args.key, corp_code, args.quarters, args.fs)
        title = corp_name
        if not quarters:
            raise SystemExit("실적 데이터를 가져오지 못했습니다. 회사/연도를 확인하세요.")

    rows = analyze(quarters)
    fs_label = {"CFS": "연결", "OFS": "별도", "DEMO": "데모"}.get(fs_used, fs_used)
    print(f"\n{title} — 영업레버리지 분석 ({fs_label} 재무제표 기준)\n")
    print(render_table(rows))
    print()
    print(summarize(rows))
    if args.csv:
        write_csv(rows, args.csv)
        print(f"\nCSV 저장: {args.csv}")


if __name__ == "__main__":
    main()
