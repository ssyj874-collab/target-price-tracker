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


if __name__ == "__main__":
    unittest.main()
