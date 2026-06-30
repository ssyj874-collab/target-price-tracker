"""네이버 업종 API 코드 탐색 2탄. python3 debug_krx.py"""
import requests, time, re

HDR = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://m.stock.naver.com/",
}
HDR_PC = {**HDR, "Referer": "https://finance.naver.com/"}

def test_mobile(code):
    r = requests.get(
        f"https://m.stock.naver.com/api/index/{code}/price",
        headers=HDR,
        params={"startTime": "20260620", "endTime": "20260630", "timeframe": "1D"},
        timeout=8,
    )
    return r.status_code, r.text[:200] if r.status_code != 404 else ""

# 1. upjong no 값으로 테스트
print("=== upjong no 값으로 모바일 API 테스트 ===")
for no in [282, 278, 263, 301, 321, 25, 273, 299, 269, 315, 265]:
    code = str(no)
    status, text = test_mobile(code)
    if status == 200:
        print(f"  [{no}] ✅ 200: {text[:150]}")
    else:
        print(f"  [{no}] {status}")
    time.sleep(0.1)

# 2. Naver 모바일 업종 목록 API 찾기
print("\n=== 모바일 업종 목록 API 탐색 ===")
for path in [
    "https://m.stock.naver.com/api/index/KOSPI/industry",
    "https://m.stock.naver.com/api/industry/list",
    "https://m.stock.naver.com/api/sector/KOSPI/list",
    "https://m.stock.naver.com/domestic/index/KOSPI/total",
    "https://m.stock.naver.com/api/index/KOSPI/sector",
    "https://m.stock.naver.com/api/board/KOSPI/industry",
]:
    r = requests.get(path, headers=HDR, timeout=8)
    print(f"  [{r.status_code}] {path.split('/')[-1] or path}")
    if r.status_code == 200:
        print(f"    → {r.text[:300]}")
    time.sleep(0.15)

# 3. Naver PC 업종별 일별시세 HTML 파싱 (BeautifulSoup 없이 regex)
print("\n=== Naver PC 업종별 일별시세 HTML 파싱 ===")
# KPI = KOSPI 전체 코드
for code in ["KPI", "KQI", "BSTP1", "BSTP2"]:
    r = requests.get(
        "https://finance.naver.com/sise/sise_index_day.nhn",
        headers=HDR_PC, params={"code": code, "page": "1"}, timeout=10,
    )
    if r.status_code == 200:
        # 날짜와 지수값 추출 시도
        dates = re.findall(r'(\d{4}\.\d{2}\.\d{2})', r.text)
        nums  = re.findall(r'<td class="number_1"><span[^>]*>([\d,\.]+)</span>', r.text)
        if dates:
            print(f"  [{code}] 날짜: {dates[:5]} | 수치: {nums[:5]}")
        else:
            print(f"  [{code}] 날짜 없음 ({len(r.content)}B)")
    else:
        print(f"  [{code}] {r.status_code}")
    time.sleep(0.2)

# 4. Naver 업종별 API (PC JSON 엔드포인트 탐색)
print("\n=== Naver PC JSON 엔드포인트 ===")
for url in [
    "https://finance.naver.com/sise/sise_upjong_day.nhn?upjong_cd=1",
    "https://finance.naver.com/api/sise/upjong?code=1",
    "https://finance.naver.com/sise/sise_group_day.nhn?type=upjong&no=282",
    "https://finance.naver.com/sise/upjong_group_list_ajax.nhn",
    "https://sise.naver.com/index.naver?code=KPI",
]:
    r = requests.get(url, headers=HDR_PC, timeout=8)
    print(f"  [{r.status_code}] {url.split('/')[-1][:50]}")
    if r.status_code == 200 and len(r.content) < 50000:
        snippet = r.text[:300]
        if snippet.strip():
            print(f"    → {snippet[:200]}")
    time.sleep(0.15)

# 5. Naver 주식 API에서 업종 차트 찾기
print("\n=== Naver 주식 API 업종 차트 ===")
for url in [
    "https://api.stock.naver.com/index/KOSPI/price?startTime=20260620&endTime=20260630&timeframe=1D",
    "https://polling.finance.naver.com/api/realtime/domestic/index/KPI",
    "https://polling.finance.naver.com/api/realtime/domestic/group/upjong",
]:
    r = requests.get(url, headers=HDR_PC, timeout=8)
    print(f"  [{r.status_code}] {url.split('/')[-2]}/{url.split('/')[-1][:40]}")
    if r.status_code == 200:
        print(f"    → {r.text[:300]}")
    time.sleep(0.15)
