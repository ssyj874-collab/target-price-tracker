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


class StoreTest(unittest.TestCase):
    def test_upsert_idempotent_and_sorted(self):
        store = {"quarterly": [{"label": "2024.1분기", "revenue": 1, "op": 1,
                                "sga": None, "inventory": None}],
                 "annual": []}
        new_q = [
            {"label": "2023.4분기", "revenue": 9, "op": 9, "sga": None, "inventory": None},
            {"label": "2024.1분기", "revenue": 2, "op": 2, "sga": None, "inventory": None},
        ]
        dart_store.upsert(store, new_q, [{"year": 2023, "revenue": 9, "op": 9,
                                          "sga": None, "inventory": None}])
        labels = [r["label"] for r in store["quarterly"]]
        self.assertEqual(labels, ["2023.4분기", "2024.1분기"])
        self.assertEqual(store["quarterly"][1]["revenue"], 2)  # 새 값으로 교체
        dart_store.upsert(store, new_q, [])  # 한 번 더 — 멱등
        self.assertEqual(len(store["quarterly"]), 2)

    def test_update_stock_end_to_end_with_mock(self):
        corp = {"corp_code": "00266961", "corp_name": "효성중공업",
                "stock_code": "298040"}

        def fake_collect(key, corp_code, year):
            if year != 2024:
                return {}
            return {1: _metrics(100 * M, 10 * M, 20 * M, 50 * M),
                    4: _metrics(700 * M, 100 * M, 110 * M, 70 * M)}

        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(dart_store, "collect_year", side_effect=fake_collect):
                store = dart_store.update_stock("KEY", corp, d, 2023, 2024)
            path = dart_store.store_path(d, corp)
            self.assertTrue(os.path.exists(path))
            with open(path, encoding="utf-8") as f:
                saved = json.load(f)
        self.assertEqual(saved["corp_name"], "효성중공업")
        self.assertEqual(len(saved["quarterly"]), 2)  # Q1 + Q4(재고만)
        self.assertEqual(saved["annual"][0]["year"], 2024)
        self.assertIn("updated", saved)


class FetchReportTest(unittest.TestCase):
    def test_cfs_then_ofs_fallback(self):
        calls = []

        def fake_api(path, **params):
            calls.append(params["fs_div"])
            if params["fs_div"] == "CFS":
                return {"status": "013", "list": []}
            return {"status": "000", "list": [_row("IS", "매출액", "100")]}

        with mock.patch.object(dart_store, "_api_json", side_effect=fake_api):
            rows = dart_store.fetch_report("K", "C", 2024, "11011")
        self.assertEqual(calls, ["CFS", "OFS"])
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
