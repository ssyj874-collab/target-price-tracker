"""DART OpenAPI에서 분기 매출액·영업이익을 받아 워치리스트 종목 파일 생성.

사용법:
    python dart_fetch.py 효성중공업 --from 2022 [옵션]
    python dart_fetch.py 298040 --from 2022 --build watch.html

    종목명 또는 6자리 종목코드로 조회. 결과는 워치리스트 디렉토리
    (기본 watchlist/)에 "<회사명>.csv"로 저장되며, --build를 주면
    디렉토리 전체로 워치리스트 HTML까지 바로 생성한다.

옵션:
    --from 2022        시작 연도 (기본: 3년 전)
    --to 2026          끝 연도 (기본: 올해)
    --dir watchlist    종목 파일을 쓸 디렉토리
    --build watch.html 저장 후 워치리스트 HTML 생성 (--fetch-price 포함)
    --key XXXX         DART 인증키 (없으면 DART_API_KEY 환경변수
                       → dart_api_key.txt 파일 순으로 찾음)
    --ofs              연결(CFS) 대신 별도(OFS) 재무제표 사용

준비물: DART 인증키 — https://opendart.fss.or.kr 회원가입 후
[인증키 신청]에서 무료 발급(즉시). 발급받은 키를 환경변수
DART_API_KEY로 export 하거나, 이 스크립트 옆에 dart_api_key.txt
파일로 저장.

분기 값 도출 방식 (DART의 손익 계정은 보고서마다 누적 기준이 섞여
있어서, 누적치끼리 차분하는 게 가장 안전하다):
    Q1 = 1분기보고서 누적
    Q2 = 반기보고서 누적 − Q1 누적
    Q3 = 3분기보고서 누적 − 반기 누적
    Q4 = 사업보고서(연간) − 3분기 누적
금액은 원 단위로 내려오므로 백만원으로 환산해 저장한다(반올림).
연결(CFS) 재무제표 우선, 없으면 별도(OFS). 컨센서스(E)는 DART에
없으므로 필요하면 리포트에서 직접 추가하거나 FnGuide 표를 붙여넣을 것.
"""

from __future__ import annotations

import io
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from typing import Optional, Sequence

_BASE = "https://opendart.fss.or.kr/api"
_HEADERS = {"User-Agent": "Mozilla/5.0"}
# 보고서 코드: 1분기/반기/3분기/사업보고서
_REPRT = {1: "11013", 2: "11012", 3: "11014", 4: "11011"}
_REVENUE_NAMES = ("매출액", "수익(매출액)", "영업수익", "매출")
_OP_NAMES = ("영업이익", "영업이익(손실)")
_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "corp_codes_cache.json")


# ---------------------------------------------------------------------------
# 인증키
# ---------------------------------------------------------------------------

def resolve_key(cli_key: Optional[str]) -> str:
    if cli_key:
        return cli_key.strip()
    env = os.environ.get("DART_API_KEY", "").strip()
    if env:
        return env
    for path in ("dart_api_key.txt",
                 os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "dart_api_key.txt")):
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                key = f.read().strip()
            if key:
                return key
    raise SystemExit(
        "DART 인증키가 없습니다.\n"
        "1) https://opendart.fss.or.kr 회원가입 → [인증키 신청] (무료, 즉시 발급)\n"
        "2) 발급받은 키를 다음 중 한 방법으로 설정:\n"
        "   - 환경변수: export DART_API_KEY=발급받은키\n"
        "   - 파일: 이 스크립트 옆에 dart_api_key.txt 로 저장\n"
        "   - 옵션: --key 발급받은키"
    )


# ---------------------------------------------------------------------------
# HTTP (테스트에서 모킹하는 지점)
# ---------------------------------------------------------------------------

def make_ssl_context() -> Optional[ssl.SSLContext]:
    """certifi가 설치돼 있으면 그 인증서 번들을 쓴다 (macOS 파이썬 대응)."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return None


_SSL_CTX = make_ssl_context()

_CERT_HELP = """SSL 인증서 오류 — macOS의 python.org 파이썬은 인증서를 따로 설치해야 합니다.
다음 중 하나를 실행한 뒤 다시 시도하세요:
  1) open "/Applications/Python 3.14/Install Certificates.command"
     (폴더명의 버전 숫자는 설치된 파이썬 버전에 맞게)
  2) python3 -m pip install certifi   (이 스크립트가 자동으로 사용합니다)"""


def _http_get(url: str, retries: int = 2) -> bytes:
    req = urllib.request.Request(url, headers=_HEADERS)
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as resp:
                return resp.read()
        except urllib.error.URLError as e:
            if isinstance(getattr(e, "reason", None), ssl.SSLCertVerificationError):
                raise SystemExit(_CERT_HELP)
            if attempt >= retries:
                raise
        except (TimeoutError, OSError):
            if attempt >= retries:
                raise
        import time

        time.sleep(2 * (attempt + 1))  # 일시적 네트워크 문제 재시도
    raise RuntimeError("unreachable")


def _api_json(path: str, **params) -> dict:
    url = f"{_BASE}/{path}?{urllib.parse.urlencode(params)}"
    data = json.loads(_http_get(url).decode("utf-8"))
    status = data.get("status")
    if status == "000":
        return data
    if status == "013":  # 조회 데이터 없음
        return {"status": "013", "list": []}
    raise RuntimeError(
        f"DART API 오류 status={status}: {data.get('message', '')} "
        f"(020=인증키 확인, 021=요청 한도 초과)"
    )


# ---------------------------------------------------------------------------
# 회사 고유번호 (corp_code) 조회 — zip을 받아 로컬 캐시
# ---------------------------------------------------------------------------

def _download_corp_map(key: str) -> dict:
    """{종목코드|회사명: {corp_code, corp_name, stock_code}} 매핑 생성."""
    raw = _http_get(f"{_BASE}/corpCode.xml?crtfc_key={key}")
    if raw[:1] == b"{":  # zip이 아니라 JSON 오류 응답
        err = json.loads(raw.decode("utf-8"))
        raise RuntimeError(f"corpCode 오류 status={err.get('status')}: {err.get('message')}")
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        xml_bytes = zf.read(zf.namelist()[0])
    entries = []
    for corp in ET.fromstring(xml_bytes).iter("list"):
        stock = (corp.findtext("stock_code") or "").strip()
        if not stock:
            continue  # 비상장 제외
        entries.append({
            "corp_code": (corp.findtext("corp_code") or "").strip(),
            "corp_name": (corp.findtext("corp_name") or "").strip(),
            "stock_code": stock,
        })
    return {"entries": entries}


def load_corp_map(key: str, refresh: bool = False) -> dict:
    if not refresh and os.path.exists(_CACHE_FILE):
        try:
            with open(_CACHE_FILE, encoding="utf-8") as f:
                cached = json.load(f)
            if cached.get("entries"):
                return cached
        except (OSError, ValueError):
            pass
    corp_map = _download_corp_map(key)
    try:
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(corp_map, f, ensure_ascii=False)
    except OSError:
        pass
    return corp_map


def lookup_corp(corp_map: dict, query: str) -> dict:
    """종목코드(6자리) 또는 회사명으로 상장사 찾기."""
    q = query.strip()
    entries = corp_map["entries"]
    if re.fullmatch(r"\d{6}", q):
        for e in entries:
            if e["stock_code"] == q:
                return e
        raise SystemExit(f"종목코드 {q}를 찾지 못했습니다.")
    exact = [e for e in entries if e["corp_name"] == q]
    if len(exact) == 1:
        return exact[0]
    partial = [e for e in entries if q in e["corp_name"]]
    if len(partial) == 1:
        return partial[0]
    if partial:
        names = ", ".join(f"{e['corp_name']}({e['stock_code']})" for e in partial[:10])
        raise SystemExit(f"'{q}'와 일치하는 상장사가 여러 개입니다: {names}")
    raise SystemExit(f"'{q}'를 찾지 못했습니다. 종목코드 6자리로 시도해 보세요.")


# ---------------------------------------------------------------------------
# 분기 실적
# ---------------------------------------------------------------------------

def _parse_amount(row: dict) -> Optional[int]:
    """누적 금액(원). 분기/반기 보고서는 당기누적(thstrm_add_amount) 우선."""
    for field in ("thstrm_add_amount", "thstrm_amount"):
        raw = (row.get(field) or "").replace(",", "").strip()
        if raw and raw != "-":
            try:
                return int(raw)
            except ValueError:
                continue
    return None


def _extract_cums(rows: list[dict], prefer_ofs: bool = False) -> Optional[tuple[int, int]]:
    """보고서 응답에서 (매출액 누적, 영업이익 누적)을 원 단위로 추출."""
    order = ("OFS", "CFS") if prefer_ofs else ("CFS", "OFS")
    for fs in order:
        rev = op = None
        for r in rows:
            if r.get("fs_div") != fs:
                continue
            name = (r.get("account_nm") or "").replace(" ", "")
            if rev is None and name in _REVENUE_NAMES:
                rev = _parse_amount(r)
            elif op is None and name in _OP_NAMES:
                op = _parse_amount(r)
        if rev is not None and op is not None:
            return rev, op
    return None


def fetch_year_cums(key: str, corp_code: str, year: int,
                    prefer_ofs: bool = False) -> dict[int, tuple[int, int]]:
    """{분기번호: (매출액 누적, 영업이익 누적)} — 없는 보고서는 생략."""
    cums = {}
    for q, reprt in _REPRT.items():
        data = _api_json("fnlttSinglAcnt.json", crtfc_key=key,
                         corp_code=corp_code, bsns_year=str(year),
                         reprt_code=reprt)
        got = _extract_cums(data.get("list", []), prefer_ofs=prefer_ofs)
        if got:
            cums[q] = got
    return cums


def quarters_from_cums(year_cums: dict[int, dict[int, tuple[int, int]]]) -> list[dict]:
    """연도별 누적치 → 분기 단독 값(백만원). 누적 차분이 불가능한 분기는 생략.

    반환: [{"label": "2022.1분기", "revenue": 599503, "op": -4765}, ...]
    """
    out = []
    for year in sorted(year_cums):
        cums = year_cums[year]
        prev = None  # 직전 분기 누적
        for q in (1, 2, 3, 4):
            cur = cums.get(q)
            if cur is None:
                prev = None  # 중간이 비면 그 뒤 분기는 차분 불가
                continue
            if q == 1:
                rev, op = cur
            elif prev is None:
                prev = cur
                continue
            else:
                rev, op = cur[0] - prev[0], cur[1] - prev[1]
            out.append({
                "label": f"{year}.{q}분기",
                "revenue": round(rev / 1e6),
                "op": round(op / 1e6),
            })
            prev = cur
    return out


# ---------------------------------------------------------------------------
# 종목 파일 저장
# ---------------------------------------------------------------------------

def write_stock_csv(path: str, stock_code: str, quarters: list[dict]) -> None:
    lines = [f"#code={stock_code}", "quarter,revenue,operating_profit"]
    for q in quarters:
        lines.append(f"{q['label']},{q['revenue']},{q['op']}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Sequence[str] | None = None) -> int:
    import datetime as dt

    argv = list(sys.argv[1:] if argv is None else argv)

    def take_option(flag: str) -> Optional[str]:
        if flag not in argv:
            return None
        i = argv.index(flag)
        try:
            value = argv[i + 1]
        except IndexError:
            raise SystemExit(f"{flag} 뒤에 값을 지정하세요.")
        del argv[i : i + 2]
        return value

    year_from = take_option("--from")
    year_to = take_option("--to")
    out_dir = take_option("--dir") or "watchlist"
    build = take_option("--build")
    cli_key = take_option("--key")
    prefer_ofs = "--ofs" in argv
    if prefer_ofs:
        argv.remove("--ofs")
    refresh = "--refresh-corps" in argv
    if refresh:
        argv.remove("--refresh-corps")

    if len(argv) != 1 or argv[0] in ("-h", "--help"):
        print(__doc__, file=sys.stderr)
        return 2

    key = resolve_key(cli_key)
    this_year = dt.date.today().year
    start = int(year_from) if year_from else this_year - 3
    end = int(year_to) if year_to else this_year

    print("회사 목록 확인 중...", file=sys.stderr)
    corp = lookup_corp(load_corp_map(key, refresh=refresh), argv[0])
    print(f"{corp['corp_name']} (종목코드 {corp['stock_code']}, "
          f"고유번호 {corp['corp_code']}) — {start}~{end}년 조회", file=sys.stderr)

    year_cums = {}
    for year in range(start, end + 1):
        cums = fetch_year_cums(key, corp["corp_code"], year, prefer_ofs=prefer_ofs)
        if cums:
            year_cums[year] = cums
            print(f"  {year}년: {len(cums)}개 보고서", file=sys.stderr)
        else:
            print(f"  {year}년: 데이터 없음", file=sys.stderr)

    quarters = quarters_from_cums(year_cums)
    if len(quarters) < 2:
        print("분기 데이터를 2개 이상 확보하지 못했습니다.", file=sys.stderr)
        return 1

    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{corp['corp_name']}.csv")
    write_stock_csv(path, corp["stock_code"], quarters)
    print(f"저장: {path} ({len(quarters)}개 분기, 단위 백만원)", file=sys.stderr)

    # 터미널 요약
    from incremental_margin import Quarter, analyze, render

    qs = [Quarter(q["label"], q["revenue"], q["op"]) for q in quarters]
    print(render(analyze(qs)))

    if build:
        import watchlist as wl

        rc = wl.main([out_dir, "--fetch-price", "--html", build])
        if rc == 0:
            print(f"\n워치리스트 리포트: {build}", file=sys.stderr)
        return rc
    print(f"\n리포트 생성: python watchlist.py {out_dir} --fetch-price --html watch.html",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
