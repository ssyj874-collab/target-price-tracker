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


if __name__ == "__main__":
    unittest.main()
