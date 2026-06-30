"""KRX API 응답 확인용. 터미널에서 python3 debug_krx.py 실행"""
import requests, io

OTP_URL = "https://data.krx.co.kr/comm/fileDn/GenerateOTP/generate.cmd"
DL_URL  = "https://data.krx.co.kr/comm/fileDn/download_csv.cmd"

session = requests.Session()
session.headers.update({
    "Referer":    "https://data.krx.co.kr/",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
})

otp_resp = session.post(OTP_URL, data={
    "locale": "ko_KR", "idxIndMidclssCd": "02",
    "indIdx": "1005", "indIdx2": "1005",
    "strtDd": "20240101", "endDd": "20241231",
    "share": "1", "money": "1", "csvxls_isNo": "false",
    "name": "fileDown", "url": "dbms/MDC/STAT/standard/MDCSTAT01001",
}, timeout=15)

print("OTP:", repr(otp_resp.text[:100]))

dl_resp = session.post(DL_URL, data={"code": otp_resp.text.strip()}, timeout=15)
print("Status:", dl_resp.status_code)
print("Content-Type:", dl_resp.headers.get("Content-Type"))
print("첫 500바이트:", dl_resp.content[:500])
