"""operating_leverage.py 오프라인 테스트 (DART API 호출을 모의 응답으로 대체)."""

import unittest
from unittest import mock

import operating_leverage as ol


def is_item(fs_div, account_nm, amount, add_amount=None):
    item = {"fs_div": fs_div, "sj_div": "IS", "account_nm": account_nm,
            "thstrm_amount": amount}
    if add_amount is not None:
        item["thstrm_add_amount"] = add_amount
    return item


def report(items):
    return {"status": "000", "message": "정상", "list": items}


# 2025년 가상 실적 (누적 기준, 단위: 원)
#   분기별 매출: 100, 150, 200, 250  → 누적 100, 250, 450, 700
#   분기별 OP :  10,  30,  50,  60  → 누적  10,  40,  90, 150
FAKE_REPORTS = {
    (2025, "11013"): report([  # 1분기: amount=3개월, add=누적(동일)
        is_item("CFS", "매출액", "100", "100"),
        is_item("CFS", "영업이익", "10", "10"),
    ]),
    (2025, "11012"): report([  # 반기: amount=3개월치, add=누적
        is_item("CFS", "매출액", "150", "250"),
        is_item("CFS", "영업이익", "30", "40"),
    ]),
    (2025, "11014"): report([
        is_item("CFS", "매출액", "200", "450"),
        is_item("CFS", "영업이익", "50", "90"),
    ]),
    (2025, "11011"): report([  # 사업보고서: add 없음, amount=연간
        is_item("CFS", "매출액", "700"),
        is_item("CFS", "영업이익(손실)", "150"),
    ]),
}


def fake_fetch(api_key, corp_code, year, reprt_code):
    return FAKE_REPORTS.get((year, reprt_code))


class TestDecumulation(unittest.TestCase):
    def test_quarterly_split(self):
        with mock.patch.object(ol, "fetch_report", side_effect=fake_fetch):
            quarters, fs = ol.fetch_quarters("k", "c", 8, "auto")
        self.assertEqual(fs, "CFS")
        self.assertEqual([(q.label, q.revenue, q.op) for q in quarters], [
            ("2025Q1", 100.0, 10.0),
            ("2025Q2", 150.0, 30.0),
            ("2025Q3", 200.0, 50.0),
            ("2025Q4", 250.0, 60.0),
        ])

    def test_incremental_margins(self):
        with mock.patch.object(ol, "fetch_report", side_effect=fake_fetch):
            quarters, _ = ol.fetch_quarters("k", "c", 8, "auto")
        rows = ol.analyze(quarters)
        self.assertIsNone(rows[0].qoq_incr)
        self.assertAlmostEqual(rows[1].qoq_incr, 20 / 50)   # 40%
        self.assertAlmostEqual(rows[2].qoq_incr, 20 / 50)   # 40%
        self.assertAlmostEqual(rows[3].qoq_incr, 10 / 50)   # 20% ← 둔화 감지
        self.assertAlmostEqual(rows[3].opm, 60 / 250)

    def test_revenue_decline_gives_none(self):
        q1 = ol.Quarter(2025, 1, 100.0, 10.0)
        q2 = ol.Quarter(2025, 2, 80.0, 12.0)  # 매출 감소
        _, _, ratio = ol.incremental(q2, q1)
        self.assertIsNone(ratio)


class TestParsing(unittest.TestCase):
    def test_amount_parsing(self):
        self.assertEqual(ol.parse_amount("1,234,567"), 1234567.0)
        self.assertEqual(ol.parse_amount("-1,000"), -1000.0)
        self.assertIsNone(ol.parse_amount("-"))
        self.assertIsNone(ol.parse_amount(""))
        self.assertIsNone(ol.parse_amount(None))

    def test_ofs_fallback(self):
        data = report([
            is_item("OFS", "매출액", "500", "500"),
            is_item("OFS", "영업이익", "50", "50"),
        ])
        self.assertIsNone(ol.extract_cumulative(data, "CFS"))
        self.assertEqual(ol.extract_cumulative(data, "OFS"), (500.0, 50.0))


if __name__ == "__main__":
    unittest.main()
