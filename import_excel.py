"""
엑셀 역사 데이터 임포트.
사용법: python3 import_excel.py <엑셀파일경로>
"""
import sys, zipfile, re
from datetime import date, timedelta
import pandas as pd
import db
import calculator as calc


def _parse_strings(z):
    with z.open("xl/sharedStrings.xml") as f:
        ss = f.read().decode("utf-8")
    return re.findall(r"<t[^>]*>([^<]*)</t>", ss)


def _excel_date(serial):
    try:
        return date(1899, 12, 30) + timedelta(days=int(float(serial)))
    except Exception:
        return None


def _parse_sheet(z, sheet_name, strings):
    """시트에서 날짜, 시장지수, 업종별 수익률 추출.
    구조: D=날짜, E=시장지수, F이후=업종수익률(소수점, *100=%)
    """
    with z.open(f"xl/worksheets/{sheet_name}.xml") as f:
        sh = f.read().decode("utf-8")

    cells_raw = re.findall(
        r'<c r="([A-Z]+)(\d+)"([^>]*)>(?:<f[^>]*>[^<]*</f>)?<v>([^<]+)</v>', sh
    )
    rows = {}
    for col, row, attrs, val in cells_raw:
        r = int(row)
        is_str = 't="s"' in attrs
        resolved = strings[int(val)] if is_str else val
        if r not in rows:
            rows[r] = {}
        rows[r][col] = resolved

    # 헤더: row 8 = 코드, row 9 = 이름
    h8 = rows.get(8, {})
    h9 = rows.get(9, {})

    # D 이후 컬럼 → 코드 매핑
    col_codes = {}  # Excel col letter → sector code/name
    for col in h8:
        if col in ("D",):
            continue
        code = h8.get(col, "")
        name = h9.get(col, "")
        if code and code not in ("Code", "Name", "Item Code", "Unit"):
            col_codes[col] = code

    market_col = "E"  # IKS500 or IKQ500
    sector_cols = {c: v for c, v in col_codes.items() if c != "E"}

    records = []
    market_records = {}

    for r in sorted(rows.keys()):
        if r < 15:
            continue
        row = rows[r]
        d_raw = row.get("D", "")
        try:
            d_val = float(d_raw)
            if d_val < 40000:
                continue
        except Exception:
            continue

        dt = _excel_date(d_val)
        if dt is None:
            continue

        # 시장지수 (종가)
        e_raw = row.get(market_col, "")
        try:
            market_price = float(e_raw)
            if market_price <= 0:
                continue
        except Exception:
            continue

        # 업종 수익률 (소수점 → %)
        sector_row = {"date": dt}
        valid = 0
        for col, code in sector_cols.items():
            v_raw = row.get(col, "")
            if not v_raw or "#" in str(v_raw):
                continue
            try:
                pct = float(v_raw) * 100  # 소수점→퍼센트
                sector_row[code] = pct
                valid += 1
            except Exception:
                pass

        if valid < 5:
            continue

        records.append(sector_row)
        market_records[dt] = market_price

    if not records:
        return pd.DataFrame(), pd.Series(dtype=float)

    returns_df = pd.DataFrame(records).set_index("date")
    market_close = pd.Series(market_records)
    market_close.index = pd.to_datetime(market_close.index).map(lambda d: d.date())
    market_close.index.name = "date"

    return returns_df, market_close


def import_market(z, strings, sheet_name, market_name):
    print(f"[{market_name}] {sheet_name} 파싱 중...")
    returns_df, market_close = _parse_sheet(z, sheet_name, strings)

    if returns_df.empty:
        print(f"[{market_name}] 데이터 없음")
        return

    print(f"[{market_name}] {len(returns_df)}일 / 업종 {len(returns_df.columns)}개")
    print(f"[{market_name}] 기간: {returns_df.index[0]} ~ {returns_df.index[-1]}")

    db.save_raw_data(market_name, returns_df, market_close)

    chart_data = calc.build_chart_data(market_close, returns_df)
    db.save_chart_cache(market_name, chart_data)
    print(f"[{market_name}] 저장 완료 ({len(chart_data['dates'])}일)\n")


def main():
    if len(sys.argv) < 2:
        print("사용법: python3 import_excel.py <엑셀파일경로>")
        print("예: python3 import_excel.py ~/Downloads/업종쏠림지수.xlsx")
        sys.exit(1)

    xlsx_path = sys.argv[1]
    print(f"파일: {xlsx_path}\n")

    db.init_db()

    with zipfile.ZipFile(xlsx_path) as z:
        strings = _parse_strings(z)
        import_market(z, strings, "sheet3", "KOSPI")
        import_market(z, strings, "sheet7", "KOSDAQ")

    print("✅ 임포트 완료. uvicorn으로 서버를 시작하세요.")


if __name__ == "__main__":
    main()
