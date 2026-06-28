"""
수급오실레이터 계산기 (KIS API 기반)
공식:
  수급비율(t) = (기관5일누적순매수대금 + 외인5일누적순매수대금) / 시가총액
  EMA12      = EMA(수급비율, 12)
  EMA26      = EMA(수급비율, 26)
  MACD       = EMA12 - EMA26
  시그널      = EMA(MACD, 9)
  오실레이터  = MACD - 시그널
"""

import os
import json
import time
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
from pykrx import stock as krx

load_dotenv()
os.environ.setdefault('KRX_ID', 'syj6718')
os.environ.setdefault('KRX_PW', 'song135!')

CACHE_DIR = Path(__file__).parent / '.cache'
CACHE_DIR.mkdir(exist_ok=True)


# ── KIS API 클라이언트 ─────────────────────────────────────────────────────

import requests as _req

_APP_KEY    = os.environ.get('KIS_APP_KEY', '')
_APP_SECRET = os.environ.get('KIS_APP_SECRET', '')
_BASE_URL   = 'https://openapi.koreainvestment.com:9443'
_TOKEN_FILE = Path(__file__).parent / 'kis_token.json'


def _get_token() -> str:
    if _TOKEN_FILE.exists():
        cached = json.loads(_TOKEN_FILE.read_text())
        if datetime.now() < datetime.fromisoformat(cached['expires_at']) - timedelta(minutes=10):
            return cached['access_token']
    resp = _req.post(f'{_BASE_URL}/oauth2/tokenP', json={
        'grant_type': 'client_credentials',
        'appkey': _APP_KEY, 'appsecret': _APP_SECRET,
    }, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    token = data['access_token']
    expires_at = datetime.now() + timedelta(seconds=int(data.get('expires_in', 86400)))
    _TOKEN_FILE.write_text(json.dumps({'access_token': token, 'expires_at': expires_at.isoformat()}))
    return token


def _kis_headers(tr_id: str) -> dict:
    return {
        'content-type':  'application/json; charset=utf-8',
        'authorization': f'Bearer {_get_token()}',
        'appkey':        _APP_KEY,
        'appsecret':     _APP_SECRET,
        'tr_id':         tr_id,
        'custtype':      'P',
    }


def kis_investor_daily(ticker: str, fromdate: str, todate: str) -> pd.DataFrame:
    """
    KIS API: 종목별 일자별 외인/기관 순매수대금
    반환 컬럼: date(index), foreign_net, institution_net (단위: 원)
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
        'fid_vol_cnt':            '100',
        'fid_input_hour_1':       '',
    }
    try:
        resp = _req.get(
            f'{_BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-investor',
            headers=_kis_headers('FHKST01010900'),
            params=params, timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get('rt_cd') != '0':
            return pd.DataFrame()
        rows = []
        for row in data.get('output', []):
            d = row.get('stck_bsop_date', '')
            if not d:
                continue
            rows.append({
                'date':            pd.to_datetime(d),
                'foreign_net':     int(row.get('frgn_ntby_tr_pbmn', 0)),
                'institution_net': int(row.get('orgn_ntby_tr_pbmn', 0)),
            })
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows).set_index('date').sort_index()
        return df
    except Exception:
        return pd.DataFrame()


# ── 유니버스: 시가총액 상위 N종목 (pykrx) ─────────────────────────────────

def last_trading_day() -> str:
    dt = datetime.today()
    for _ in range(10):
        if dt.weekday() < 5:
            return dt.strftime('%Y%m%d')
        dt -= timedelta(days=1)
    return datetime.today().strftime('%Y%m%d')


def get_top_n_by_marketcap(ref_date: str, n: int) -> list[str]:
    """시가총액 상위 N종목 (캐시 사용)"""
    dt = datetime.strptime(ref_date, '%Y%m%d')
    for _ in range(10):
        candidate = dt.strftime('%Y%m%d')
        cache_file = CACHE_DIR / f'universe_{candidate}.json'
        if cache_file.exists():
            tickers = json.loads(cache_file.read_text())
            if len(tickers) > 0:
                print(f"  (캐시 로드: {candidate}, {len(tickers)}종목)")
                return tickers[:n]
        dt -= timedelta(days=1)

    print(f"  시가총액 조회 중 (최초 1회, 약 10~20분 소요)...")
    all_tickers = []
    for mkt in ('KOSPI', 'KOSDAQ'):
        try:
            all_tickers += list(krx.get_market_ticker_list(ref_date, market=mkt))
        except Exception as e:
            print(f"  [WARN] {mkt} 목록 조회 실패: {e}")

    caps = {}
    total = len(all_tickers)
    print(f"  전체 {total}종목 시가총액 수집 중...")
    for i, ticker in enumerate(all_tickers, 1):
        if i % 100 == 0:
            print(f"\r  {i}/{total}...", end='', flush=True)
        try:
            df = krx.get_market_cap_by_date(ref_date, ref_date, ticker)
            caps[ticker] = int(df['시가총액'].iloc[0]) if not df.empty else 0
        except Exception:
            caps[ticker] = 0

    print()
    sorted_tickers = sorted(caps, key=lambda t: caps[t], reverse=True)
    cache_file = CACHE_DIR / f'universe_{ref_date}.json'
    cache_file.write_text(json.dumps(sorted_tickers))
    print(f"  캐시 저장: {cache_file}")
    return sorted_tickers[:n]


# ── 데이터 수집 (KIS API + pykrx 시가총액) ───────────────────────────────

def fetch_investor_data(tickers: list[str], fromdate: str, todate: str,
                        verbose: bool = True) -> pd.DataFrame:
    """
    KIS API로 외인/기관 순매수대금, pykrx로 시가총액 수집
    """
    rows = []
    total = len(tickers)
    for i, ticker in enumerate(tickers, 1):
        if verbose:
            print(f"\r  {i}/{total} {ticker}...", end='', flush=True)

        inv = kis_investor_daily(ticker, fromdate, todate)
        try:
            cap = krx.get_market_cap_by_date(fromdate, todate, ticker)[['시가총액']]
        except Exception:
            cap = pd.DataFrame()

        if inv.empty or cap.empty:
            time.sleep(0.05)
            continue

        for dt in inv.index:
            if dt not in cap.index:
                continue
            r = inv.loc[dt]
            rows.append({
                'ticker':          ticker,
                'date':            dt,
                'foreign_net':     r['foreign_net'],
                'institution_net': r['institution_net'],
                'market_cap':      cap.loc[dt, '시가총액'],
            })
        time.sleep(0.05)  # KIS API rate limit

    if verbose:
        print()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df['date'] = pd.to_datetime(df['date'])
    return df.sort_values(['ticker', 'date'])


# ── EMA / 오실레이터 계산 ─────────────────────────────────────────────────

def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def calc_sugu_oscillator(raw: pd.DataFrame) -> pd.DataFrame:
    results = []
    for ticker, grp in raw.groupby('ticker'):
        grp = grp.set_index('date').sort_index()
        if len(grp) < 30:
            continue

        roll5  = (grp['foreign_net'] + grp['institution_net']).rolling(5).sum()
        mktcap = grp['market_cap'].replace(0, np.nan)
        ratio  = roll5 / mktcap

        valid = ratio.dropna()
        if len(valid) < 26:
            continue

        ema12  = _ema(valid, 12)
        ema26  = _ema(valid, 26)
        macd   = ema12 - ema26
        signal = _ema(macd, 9)
        osc    = macd - signal

        results.append({
            'ticker':     ticker,
            'date':       grp.index[-1],
            'macd':       round(macd.iloc[-1] * 100, 4),
            'signal':     round(signal.iloc[-1] * 100, 4),
            'oscillator': round(osc.iloc[-1] * 100, 4),
        })

    if not results:
        return pd.DataFrame()

    return (pd.DataFrame(results)
            .set_index('ticker')
            .sort_values('oscillator', ascending=False))


# ── 메인 ─────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    today    = datetime.today()
    todate   = today.strftime('%Y%m%d')
    fromdate = (today - timedelta(days=120)).strftime('%Y%m%d')

    ref_date = last_trading_day()
    print(f"기준일: {ref_date}, 기간: {fromdate} ~ {todate}")

    print("시가총액 상위 700 종목 선정 중...")
    tickers = get_top_n_by_marketcap(ref_date, 700)
    print(f"  → {len(tickers)}개, 상위 5개: {tickers[:5]}")
    for t in tickers[:5]:
        print(f"    {t}: {krx.get_market_ticker_name(t)}")

    # 테스트: 상위 5개만
    test_tickers = tickers[:5]
    print(f"\n[KIS API] 투자자 데이터 수집 중...")
    raw = fetch_investor_data(test_tickers, fromdate, todate)
    print(f"수집된 데이터: {len(raw)}행")

    if not raw.empty:
        result = calc_sugu_oscillator(raw)
        result['종목명'] = result.index.map(krx.get_market_ticker_name)
        print("\n[수급오실레이터 결과]")
        print(result[['종목명', 'macd', 'signal', 'oscillator']].to_string())
