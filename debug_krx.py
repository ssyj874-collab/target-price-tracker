"""네이버 업종 API 탐색 3탄 + Yahoo Finance. python3 debug_krx.py"""
import requests, time, re, json

HDR = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://finance.naver.com/",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

def get(label, url, params=None, headers=None):
    try:
        r = requests.get(url, headers=headers or HDR, params=params, timeout=10)
        print(f"[{label}] {r.status_code} ({len(r.content)}B)")
        if r.status_code == 200 and len(r.content) < 200000:
            ct = r.headers.get("content-type", "")
            if "json" in ct:
                j = r.json()
                print(f"  JSON: {str(j)[:400]}")
            else:
                # 날짜 패턴 탐색
                text = r.text
                dates = re.findall(r'\d{4}[.\-/]\d{2}[.\-/]\d{2}', text)
                nums  = re.findall(r'[\d,]{4,}\.?\d*', text)
                if dates:
                    print(f"  날짜 발견: {dates[:5]}")
                    print(f"  숫자: {nums[:10]}")
                else:
                    print(f"  텍스트: {text[:300]}")
    except Exception as e:
        print(f"[{label}] 오류: {e}")
    print()
    time.sleep(0.3)

print("=== 네이버 .naver suffix 시도 ===")
get("업종 목록(.naver)", "https://finance.naver.com/sise/sise_group.naver", {"type": "upjong"})
get("업종 상세 282", "https://finance.naver.com/sise/sise_group_detail.naver", {"type": "upjong", "no": "282"})
get("업종 상세 278", "https://finance.naver.com/sise/sise_group_detail.naver", {"type": "upjong", "no": "278"})

print("=== 네이버 업종 일별 차트 데이터 ===")
# 네이버 업종 지수 일별 (차트용 API)
for code in ["KPI", "KQI", "0001", "1005"]:
    get(f"index_chart_day({code})",
        "https://finance.naver.com/sise/sise_index_chart_day.nhn",
        {"code": code, "timeframe": "day", "count": "10"})

# 네이버 차트 데이터 API
get("fchart upjong 282",
    "https://fchart.stock.naver.com/sise.nhn",
    {"symbol": "282", "timeframe": "day", "count": "5", "requestType": "0"})

get("fchart upjong 278",
    "https://fchart.stock.naver.com/sise.nhn",
    {"symbol": "278", "timeframe": "day", "count": "5", "requestType": "0"})

# 네이버 Finance 새 API
get("naver finance new API",
    "https://finance.naver.com/sise/ajax/sise_group_info.naver",
    {"type": "upjong", "no": "282"})

print("=== Yahoo Finance 한국 시장 ===")
YHD = {"User-Agent": "curl/7.79.1"}

# KOSPI 전체
get("Yahoo KOSPI", "https://query1.finance.yahoo.com/v8/finance/chart/%5EKS11",
    {"interval": "1d", "range": "5d"}, headers=YHD)

# 한국 섹터 ETF들 (TIGER ETF)
for sym in ["139270.KS", "091160.KS", "091170.KS"]:  # 삼성전자, 필라델피아 등
    get(f"Yahoo {sym}",
        f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
        {"interval": "1d", "range": "5d"}, headers=YHD)

print("=== Stooq 한국 시장 ===")
# Stooq - 한국 섹터 인덱스
for sym in ["^ks11", "^ks50", "^kq11", "^ks10p"]:
    get(f"Stooq {sym}",
        f"https://stooq.com/q/d/l/",
        {"s": sym, "i": "d"},
        headers={"User-Agent": "Mozilla/5.0"})
