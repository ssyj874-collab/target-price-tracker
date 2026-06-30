"""네이버 업종 HTML 파싱 + KRX 로컬 접근. python3 debug_krx.py"""
import requests, time, re, json

HDR = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://finance.naver.com/",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}

# ============================================================
# 1. 네이버 업종 목록 HTML 파싱 (등락률 추출)
# ============================================================
print("=== 네이버 업종 목록 HTML 파싱 ===\n")
r = requests.get(
    "https://finance.naver.com/sise/sise_group.naver",
    headers=HDR, params={"type": "upjong"}, timeout=15,
)
html = r.text
# "등락률" 근처 파싱
# 패턴: 업종명, 지수, 전일비, 등락률
rows = re.findall(
    r'type=upjong&amp;no=(\d+)[^>]*>([^<]+)</a>.*?'
    r'<td[^>]*class="[^"]*number[^"]*"[^>]*>([\d,\.]+)</td>.*?'
    r'<td[^>]*>([\d,\.\+\-]+)%?</td>',
    html, re.DOTALL
)
if rows:
    print(f"파싱 성공! {len(rows)}개 업종:")
    for no, name, idx, rate in rows[:10]:
        print(f"  no={no} {name.strip()} | 지수={idx} | 등락={rate}")
else:
    # 대안 패턴
    print("패턴1 실패, 대안 시도...")
    # 등락률 텍스트 근처 raw 데이터
    pos = html.find('등락률')
    if pos > 0:
        print(f"'등락률' 위치: {pos}")
        print(html[pos-200:pos+500])
    else:
        print("'등락률' 텍스트 없음")

    # 업종명 목록이라도 추출
    names = re.findall(r'type=upjong&(?:amp;)?no=(\d+)[^>]*>([^<]{2,20})</a>', html)
    print(f"\n업종명 {len(names)}개 발견:")
    for no, name in names[:20]:
        print(f"  no={no}: {name.strip()}")

    # 숫자 데이터 근처 샘플
    chunk_pos = html.find('1,')
    if chunk_pos > 0:
        print(f"\nHTML 샘플 (숫자 근처):\n{html[chunk_pos-100:chunk_pos+500]}")

print()

# ============================================================
# 2. 네이버 업종 상세 페이지에서 차트 API URL 찾기
# ============================================================
print("=== 네이버 업종 상세 페이지 분석 (no=282) ===\n")
r2 = requests.get(
    "https://finance.naver.com/sise/sise_group_detail.naver",
    headers=HDR, params={"type": "upjong", "no": "282"}, timeout=15,
)
html2 = r2.text
# API URL 패턴 찾기
api_urls = re.findall(r'(?:fetch|axios|url|href|src)["\s:=]+(["\'])([^"\']*(?:api|chart|json|ajax)[^"\']*)\1', html2, re.I)
print(f"API URL {len(api_urls)}개 발견:")
for _, url in api_urls[:20]:
    print(f"  {url}")

# 등락률 데이터
ctrt = re.findall(r'(?:prdy_ctrt|fluctuat|등락)[^:]*[:\s=]+"?([\d\.\-\+]+)"?', html2, re.I)
print(f"\n등락률 데이터: {ctrt[:10]}")

print()

# ============================================================
# 3. KRX 데이터 포털 (Mac 로컬에서 접근)
# ============================================================
print("=== KRX 데이터포털 (OTP 방식 로컬 시도) ===\n")
sess = requests.Session()
sess.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Origin": "http://data.krx.co.kr",
    "Referer": "http://data.krx.co.kr/contents/MDC/MAIN/main/MDCMain.jsp",
})

# 먼저 메인 페이지 접근 (쿠키 획득)
r3 = sess.get("http://data.krx.co.kr/contents/MDC/MAIN/main/MDCMain.jsp", timeout=10)
print(f"KRX 메인: {r3.status_code}")

time.sleep(0.5)

# 업종지수 데이터 요청 (올바른 BLD로)
for bld_name, bld, extra in [
    ("업종지수 시세", "dbms/MDC/STAT/standard/MDCSTAT00601",
     {"trdDd": "20260630", "idxIndMktClss": "1", "idxIndClss": "02", "share": "1", "money": "1"}),
    ("업종지수 추이", "dbms/MDC/STAT/standard/MDCSTAT00602",
     {"trdDd": "20260630", "idxIndMktClss": "1", "idxIndClss": "02"}),
    ("지수 기간별", "dbms/MDC/STAT/standard/MDCSTAT00603",
     {"strtDd": "20260620", "endDd": "20260630", "idxIndMktClss": "1", "idxIndClss": "02", "idxCd": "1001"}),
]:
    r4 = sess.post(
        "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd",
        data={"bld": bld, "locale": "ko_KR", **extra},
        timeout=10,
    )
    print(f"[{bld_name}] {r4.status_code} ({len(r4.content)}B)")
    if r4.status_code == 200:
        try:
            j = r4.json()
            print(f"  키: {list(j.keys())[:8]}")
            for k, v in j.items():
                if isinstance(v, list) and v:
                    print(f"  {k}[0]: {v[0]}")
        except:
            print(f"  텍스트: {r4.text[:200]}")
    else:
        print(f"  → {r4.text[:100]}")
    time.sleep(0.5)
