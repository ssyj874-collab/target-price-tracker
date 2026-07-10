"""일별 주가 시계열 확보 — 네이버 금융 API 또는 CSV 파일.

리포트의 주가는 분기별 점이 아니라 일별 선그래프로 그려지므로,
여기서는 일봉 종가 시계열 전체를 확보하는 것이 목표다:

- fetch_for_quarters(): 네이버 금융(비공식 공개 API, 키 불필요)에서
  첫 분기 시작 전 ~ 오늘까지의 일봉을 받아 (분기말 종가가 채워진
  quarters, 리포트용 일별 시계열, 실패 사유)를 돌려준다.
- load_price_csv(): 증권사·네이버 등에서 내려받은 일별 시세 CSV
  (날짜,종가 — date,close/헤더 없는 2열도 허용)를 같은 형태로 읽는다.

분기말 종가는 터미널 테이블과 KPI용으로 함께 채운다(컨센서스(E) 분기와
미래 분기는 건너뜀). 네트워크 실패 시 예외 대신 사유 문자열을 돌려줘서
주가 없이 리포트를 계속 만들 수 있게 한다.
"""

from __future__ import annotations

import calendar
import csv
import datetime as dt
import re
import urllib.error
import urllib.request
from typing import Optional, Sequence

from incremental_margin import Quarter

_ENDPOINT = "https://api.finance.naver.com/siseJson.naver"
# 헤더 없는 요청은 차단될 수 있어 브라우저 UA를 붙인다.
_HEADERS = {"User-Agent": "Mozilla/5.0"}

_LABEL_RE = re.compile(r"^(\d{4})(?:[./\-](\d{1,2})|Q([1-4]))$")
_LABEL_KR = re.compile(r"^(\d{2,4})\.([1-4])분기$")


def quarter_end(label: str) -> Optional[dt.date]:
    """분기 라벨 → 분기 말일. 23.1분기, 2025.1분기, 2025/03, 2025Q1 허용.

    2자리 연도는 2000년대로 본다. FnGuide식 라벨(2025/03)은 그 달이 분기
    마지막 달이라는 뜻이므로 해당 월의 말일을 쓴다. 달이 3/6/9/12가
    아니어도(변칙 결산) 그대로 그 달의 말일로 처리한다.
    """
    label = label.strip()
    m = _LABEL_KR.match(label)
    if m:
        year = int(m.group(1))
        if year < 100:
            year += 2000
        month = int(m.group(2)) * 3
        return dt.date(year, month, calendar.monthrange(year, month)[1])
    m = _LABEL_RE.match(label)
    if not m:
        return None
    year = int(m.group(1))
    month = int(m.group(2)) if m.group(2) else int(m.group(3)) * 3
    if not 1 <= month <= 12:
        return None
    return dt.date(year, month, calendar.monthrange(year, month)[1])


def _fetch_daily_closes(code: str, start: dt.date, end: dt.date) -> dict[dt.date, float]:
    """네이버 일봉 종가 조회. {날짜: 종가}. 파싱은 정규식으로 방어적으로."""
    url = (
        f"{_ENDPOINT}?symbol={code}&requestType=1"
        f"&startTime={start:%Y%m%d}&endTime={end:%Y%m%d}&timeframe=day"
    )
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    closes = {}
    # 행 형식: ["20250102", 시가, 고가, 저가, 종가, 거래량, 외인소진율]
    for m in re.finditer(r'\[\s*"(\d{8})"\s*,([^\]]*)\]', body):
        parts = [p.strip() for p in m.group(2).split(",")]
        if len(parts) < 4:
            continue
        try:
            date = dt.datetime.strptime(m.group(1), "%Y%m%d").date()
            closes[date] = float(parts[3])  # 날짜 뒤 4번째 = 종가
        except ValueError:
            continue
    return closes


def load_price_csv(path: str) -> dict[dt.date, float]:
    """일별 시세 CSV → {날짜: 종가}.

    헤더 '날짜/date'와 '종가/close/주가' 열을 찾고, 헤더가 없으면
    앞 두 열을 (날짜, 종가)로 본다. 날짜는 2025-01-02 / 2025.01.02 /
    2025/01/02 / 20250102 허용. 종가의 쉼표는 제거.
    """
    closes: dict[dt.date, float] = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = [r for r in csv.reader(f) if any(c.strip() for c in r)]
    if not rows:
        return closes
    date_idx, close_idx, start = 0, 1, 0
    head = [c.strip().lower() for c in rows[0]]
    date_names = {"날짜", "일자", "date"}
    close_names = {"종가", "주가", "close", "price"}
    if any(h in date_names for h in head):
        date_idx = next(i for i, h in enumerate(head) if h in date_names)
        close_idx = next(
            (i for i, h in enumerate(head) if h in close_names), 1
        )
        start = 1
    for r in rows[start:]:
        if len(r) <= max(date_idx, close_idx):
            continue
        raw_d = r[date_idx].strip().replace(".", "-").replace("/", "-")
        raw_c = r[close_idx].replace(",", "").strip()
        try:
            if re.fullmatch(r"\d{8}", raw_d):
                date = dt.datetime.strptime(raw_d, "%Y%m%d").date()
            else:
                date = dt.date.fromisoformat(raw_d)
            closes[date] = float(raw_c)
        except ValueError:
            continue
    return closes


def closes_to_series(closes: dict[dt.date, float]) -> list[list]:
    """리포트 임베드용 [[ISO날짜, 종가], ...] (날짜순)."""
    return [[d.isoformat(), closes[d]] for d in sorted(closes)]


def fill_quarter_prices(
    quarters: Sequence[Quarter],
    closes: dict[dt.date, float],
    today: Optional[dt.date] = None,
) -> list[Quarter]:
    """각 실적 분기의 분기말(직전 거래일) 종가로 price를 채운 새 리스트.

    이미 price가 있는 분기는 덮어쓰지 않고, (E)·미래 분기는 건너뛴다.
    분기말 근처(10일 이내)에 데이터가 없으면 채우지 않는다.
    """
    today = today or dt.date.today()
    dates = sorted(closes)
    result = list(quarters)
    for i, q in enumerate(quarters):
        if q.estimate or q.price is not None:
            continue
        end = quarter_end(q.label)
        if end is None or end > today:
            continue
        candidates = [d for d in dates if d <= end]
        if not candidates:
            continue
        last = candidates[-1]
        if end - last > dt.timedelta(days=10):
            continue
        result[i] = Quarter(
            label=q.label,
            revenue=q.revenue,
            operating_profit=q.operating_profit,
            price=closes[last],
            estimate=q.estimate,
        )
    return result


def fetch_for_quarters(
    quarters: Sequence[Quarter], code: str, today: Optional[dt.date] = None
) -> tuple[list[Quarter], list[list], Optional[str]]:
    """네이버에서 일봉을 받아 (quarters, 일별 시계열, 실패 사유)를 반환.

    조회 범위: 가장 이른 분기의 말일 100일 전 ~ 오늘. 실패하면
    quarters는 그대로, 시계열은 빈 리스트, 사유 문자열이 채워진다.
    """
    today = today or dt.date.today()
    ends = [quarter_end(q.label) for q in quarters]
    known = [e for e in ends if e is not None]
    if not known:
        return list(quarters), [], "분기 라벨에서 날짜를 읽을 수 없음"
    start = min(known) - dt.timedelta(days=100)
    try:
        closes = _fetch_daily_closes(code, start, today)
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        return list(quarters), [], f"{code}: {e}"
    if not closes:
        return list(quarters), [], f"{code}: 시세 데이터가 비어 있음 (종목코드 확인)"
    filled = fill_quarter_prices(quarters, closes, today=today)
    return filled, closes_to_series(closes), None


def fill_prices(
    quarters: Sequence[Quarter], code: str, today: Optional[dt.date] = None
) -> tuple[list[Quarter], Optional[str]]:
    """(하위호환) 분기말 종가만 채운다. 새 코드는 fetch_for_quarters 사용."""
    filled, _series, err = fetch_for_quarters(quarters, code, today=today)
    return filled, err
