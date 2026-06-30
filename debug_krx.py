"""네이버 업종 API URL 추출 + 대안 소스 탐색. python3 debug_krx.py"""
import requests, time, re, json

HDR = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://finance.naver.com/",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

# ============================================================
# 1. 업종 목록 HTML에서 API URL / 데이터 찾기
# ============================================================
print("=== 네이버 업종 목록 HTML 내 API URL 추출 ===\n")
r = requests.get(
    "https://finance.naver.com/sise/sise_group.naver",
    headers=HDR, params={"type": "upjong"}, timeout=15,
)
html = r.text

# polling / api / ajax URL 찾기
found_urls = set()
for pattern in [
    r'["\']([^"\']*(?:polling|realtime|ajax|/api/)[^"\']*)["\']',
    r'url\s*:\s*["\']([^"\']+)["\']',
    r'fetch\(["\']([^"\']+)["\']',
]:
    for m in re.finditer(pattern, html, re.I):
        u = m.group(1)
        if u.startswith(('http', '/')):
            found_urls.add(u)

print(f"발견된 API URL {len(found_urls)}개:")
for u in sorted(found_urls)[:30]:
    print(f"  {u}")

# __NEXT_DATA__ 탐색
nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>({.*?})</script>', html, re.S)
if nd:
    print(f"\n__NEXT_DATA__ 발견! 길이: {len(nd.group(1))}")
    try:
        data = json.loads(nd.group(1))
        print(f"  키: {list(data.keys())}")
    except:
        print(f"  파싱 실패: {nd.group(1)[:200]}")
else:
    print("\n__NEXT_DATA__ 없음")

# 업종 데이터 직접 포함 여부
upjong_json = re.search(r'upjong[^=]*=\s*(\[{.*?}\])', html, re.S)
if upjong_json:
    print(f"\n업종 JSON 데이터 발견: {upjong_json.group(1)[:300]}")

print()

# ============================================================
# 2. 네이버 업종 AJAX 엔드포인트 직접 시도
# ============================================================
print("=== 네이버 업종 AJAX 엔드포인트 ===\n")

HDR2 = {**HDR, "Accept": "application/json, text/plain, */*",
         "X-Requested-With": "XMLHttpRequest"}

for url in [
    "https://finance.naver.com/sise/sise_group_ajax.naver?type=upjong",
    "https://finance.naver.com/sise/ajaxSiseUpjong.naver?type=upjong",
    "https://finance.naver.com/sise/getUpjongList.naver",
    "https://finance.naver.com/api/sise/upjongList",
    "https://finance.naver.com/api/sise/group?type=upjong",
    "https://api.finance.naver.com/service/sise/upjong",
    "https://m.stock.naver.com/api/sector/list",
    "https://m.stock.naver.com/api/domestic/market/sector",
    "https://m.stock.naver.com/api/domestic/market/KOSPI/sector",
    "https://m.stock.naver.com/api/domestic/category/industry",
    "https://m.stock.naver.com/api/domestic/upjong",
]:
    try:
        r2 = requests.get(url, headers=HDR2, timeout=8)
        ct = r2.headers.get("content-type", "")
        print(f"  [{r2.status_code}] {url.split('naver.com')[-1][:60]}")
        if r2.status_code == 200 and "json" in ct:
            j = r2.json()
            print(f"    JSON: {str(j)[:200]}")
        elif r2.status_code == 200 and r2.text.strip().startswith(('[', '{')):
            print(f"    JSON-like: {r2.text[:200]}")
    except Exception as e:
        print(f"  [오류] {url.split('naver.com')[-1][:60]}: {e}")
    time.sleep(0.2)

print()

# ============================================================
# 3. Naver Finance 업종 차트 히스토리 (fchart 변형)
# ============================================================
print("=== fchart 업종 코드 변형 테스트 ===\n")
for sym in ["KPI1", "KPI2", "KPI3", "U282", "UPJ282", "UPJONG282",
            "N282", "GROUP282", "B282", "S282", "F282"]:
    r3 = requests.get("https://fchart.stock.naver.com/sise.nhn",
        headers=HDR,
        params={"symbol": sym, "timeframe": "day", "count": "3", "requestType": "0"},
        timeout=8)
    body = r3.text.strip()
    if "<candle" in body or ("200" == str(r3.status_code) and len(body) > 60):
        print(f"  [{sym}] ✅ {body[:200]}")
    elif r3.status_code != 200:
        print(f"  [{sym}] {r3.status_code}")
    # else: silent (empty protocol)
    time.sleep(0.1)

print("(✅ 없으면 모두 빈 protocol)")
