"""
업종별 수급오실레이터 계산기 (KIS API 직접 조회)
KRX 업종코드로 기관/외국인 순매수대금을 직접 조회해서 오실레이터를 계산합니다.

공식 (종목별과 동일):
  수급비율(t) = (기관5일누적순매수 + 외인5일누적순매수) / 업종시가총액
  EMA12 → EMA26 → MACD → signal(9) → oscillator

사용법:
    python3 sector_calculator.py
"""

import os, json, time, requests
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

SECTOR_CACHE = CACHE_DIR / 'sector_raw_cache.parquet'
OUTPUT_FILE  = Path(__file__).parent / 'sector_result.json'

# ── KRX 업종코드 목록 ─────────────────────────────────────────────────────
# 한투 MTS "국내 업종" 기준 (KOSPI + KOSDAQ)
# fid_cond_mrkt_div_code: U=업종
# 업종코드는 KRX 기준 숫자코드

KOSPI_SECTORS = {
    '0001': '종합(KOSPI)',
    '0002': '대형주',
    '0003': '중형주',
    '0004': '소형주',
    '0005': '음식료·담배',
    '0006': '섬유·의류',
    '0007': '종이·목재',
    '0008': '화학',
    '0009': '의약품',
    '0010': '비금속',
    '0011': '철강·금속',
    '0012': '기계',
    '0013': '전기·전자',
    '0014': '의료·정밀기기',
    '0015': '운송장비·부품',
    '0016': '유통업',
    '0017': '전기·가스업',
    '0018': '건설업',
    '0019': '운송·창고업',
    '0020': '통신업',
    '0024': '금융업',
    '0025': '은행',
    '0026': '증권',
    '0027': '보험',
    '0028': '서비스업',
    '0029': '제조업',
}

KOSDAQ_SECTORS = {
    '1001': '종합(KOSDAQ)',
    '1002': '대형주',
    '1003': '중형주',
    '1004': '소형주',
    '1005': '음식료·담배',
    '1006': '섬유·의류',
    '1007': '종이·목재',
    '1008': '화학',
    '1009': '제약',
    '1010': '비금속',
    '1011': '금속',
    '1012': '기계·장비',
    '1013': '전기·전자',
    '1014': '의료·정밀기기',
    '1015': '운송장비·부품',
    '1016': '유통',
    '1017': '건설',
    '1018': '운송·창고',
    '1019': '통신방송서비스',
    '1020': '금융',
    '1021': 'IT서비스',
    '1022': '일반서비스',
    '1023': '제조업',
}

ALL_SECTORS = {}
ALL_SECTORS.update({k: f'[KOSPI] {v}' for k, v in KOSPI_SECTORS.items()})
ALL_SECTORS.update({k: f'[KOSDAQ] {v}' for k, v in KOSDAQ_SECTORS.items()})


# ── 인증 ─────────────────────────────────────────────────────────────────

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


# ── KIS API: 업종별 투자자 기간 데이터 ───────────────────────────────────

def kis_sector_daily(sector_code: str, fromdate: str, todate: str) -> pd.DataFrame:
    """
    FHKUP03500100: 업종별 투자자 기간별 매매 현황
    반환 필드: stck_bsop_date, frgn_ntby_tr_pbmn, orgn_ntby_tr_pbmn, prdy_clpr (업종지수)
    단위: 백만원
    """
    # 시장 구분: KOSPI=0001~, KOSDAQ=1001~
    mrkt_div = 'K' if sector_code.startswith('1') else 'J'

    params = {
        'fid_cond_mrkt_div_code': 'U',
        'fid_input_iscd':         sector_code,
        'fid_input_date_1':       fromdate,
        'fid_input_date_2':       todate,
        'fid_period_div_code':    'D',
        'fid_div_cls_code':       '0',
    }
    try:
        resp = requests.get(
            f'{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-sector-timedata',
            headers=_h('FHKUP03500100'),
            params=params, timeout=10,
        )
        data = resp.json()

        if data.get('rt_cd') != '0':
            print(f"  [{sector_code}] API 오류: {data.get('msg1','')}")
            return pd.DataFrame()

        rows = []
        for row in data.get('output', []):
            d = row.get('stck_bsop_date', '')
            if not d:
                continue
            frgn = float(row.get('frgn_ntby_tr_pbmn') or 0) * 1_000_000
            orgn = float(row.get('orgn_ntby_tr_pbmn') or 0) * 1_000_000
            # 업종 시가총액 직접 제공되면 사용, 없으면 지수값으로 대체
            mktcap = float(row.get('hts_avls') or row.get('prdy_clpr') or 0)
            rows.append({
                'date':  pd.to_datetime(d),
                'frgn':  frgn,
                'orgn':  orgn,
                'mktcap': mktcap,
            })
        return pd.DataFrame(rows).sort_values('date').reset_index(drop=True)

    except Exception as e:
        print(f"  [{sector_code}] 예외: {e}")
        return pd.DataFrame()


# ── 오실레이터 계산 ──────────────────────────────────────────────────────

def calc_oscillator(df: pd.DataFrame) -> pd.DataFrame:
    """
    수급비율 = (기관5일누적 + 외인5일누적) / 업종시총
    EMA12 → EMA26 → MACD → signal(9) → oscillator
    """
    if df.empty or len(df) < 10:
        return pd.DataFrame()

    df = df.copy()

    # 5일 누적 순매수
    df['net5'] = (df['frgn'] + df['orgn']).rolling(5).sum()

    # 시가총액이 있으면 비율, 없으면 절대금액으로 대체
    if df['mktcap'].abs().sum() > 0:
        df['ratio'] = df['net5'] / (df['mktcap'] * 1e8)  # 억원 단위 mktcap
    else:
        df['ratio'] = df['net5'] / 1e12  # 스케일만 맞춤

    df['ema12']  = df['ratio'].ewm(span=12, adjust=False).mean()
    df['ema26']  = df['ratio'].ewm(span=26, adjust=False).mean()
    df['macd']   = df['ema12'] - df['ema26']
    df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['osc']    = df['macd'] - df['signal']

    # 20일 누적 순매도 (표시용)
    df['net20'] = (df['frgn'] + df['orgn']).rolling(20).sum() / 1e8  # 억원

    return df.dropna(subset=['osc'])


# ── 누적 캐시 관리 ────────────────────────────────────────────────────────

def load_cache() -> pd.DataFrame:
    if SECTOR_CACHE.exists():
        return pd.read_parquet(SECTOR_CACHE)
    return pd.DataFrame()


def save_cache(df: pd.DataFrame):
    df.to_parquet(SECTOR_CACHE, index=False)


def merge_cache(existing: pd.DataFrame, new_df: pd.DataFrame) -> pd.DataFrame:
    if existing.empty:
        return new_df
    if new_df.empty:
        return existing
    combined = pd.concat([existing, new_df], ignore_index=True)
    combined = combined.drop_duplicates(subset=['sector_code', 'date'], keep='last')
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=130)
    combined = combined[combined['date'] >= cutoff]
    return combined.sort_values(['sector_code', 'date']).reset_index(drop=True)


# ── 메인 실행 ─────────────────────────────────────────────────────────────

def run(sectors: dict = None):
    if sectors is None:
        sectors = ALL_SECTORS

    today    = datetime.now().strftime('%Y%m%d')
    fromdate = (datetime.now() - timedelta(days=45)).strftime('%Y%m%d')

    print(f"업종별 수급오실레이터 계산 ({len(sectors)}개 업종)")
    print(f"  조회기간: {fromdate} ~ {today}")

    existing_cache = load_cache()

    new_rows = []
    for i, (code, name) in enumerate(sectors.items(), 1):
        print(f"\r  [{i:3d}/{len(sectors)}] {code} {name[:12]:12s}", end='', flush=True)
        df = kis_sector_daily(code, fromdate, today)
        if df.empty:
            continue
        df['sector_code'] = code
        new_rows.append(df)
        time.sleep(0.05)

    print()

    if not new_rows:
        print("수집된 데이터 없음. TR_ID 또는 파라미터를 확인하세요.")
        _debug_single(list(sectors.keys())[0])
        return

    new_df = pd.concat(new_rows, ignore_index=True)
    merged = merge_cache(existing_cache, new_df)
    save_cache(merged)
    print(f"  캐시 저장: {len(merged)}행")

    # 업종별 오실레이터 계산
    output_data = []
    for code, name in sectors.items():
        grp = merged[merged['sector_code'] == code].copy()
        if len(grp) < 10:
            continue
        result = calc_oscillator(grp)
        if result.empty:
            continue

        last = result.iloc[-1]
        history = []
        for _, r in result.iterrows():
            history.append({
                'date':   r['date'].strftime('%Y-%m-%d'),
                'mktcap': round(float(r['mktcap']), 1),
                'net20':  round(float(r['net20']), 1),
                'osc':    round(float(r['osc']) * 100, 6),
            })

        output_data.append({
            'sector_code': code,
            'name':        name,
            'mktcap':      round(float(last['mktcap']), 1),
            'net20':       round(float(last['net20']), 1),
            'oscillator':  round(float(last['osc']) * 100, 6),
            'macd':        round(float(last['macd']) * 100, 6),
            'signal':      round(float(last['signal']) * 100, 6),
            'date':        last['date'].strftime('%Y-%m-%d'),
            'history':     history,
        })

    output_data.sort(key=lambda x: x['oscillator'], reverse=True)

    output = {
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'ref_date':   today,
        'data':       output_data,
    }
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"\n업종 결과 저장: {OUTPUT_FILE} ({len(output_data)}개 업종)")

    print("\n[오실레이터 상위 5]")
    for row in output_data[:5]:
        print(f"  {row['name']:25s}  osc={row['oscillator']:+.4f}%  net20={row['net20']:+,.0f}억")


def _debug_single(code: str):
    """여러 후보 엔드포인트를 순서대로 시도해서 작동하는 것 찾기"""
    today    = datetime.now().strftime('%Y%m%d')
    fromdate = (datetime.now() - timedelta(days=10)).strftime('%Y%m%d')

    candidates = [
        # (tr_id, url_path, params)
        ('FHKUP03500100', '/uapi/domestic-stock/v1/quotations/inquire-sector-timedata', {
            'fid_cond_mrkt_div_code': 'U', 'fid_input_iscd': code,
            'fid_input_date_1': fromdate, 'fid_input_date_2': today,
            'fid_period_div_code': 'D', 'fid_div_cls_code': '0',
        }),
        ('FHKST03030100', '/uapi/domestic-stock/v1/quotations/inquire-daily-sector-index', {
            'fid_cond_mrkt_div_code': 'U', 'fid_input_iscd': code,
            'fid_input_date_1': fromdate, 'fid_input_date_2': today,
            'fid_period_div_code': 'D',
        }),
        ('FHKST03030200', '/uapi/domestic-stock/v1/quotations/inquire-daily-sector-index', {
            'fid_cond_mrkt_div_code': 'U', 'fid_input_iscd': code,
            'fid_input_date_1': fromdate, 'fid_input_date_2': today,
            'fid_period_div_code': 'D',
        }),
        ('FHKUP03500100', '/uapi/domestic-stock/v1/quotations/inquire-investor-trend-estimate', {
            'fid_cond_mrkt_div_code': 'U', 'fid_input_iscd': code,
            'fid_input_date_1': fromdate, 'fid_input_date_2': today,
        }),
        ('FHKST03030100', '/uapi/domestic-stock/v1/quotations/inquire-sector-index', {
            'fid_cond_mrkt_div_code': 'U', 'fid_input_iscd': code,
            'fid_input_date_1': fromdate, 'fid_input_date_2': today,
        }),
    ]

    for tr_id, path, params in candidates:
        url = BASE_URL + path
        print(f"\n시도: TR={tr_id}")
        print(f"  URL: {path}")
        try:
            resp = requests.get(url, headers=_h(tr_id), params=params, timeout=10)
            body = resp.text[:800] if resp.text else '(빈 응답)'
            print(f"  HTTP {resp.status_code}: {body}")
            if resp.status_code == 200 and resp.text:
                try:
                    j = resp.json()
                    if j.get('rt_cd') == '0':
                        print(f"\n  ★ 성공! TR_ID={tr_id}, path={path}")
                        print(json.dumps(j, ensure_ascii=False, indent=2)[:2000])
                        return
                except Exception:
                    pass
        except Exception as e:
            print(f"  오류: {e}")
        time.sleep(0.3)


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--debug':
        code = sys.argv[2] if len(sys.argv) > 2 else '0008'
        _debug_single(code)
    else:
        run()
