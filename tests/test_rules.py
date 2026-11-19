"""Pure business rules: window bounds, currency conversion and the 90-day metrics."""

import datetime as dt

import pytest

from risk_agents.data.rules import (
    Metrics90d,
    NativeTotals,
    Window,
    metrics_usd,
    percentile_rank,
    to_usd,
    window_for,
)


class TestWindow:
    def test_ninety_days_ending_on_the_cutoff_inclusive(self):
        assert window_for("2026-10-31") == Window("2026-08-03 00:00:00", "2026-10-31 23:59:59")

    def test_spans_exactly_the_requested_number_of_calendar_days(self):
        window = window_for("2026-10-31")
        start = dt.date.fromisoformat(window.start[:10])
        end = dt.date.fromisoformat(window.end[:10])
        assert (end - start).days + 1 == 90

    def test_accepts_a_date_object(self):
        assert window_for(dt.date(2026, 10, 31)) == window_for("2026-10-31")

    def test_crosses_a_leap_day(self):
        assert window_for("2024-03-01", days=2).start == "2024-02-29 00:00:00"

    def test_one_day_window_is_the_cutoff_day(self):
        assert window_for("2026-10-31", days=1) == Window(
            "2026-10-31 00:00:00", "2026-10-31 23:59:59"
        )

    @pytest.mark.parametrize("days", [0, -5])
    def test_rejects_empty_windows(self, days):
        with pytest.raises(ValueError, match="days"):
            window_for("2026-10-31", days=days)

    def test_rejects_a_malformed_cutoff(self):
        with pytest.raises(ValueError):
            window_for("31/10/2026")

    def test_contains_compares_timestamps_as_text(self):
        window = window_for("2026-10-31")
        assert window.contains("2026-08-03 00:00:00")
        assert window.contains("2026-10-31 23:59:59")
        assert not window.contains("2026-08-02 23:59:59")
        assert not window.contains("2026-11-01 00:00:00")


class TestToUsd:
    def test_multiplies_by_the_rate_and_rounds_to_cents(self):
        assert to_usd(400.0, 0.054) == 21.6

    def test_usd_is_unchanged(self):
        assert to_usd(81835.91, 1.0) == 81835.91

    def test_a_tiny_negative_amount_rounds_to_zero_not_negative_zero(self):
        assert str(to_usd(-0.001, 1.0)) == "0.0"

    @pytest.mark.parametrize("rate", [0.0, -1.0])
    def test_rejects_a_non_positive_rate(self, rate):
        with pytest.raises(ValueError, match="rate"):
            to_usd(10.0, rate)


class TestMetricsUsd:
    def test_converts_every_amount_and_computes_ggr(self):
        totals = NativeTotals(
            deposits=400.0,
            withdrawals=1367.74,
            staked=1558.5,
            paid_out=1218.0,
            bonuses=800.0,
            n_bets=40,
        )
        assert metrics_usd(totals, 0.054) == Metrics90d(
            depositos_aprobados=21.6,
            retiros_aprobados=73.86,
            monto_apostado=84.16,
            ggr=18.39,
            bonos_otorgados=43.2,
            n_apuestas=40,
        )

    def test_ggr_is_negative_when_the_player_wins(self):
        totals = NativeTotals(0.0, 0.0, staked=100.0, paid_out=150.0, bonuses=0.0, n_bets=3)
        assert metrics_usd(totals, 1.0).ggr == -50.0

    def test_ggr_is_rounded_after_subtracting(self):
        # Rounding each side first gives 0.10 - 0.10 = 0.0; the definition rounds the difference.
        totals = NativeTotals(0.0, 0.0, staked=0.104, paid_out=0.096, bonuses=0.0, n_bets=1)
        assert metrics_usd(totals, 1.0).ggr == 0.01

    def test_no_activity_gives_zeros_not_negative_zero(self):
        metrics = metrics_usd(NativeTotals(0.0, 0.0, 0.0, 0.0, 0.0, 0), 0.054)
        assert metrics.as_dict() == {
            "depositos_aprobados": 0.0,
            "retiros_aprobados": 0.0,
            "monto_apostado": 0.0,
            "ggr": 0.0,
            "bonos_otorgados": 0.0,
            "n_apuestas": 0,
        }
        assert str(metrics.ggr) == "0.0"

    def test_as_dict_uses_the_schema_field_names_in_order(self):
        metrics = metrics_usd(NativeTotals(1.0, 2.0, 3.0, 1.0, 4.0, 5), 1.0)
        assert list(metrics.as_dict()) == [
            "depositos_aprobados",
            "retiros_aprobados",
            "monto_apostado",
            "ggr",
            "bonos_otorgados",
            "n_apuestas",
        ]


class TestPercentileRank:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [(0, 0), (1, 25), (2.5, 50), (4, 100), (99, 100)],
    )
    def test_share_of_the_population_at_or_below_the_value(self, value, expected):
        assert percentile_rank([1, 2, 3, 4], value) == expected

    def test_ties_count_as_at_or_below(self):
        assert percentile_rank([5, 5, 5, 5], 5) == 100

    def test_an_empty_population_has_no_percentile(self):
        assert percentile_rank([], 3) is None
