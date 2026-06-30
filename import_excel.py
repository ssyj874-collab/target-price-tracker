"""
엑셀 역사 데이터 임포트.
사용법: python3 import_excel.py <엑셀파일경로>
"""
import sys, zipfile, io
from datetime import date, timedelta
import xml.etree.ElementTree as ET
import pandas as pd
import db
import calculator as calc

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _parse_strings(z):
    """sharedStrings.xml → 문자열 리스트."""
    with z.open("xl/sharedStrings.xml") as f:
        tree = ET.parse(f)
    result = []
    for si in tree.getroot().iter(f"{NS}si"):
        texts = [t.text or "" for t in si.iter(f"{NS}t")]
        result.append("".join(texts))
    return result


def _col_to_idx(col: str) -> int:
    """Excel 컬럼 문자 → 0-based 인덱스 (A=0, B=1, Z=25, AA=26, ...)."""
    idx = 0
    for ch in col:
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx - 1


def _excel_date(serial_str: str):
    try:
        serial = int(float(serial_str))
        if serial < 40000:
            return None
        return date(1899, 12, 30) + timedelta(days=serial)
    except Exception:
        return None


def _parse_sheet(z, sheet_name: str, strings: list):
    """iterparse로 시트를 스트리밍 파싱. 메모리 절약."""
    print(f"  XML 스트리밍 파싱 중 ({sheet_name})...")
    rows_data = {}

    with z.open(f"xl/worksheets/{sheet_name}.xml") as f:
        context = ET.iterparse(f, events=("end",))
        for event, elem in context:
            if elem.tag != f"{NS}row":
                continue
            r_num = int(elem.get("r", 0))
            row_cells = {}
            for c in elem.findall(f"{NS}c"):
                ref = c.get("r", "")
                # 컬럼 문자 추출 (숫자 제거)
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

    # 헤더: row 8 = 코드, row 9 = 이름
    h8 = rows_data.get(8, {})
    h9 = rows_data.get(9, {})

    # 컬럼 매핑: 컬럼 문자 → 업종 코드
    sector_cols = {}
    market_col = None
    for col, code in h8.items():
        if col == "D" or not code or code in ("Code", "Name", "Item Code", "Unit"):
            continue
        if col == "E":
            market_col = "E"
        else:
            sector_cols[col] = code

    if not market_col:
        print("  시장 컬럼(E) 없음")
        return pd.DataFrame(), pd.Series(dtype=float)

    print(f"  업종 수: {len(sector_cols)}")

    records = []
    market_records = {}

    for r_num in sorted(rows_data.keys()):
        if r_num < 15:
            continue
        row = rows_data[r_num]

        # 날짜
        dt = _excel_date(row.get("D", ""))
        if dt is None:
            continue

        # 시장지수
        e_raw = row.get("E", "")
        try:
            market_price = float(e_raw)
            if market_price <= 0:
                continue
        except Exception:
            continue

        # 업종 수익률 (소수점 → %)
        sector_row = {}
        valid = 0
        for col, code in sector_cols.items():
            v_raw = row.get(col, "")
            if not v_raw or "#" in str(v_raw):
                continue
            try:
                pct = float(v_raw) * 100
                sector_row[code] = pct
                valid += 1
            except Exception:
                pass

        if valid < 5:
            continue

        records.append({"date": dt, **sector_row})
        market_records[dt] = market_price

    if not records:
        return pd.DataFrame(), pd.Series(dtype=float)

    returns_df = pd.DataFrame(records).set_index("date")
    market_close = pd.Series(market_records)
    market_close.index = pd.to_datetime(list(market_records.keys())).map(lambda d: d.date())
    market_close.index.name = "date"

    return returns_df, market_close


def import_market(z, strings, sheet_name, market_name):
    print(f"\n[{market_name}] {sheet_name} 파싱 시작...")
    returns_df, market_close = _parse_sheet(z, sheet_name, strings)

    if returns_df.empty:
        print(f"[{market_name}] 데이터 없음")
        return

    print(f"[{market_name}] {len(returns_df)}일 / 업종 {len(returns_df.columns)}개")
    print(f"[{market_name}] 기간: {returns_df.index[0]} ~ {returns_df.index[-1]}")
    print(f"[{market_name}] DB 저장 중...")

    db.save_raw_data(market_name, returns_df, market_close)

    print(f"[{market_name}] 차트 계산 중...")
    chart_data = calc.build_chart_data(market_close, returns_df)
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
        print(f"  문자열 {len(strings)}개\n")
        import_market(z, strings, "sheet3", "KOSPI")
        import_market(z, strings, "sheet7", "KOSDAQ")

    print("\n✅ 임포트 완료. 이제 서버를 시작하세요:")
    print("  uvicorn app:app --host 0.0.0.0 --port 8000")


if __name__ == "__main__":
    main()
