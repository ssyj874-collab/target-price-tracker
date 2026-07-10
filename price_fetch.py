"""네이버 금융 시세 API에서 분기말 종가를 받아 Quarter.price를 채운다.

엔드포인트: https://api.finance.naver.com/siseJson.naver (비공식 공개 API,
키 불필요). 일봉을 받아 각 분기의 마지막 거래일 종가를 고른다.

- 실적 분기만 채운다. 컨센서스(E) 분기와 오늘 이후로 끝나는 분기는 건너뜀.
- 이미 price가 있는 분기는 덮어쓰지 않는다.
- 네트워크 실패 시 예외 대신 실패 사유 문자열을 돌려줘서 주가 없이
  리포트를 계속 만들 수 있게 한다.
"""

from __future__ import annotations

import calendar
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


def quarter_end(label: str) -> Optional[dt.date]:
    """분기 라벨 → 분기 말일. 2025/03, 2025-3, 2025Q1 모두 허용.

    FnGuide식 라벨(2025/03)은 그 달이 분기 마지막 달이라는 뜻이므로
    해당 월의 말일을 쓴다. 달이 3/6/9/12가 아니어도(변칙 결산) 그대로
    그 달의 말일로 처리한다.
    """
    m = _LABEL_RE.match(label.strip())
    if not m:
        return None
    year = int(m.group(1))
    month = int(m.group(2)) if m.group(2) else int(m.group(3)) * 3
    if not 1 <= month <= 12:
        return None
    return dt.date(year, month, calendar.monthrange(year, month)[1])


def _fetch_daily_closes(code: str, start: dt.date, end: dt.date) -> dict[dt.date, float]:
    """일봉 종가 조회. {날짜: 종가}. 파싱은 정규식으로 방어적으로 한다."""
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


def fill_prices(
    quarters: Sequence[Quarter], code: str, today: Optional[dt.date] = None
) -> tuple[list[Quarter], Optional[str]]:
    """분기말(직전 거래일) 종가로 price를 채운 새 리스트와 실패 사유를 반환."""
    today = today or dt.date.today()
    targets = {}
    for i, q in enumerate(quarters):
        if q.estimate or q.price is not None:
            continue
        end = quarter_end(q.label)
        if end is None or end > today:
            continue
        targets[i] = end
    if not targets:
        return list(quarters), None

    span_start = min(targets.values()) - dt.timedelta(days=14)
    span_end = min(max(targets.values()), today)
    try:
        closes = _fetch_daily_closes(code, span_start, span_end)
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        return list(quarters), f"{code}: {e}"
    if not closes:
        return list(quarters), f"{code}: 시세 데이터가 비어 있음 (종목코드 확인)"

    dates = sorted(closes)
    result = list(quarters)
    for i, end in targets.items():
        # 분기 말일 이전의 마지막 거래일 종가
        candidates = [d for d in dates if d <= end]
        if not candidates:
            continue
        last = candidates[-1]
        if end - last > dt.timedelta(days=10):
            continue  # 분기말 근처 데이터가 없으면 채우지 않는다
        q = result[i]
        result[i] = Quarter(
            label=q.label,
            revenue=q.revenue,
            operating_profit=q.operating_profit,
            price=closes[last],
            estimate=q.estimate,
        )
    return result, None
