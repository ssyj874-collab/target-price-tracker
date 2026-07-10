import unittest

from incremental_margin import (
    Quarter,
    Trend,
    analyze,
    break_even_revenue,
    incremental_rows,
)


def q(label, revenue, op):
    return Quarter(label=label, revenue=revenue, operating_profit=op)


class IncrementalMarginTest(unittest.TestCase):
    def test_samsung_example_10_40(self):
        """통화 예시: 100조/10조 → 150조/30조 이면 증분 이익률 40%."""
        rows = incremental_rows([q("Q1", 100, 10), q("Q2", 150, 30)])
        self.assertEqual(rows[0].delta_revenue, 50)
        self.assertEqual(rows[0].delta_profit, 20)
        self.assertAlmostEqual(rows[0].incremental_margin, 40.0)

    def test_overall_margin(self):
        self.assertAlmostEqual(q("Q1", 150, 30).operating_margin, 20.0)
        self.assertIsNone(q("Q1", 0, 0).operating_margin)

    def test_plateau_detected_while_overall_margin_still_rising(self):
        """매출 150→200, 추가 이익 여전히 20조: 전체 이익률은 오르지만
        증분 이익률은 40%에서 정체 — P 반영 완료 신호."""
        quarters = [q("Q1", 100, 10), q("Q2", 150, 30), q("Q3", 200, 50)]
        analysis = analyze(quarters)
        self.assertIs(analysis.trend, Trend.PLATEAU)
        # 전체 이익률은 20% → 25%로 여전히 상승 중
        self.assertAlmostEqual(quarters[-1].operating_margin, 25.0)

    def test_rising_trend(self):
        analysis = analyze([q("Q1", 100, 10), q("Q2", 150, 30), q("Q3", 200, 70)])
        self.assertIs(analysis.trend, Trend.RISING)

    def test_falling_trend(self):
        analysis = analyze([q("Q1", 100, 10), q("Q2", 150, 30), q("Q3", 200, 35)])
        self.assertIs(analysis.trend, Trend.FALLING)

    def test_zero_delta_revenue_gives_none(self):
        rows = incremental_rows([q("Q1", 100, 10), q("Q2", 100, 12)])
        self.assertIsNone(rows[0].incremental_margin)

    def test_declining_revenue_excluded_from_trend(self):
        """매출 감소 구간은 부호가 뒤집혀 추세 비교에서 제외한다."""
        analysis = analyze([q("Q1", 100, 10), q("Q2", 90, 5), q("Q3", 95, 7)])
        self.assertIs(analysis.trend, Trend.UNKNOWN)

    def test_break_even_from_linear_data(self):
        """OP = 0.4*R − 30 이면 손익분기 매출은 75."""
        quarters = [q("Q1", 100, 10), q("Q2", 150, 30), q("Q3", 200, 50)]
        self.assertAlmostEqual(break_even_revenue(quarters), 75.0)

    def test_break_even_none_when_flat_revenue(self):
        self.assertIsNone(break_even_revenue([q("Q1", 100, 10), q("Q2", 100, 20)]))

    def test_margin_gap_positive_while_average_rising(self):
        """Δm ∝ (m_inc − m): 격차가 양수면 전체 이익률 상승 중."""
        analysis = analyze([q("Q1", 100, 10), q("Q2", 150, 30)])
        # m_inc 40%, 전체 20% → 격차 +20%p
        self.assertAlmostEqual(analysis.margin_gap, 20.0)

    def test_margin_gap_zero_at_overall_margin_peak(self):
        """증분 이익률이 전체 이익률과 같아지는 분기가 전체 이익률 고점."""
        analysis = analyze([q("Q3", 200, 50), q("Q4", 250, 62.5)])
        self.assertAlmostEqual(analysis.margin_gap, 0.0)
        self.assertAlmostEqual(analysis.quarters[-1].operating_margin, 25.0)

    def test_black_ink_turn_signal(self):
        """영업이익이 마이너스에서 플러스로 돌아서면 흑자 전환 시그널."""
        analysis = analyze([q("Q1", 100, -5), q("Q2", 120, 3)])
        self.assertTrue(any("흑자 전환" in s for s in analysis.signals))

    def test_spike_signal(self):
        analysis = analyze([q("Q1", 100, 10), q("Q2", 150, 20), q("Q3", 200, 60)])
        self.assertTrue(any("사업보고서" in s for s in analysis.signals))

    def test_requires_two_quarters(self):
        with self.assertRaises(ValueError):
            analyze([q("Q1", 100, 10)])


class PriceAndReportTest(unittest.TestCase):
    def _quarters(self, with_price=True):
        price = [54000, 72000, 89000, 83000] if with_price else [None] * 4
        specs = [(100, 10), (150, 30), (200, 50), (250, 62.5)]
        return [
            Quarter(f"Q{i+1}", rev, op, price=p)
            for i, ((rev, op), p) in enumerate(zip(specs, price))
        ]

    def test_price_change_pct(self):
        from incremental_margin import price_change_pct

        qs = self._quarters()
        self.assertAlmostEqual(price_change_pct(qs[0], qs[1]), 100 / 3)
        self.assertIsNone(price_change_pct(qs[0], q("Q2", 1, 1)))

    def test_render_includes_price_columns(self):
        from incremental_margin import render

        out = render(analyze(self._quarters()))
        self.assertIn("주가", out)
        self.assertIn("+33.3%", out)

    def test_render_without_price_has_no_price_columns(self):
        from incremental_margin import render

        out = render(analyze(self._quarters(with_price=False)))
        header = out.splitlines()[0]
        self.assertNotIn("주가", header)

    def test_html_report_smoke(self):
        from report import render_html

        page = render_html(analyze(self._quarters()))
        self.assertIn('id="price-chart"', page)
        self.assertIn('id="margin-chart"', page)
        self.assertIn("분기 실적표", page)
        self.assertIn('"hasPrice": true', page)

    def test_html_report_without_price_skips_price_panel(self):
        from report import render_html

        page = render_html(analyze(self._quarters(with_price=False)))
        self.assertNotIn('id="price-chart"', page)
        self.assertIn('id="margin-chart"', page)


SAMPLE_PASTE = """\
\t2025/03\t2025/06\t2025/09\t2025/12\t2026/03\t2026/06(E)\t2026/09(E)\t2026/12(E)
매출액\t10,761\t15,253\t16,241\t17,430\t13,582\t18,143\t18,929\t20,699
영업이익\t1,024\t1,643\t2,198\t2,605\t1,523
영업이익률\t9.5\t10.8\t13.5\t14.9\t11.2\t15.7\t16.1\t17.0
영업이익(발표기준)\t1,024\t1,643\t2,198\t2,605\t1,523\t2,845\t3,052\t3,529
"""


class PasteParseTest(unittest.TestCase):
    def test_parse_fnguide_paste(self):
        from incremental_margin import parse_paste

        quarters = parse_paste(SAMPLE_PASTE)
        self.assertEqual(len(quarters), 8)
        self.assertEqual(quarters[0].label, "2025/03")
        self.assertEqual(quarters[0].revenue, 10761)
        self.assertEqual(quarters[0].operating_profit, 1024)
        self.assertFalse(quarters[0].estimate)
        # 컨센서스 분기: 영업이익 행이 비어 있어도 발표기준 행으로 채워짐
        self.assertTrue(quarters[5].estimate)
        self.assertEqual(quarters[5].operating_profit, 2845)
        # 영업이익률 행은 매출/영업이익으로 오인되지 않아야 함
        self.assertEqual(quarters[4].operating_profit, 1523)

    def test_estimates_excluded_from_trend_and_kpi_basis(self):
        from incremental_margin import parse_paste

        analysis = analyze(parse_paste(SAMPLE_PASTE))
        # 실적치 마지막 두 유효 증분(56.2% → 34.2%) 기준으로 하락.
        # 컨센서스(29.0→26.3→26.9)가 판정을 바꾸지 않는다.
        self.assertIs(analysis.trend, Trend.FALLING)
        self.assertTrue(any("컨센서스" in s for s in analysis.signals))

    def test_looks_like_paste_and_csv_dispatch(self):
        from incremental_margin import looks_like_paste

        self.assertTrue(looks_like_paste(SAMPLE_PASTE))
        self.assertFalse(looks_like_paste("quarter,revenue,operating_profit\nQ1,1,1\n"))

    def test_space_separated_paste(self):
        from incremental_margin import parse_paste

        text = (
            "2025/03 2025/06 2025/09\n"
            "매출액 100 150 200\n"
            "영업이익 10 30 50\n"
            "주가 54,000 72,000 89,000\n"
        )
        quarters = parse_paste(text)
        self.assertEqual(len(quarters), 3)
        self.assertEqual(quarters[2].price, 89000)


class PriceFetchTest(unittest.TestCase):
    def test_quarter_end_labels(self):
        import datetime as dt

        from price_fetch import quarter_end

        self.assertEqual(quarter_end("2025/03"), dt.date(2025, 3, 31))
        self.assertEqual(quarter_end("2025Q2"), dt.date(2025, 6, 30))
        self.assertEqual(quarter_end("2025-12"), dt.date(2025, 12, 31))
        self.assertIsNone(quarter_end("이상한라벨"))

    def test_fill_prices_uses_last_close_before_quarter_end(self):
        import datetime as dt
        from unittest import mock

        import price_fetch

        closes = {
            dt.date(2025, 3, 28): 54000.0,  # 3/31이 휴장일 때 직전 거래일
            dt.date(2025, 6, 30): 72000.0,
        }
        quarters = [q("2025/03", 100, 10), q("2025/06", 150, 30)]
        with mock.patch.object(
            price_fetch, "_fetch_daily_closes", return_value=closes
        ):
            filled, err = price_fetch.fill_prices(
                quarters, "005930", today=dt.date(2025, 7, 10)
            )
        self.assertIsNone(err)
        self.assertEqual(filled[0].price, 54000)
        self.assertEqual(filled[1].price, 72000)

    def test_fill_prices_skips_estimates_and_future(self):
        import datetime as dt
        from unittest import mock

        import price_fetch

        quarters = [
            q("2025/03", 100, 10),
            Quarter("2025/06", 150, 30, estimate=True),
        ]
        with mock.patch.object(
            price_fetch, "_fetch_daily_closes",
            return_value={dt.date(2025, 3, 31): 54000.0},
        ):
            filled, err = price_fetch.fill_prices(
                quarters, "005930", today=dt.date(2025, 7, 10)
            )
        self.assertEqual(filled[0].price, 54000)
        self.assertIsNone(filled[1].price)

    def test_fill_prices_network_failure_returns_reason(self):
        import datetime as dt
        import urllib.error
        from unittest import mock

        import price_fetch

        with mock.patch.object(
            price_fetch, "_fetch_daily_closes",
            side_effect=urllib.error.URLError("blocked"),
        ):
            filled, err = price_fetch.fill_prices(
                [q("2025/03", 100, 10), q("2025/06", 150, 30)],
                "005930",
                today=dt.date(2025, 7, 10),
            )
        self.assertIsNotNone(err)
        self.assertIsNone(filled[0].price)


if __name__ == "__main__":
    unittest.main()
