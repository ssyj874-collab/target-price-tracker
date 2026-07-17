import io
import json
import os
import tempfile
import unittest
import zipfile
from unittest import mock

import dart_fetch


def _zip_xml(xml: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("CORPCODE.xml", xml)
    return buf.getvalue()


CORP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<result>
  <list><corp_code>00266961</corp_code><corp_name>효성중공업</corp_name><stock_code>298040</stock_code></list>
  <list><corp_code>00126380</corp_code><corp_name>삼성전자</corp_name><stock_code>005930</stock_code></list>
  <list><corp_code>99999999</corp_code><corp_name>비상장회사</corp_name><stock_code> </stock_code></list>
</result>"""


def _is_row(fs, name, amount, add=""):
    return {"fs_div": fs, "sj_div": "IS", "account_nm": name,
            "thstrm_amount": amount, "thstrm_add_amount": add}


class CorpMapTest(unittest.TestCase):
    def _corp_map(self):
        with mock.patch.object(dart_fetch, "_http_get", return_value=_zip_xml(CORP_XML)):
            return dart_fetch._download_corp_map("KEY")

    def test_download_excludes_unlisted(self):
        entries = self._corp_map()["entries"]
        self.assertEqual(len(entries), 2)  # 비상장 제외

    def test_lookup_by_name_and_code(self):
        corp_map = self._corp_map()
        by_name = dart_fetch.lookup_corp(corp_map, "효성중공업")
        self.assertEqual(by_name["corp_code"], "00266961")
        by_code = dart_fetch.lookup_corp(corp_map, "005930")
        self.assertEqual(by_code["corp_name"], "삼성전자")

    def test_lookup_missing_raises(self):
        with self.assertRaises(SystemExit):
            dart_fetch.lookup_corp(self._corp_map(), "없는회사")


class ExtractTest(unittest.TestCase):
    def test_prefers_cfs_and_add_amount(self):
        rows = [
            _is_row("OFS", "매출액", "1", add="2"),
            _is_row("OFS", "영업이익", "3", add="4"),
            # 연결(CFS)이 우선, 누적(thstrm_add_amount)이 우선
            _is_row("CFS", "매출액", "926,834,000,000", add="1,526,337,000,000"),
            _is_row("CFS", "영업이익(손실)", "42,140,000,000", add="37,375,000,000"),
        ]
        rev, op = dart_fetch._extract_cums(rows)
        self.assertEqual(rev, 1526337000000)
        self.assertEqual(op, 37375000000)

    def test_falls_back_to_ofs(self):
        rows = [
            _is_row("OFS", "매출액", "100"),
            _is_row("OFS", "영업이익", "10"),
        ]
        self.assertEqual(dart_fetch._extract_cums(rows), (100, 10))

    def test_prefer_ofs_flag(self):
        rows = [
            _is_row("CFS", "매출액", "1"), _is_row("CFS", "영업이익", "2"),
            _is_row("OFS", "매출액", "100"), _is_row("OFS", "영업이익", "10"),
        ]
        self.assertEqual(dart_fetch._extract_cums(rows, prefer_ofs=True), (100, 10))


class QuartersFromCumsTest(unittest.TestCase):
    def test_differencing(self):
        # 효성중공업 2022년 실제 값(백만원→원)으로 누적 구성
        m = 1_000_000
        cums = {2022: {
            1: (599_503 * m, -4_765 * m),
            2: ((599_503 + 926_834) * m, (-4_765 + 42_140) * m),
            3: ((599_503 + 926_834 + 786_312) * m, (-4_765 + 42_140 + 56_052) * m),
            4: ((599_503 + 926_834 + 786_312 + 1_197_495) * m,
                (-4_765 + 42_140 + 56_052 + 49_822) * m),
        }}
        quarters = dart_fetch.quarters_from_cums(cums)
        self.assertEqual([q["label"] for q in quarters],
                         ["2022.1분기", "2022.2분기", "2022.3분기", "2022.4분기"])
        self.assertEqual([q["revenue"] for q in quarters],
                         [599_503, 926_834, 786_312, 1_197_495])
        self.assertEqual([q["op"] for q in quarters],
                         [-4_765, 42_140, 56_052, 49_822])

    def test_missing_middle_report_skips_dependent_quarter(self):
        m = 1_000_000
        cums = {2024: {
            1: (100 * m, 10 * m),
            # 반기(2분기) 누락
            3: (300 * m, 30 * m),
            4: (400 * m, 40 * m),
        }}
        quarters = dart_fetch.quarters_from_cums(cums)
        # Q1은 그대로, Q2 불가, Q3은 차분 기준 소실로 생략, Q4 = 연간-3분기누적
        self.assertEqual([q["label"] for q in quarters],
                         ["2024.1분기", "2024.4분기"])
        self.assertEqual(quarters[1]["revenue"], 100)

    def test_multi_year_sorted(self):
        m = 1_000_000
        cums = {
            2023: {1: (10 * m, 1 * m)},
            2022: {1: (20 * m, 2 * m)},
        }
        labels = [q["label"] for q in dart_fetch.quarters_from_cums(cums)]
        self.assertEqual(labels, ["2022.1분기", "2023.1분기"])


class WriteAndRoundtripTest(unittest.TestCase):
    def test_write_csv_loads_via_watchlist(self):
        from watchlist import load_stock_file

        quarters = [
            {"label": "2022.1분기", "revenue": 599503, "op": -4765},
            {"label": "2022.2분기", "revenue": 926834, "op": 42140},
        ]
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "효성중공업.csv")
            dart_fetch.write_stock_csv(path, "298040", quarters)
            name, parsed, code = load_stock_file(path)
        self.assertEqual(name, "효성중공업")
        self.assertEqual(code, "298040")
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0].operating_profit, -4765)
        self.assertEqual(parsed[0].label, "2022.1분기")


class ListedCodesTest(unittest.TestCase):
    def test_parse_kind_download(self):
        kospi = "<table><tr><td>삼성전자</td><td>005930</td></tr></table>"
        kosdaq = "<table><tr><td>에코프로</td><td>086520</td></tr></table>"
        with mock.patch.object(
            dart_fetch, "_http_get",
            side_effect=[kospi.encode("cp949"), kosdaq.encode("cp949")],
        ), mock.patch.object(dart_fetch, "_LISTED_CACHE", "/nonexistent/x.json"):
            codes = dart_fetch.fetch_listed_codes(refresh=True)
        self.assertEqual(codes["005930"], "유가")
        self.assertEqual(codes["086520"], "코스닥")
        self.assertEqual(len(codes), 2)

    def test_fetch_failure_returns_none(self):
        with mock.patch.object(dart_fetch, "_http_get",
                               side_effect=OSError("down")), \
             mock.patch.object(dart_fetch, "_LISTED_CACHE", "/nonexistent/x.json"):
            self.assertIsNone(dart_fetch.fetch_listed_codes(refresh=True))


class ResumeIndexTest(unittest.TestCase):
    def _corps(self, names):
        return [{"corp_name": n, "stock_code": f"{i:06d}", "corp_code": str(i)}
                for i, n in enumerate(names)]

    def test_name_based_resume_with_filtered_list(self):
        import dart_app

        corps = self._corps(["가나", "다라", "마바", "사아"])
        state = {"mode": "backfill", "last_name": "마바"}
        self.assertEqual(dart_app.resume_index(corps, state, "K"), 2)

    def test_old_index_state_migrates_via_full_list(self):
        import dart_app

        full = self._corps(["가나", "나나", "다라", "라라", "마바"])
        filtered = [c for c in full if c["corp_name"] != "나나"]
        state = {"mode": "backfill", "index": 2}  # 옛 형식: 전체 목록의 '다라'
        with mock.patch.object(dart_app, "load_corp_map",
                               return_value={"entries": full}):
            idx = dart_app.resume_index(filtered, state, "K")
        self.assertEqual(filtered[idx]["corp_name"], "다라")

    def test_no_state_starts_at_zero(self):
        import dart_app

        self.assertEqual(dart_app.resume_index(self._corps(["가"]), {}, "K"), 0)


class ApiJsonTest(unittest.TestCase):
    def test_no_data_status_returns_empty(self):
        body = json.dumps({"status": "013", "message": "조회된 데이타가 없습니다."})
        with mock.patch.object(dart_fetch, "_http_get", return_value=body.encode()):
            data = dart_fetch._api_json("fnlttSinglAcnt.json", crtfc_key="K")
        self.assertEqual(data["list"], [])

    def test_error_status_raises(self):
        body = json.dumps({"status": "020", "message": "등록되지 않은 키입니다."})
        with mock.patch.object(dart_fetch, "_http_get", return_value=body.encode()):
            with self.assertRaises(RuntimeError):
                dart_fetch._api_json("fnlttSinglAcnt.json", crtfc_key="BAD")


if __name__ == "__main__":
    unittest.main()
