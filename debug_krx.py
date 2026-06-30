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
        print("  →", r.text[:300])
    print()

common = {"FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": "0001",
          "FID_INPUT_DATE_1": "20240101", "FID_INPUT_DATE_2": "20240110",
          "FID_PERIOD_DIV_CODE": "D"}

# 업종 기간별 시세 후보들
test("chartprice", "/uapi/domestic-stock/v1/quotations/inquire-index-chartprice", "FHKUP03500100", common)
test("daily-chartprice", "/uapi/domestic-stock/v1/quotations/inquire-daily-chartprice", "FHKST03010100", {**common, "FID_ORG_ADJ_PRC": "1"})
test("index-price(현재가)", "/uapi/domestic-stock/v1/quotations/inquire-index-price", "FHPUP02100000",
     {"FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": "0001"})
test("sector-index", "/uapi/domestic-stock/v1/quotations/inquire-sector-index", "FHKUP02100200", common)
