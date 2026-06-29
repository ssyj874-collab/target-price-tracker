"""
종목명 일괄 업데이트 스크립트
장 마감 후 또는 주말에 한 번 실행하면 한글 종목명을 영구 캐시에 저장합니다.
이후에는 장중에 sugu_calculator.py를 실행해도 항상 한글명이 표시됩니다.

사용법:
    python3 fetch_names.py
"""

import json
import time
from pathlib import Path
from sugu_calculator import load_universe, kis_stock_info, NAMES_FILE, CACHE_DIR

def main():
    tickers = load_universe()
    total   = len(tickers)

    existing = {}
    if NAMES_FILE.exists():
        existing = json.loads(NAMES_FILE.read_text())

    print(f"종목명 수집 시작: {total}개 종목")
    updated = 0
    for i, ticker in enumerate(tickers, 1):
        info = kis_stock_info(ticker)
        name = info.get('name', '')
        if name and name != ticker:
            existing[ticker] = name
            updated += 1
        print(f"\r  {i}/{total} {ticker} → {name}", end='', flush=True)
        time.sleep(0.05)

    print(f"\n\n{updated}개 종목명 업데이트 완료")
    NAMES_FILE.write_text(json.dumps(existing, ensure_ascii=False, indent=2))
    print(f"저장: {NAMES_FILE}")

    # sugu_result.json도 이름 업데이트
    result_file = Path(__file__).parent / 'sugu_result.json'
    if result_file.exists():
        result = json.loads(result_file.read_text())
        for row in result.get('data', []):
            t = row.get('ticker', '')
            if t in existing:
                row['name'] = existing[t]
        result_file.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(f"sugu_result.json 종목명 업데이트 완료")

if __name__ == '__main__':
    main()
