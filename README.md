# KOSPI/KOSDAQ SIO Calculator

카페라떼 엑셀의 SIO(Strength Index Oscillator) 값을 pykrx로 재현합니다.

## SIO 수식

```
SIO = IF(D > E, D, -E) * 100

D = AVERAGE(J, K)
E = 1 - D           ← AVERAGE(1-J, 1-K)와 동일
J = F / (F + G)     ← 상승종목 거래량 비율
K = H / (H + I)     ← 상승종목 등락폭 비율
```

| 변수 | 정의 |
|------|------|
| F | 상승종목 거래량 (또는 거래대금) |
| G | 하락종목 거래량 (또는 거래대금) |
| H | 상승종목 등락률 합산 |
| I | 하락종목 등락률 절대값 합산 |

## 설치

```bash
pip install -r requirements.txt
export KRX_ID=<KRX아이디>
export KRX_PW=<KRX비밀번호>
```

## 사용법

```bash
# 단일 날짜 상세 출력
python sio_calculator.py KOSPI 20250603 --debug

# 거래대금 기준
python sio_calculator.py KOSPI 20250603 --debug --value

# 기간 조회
python sio_calculator.py KOSPI 20250101 --end 20250630

# 부호 반전 전체 가설 진단
python diagnose_sign_bug.py KOSPI 20250603
```

## 부호 반전 원인 진단

`diagnose_sign_bug.py`는 동일 데이터에 대해 여러 가설(거래량 vs 거래대금,
I 부호 처리, 비교 방향)을 동시에 테스트하여 어느 조합이 엑셀값과 일치하는지
찾아냅니다.

엑셀 값과 직접 비교:

```python
from diagnose_sign_bug import compare_with_excel

# (날짜, 엑셀SIO값) 리스트 입력
compare_with_excel('KOSPI', [
    ('20250603', 12.34),
    ('20250604', -8.77),
    ...
])
```
