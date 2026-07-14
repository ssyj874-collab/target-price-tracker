import json
import os
import tempfile
import unittest
from unittest import mock

import dart_store


def _row(sj, name, amount, add="", acc_id=""):
    return {"sj_div": sj, "account_nm": name, "account_id": acc_id,
            "thstrm_amount": amount, "thstrm_add_amount": add}


M = 1_000_000


def _metrics(rev, op, sga=None, inv=None):
    return {"revenue": rev, "op": op, "sga": sga, "inventory": inv}


class ExtractMetricsTest(unittest.TestCase):
    def test_matches_by_account_id_and_name(self):
        rows = [
            _row("IS", "수익(매출액)", "100", add="300",
                 acc_id="ifrs-full_Revenue"),
            _row("IS", "영업이익(손실)", "10", add="30",
                 acc_id="dart_OperatingIncomeLoss"),
            _row("IS", "판매비와관리비", "5", add="15"),
            _row("BS", "재고자산", "77", acc_id="ifrs-full_Inventories"),
        ]
        m = dart_store.extract_metrics(rows)
        # 손익은 누적(thstrm_add_amount) 우선, 재고는 시점값
        self.assertEqual(m, {"revenue": 300, "op": 30, "sga": 15, "inventory": 77})

    def test_missing_items_are_none(self):
        rows = [_row("IS", "매출액", "100")]
        m = dart_store.extract_metrics(rows)
        self.assertEqual(m["revenue"], 100)
        self.assertIsNone(m["op"])
        self.assertIsNone(m["sga"])
        self.assertIsNone(m["inventory"])

    def test_ignores_wrong_statement(self):
        # 재고자산이라는 이름이 손익(IS)에 있어도 무시
        rows = [_row("IS", "재고자산", "999")]
        self.assertIsNone(dart_store.extract_metrics(rows)["inventory"])

    def test_cis_single_statement_company(self):
        # 단일 포괄손익계산서(CIS)만 쓰는 회사도 손익 항목을 잡아야 한다
        rows = [
            _row("CIS", "매출액", "100"),
            _row("CIS", "영업이익", "10"),
            _row("CIS", "판매비와관리비", "5"),
        ]
        m = dart_store.extract_metrics(rows)
        self.assertEqual((m["revenue"], m["op"], m["sga"]), (100, 10, 5))

    def test_ordinal_prefix_and_loss_names(self):
        rows = [
            _row("IS", "Ⅰ. 매출액", "100"),
            _row("IS", "영업손실", "-10"),
        ]
        m = dart_store.extract_metrics(rows)
        self.assertEqual(m["revenue"], 100)
        self.assertEqual(m["op"], -10)


class BuildQuartersTest(unittest.TestCase):
    def test_differencing_and_inventory_point(self):
        year_data = {2024: {
            1: _metrics(100 * M, 10 * M, 20 * M, 50 * M),
            2: _metrics(250 * M, 30 * M, 45 * M, 60 * M),
            3: _metrics(450 * M, 60 * M, 75 * M, 55 * M),
            4: _metrics(700 * M, 100 * M, 110 * M, 70 * M),
        }}
        rows = dart_store.build_quarters(year_data)
        self.assertEqual([r["revenue"] for r in rows], [100, 150, 200, 250])
        self.assertEqual([r["op"] for r in rows], [10, 20, 30, 40])
        self.assertEqual([r["sga"] for r in rows], [20, 25, 30, 35])
        # 재고는 차분하지 않고 분기말 잔액 그대로
        self.assertEqual([r["inventory"] for r in rows], [50, 60, 55, 70])
        self.assertEqual(rows[2]["label"], "2024.3분기")

    def test_missing_middle_keeps_inventory_only(self):
        year_data = {2024: {
            1: _metrics(100 * M, 10 * M, None, 50 * M),
            # 2분기(반기) 누락
            3: _metrics(450 * M, 60 * M, None, 55 * M),
        }}
        rows = dart_store.build_quarters(year_data)
        self.assertEqual(len(rows), 2)
        q3 = rows[1]
        self.assertIsNone(q3["revenue"])  # 차분 기준 없음
        self.assertEqual(q3["inventory"], 55)  # 시점값은 유지

    def test_sga_missing_in_one_report(self):
        year_data = {2024: {
            1: _metrics(100 * M, 10 * M, None, None),
            2: _metrics(250 * M, 30 * M, 45 * M, None),
        }}
        rows = dart_store.build_quarters(year_data)
        self.assertEqual(rows[1]["revenue"], 150)
        self.assertIsNone(rows[1]["sga"])  # 전분기 판관비가 없으면 차분 불가


class BuildAnnualTest(unittest.TestCase):
    def test_annual_from_q4(self):
        year_data = {
            2023: {4: _metrics(700 * M, 100 * M, 110 * M, 70 * M)},
            2024: {1: _metrics(100 * M, 10 * M, None, None)},  # 사업보고서 없음
        }
        rows = dart_store.build_annual(year_data)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0], {"year": 2023, "revenue": 700, "op": 100,
                                   "sga": 110, "inventory": 70})


CORP = {"corp_code": "00266961", "corp_name": "효성중공업",
        "stock_code": "298040"}


class StoreTest(unittest.TestCase):
    def test_ensure_periods_skips_stored_and_saves(self):
        calls = []

        def fake_fetch(key, corp_code, year, q, fs_hint=None):
            calls.append((year, q, fs_hint))
            if (year, q) == (2024, 1):
                return _metrics(100 * M, 10 * M, 20 * M, 50 * M), "CFS"
            return None, None  # 미공시

        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(dart_store, "fetch_period", side_effect=fake_fetch):
                store, added = dart_store.ensure_periods(
                    "KEY", CORP, d, [(2024, 1), (2024, 2)])
                self.assertEqual(added, 1)
                self.assertEqual(len(calls), 2)
                # 두 번째 실행: 저장된 (2024,1)은 건너뛰고 (2024,2)만 재시도
                calls.clear()
                store, added = dart_store.ensure_periods(
                    "KEY", CORP, d, [(2024, 1), (2024, 2)])
                self.assertEqual(added, 0)
                self.assertEqual([c[:2] for c in calls], [(2024, 2)])
                # fs_div 힌트가 기억됨
                self.assertEqual(calls[0][2], "CFS")
            path = dart_store.store_path(d, CORP)
            with open(path, encoding="utf-8") as f:
                saved = json.load(f)
        self.assertEqual(saved["cums"]["2024"]["1"]["revenue"], 100 * M)
        self.assertEqual(saved["quarterly"][0]["revenue"], 100)
        self.assertIn("updated", saved)

    def test_budget_exceeded_saves_partial(self):
        seen = []

        def fake_fetch(key, corp_code, year, q, fs_hint=None):
            seen.append((year, q))
            if len(seen) == 1:
                return _metrics(100 * M, 10 * M, None, None), "CFS"
            raise dart_store.BudgetExceeded("한도")

        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(dart_store, "fetch_period", side_effect=fake_fetch):
                with self.assertRaises(dart_store.BudgetExceeded):
                    dart_store.ensure_periods("KEY", CORP, d,
                                              [(2024, 1), (2024, 2)])
            saved = dart_store.load_store(dart_store.store_path(d, CORP))
        # 한도 전에 받은 (2024,1)은 저장돼 있어야 한다
        self.assertEqual(saved["cums"]["2024"]["1"]["revenue"], 100 * M)

    def test_update_stock_compat(self):
        def fake_fetch(key, corp_code, year, q, fs_hint=None):
            if year == 2024 and q in (1, 4):
                vals = {1: _metrics(100 * M, 10 * M, 20 * M, 50 * M),
                        4: _metrics(700 * M, 100 * M, 110 * M, 70 * M)}
                return vals[q], "CFS"
            return None, None

        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(dart_store, "fetch_period", side_effect=fake_fetch):
                store = dart_store.update_stock("KEY", CORP, d, 2023, 2024)
        self.assertEqual(len(store["quarterly"]), 2)  # Q1 + Q4(재고만)
        self.assertEqual(store["annual"][0]["year"], 2024)


class PeriodsTest(unittest.TestCase):
    def test_rolling_periods_excludes_current_quarter(self):
        import datetime as dt

        periods = dart_store.rolling_periods(dt.date(2026, 7, 12))
        # 2026년 3분기 진행 중 → 직전 4개: 2025.3 ~ 2026.2
        self.assertEqual(periods, [(2025, 3), (2025, 4), (2026, 1), (2026, 2)])

    def test_rolling_periods_year_boundary(self):
        import datetime as dt

        periods = dart_store.rolling_periods(dt.date(2026, 2, 1))
        self.assertEqual(periods, [(2025, 1), (2025, 2), (2025, 3), (2025, 4)])

    def test_missing_periods(self):
        store = {"cums": {"2024": {"1": {}, "2": {}}}}
        got = dart_store.missing_periods(store, [(2024, 1), (2024, 3), (2025, 1)])
        self.assertEqual(got, [(2024, 3), (2025, 1)])


class FetchPeriodTest(unittest.TestCase):
    def test_cfs_then_ofs_fallback(self):
        calls = []

        def fake_api(path, **params):
            calls.append(params["fs_div"])
            if params["fs_div"] == "CFS":
                return {"status": "013", "list": []}
            return {"status": "000", "list": [
                _row("IS", "매출액", "100"), _row("IS", "영업이익", "10")]}

        with mock.patch.object(dart_store, "_api_json", side_effect=fake_api):
            metrics, fs = dart_store.fetch_period("K", "C", 2024, 4)
        self.assertEqual(calls, ["CFS", "OFS"])
        self.assertEqual(fs, "OFS")
        self.assertEqual(metrics["revenue"], 100)

    def test_bank_without_revenue_still_stored(self):
        # 은행·지주는 매출액 계정이 없다 — 영업이익만으로도 채택
        def fake_api(path, **params):
            return {"status": "000", "list": [
                _row("CIS", "영업이익", "1,000,000,000,000")]}

        with mock.patch.object(dart_store, "_api_json", side_effect=fake_api):
            metrics, fs = dart_store.fetch_period("K", "C", 2024, 1)
        self.assertIsNotNone(metrics)
        self.assertIsNone(metrics["revenue"])
        self.assertEqual(metrics["op"], 1_000_000_000_000)

    def test_quarters_with_op_only(self):
        year_data = {2024: {
            1: _metrics(None, 10 * M, None, None),
            2: _metrics(None, 25 * M, None, None),
        }}
        rows = dart_store.build_quarters(year_data)
        self.assertEqual([r["op"] for r in rows], [10, 15])
        self.assertEqual([r["revenue"] for r in rows], [None, None])

    def test_fs_hint_tried_first(self):
        calls = []

        def fake_api(path, **params):
            calls.append(params["fs_div"])
            return {"status": "000", "list": [
                _row("IS", "매출액", "100"), _row("IS", "영업이익", "10")]}

        with mock.patch.object(dart_store, "_api_json", side_effect=fake_api):
            _m, fs = dart_store.fetch_period("K", "C", 2024, 1, fs_hint="OFS")
        self.assertEqual(calls, ["OFS"])  # 힌트 먼저, 성공하면 1회로 끝
        self.assertEqual(fs, "OFS")

    def test_api_hook_invoked(self):
        count = []
        dart_store.API_HOOK = lambda: count.append(1)
        try:
            with mock.patch.object(dart_store, "_api_json",
                                   return_value={"status": "013", "list": []}):
                dart_store.fetch_period("K", "C", 2024, 1)
        finally:
            dart_store.API_HOOK = None
        self.assertEqual(len(count), 2)  # CFS·OFS 각 1회


if __name__ == "__main__":
    unittest.main()
