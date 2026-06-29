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

UNIVERSE_FILE  = Path(__file__).parent / 'universe_700.json'
UNIVERSE_FILE2 = Path(__file__).parent / 'universe_701_1400.json'


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


# ── 유니버스: universe_700.json 로드 ─────────────────────────────────────

def load_universe() -> tuple[list[str], dict]:
    """universe_700.json + universe_701_1400.json 합쳐서 로드"""
    if not UNIVERSE_FILE.exists():
        raise FileNotFoundError(f"유니버스 파일 없음: {UNIVERSE_FILE}")

    def _parse(f):
        data = json.loads(f.read_text())
        if data and isinstance(data[0], dict):
            return [d['ticker'] for d in data], {d['ticker']: d.get('name', d['ticker']) for d in data}
        return data, {}

    tickers, names = _parse(UNIVERSE_FILE)

    if UNIVERSE_FILE2.exists():
        tickers2, names2 = _parse(UNIVERSE_FILE2)
        # 중복 제거
        seen = set(tickers)
        for t in tickers2:
            if t not in seen:
                tickers.append(t)
                seen.add(t)
        names.update(names2)

    print(f"  유니버스 로드: {len(tickers)}종목")
    return tickers, names


# ── KIS API: 종목 현재가 (상장주식수 + 종목명) ────────────────────────────

def kis_stock_info(ticker: str) -> dict:
    """종목 상장주식수 + 한글명 조회"""
    try:
        resp = requests.get(
            f'{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price',
            headers=_h('FHKST01010100'),
            params={'fid_cond_mrkt_div_code': 'J', 'fid_input_iscd': ticker},
            timeout=10,
        )
        data = resp.json()
        output = data.get('output', {})
        return {
            'shares': int(output.get('lstn_stcn') or 0),
            'name':   output.get('hts_kor_isnm') or ticker,
        }
    except Exception:
        return {'shares': 0, 'name': ticker}


# ── KIS API: 종목별 일자별 투자자 순매수대금 ──────────────────────────────

def kis_stock_daily_period(ticker: str, fromdate: str, todate: str, shares: int) -> pd.DataFrame:
    """
    KIS FHKST01010900: 종목별 투자자 기간 데이터 (최대 30행)
    frgn_ntby_tr_pbmn, orgn_ntby_tr_pbmn 단위: 백만원 → 원으로 변환
    시가총액 = 종가 × 상장주식수
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
                # 백만원 → 원 (빈 문자열 처리)
                'foreign_net':     int(row.get('frgn_ntby_tr_pbmn') or 0) * 1_000_000,
                'institution_net': int(row.get('orgn_ntby_tr_pbmn') or 0) * 1_000_000,
                'close':           int(row.get('stck_clpr') or 0),
            })
        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows).set_index('date').sort_index()
        df['market_cap'] = df['close'] * shares
        return df[['foreign_net', 'institution_net', 'market_cap']]

    except Exception:
        return pd.DataFrame()


def kis_stock_daily(ticker: str, fromdate: str, todate: str) -> pd.DataFrame:
    """
    KIS API 30행 제한 우회: 기간을 30일 단위로 분할하여 여러 번 호출
    전체 기간 데이터를 합산하여 반환
    """
    info = kis_stock_info(ticker)
    shares = info['shares']
    name   = info['name']
    time.sleep(0.05)

    # API가 0 반환 시 영구 캐시에서 복원
    if shares == 0:
        shares = load_persistent_shares().get(ticker, 0)
    else:
        save_persistent_shares(ticker, shares)

    if shares == 0:
        return pd.DataFrame()

    # 기간을 30일 단위로 분할
    end_dt   = datetime.strptime(todate, '%Y%m%d')
    start_dt = datetime.strptime(fromdate, '%Y%m%d')
    all_frames = []

    current_end = end_dt
    while current_end >= start_dt:
        current_start = max(current_end - timedelta(days=29), start_dt)
        chunk = kis_stock_daily_period(
            ticker,
            current_start.strftime('%Y%m%d'),
            current_end.strftime('%Y%m%d'),
            shares,
        )
        if not chunk.empty:
            all_frames.append(chunk)
        current_end = current_start - timedelta(days=1)
        time.sleep(0.05)

    if not all_frames:
        return pd.DataFrame()

    combined = pd.concat(all_frames)
    combined = combined[~combined.index.duplicated(keep='first')].sort_index()
    combined.attrs['name'] = name
    return combined


# ── 데이터 수집 ────────────────────────────────────────────────────────────

def fetch_all(tickers: list[str], fromdate: str, todate: str) -> tuple[pd.DataFrame, dict]:
    """raw 데이터 + 종목명 dict 반환"""
    rows = []
    names = {}
    total = len(tickers)
    for i, ticker in enumerate(tickers, 1):
        print(f"\r  {i}/{total} {ticker}...", end='', flush=True)
        df = kis_stock_daily(ticker, fromdate, todate)
        if not df.empty:
            df['ticker'] = ticker
            rows.append(df.reset_index())
        names[ticker] = df.attrs.get('name', '') or ticker

    print()
    if not rows:
        return pd.DataFrame(), names
    return pd.concat(rows, ignore_index=True).sort_values(['ticker', 'date']), names


# ── 오실레이터 계산 ────────────────────────────────────────────────────────

def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()


def calc_oscillator(raw: pd.DataFrame, names: dict = None) -> pd.DataFrame:
    if names is None:
        names = {}
    results = []
    for ticker, grp in raw.groupby('ticker'):
        grp = grp.set_index('date').sort_index()
        if len(grp) < 20:
            continue

        net_buy    = grp['foreign_net'] + grp['institution_net']
        roll20_sum = net_buy.rolling(20).sum()
        roll5      = net_buy.rolling(5).sum()
        mktcap     = grp['market_cap'].replace(0, np.nan)
        ratio      = roll5 / mktcap

        valid = ratio.dropna()
        if len(valid) < 10:
            continue

        ema12  = _ema(valid, 12)
        ema26  = _ema(valid, 26)
        macd   = ema12 - ema26
        signal = _ema(macd, 9)
        osc    = macd - signal

        net20_eok = round(roll20_sum.iloc[-1] / 1_0000_0000, 1)

        # 히스토리: 차트용 시계열
        history = []
        for dt in grp.index:
            dt_str = dt.strftime('%Y-%m-%d')
            mc     = grp.loc[dt, 'market_cap']
            n20    = roll20_sum.get(dt)
            o      = osc.get(dt) if dt in osc.index else None
            history.append({
                'date':    dt_str,
                'mktcap':  round(mc / 1_0000_0000, 1) if mc and mc > 0 else None,
                'net20':   round(-n20 / 1_0000_0000, 1) if n20 is not None and not np.isnan(n20) else None,
                'osc':     round(o * 100, 4) if o is not None and not np.isnan(o) else None,
            })

        results.append({
            'ticker':     ticker,
            'name':       names.get(ticker, ticker),
            'date':       grp.index[-1],
            'net20':      net20_eok,
            'macd':       round(macd.iloc[-1] * 100, 4),
            'signal':     round(signal.iloc[-1] * 100, 4),
            'oscillator': round(osc.iloc[-1] * 100, 4),
            'history':    history,
        })

    if not results:
        return pd.DataFrame()
    return pd.DataFrame(results).set_index('ticker').sort_values('net20', ascending=True)


# ── 메인 ─────────────────────────────────────────────────────────────────

def last_trading_day() -> str:
    dt = datetime.today()
    for _ in range(10):
        if dt.weekday() < 5:
            return dt.strftime('%Y%m%d')
        dt -= timedelta(days=1)
    return datetime.today().strftime('%Y%m%d')


OUTPUT_FILE   = Path(__file__).parent / 'sugu_result.json'
RAW_CACHE     = CACHE_DIR / 'sugu_raw_cache.parquet'
NAMES_FILE    = CACHE_DIR / 'names_persistent.json'  # 영구 종목명 캐시
SHARES_FILE   = CACHE_DIR / 'shares_persistent.json'  # 영구 상장주식수 캐시


def load_persistent_shares() -> dict:
    if SHARES_FILE.exists():
        return {k: int(v) for k, v in json.loads(SHARES_FILE.read_text()).items()}
    return {}


def save_persistent_shares(ticker: str, shares: int):
    """상장주식수 영구 캐시에 저장 (0이면 저장 안 함)"""
    if shares <= 0:
        return
    existing = load_persistent_shares()
    existing[ticker] = shares
    SHARES_FILE.write_text(json.dumps(existing, ensure_ascii=False))


def load_persistent_names() -> dict:
    if NAMES_FILE.exists():
        return json.loads(NAMES_FILE.read_text())
    return {}


def save_persistent_names(names: dict):
    """기존 영구 캐시와 병합 후 저장 (티커 코드값은 덮어쓰지 않음)"""
    existing = load_persistent_names()
    for ticker, name in names.items():
        # 새 이름이 실제 한글명(티커 코드 아님)일 때만 업데이트
        if name and name != ticker:
            existing[ticker] = name
    NAMES_FILE.write_text(json.dumps(existing, ensure_ascii=False, indent=2))


def run_full(n: int = 700):
    today    = datetime.today()
    todate   = today.strftime('%Y%m%d')
    fromdate = (today - timedelta(days=120)).strftime('%Y%m%d')
    ref_date = last_trading_day()

    print(f"기준일: {ref_date}, 기간: {fromdate} ~ {todate}")

    print("유니버스 로드 중...")
    tickers, universe_names = load_universe()
    tickers = tickers[:n]
    print(f"  → {len(tickers)}개 종목")

    # 오늘 캐시가 있으면 API 재호출 생략
    if RAW_CACHE.exists():
        cache_mtime = datetime.fromtimestamp(RAW_CACHE.stat().st_mtime).strftime('%Y%m%d')
        if cache_mtime == ref_date:
            print(f"  (오늘 캐시 로드: {RAW_CACHE})")
            raw = pd.read_parquet(RAW_CACHE)
        else:
            raw = None
    else:
        raw = None

    # 종목명: universe_700.json 우선, 영구 캐시로 보완
    names = {**load_persistent_names(), **universe_names}

    if raw is None:
        print(f"\n투자자 데이터 수집 중 ({len(tickers)}개)...")
        raw, new_names = fetch_all(tickers, fromdate, todate)
        # 새로 수집한 이름을 영구 캐시에 반영 (한글명만)
        save_persistent_names(new_names)
        names = load_persistent_names()
        # 영구 캐시에 없는 종목은 새로 수집한 이름 사용
        for t, n in new_names.items():
            if t not in names:
                names[t] = n

        if not raw.empty:
            # 누적 캐시: 기존 데이터와 병합하여 최대 90 거래일 보존
            if RAW_CACHE.exists():
                try:
                    existing = pd.read_parquet(RAW_CACHE)
                    raw = pd.concat([existing, raw])
                    raw = raw[~raw.duplicated(subset=['ticker', 'date'], keep='last')]
                    raw = raw.sort_values(['ticker', 'date'])
                    # 종목별 최근 90 거래일만 유지
                    raw = (raw.groupby('ticker', group_keys=False)
                             .apply(lambda g: g.tail(90))
                             .reset_index(drop=True))
                    print(f"  기존 캐시 병합 완료: {len(raw)}행")
                except Exception as e:
                    print(f"  기존 캐시 병합 실패 ({e}), 새 데이터로 덮어씀")
            raw.to_parquet(RAW_CACHE)
            print(f"  캐시 저장: {RAW_CACHE}")

    print(f"수집된 데이터: {len(raw)}행")

    if raw.empty:
        print("데이터 없음")
        return

    result = calc_oscillator(raw, names)
    if result.empty:
        print("계산 결과 없음 (데이터 부족)")
        return

    print(f"\n[수급오실레이터 결과] {len(result)}종목")
    print(result[['name', 'net20', 'oscillator']].head(20).to_string())

    # JSON 저장
    df_out = result.reset_index()
    df_out['date'] = df_out['date'].dt.strftime('%Y-%m-%d')
    out = {
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'ref_date':   ref_date,
        'data': df_out.to_dict(orient='records'),
    }
    OUTPUT_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\n저장 완료: {OUTPUT_FILE}")


if __name__ == '__main__':
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 700
    run_full(n)
