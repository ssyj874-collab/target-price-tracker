"""
업종별 수급오실레이터 계산기
sugu_result.json (종목별 데이터)을 sector_universe.json (업종→종목 매핑)으로
집계하여 sector_result.json을 생성합니다.

집계 방식:
  각 날짜별로 업종 내 종목들의 net20, osc를 시가총액 가중 평균
  업종 오실레이터 = Σ(종목 osc × 종목 mktcap) / Σ(종목 mktcap)
  업종 net20     = Σ(종목 net20)  (억원 단순 합산)

사용법:
    python3 sector_calculator.py
"""

import json
from pathlib import Path
from datetime import datetime

RESULT_FILE  = Path(__file__).parent / 'sugu_result.json'
SECTOR_FILE  = Path(__file__).parent / 'sector_universe.json'
OUTPUT_FILE  = Path(__file__).parent / 'sector_result.json'


def run():
    if not RESULT_FILE.exists():
        print(f"종목 데이터 없음: {RESULT_FILE}")
        print("먼저 python3 sugu_calculator.py 를 실행하세요.")
        return

    if not SECTOR_FILE.exists():
        print(f"업종 매핑 없음: {SECTOR_FILE}")
        print("먼저 python3 extract_sector.py <엑셀파일> 를 실행하세요.")
        return

    result  = json.loads(RESULT_FILE.read_text())
    sectors = json.loads(SECTOR_FILE.read_text())

    # 종목별 데이터 인덱싱
    stock_map = {row['ticker']: row for row in result.get('data', []) if 'ticker' in row}
    print(f"종목 데이터: {len(stock_map)}개")
    print(f"업종 데이터: {len(sectors)}개")

    output_data = []

    for sec_code, sec_info in sectors.items():
        sec_name    = sec_info.get('name', sec_code)
        member_tkrs = sec_info.get('tickers', [])

        # 해당 업종에 데이터 있는 종목만
        members = [stock_map[t] for t in member_tkrs if t in stock_map]
        if not members:
            continue

        # 최신 osc/net20/mktcap (단일값) 기준으로 집계
        total_mktcap = sum(m.get('mktcap', 0) or 0 for m in members)
        if total_mktcap <= 0:
            # mktcap 없으면 단순 평균
            sec_osc  = sum(m.get('oscillator', 0) or 0 for m in members) / len(members)
            sec_net20 = sum(m.get('net20', 0) or 0 for m in members)
            sec_macd  = sum(m.get('macd', 0) or 0 for m in members) / len(members)
            sec_signal = sum(m.get('signal', 0) or 0 for m in members) / len(members)
        else:
            # 시가총액 가중 평균
            sec_osc  = sum((m.get('oscillator', 0) or 0) * (m.get('mktcap', 0) or 0)
                           for m in members) / total_mktcap
            sec_macd  = sum((m.get('macd', 0) or 0) * (m.get('mktcap', 0) or 0)
                            for m in members) / total_mktcap
            sec_signal = sum((m.get('signal', 0) or 0) * (m.get('mktcap', 0) or 0)
                             for m in members) / total_mktcap
            sec_net20 = sum(m.get('net20', 0) or 0 for m in members)  # 순매도 합산

        # 기준일: 멤버 중 가장 최근 날짜
        dates = [m.get('date', '') for m in members if m.get('date')]
        ref_date = max(dates) if dates else ''

        # 히스토리 집계: 날짜별로 멤버 종목들의 hist 합산
        date_mktcap = {}  # date -> total mktcap
        date_net20  = {}  # date -> sum net20
        date_osc_wt = {}  # date -> weighted osc sum

        for m in members:
            hist = m.get('history', [])
            for h in hist:
                d = h.get('date', '')
                if not d:
                    continue
                mk = h.get('mktcap', 0) or 0
                n20 = h.get('net20', 0) or 0
                osc = h.get('osc', 0) or 0
                date_mktcap[d] = date_mktcap.get(d, 0) + mk
                date_net20[d]  = date_net20.get(d, 0) + n20
                date_osc_wt[d] = date_osc_wt.get(d, 0) + osc * mk

        history = []
        for d in sorted(date_mktcap.keys()):
            mk  = date_mktcap[d]
            n20 = date_net20[d]
            osc = (date_osc_wt[d] / mk) if mk > 0 else 0
            history.append({'date': d, 'mktcap': round(mk, 1),
                             'net20': round(n20, 1), 'osc': round(osc, 6)})

        output_data.append({
            'sector_code': sec_code,
            'name':        sec_name,
            'member_count': len(members),
            'mktcap':      round(total_mktcap, 1),
            'net20':       round(sec_net20, 1),
            'oscillator':  round(sec_osc, 6),
            'macd':        round(sec_macd, 6),
            'signal':      round(sec_signal, 6),
            'date':        ref_date,
            'history':     history,
        })

    # 오실레이터 내림차순 정렬
    output_data.sort(key=lambda x: x['oscillator'], reverse=True)

    output = {
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'ref_date':   result.get('ref_date', ''),
        'data':       output_data,
    }
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"\n업종 결과 저장: {OUTPUT_FILE} ({len(output_data)}개 업종)")

    # 상위/하위 5개 출력
    print("\n[오실레이터 상위 5개 업종]")
    for row in output_data[:5]:
        print(f"  {row['name']:20s} osc={row['oscillator']:+.4f}%  "
              f"net20={row['net20']:+,.1f}억  종목수={row['member_count']}")
    print("\n[오실레이터 하위 5개 업종]")
    for row in output_data[-5:]:
        print(f"  {row['name']:20s} osc={row['oscillator']:+.4f}%  "
              f"net20={row['net20']:+,.1f}억  종목수={row['member_count']}")


if __name__ == '__main__':
    run()
