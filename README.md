# target-price-tracker

## 영업레버리지 계산기 (`operating_leverage.py`)

DART(전자공시) 오픈API에서 분기 실적을 받아 **증분 영업이익률**을 계산한다.
전체 영업이익률의 평균이 아니라, "추가된 매출에서 얼마가 남았는가"라는
기울기를 보는 방식이다.

```
증분 영업이익률 = Δ영업이익 ÷ Δ매출
```

- 기울기가 커지는 동안 → 이익 성장 폭발 구간
- 기울기 정체/하락 → 가격(P) 반영이 끝났다는 신호. 물량(Q) 여력 확인 필요
- 당기순이익은 쓰지 않는다 (평가손익 등 노이즈). 영업이익만 본다

### 사용법

1. https://opendart.fss.or.kr 에서 무료 API 키 발급
2. 실행:

```bash
export DART_API_KEY=발급받은키
python3 operating_leverage.py --name 삼성전자 --quarters 8
python3 operating_leverage.py --name 효성중공업 --csv result.csv
python3 operating_leverage.py --demo          # 키 없이 계산 로직 확인
```

표준 라이브러리만 사용하므로 별도 설치가 필요 없다 (Python 3.8+).

### 계산 방식

- 1분기(11013)·반기(11012)·3분기(11014)·사업보고서(11011)의 누적 손익을
  받아 분기 단위로 분해 (Q2 = 반기누적 − 1분기, Q4 = 연간 − 3분기누적)
- 연결(CFS) 재무제표 우선, 없으면 별도(OFS)
- QoQ와 YoY(계절성 제거) 증분 이익률을 함께 출력
- 매출이 감소한 구간은 기울기 해석이 무의미하므로 `-` 처리

### 테스트

```bash
python3 -m unittest test_operating_leverage
```
