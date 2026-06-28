"""
수급오실레이터 계산기 (KIS API 전용)
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
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

APP_KEY    = os.environ.get('KIS_APP_KEY', '')
APP_SECRET = os.environ.get('KIS_APP_SECRET', '')
BASE_URL   = 'https://openapi.koreainvestment.com:9443'
TOKEN_FILE = Path(__file__).parent / 'kis_token.json'
CACHE_DIR  = Path(__file__).parent / '.cache'
CACHE_DIR.mkdir(exist_ok=True)


# ── KIS API 인증 ──────────────────────────────────────────────────────────

def get_token() -> str:
    if TOKEN_FILE.exists():
        cached = json.loads(TOKEN_FILE.read_text())
        if datetime.now() < datetime.fromisoformat(cached['expires_at']) - timedelta(minutes=10):
            return cached['access_token']
    resp = requests.post(f'{BASE_URL}/oauth2/tokenP', json={
        'grant_type': 'client_credentials',
        'appkey': APP_KEY, 'appsecret': APP_SECRET,
    }, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    expires_at = datetime.now() + timedelta(seconds=int(data.get('expires_in', 86400)))
    TOKEN_FILE.write_text(json.dumps({
        'access_token': data['access_token'],
        'expires_at':   expires_at.isoformat(),
    }))
    return data['access_token']


def _h(tr_id: str) -> dict:
    return {
        'content-type':  'application/json; charset=utf-8',
        'authorization': f'Bearer {get_token()}',
        'appkey':        APP_KEY,
        'appsecret':     APP_SECRET,
        'tr_id':         tr_id,
        'custtype':      'P',
    }


# ── KIS API: 유니버스 (시가총액 순위) ─────────────────────────────────────

def kis_market_cap_ranking(market: str = 'J', top_n: int = 700) -> list[dict]:
    """
    KIS API 시가총액 순위 조회
    market: J=전체주식, W=전체(ETF포함)
    반환: [{'ticker': '005930', 'name': '삼성전자', 'market_cap': 123456789}, ...]
    """
    results = []
    # KIS API는 한번에 30개씩, 페이지 반복
    for fid_trgt_cls_code in range(1, 30):
        params = {
            'fid_cond_mrkt_div_code': market,
            'fid_cond_scr_div_code':  '20174',
            'fid_input_iscd':         '0000',
            'fid_div_cls_code':       '0',
            'fid_blng_cls_code':      '0',
            'fid_trgt_cls_code':      str(fid_trgt_cls_code),
            'fid_trgt_exls_cls_code': '0',
            'fid_input_price_1':      '',
            'fid_input_price_2':      '',
            'fid_vol_cnt':            '',
            'fid_input_date_1':       '',
        }
        try:
            resp = requests.get(
                f'{BASE_URL}/uapi/domestic-stock/v1/ranking/market-cap',
                headers=_h('FHPST01740000'),
                params=params, timeout=10,
            )
            data = resp.json()
            if data.get('rt_cd') != '0':
                break
            output = data.get('output', [])
            if not output:
                break
            for row in output:
                results.append({
                    'ticker':     row.get('stck_shrn_iscd', ''),
                    'name':       row.get('hts_kor_isnm', ''),
                    'market_cap': int(row.get('stck_avls', 0)) * 100_000_000,  # 억원 → 원
                })
            if len(results) >= top_n:
                break
        except Exception as e:
            print(f"[WARN] 시가총액 순위 조회 실패: {e}")
            break
        time.sleep(0.05)

    return results[:top_n]


def get_top_n_tickers(ref_date: str, n: int) -> list[str]:
    """시가총액 상위 N종목 티커 반환 (캐시)"""
    dt = datetime.strptime(ref_date, '%Y%m%d')
    for _ in range(7):
        candidate = dt.strftime('%Y%m%d')
        cache_file = CACHE_DIR / f'universe_kis_{candidate}.json'
        if cache_file.exists():
            data = json.loads(cache_file.read_text())
            if data:
                print(f"  (캐시 로드: {candidate}, {len(data)}종목)")
                return [d['ticker'] for d in data[:n]]
        dt -= timedelta(days=1)

    print("  KIS API 시가총액 순위 조회 중...")
    ranking = kis_market_cap_ranking(top_n=n)
    if not ranking:
        raise RuntimeError("시가총액 순위 조회 실패")

    cache_file = CACHE_DIR / f'universe_kis_{ref_date}.json'
    cache_file.write_text(json.dumps(ranking, ensure_ascii=False))
    print(f"  캐시 저장: {len(ranking)}종목")
    return [d['ticker'] for d in ranking[:n]]


def get_ticker_names_from_cache(ref_date: str) -> dict:
    dt = datetime.strptime(ref_date, '%Y%m%d')
    for _ in range(7):
        candidate = dt.strftime('%Y%m%d')
        cache_file = CACHE_DIR / f'universe_kis_{candidate}.json'
        if cache_file.exists():
            data = json.loads(cache_file.read_text())
            return {d['ticker']: d['name'] for d in data}
        dt -= timedelta(days=1)
    return {}


# ── KIS API: 종목별 일자별 투자자 순매수대금 + 시가총액 ──────────────────

def kis_stock_daily(ticker: str, fromdate: str, todate: str) -> pd.DataFrame:
    """
    KIS API: 종목별 일자별 외인/기관 순매수대금 + 시가총액
    반환: date(index), foreign_net, institution_net, market_cap (원)
    """
    # 1) 투자자별 순매수대금
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
        resp = requests.get(
            f'{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-investor',
            headers=_h('FHKST01010900'),
            params=params, timeout=10,
        )
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
                'close':           int(row.get('stck_clpr', 0)),
                'shares':          int(row.get('lstn_stcn', 0)),  # 상장주식수
            })
        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows).set_index('date').sort_index()
        # 시가총액 = 종가 × 상장주식수
        df['market_cap'] = df['close'] * df['shares']
        return df[['foreign_net', 'institution_net', 'market_cap']]

    except Exception:
        return pd.DataFrame()


# ── 데이터 수집 ────────────────────────────────────────────────────────────

def fetch_all(tickers: list[str], fromdate: str, todate: str) -> pd.DataFrame:
    rows = []
    total = len(tickers)
    for i, ticker in enumerate(tickers, 1):
        print(f"\r  {i}/{total} {ticker}...", end='', flush=True)
        df = kis_stock_daily(ticker, fromdate, todate)
        if not df.empty:
            df['ticker'] = ticker
            rows.append(df.reset_index())
        time.sleep(0.05)

    print()
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True).sort_values(['ticker', 'date'])


# ── 오실레이터 계산 ────────────────────────────────────────────────────────

def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()


def calc_oscillator(raw: pd.DataFrame) -> pd.DataFrame:
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
    return pd.DataFrame(results).set_index('ticker').sort_values('oscillator', ascending=False)


# ── 메인 ─────────────────────────────────────────────────────────────────

def last_trading_day() -> str:
    dt = datetime.today()
    for _ in range(10):
        if dt.weekday() < 5:
            return dt.strftime('%Y%m%d')
        dt -= timedelta(days=1)
    return datetime.today().strftime('%Y%m%d')


if __name__ == '__main__':
    today    = datetime.today()
    todate   = today.strftime('%Y%m%d')
    fromdate = (today - timedelta(days=120)).strftime('%Y%m%d')
    ref_date = last_trading_day()

    print(f"기준일: {ref_date}, 기간: {fromdate} ~ {todate}")

    print("시가총액 상위 700 종목 선정 중...")
    tickers = get_top_n_tickers(ref_date, 700)
    names   = get_ticker_names_from_cache(ref_date)
    print(f"  → {len(tickers)}개 종목")
    for t in tickers[:10]:
        print(f"    {t}: {names.get(t, '?')}")

    # 테스트: 상위 5개
    test_tickers = tickers[:5]
    print(f"\n투자자 데이터 수집 중 (테스트 5개)...")
    raw = fetch_all(test_tickers, fromdate, todate)
    print(f"수집된 데이터: {len(raw)}행")

    if not raw.empty:
        result = calc_oscillator(raw)
        result['종목명'] = result.index.map(lambda t: names.get(t, t))
        print("\n[수급오실레이터 결과]")
        print(result[['종목명', 'macd', 'signal', 'oscillator']].to_string())
