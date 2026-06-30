"""
엑셀 역사 데이터 임포트 (순수 Python, numpy/pandas 없음).
사용법: python3 import_excel.py <엑셀파일경로>
"""
import sys, zipfile, json
from datetime import date, timedelta
import xml.etree.ElementTree as ET
import db
import calculator as calc

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _parse_strings(z):
    with z.open("xl/sharedStrings.xml") as f:
        tree = ET.parse(f)
    result = []
    for si in tree.getroot().iter(f"{NS}si"):
        texts = [t.text or "" for t in si.iter(f"{NS}t")]
        result.append("".join(texts))
    return result


def _excel_date(serial_str: str):
    try:
        serial = int(float(serial_str))
        if serial < 40000:
            return None
        return date(1899, 12, 30) + timedelta(days=serial)
    except Exception:
        return None


def _parse_sheet(z, sheet_name: str, strings: list):
    """iterparse로 시트를 스트리밍 파싱. 순수 Python dict 반환."""
    print(f"  XML 스트리밍 파싱 중 ({sheet_name})...")
    rows_data = {}

    with z.open(f"xl/worksheets/{sheet_name}.xml") as f:
        for event, elem in ET.iterparse(f, events=("end",)):
            if elem.tag != f"{NS}row":
                continue
            r_num = int(elem.get("r", 0))
            row_cells = {}
            for c in elem.findall(f"{NS}c"):
                ref = c.get("r", "")
                col_str = "".join(ch for ch in ref if ch.isalpha())
                c_type = c.get("t", "")
                v_elem = c.find(f"{NS}v")
                if v_elem is None or v_elem.text is None:
                    continue
                val = v_elem.text
                if c_type == "s":
                    try:
                        val = strings[int(val)]
                    except Exception:
                        pass
                row_cells[col_str] = val
            if row_cells:
                rows_data[r_num] = row_cells
            elem.clear()

    h8 = rows_data.get(8, {})
    h9 = rows_data.get(9, {})

    # 컬럼 매핑
    sector_cols = {}
    for col, code in h8.items():
        if col in ("D", "E") or not code:
            continue
        if code in ("Code", "Name", "Item Code", "Unit"):
            continue
        sector_cols[col] = code

    print(f"  업종 수: {len(sector_cols)}")

    returns_by_date = {}   # {date: {sector_code: pct}}
    market_close = {}      # {date: price}

    count = 0
    for r_num in sorted(rows_data.keys()):
        if r_num < 15:
            continue
        row = rows_data[r_num]

        dt = _excel_date(row.get("D", ""))
        if dt is None:
            continue

        e_raw = row.get("E", "")
        try:
            market_price = float(e_raw)
            if market_price <= 0:
                continue
        except Exception:
            continue

        sector_row = {}
        for col, code in sector_cols.items():
            v_raw = row.get(col, "")
            if not v_raw or "#" in str(v_raw):
                continue
            try:
                sector_row[code] = float(v_raw) * 100
            except Exception:
                pass

        if len(sector_row) < 5:
            continue

        returns_by_date[dt] = sector_row
        market_close[dt] = market_price
        count += 1

    print(f"  유효 데이터 행: {count}개")
    return returns_by_date, market_close


def import_market(z, strings, sheet_name, market_name):
    print(f"\n[{market_name}] {sheet_name} 파싱 시작...")
    returns_by_date, market_close = _parse_sheet(z, sheet_name, strings)

    if not returns_by_date:
        print(f"[{market_name}] 데이터 없음")
        return

    dates = sorted(returns_by_date.keys())
    print(f"[{market_name}] 기간: {dates[0]} ~ {dates[-1]}")
    print(f"[{market_name}] DB 저장 중...")

    db.save_raw_json(market_name, returns_by_date, market_close)

    print(f"[{market_name}] 차트 계산 중...")
    chart_data = calc.build_chart_data(market_close, returns_by_date)
    db.save_chart_cache(market_name, chart_data)
    print(f"[{market_name}] ✅ 완료 ({len(chart_data['dates'])}일)")


def main():
    if len(sys.argv) < 2:
        print("사용법: python3 import_excel.py <엑셀파일경로>")
        sys.exit(1)

    xlsx_path = sys.argv[1]
    print(f"파일: {xlsx_path}\n")

    db.init_db()

    with zipfile.ZipFile(xlsx_path) as z:
        print("sharedStrings 파싱 중...")
        strings = _parse_strings(z)
        print(f"  문자열 {len(strings)}개")
        import_market(z, strings, "sheet3", "KOSPI")
        import_market(z, strings, "sheet7", "KOSDAQ")

    print("\n✅ 임포트 완료. 이제 서버를 시작하세요:")
    print("  uvicorn app:app --host 0.0.0.0 --port 8000")


if __name__ == "__main__":
    main()
