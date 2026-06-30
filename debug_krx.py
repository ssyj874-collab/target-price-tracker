"""KIS API 연결 테스트. python3 debug_krx.py"""
import os, requests
from dotenv import load_dotenv
load_dotenv()

KEY = os.getenv("KIS_APP_KEY")
SEC = os.getenv("KIS_APP_SECRET")
BASE = "https://openapi.koreainvestment.com:9443"

# 토큰 발급
r = requests.post(f"{BASE}/oauth2/tokenP", json={
    "grant_type": "client_credentials", "appkey": KEY, "appsecret": SEC,
}, timeout=10)
print("토큰 상태:", r.status_code)
if r.status_code != 200:
    print(r.text); exit()

token = r.json()["access_token"]
print("토큰:", token[:30], "...")

# 코스피 종합 기간별 시세 테스트
r2 = requests.get(f"{BASE}/uapi/domestic-stock/v1/quotations/inquire-index-chartprice",
    headers={"authorization": f"Bearer {token}", "appkey": KEY, "appsecret": SEC,
             "tr_id": "FHKUP03500100", "custtype": "P"},
    params={"FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": "0001",
            "FID_INPUT_DATE_1": "20240101", "FID_INPUT_DATE_2": "20240110",
            "FID_PERIOD_DIV_CODE": "D"},
    timeout=15)
print("업종시세 상태:", r2.status_code)
print("응답:", r2.text[:500])
