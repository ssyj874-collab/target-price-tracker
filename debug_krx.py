"""네이버 모바일 API 업종코드 탐색. python3 debug_krx.py"""
import requests, time, json

HDR = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://m.stock.naver.com/",
}

BASE = "https://m.stock.naver.com/api"

def get_json(url, params=None):
    r = requests.get(url, headers=HDR, params=params, timeout=10)
    if r.status_code == 200:
        try:
            return r.json()
        except:
            return r.text
    return None

# 1. 먼저 전체 인덱스 목록 확인
print("=== 네이버 인덱스 목록 ===")
for path in [
    "/index/kospi/price",
    "/index/sector/list",
    "/index/upjong/list",
    "/sector/list",
    "/index/sectorList",
    "/stock/sector/list",
]:
    r = requests.get(f"{BASE}{path}", headers=HDR, timeout=10)
    print(f"[{path}] {r.status_code} ({len(r.content)}B)")
    if r.status_code == 200:
        try:
            j = r.json()
            if isinstance(j, list):
                print(f"  리스트 {len(j)}개 | 첫번째: {str(j[0])[:200]}")
            elif isinstance(j, dict):
                print(f"  키: {list(j.keys())[:8]}")
        except:
            print(f"  텍스트: {r.text[:200]}")
    time.sleep(0.2)

print()

# 2. KOSPI 업종 목록 검색
print("=== KOSPI 업종 목록 ===")
for path in [
    "/index/KOSPI/sectorList",
    "/index/sectorList?market=KOSPI",
    "/domestic/index/sectorList",
    "/index/group/list",
]:
    r = requests.get(f"{BASE}{path}", headers=HDR, timeout=10)
    print(f"[{path}] {r.status_code} ({len(r.content)}B)")
    if r.status_code == 200:
        try:
            j = r.json()
            print(f"  {str(j)[:300]}")
        except:
            print(f"  {r.text[:200]}")
    time.sleep(0.2)

print()

# 3. 알려진 업종 코드 후보 테스트
print("=== 업종 코드 후보 테스트 (기간별 데이터) ===")
CANDIDATES = [
    # Naver 전통 코드
    "KPI", "KQI", "KPI001", "KPI002", "KPI003",
    # 업종 번호
    "001", "002", "003", "KOSPI_FOOD",
    # 네이버 upjong 코드
    "UPJONG_1", "UPJONG001",
    # 다른 형식
    "KOSPI.GIC.10", "GIC10",
]
for code in CANDIDATES:
    r = requests.get(
        f"{BASE}/index/{code}/price",
        headers=HDR,
        params={"startTime": "20260620", "endTime": "20260630", "timeframe": "1D"},
        timeout=10,
    )
    if r.status_code == 200:
        try:
            j = r.json()
            if j:
                print(f"[{code}] ✅ 200 - {str(j[0])[:200]}")
            else:
                print(f"[{code}] 200 빈 리스트")
        except:
            print(f"[{code}] 200 텍스트: {r.text[:100]}")
    else:
        print(f"[{code}] {r.status_code}")
    time.sleep(0.15)

print()

# 4. 네이버 PC 업종 페이지에서 upjong 코드 추출
print("=== 네이버 PC 업종 목록 파싱 ===")
r = requests.get(
    "https://finance.naver.com/sise/sise_group.nhn",
    headers={**HDR, "Referer": "https://finance.naver.com/"},
    params={"type": "upjong"},
    timeout=10,
)
if r.status_code == 200:
    # no= 값 찾기
    import re
    hits = re.findall(r'no=(\d+)[^>]*>([^<]+)</a>', r.text)
    print(f"발견된 upjong 코드 ({len(hits)}개):")
    for no, name in hits[:30]:
        print(f"  no={no}: {name.strip()}")
