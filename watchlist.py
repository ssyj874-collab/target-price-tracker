"""워치리스트 리포트 생성 — 종목 파일 여러 개를 하나의 HTML로.

사용법:
    python watchlist.py <디렉토리 | 파일들...> [--html watch.html]
                        [--fetch-price] [--title "워치리스트 이름"]

- 파일 하나가 종목 하나. 종목명은 파일명(확장자 제외).
- 파일 내용은 incremental_margin.py와 같은 형식(가로형 붙여넣기 또는 CSV).
- 파일 안에 `#code=298040` (또는 `# code: 298040`) 주석 줄을 넣으면
  --fetch-price 플래그로 네이버에서 일별 종가 시계열을 받아 심는다.
- 디렉토리를 주면 그 안의 *.txt, *.csv 전부(이름순).

예: watchlist/효성중공업.txt 첫 줄에 #code=298040 을 넣고
    python watchlist.py watchlist/ --fetch-price --html watch.html
"""

from __future__ import annotations

import os
import re
import sys
from typing import Optional, Sequence

from incremental_margin import analyze, looks_like_paste, parse_csv_text, parse_paste, render

_CODE_RE = re.compile(r"^#\s*code\s*[:=]\s*(\d{6})\s*$", re.IGNORECASE | re.MULTILINE)


def load_stock_file(path: str) -> tuple[str, list, Optional[str]]:
    """파일 → (종목명, 분기 리스트, 종목코드 또는 None)."""
    name = os.path.splitext(os.path.basename(path))[0]
    with open(path, encoding="utf-8-sig") as f:
        text = f.read()
    m = _CODE_RE.search(text)
    code = m.group(1) if m else None
    # 주석 줄 제거 후 파싱 (파서는 모르는 줄을 무시하지만 명시적으로)
    body = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
    quarters = parse_paste(body) if looks_like_paste(body) else parse_csv_text(body)
    return name, quarters, code


def collect_inputs(paths: Sequence[str]) -> list[str]:
    files = []
    for p in paths:
        if os.path.isdir(p):
            files.extend(
                os.path.join(p, f)
                for f in sorted(os.listdir(p))
                if f.lower().endswith((".txt", ".csv")) and not f.startswith(".")
            )
        else:
            files.append(p)
    return files


def main(argv: Sequence[str] | None = None) -> int:
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

    html_out = take_option("--html")
    page_title = take_option("--title") or "증분 이익률 워치리스트"
    do_fetch = "--fetch-price" in argv
    if do_fetch:
        argv.remove("--fetch-price")

    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__, file=sys.stderr)
        return 2

    files = collect_inputs(argv)
    if not files:
        print("입력 파일이 없습니다.", file=sys.stderr)
        return 1

    stocks = []
    for path in files:
        try:
            name, quarters, code = load_stock_file(path)
        except (OSError, ValueError) as e:
            print(f"[{path}] 읽기 실패: {e}", file=sys.stderr)
            continue
        if len(quarters) < 2:
            print(f"[{path}] 분기 2개 미만 — 건너뜀", file=sys.stderr)
            continue
        price_series = None
        if do_fetch and code:
            from price_fetch import fetch_for_quarters

            quarters, price_series, failure = fetch_for_quarters(quarters, code)
            if failure:
                print(f"[{name}] 주가 조회 실패: {failure}", file=sys.stderr)
                price_series = None
        elif do_fetch and not code:
            print(f"[{name}] #code=종목코드 주석이 없어 주가 생략", file=sys.stderr)

        analysis = analyze(quarters)
        stocks.append(
            {"name": name, "analysis": analysis, "price_series": price_series}
        )
        print(f"\n=== {name}" + (f" ({code})" if code else "") + " ===")
        print(render(analysis))

    if not stocks:
        print("생성할 종목이 없습니다.", file=sys.stderr)
        return 1

    if html_out:
        from report import render_watchlist

        with open(html_out, "w", encoding="utf-8") as f:
            f.write(render_watchlist(stocks, page_title=page_title))
        print(f"\nHTML 워치리스트 리포트 생성: {html_out} (종목 {len(stocks)}개)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
