# KOSPI/KOSDAQ SIO Calculator

카페라떼 엑셀의 SIO(Strength Index Oscillator)를 pykrx로 완전 재현합니다.
KOSPI/KOSDAQ 각 245일 검증: **부호 일치 100%, 평균 오차 0.00, 최대 오차 0.01**

## 확정 수식

```
SIO = D×100        (D > 0.5, 상승장)
SIO = -(1-D)×100   (D ≤ 0.5, 하락장)

D = (J + K) / 2

J = F / (F + G)
  F = 상승종목 거래대금 합
  G = 하락종목 거래대금 합

K = H / (H + I)
  H = 상승종목 등락폭 합  (양수)
  I = 하락종목 등락폭 절대값 합
  등락폭 = 전일종가 × 등락률/100
         = 종가 / (1 + 등락률/100) × 등락률/100  ← pykrx에서 전일종가 역산
```

**SIO 해석:**
- `|SIO| < 50` 은 나오지 않음 (D=0.5가 경계)
- `|SIO| ≥ 80` → 패닉 바잉/셀링 구간

## 설치

```bash
pip3 install pykrx pandas numpy
export KRX_ID=<KRX아이디>
export KRX_PW=<KRX비밀번호>
```

## 사용법

```bash
# 단일 날짜 상세 출력
python3 sio_calculator.py KOSPI 20250625 --debug

# 기간 조회
python3 sio_calculator.py KOSPI 20250101 --end 20251231

# 엑셀 레퍼런스와 전수 비교 (245일)
python3 verify_sio.py KOSPI
python3 verify_sio.py KOSDAQ

# 단일 날짜 가설 테스트
python3 verify_sio.py KOSPI --hypothesis 20250625
```

## 파일 구성

| 파일 | 설명 |
|------|------|
| `sio_calculator.py` | SIO 계산 코어 + CLI |
| `verify_sio.py` | 엑셀 레퍼런스 전수 비교 + 가설 테스트 |
| `diagnose_sign_bug.py` | 부호 반전 원인 진단 (개발용) |
| `kospi_sio_reference.csv` | 엑셀 레퍼런스 245일 (KOSPI) |
| `kosdaq_sio_reference.csv` | 엑셀 레퍼런스 245일 (KOSDAQ) |
