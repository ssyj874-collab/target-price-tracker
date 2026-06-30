"""네이버 업종 API 데이터 확인. python3 debug_krx.py"""
import requests, time, re, json

HDR = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://finance.naver.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

BASE = "https://finance.naver.com"

def show(label, url, params=None):
    r = requests.get(url, headers=HDR, params=params, timeout=10)
    ct = r.headers.get("content-type","")
    print(f"[{label}] {r.status_code} ({len(r.content)}B) ct={ct[:40]}")
    if r.status_code == 200:
        try:
            j = r.json()
            if isinstance(j, list):
                print(f"  리스트 {len(j)}개")
                if j:
                    print(f"  첫번째: {json.dumps(j[0], ensure_ascii=False)[:400]}")
                    print(f"  두번째: {json.dumps(j[1], ensure_ascii=False)[:200] if len(j)>1 else ''}")
            elif isinstance(j, dict):
                print(f"  키: {list(j.keys())}")
                print(f"  내용: {json.dumps(j, ensure_ascii=False)[:600]}")
        except:
            print(f"  텍스트: {r.text[:500]}")
    else:
        print(f"  → {r.text[:200]}")
    print()
    time.sleep(0.3)

print("=== 네이버 업종 API (200 확인된 것) ===\n")

show("upjongList", f"{BASE}/api/sise/upjongList")
show("group?upjong", f"{BASE}/api/sise/group", {"type": "upjong"})

print("=== 히스토리 관련 엔드포인트 ===\n")

# upjongList 기반 히스토리 탐색
show("upjongList?no=282", f"{BASE}/api/sise/upjongList", {"no": "282"})
show("upjongList?no=282&page=2", f"{BASE}/api/sise/upjongList", {"no": "282", "page": "2"})
show("upjongHistory", f"{BASE}/api/sise/upjongHistory", {"no": "282"})
show("upjongChart", f"{BASE}/api/sise/upjongChart", {"no": "282", "timeframe": "day", "count": "10"})
show("upjongDay", f"{BASE}/api/sise/upjongDay", {"no": "282"})
show("upjong detail", f"{BASE}/api/sise/upjong", {"no": "282", "type": "upjong"})
show("group detail", f"{BASE}/api/sise/group", {"type": "upjong", "no": "282"})
show("group history", f"{BASE}/api/sise/groupHistory", {"type": "upjong", "no": "282"})

print("=== upjong 코드로 모바일 API 재시도 ===\n")

HDR_M = {**HDR, "Referer": "https://m.stock.naver.com/"}
for code in ["UPJONG282", "KOSPI_UPJONG_282", "U282", "SECTOR282",
             "UPJONG_282", "upjong282", "KRX282"]:
    r = requests.get(
        f"https://m.stock.naver.com/api/index/{code}/price",
        headers=HDR_M,
        params={"startTime": "20260623", "endTime": "20260630", "timeframe": "1D"},
        timeout=8,
    )
    if r.status_code == 200:
        print(f"  [{code}] ✅ {r.text[:200]}")
    elif r.status_code != 409:
        print(f"  [{code}] {r.status_code}: {r.text[:80]}")
    time.sleep(0.1)

print("(409가 아닌 코드만 출력)")
print()

# upjongList로 받은 no 기반 히스토리
print("=== 네이버 upjong 차트/히스토리 패턴 완전 탐색 ===\n")
for suffix in ["Chart", "History", "Price", "Day", "Daily", "Candle", "Ohlc"]:
    for no in ["282", "278"]:
        url = f"{BASE}/api/sise/upjong{suffix}"
        r = requests.get(url, headers=HDR, params={"no": no, "count": "5"}, timeout=8)
        if r.status_code == 200 and len(r.content) > 100:
            print(f"  [✅ upjong{suffix} no={no}] {r.text[:300]}")
        time.sleep(0.1)
print("(200+데이터 없으면 빈 출력)")
