"""네이버금융 업종 시세 API 탐색. python3 debug_krx.py"""
import requests, time

HDR = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://finance.naver.com/",
}

def get(label, url, **kwargs):
    try:
        r = requests.get(url, headers=HDR, timeout=10, **kwargs)
        print(f"[{label}] {r.status_code} ({len(r.content)} bytes)")
        if r.status_code == 200:
            ct = r.headers.get("content-type","")
            if "json" in ct:
                j = r.json()
                if isinstance(j, dict):
                    print("  keys:", list(j.keys())[:10])
                elif isinstance(j, list):
                    print("  list len:", len(j), "| first:", str(j[0])[:200] if j else "")
            else:
                print("  →", r.text[:400])
        else:
            print("  →", r.text[:200])
    except Exception as e:
        print(f"[{label}] ERROR: {e}")
    print()
    time.sleep(0.3)

print("=== 네이버 금융 업종지수 ===\n")

# 업종별 지수 목록 (코스피 업종 목록)
get("업종 목록", "https://finance.naver.com/sise/sise_group.nhn",
    params={"type": "upjong"})

# 업종 상세 (no=3: 음식료품?)
get("음식료품 상세(no=3)", "https://finance.naver.com/sise/sise_group_detail.nhn",
    params={"type": "upjong", "no": "3"})

# 업종 차트 - fchart
get("fchart KPI", "https://fchart.stock.naver.com/sise.nhn",
    params={"symbol": "KPI", "timeframe": "day", "count": "5", "requestType": "0"})

# 네이버 업종지수 차트 - 다른 API
get("업종 차트 API", "https://m.stock.naver.com/api/index/KOSPI/price",
    params={"startTime": "20240101", "endTime": "20240110", "timeframe": "1D"})

# 업종 일별 시세 - HTML scraping target
get("업종 일별시세 페이지", "https://finance.naver.com/sise/sise_index_day.nhn",
    params={"code": "KPI", "page": "1"})

print("=== 네이버 금융 업종 차트 데이터 ===\n")

# 네이버 업종별 차트 (코스피 서브인덱스)
for code in ["001", "002", "003", "004", "005", "006"]:
    get(f"업종코드 {code}", "https://finance.naver.com/sise/sise_index_day.nhn",
        params={"code": code, "page": "1"})

print("=== KRX 데이터포털 업종지수 ===\n")

# KRX 업종지수 - 올바른 BLD 탐색
for bld in [
    "dbms/MDC/STAT/standard/MDCSTAT00101",   # 전체 시장 기본
    "dbms/MDC/STAT/standard/MDCSTAT00801",   # 업종 시세?
    "dbms/MDC/STAT/standard/MDCSTAT00901",
    "dbms/MDC/STAT/standard/MDCSTAT01601",   # 업종 지수?
    "dbms/MDC/STAT/standard/MDCSTAT01701",
]:
    get(f"KRX {bld.split('/')[-1]}", "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd",
        params={
            "bld": bld,
            "locale": "ko_KR",
            "trdDd": "20240102",
            "idxIndMktClss": "01",
            "idxIndClss": "02",
        })
