"""
KIS (한국투자증권) API 클라이언트
외국인/기관 종목별 순매수 데이터 수집용
"""

import os
import json
import time
import requests
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

APP_KEY    = os.environ['KIS_APP_KEY']
APP_SECRET = os.environ['KIS_APP_SECRET']
ACCOUNT_NO = os.environ['KIS_ACCOUNT_NO']

BASE_URL   = 'https://openapi.koreainvestment.com:9443'
TOKEN_FILE = Path(__file__).parent / 'kis_token.json'


def get_access_token() -> str:
    """액세스 토큰 발급 (캐시: 하루)"""
    if TOKEN_FILE.exists():
        cached = json.loads(TOKEN_FILE.read_text())
        expires_at = datetime.fromisoformat(cached['expires_at'])
        if datetime.now() < expires_at - timedelta(minutes=10):
            return cached['access_token']

    resp = requests.post(
        f'{BASE_URL}/oauth2/tokenP',
        json={
            'grant_type': 'client_credentials',
            'appkey':     APP_KEY,
            'appsecret':  APP_SECRET,
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    token = data['access_token']
    expires_at = datetime.now() + timedelta(seconds=int(data.get('expires_in', 86400)))
    TOKEN_FILE.write_text(json.dumps({
        'access_token': token,
        'expires_at':   expires_at.isoformat(),
    }))
    return token


def _headers(tr_id: str) -> dict:
    return {
        'content-type':  'application/json; charset=utf-8',
        'authorization': f'Bearer {get_access_token()}',
        'appkey':        APP_KEY,
        'appsecret':     APP_SECRET,
        'tr_id':         tr_id,
        'custtype':      'P',
    }


def get_investor_by_stock(ticker: str, date: str = '') -> dict:
    """
    종목별 외국인/기관 순매수 조회
    ticker: 종목코드 (6자리, 예: '005930')
    date:   조회일자 YYYYMMDD (기본: 오늘)
    반환: {'foreign_net': ..., 'institution_net': ..., 'individual_net': ...}
    """
    if not date:
        date = datetime.today().strftime('%Y%m%d')

    params = {
        'fid_cond_mrkt_div_code': 'J',   # 주식
        'fid_input_iscd':         ticker,
        'fid_div_cls_code':       '0',   # 순매수
        'fid_blng_cls_code':      '0',
        'fid_trgt_cls_code':      '111111111',
        'fid_trgt_exls_cls_code': '000000',
        'fid_input_date_1':       date,
        'fid_input_date_2':       date,
        'fid_vol_cnt':            '40',
        'fid_input_hour_1':       '',
    }
    resp = requests.get(
        f'{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-investor',
        headers=_headers('FHKST01010900'),
        params=params,
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get('rt_cd') != '0':
        raise RuntimeError(f"KIS API 오류: {data.get('msg1')}")

    output = data.get('output', [{}])
    row = output[0] if output else {}
    return {
        'foreign_net':     int(row.get('frgn_ntby_qty', 0)),
        'institution_net': int(row.get('orgn_ntby_qty', 0)),
        'individual_net':  int(row.get('indv_ntby_qty', 0)),
    }


def get_investor_trend(ticker: str, fromdate: str, todate: str) -> list[dict]:
    """
    종목별 외국인/기관 순매수 기간 조회
    반환: [{'date': 'YYYYMMDD', 'foreign_net_amount': ..., 'institution_net_amount': ..., 'market_cap': ...}, ...]
    """
    params = {
        'fid_cond_mrkt_div_code': 'J',
        'fid_input_iscd':         ticker,
        'fid_div_cls_code':       '0',
        'fid_blng_cls_code':      '0',
        'fid_trgt_cls_code':      '111111111',
        'fid_trgt_exls_cls_code': '000000',
        'fid_input_date_1':       fromdate,
        'fid_input_date_2':       todate,
        'fid_vol_cnt':            '40',
        'fid_input_hour_1':       '',
    }
    resp = requests.get(
        f'{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-investor',
        headers=_headers('FHKST01010900'),
        params=params,
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get('rt_cd') != '0':
        raise RuntimeError(f"KIS API 오류: {data.get('msg1')}")

    rows = []
    for row in data.get('output', []):
        rows.append({
            'date':                   row.get('stck_bsop_date', ''),
            'foreign_net_amount':     int(row.get('frgn_ntby_tr_pbmn', 0)),
            'institution_net_amount': int(row.get('orgn_ntby_tr_pbmn', 0)),
            'foreign_sell_amount':    int(row.get('frgn_seln_tr_pbmn', 0)),
            'institution_sell_amount':int(row.get('orgn_seln_tr_pbmn', 0)),
            'close':                  int(row.get('stck_clpr', 0)),
        })
    return rows


if __name__ == '__main__':
    print("KIS API 토큰 발급 테스트...")
    token = get_access_token()
    print(f"토큰 발급 성공: {token[:20]}...")

    print("\n삼성전자(005930) 외국인/기관 순매수 조회...")
    result = get_investor_by_stock('005930')
    print(f"  외국인 순매수(주): {result['foreign_net']:,}")
    print(f"  기관   순매수(주): {result['institution_net']:,}")
    print(f"  개인   순매수(주): {result['individual_net']:,}")
