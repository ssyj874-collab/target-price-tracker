"""KIS API 엔드포인트 탐색. python3 debug_krx.py"""
import os, requests
from dotenv import load_dotenv
load_dotenv()

KEY = os.getenv("KIS_APP_KEY")
SEC = os.getenv("KIS_APP_SECRET")
BASE = "https://openapi.koreainvestment.com:9443"

r = requests.post(f"{BASE}/oauth2/tokenP", json={
    "grant_type": "client_credentials", "appkey": KEY, "appsecret": SEC,
}, timeout=10)
token = r.json()["access_token"]
print("토큰 OK\n")

def test(label, path, tr_id, params):
    h = {"authorization": f"Bearer {token}", "appkey": KEY, "appsecret": SEC,
         "tr_id": tr_id, "custtype": "P"}
    r = requests.get(f"{BASE}{path}", headers=h, params=params, timeout=10)
    print(f"[{label}] {r.status_code}")
    if r.status_code == 200:
        j = r.json()
        print("  keys:", list(j.keys()))
        for k, v in j.items():
            if isinstance(v, list) and v:
                print(f"  {k}[0]:", v[0])
                break
            elif k not in ("rt_cd","msg_cd","msg1"):
                print(f"  {k}:", str(v)[:200])
    else:
        print("  →", r.text[:300])
    print()

# 현재가 (작동 확인) - output2 포함 여부 확인
print("=== 현재가 상세 출력 ===")
h = {"authorization": f"Bearer {token}", "appkey": KEY, "appsecret": SEC,
     "tr_id": "FHPUP02100000", "custtype": "P"}
r2 = requests.get(f"{BASE}/uapi/domestic-stock/v1/quotations/inquire-index-price",
    headers=h, params={"FID_COND_MRKT_DIV_CODE":"U","FID_INPUT_ISCD":"1005"}, timeout=10)
j = r2.json()
print("keys:", list(j.keys()))
if "output" in j:
    print("output:", j["output"])
print()

period = {"FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": "1005",
          "FID_INPUT_DATE_1": "20240101", "FID_INPUT_DATE_2": "20240110",
          "FID_PERIOD_DIV_CODE": "D"}

period2 = {"FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": "1005",
           "FID_INPUT_DATE_1": "20240101", "FID_INPUT_DATE_2": "20240110"}

print("=== 기간별 후보 ===")
for label, path, tr_id, params in [
    # 기존 실패
    ("inquire-index-chartprice(FHKUP03500100)", "/uapi/domestic-stock/v1/quotations/inquire-index-chartprice", "FHKUP03500100", period),
    # 차트 관련 다른 TR
    ("inquire-index-chartprice(FHKUP03500200)", "/uapi/domestic-stock/v1/quotations/inquire-index-chartprice", "FHKUP03500200", period),
    # 일별 시세 관련
    ("inquire-daily-price(FHKST03010100)", "/uapi/domestic-stock/v1/quotations/inquire-daily-price", "FHKST03010100",
     {"FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": "1005", "FID_INPUT_DATE_1": "20240101", "FID_INPUT_DATE_2": "20240110", "FID_PERIOD_DIV_CODE": "D", "FID_ORG_ADJ_PRC": "1"}),
    # 업종 일별 주가
    ("inquire-daily-itemchartprice(FHKST03010100)", "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice", "FHKST03010100",
     {"FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": "1005", "FID_INPUT_DATE_1": "20240101", "FID_INPUT_DATE_2": "20240110", "FID_PERIOD_DIV_CODE": "D", "FID_ORG_ADJ_PRC": "1"}),
    # 업종별 시세 (FHPUP02100200)
    ("inquire-index-price(FHPUP02100200)", "/uapi/domestic-stock/v1/quotations/inquire-index-price", "FHPUP02100200",
     {"FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": "1005"}),
    # 업종별 일별시세
    ("inquire-member(FHPUP02100000+date)", "/uapi/domestic-stock/v1/quotations/inquire-index-price", "FHPUP02100000",
     {"FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": "1005", "FID_INPUT_DATE_1": "20240101"}),
    # 시장코드 변경 시도 (U → N)
    ("inquire-index-chartprice(N,FHKUP03500100)", "/uapi/domestic-stock/v1/quotations/inquire-index-chartprice", "FHKUP03500100",
     {"FID_COND_MRKT_DIV_CODE": "N", "FID_INPUT_ISCD": "1005", "FID_INPUT_DATE_1": "20240101", "FID_INPUT_DATE_2": "20240110", "FID_PERIOD_DIV_CODE": "D"}),
    # KOSPI 지수 자체 period (0001)
    ("inquire-index-chartprice(0001)", "/uapi/domestic-stock/v1/quotations/inquire-index-chartprice", "FHKUP03500100",
     {"FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": "0001", "FID_INPUT_DATE_1": "20240101", "FID_INPUT_DATE_2": "20240110", "FID_PERIOD_DIV_CODE": "D"}),
    # 다른 경로명 시도
    ("inquire-index-chart-price", "/uapi/domestic-stock/v1/quotations/inquire-index-chart-price", "FHKUP03500100", period),
    ("inquire-daily-index-price", "/uapi/domestic-stock/v1/quotations/inquire-daily-index-price", "FHKUP03500100", period),
]:
    test(label, path, tr_id, params)
