from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from eod_pipeline.backtest.engine import run_backtest
from eod_pipeline.backtest.metrics import (
    ANNUALIZATION_FACTOR,
    BacktestMetrics,
    annualized_sharpe,
    maximum_drawdown,
    minute_pnl_buckets,
)
from eod_pipeline.backtest.risk import RiskReason, check_risk
from eod_pipeline.backtest.snapshots import SnapshotArrays
from eod_pipeline.backtest.strategies import (
    Side,
    StrategySignals,
    defensive_signals,
    mean_reversion_signals,
    momentum_signals,
)
from eod_pipeline.backtest.sweep import (
    canonical_json,
    parameter_grid,
    run_sweep,
)
from eod_pipeline.run_sweep import parse_args
from eod_pipeline.settings import RiskLimits, load_settings


ROOT = Path(__file__).resolve().parents[1]
SESSION_START_NS = 34_200_000_000_000


def snapshots(
    *,
    time_ns: list[int],
    bid: list[int],
    ask: list[int],
) -> SnapshotArrays:
    bid_array = np.array(bid, dtype=np.int64)
    ask_array = np.array(ask, dtype=np.int64)
    return SnapshotArrays(
        seq=np.arange(1, len(time_ns) + 1, dtype=np.int64),
        time_ns=np.array(time_ns, dtype=np.int64),
        bid_cents=bid_array,
        ask_cents=ask_array,
        mid_half_cents=bid_array + ask_array,
        spread_cents=ask_array - bid_array,
    )


def manual_signals(
    sides: list[Side],
    quantities: list[int],
    prices: list[int],
) -> StrategySignals:
    return StrategySignals(
        side=np.array(sides, dtype=np.int8),
        quantity=np.array(quantities, dtype=np.int64),
        price_cents=np.array(prices, dtype=np.int64),
    )


class StrategyTests(unittest.TestCase):
    def test_momentum_cold_start_boundaries_and_repeated_signals(self) -> None:
        data = snapshots(
            time_ns=[0, 1, 2, 3],
            bid=[99, 99, 100, 100],
            ask=[101, 101, 102, 102],
        )
        threshold = float(np.float32(2) / np.float32(202))
        signals = momentum_signals(
            data,
            lookback=2,
            entry_thresh=threshold,
            base_lot=50,
            pos_scalar=0.5,
        )
        self.assertEqual(signals.side.tolist(), [0, 0, 1, 1])
        self.assertEqual(signals.quantity.tolist(), [0, 0, 25, 25])
        self.assertEqual(signals.price_cents.tolist(), [0, 0, 102, 102])

    def test_momentum_negative_boundary_uses_bid(self) -> None:
        data = snapshots(time_ns=[0, 1], bid=[100, 99], ask=[102, 101])
        threshold = float(np.float32(2) / np.float32(200))
        signals = momentum_signals(
            data,
            lookback=1,
            entry_thresh=threshold,
            base_lot=10,
            pos_scalar=1,
        )
        self.assertEqual(Side(signals.side[1]), Side.SELL)
        self.assertEqual(signals.price_cents[1], 99)

    def test_mean_reversion_excludes_current_tick_and_uses_aggressive_price(self) -> None:
        data = snapshots(
            time_ns=[0, 1, 2, 3],
            bid=[99, 99, 101, 97],
            ask=[101, 101, 103, 99],
        )
        signals = mean_reversion_signals(
            data,
            window=2,
            dev_thresh=0.01,
            base_lot=50,
            pos_scalar=1,
        )
        self.assertEqual(signals.side.tolist(), [0, 0, 2, 1])
        self.assertEqual(signals.price_cents.tolist(), [0, 0, 101, 99])

    def test_defensive_is_hold_only(self) -> None:
        data = snapshots(time_ns=[0, 1], bid=[99, 99], ask=[101, 110])
        signals = defensive_signals(
            data,
            spread_floor=1,
            base_lot=50,
            pos_scalar=1,
        )
        self.assertEqual(signals.side.tolist(), [0, 0])


class RiskTests(unittest.TestCase):
    def setUp(self) -> None:
        self.limits = RiskLimits(500, 10, 2, 1)

    def test_limits_are_inclusive(self) -> None:
        decision = check_risk(
            self.limits,
            position=0,
            side=Side.BUY,
            quantity=10,
            price_cents=5_000,
            in_flight_count=0,
            accepted_orders_in_window=1,
        )
        self.assertTrue(decision.accepted)

    def test_all_exceeded_reasons_are_reported(self) -> None:
        decision = check_risk(
            self.limits,
            position=10,
            side=Side.BUY,
            quantity=11,
            price_cents=5_000,
            in_flight_count=1,
            accepted_orders_in_window=2,
        )
        self.assertEqual(
            decision.reasons,
            (
                RiskReason.NOTIONAL,
                RiskReason.POSITION,
                RiskReason.ORDER_RATE,
                RiskReason.IN_FLIGHT,
            ),
        )


class EngineTests(unittest.TestCase):
    def test_fill_delay_ordering_pending_exposure_and_end_settlement(self) -> None:
        data = snapshots(
            time_ns=[0, 50_000_000, 100_000_000],
            bid=[99, 99, 99],
            ask=[101, 101, 101],
        )
        signals = manual_signals(
            [Side.BUY, Side.HOLD, Side.BUY],
            [10, 0, 10],
            [101, 0, 101],
        )
        run = run_backtest(
            data,
            signals,
            RiskLimits(1_000, 10, 100, 10),
        )
        self.assertEqual(run.equity_half_cents[1], 0)
        self.assertEqual(run.accepted, 2)
        self.assertEqual(run.fills, 2)
        self.assertEqual(run.final_position, 20)
        self.assertEqual(run.total_pnl_half_cents, -40)
        self.assertEqual(run.max_in_flight, 2)

    def test_short_selling_and_rolling_one_second_boundary(self) -> None:
        data = snapshots(
            time_ns=[0, 500_000_000, 1_000_000_000],
            bid=[99, 99, 99],
            ask=[101, 101, 101],
        )
        signals = manual_signals(
            [Side.SELL, Side.SELL, Side.SELL],
            [1, 1, 1],
            [99, 99, 99],
        )
        run = run_backtest(
            data,
            signals,
            RiskLimits(1_000, 10, 2, 10),
        )
        self.assertEqual(run.accepted, 3)
        self.assertEqual(run.max_order_rate, 2)
        self.assertEqual(run.final_position, -3)


class MetricsTests(unittest.TestCase):
    def test_fixed_390_buckets_and_zero_fill(self) -> None:
        times = np.array(
            [SESSION_START_NS + 30_000_000_000, SESSION_START_NS + 90_000_000_000],
            dtype=np.int64,
        )
        equity = np.array([10, 25], dtype=np.int64)
        pnl = minute_pnl_buckets(times, equity)
        self.assertEqual(len(pnl), 390)
        self.assertEqual(pnl[:3].tolist(), [10, 15, 0])
        self.assertEqual(int(np.sum(pnl)), 25)

    def test_sample_sharpe_and_undefined_cases(self) -> None:
        pnl = np.zeros(390, dtype=np.int64)
        pnl[0] = 10
        expected = float(np.mean(pnl) / np.std(pnl, ddof=1) * ANNUALIZATION_FACTOR)
        self.assertAlmostEqual(annualized_sharpe(pnl, fills=1), expected)
        self.assertIsNone(annualized_sharpe(np.zeros(390), fills=1))
        self.assertIsNone(annualized_sharpe(pnl, fills=0))

    def test_tick_drawdown_catches_intraminute_low(self) -> None:
        self.assertEqual(maximum_drawdown(np.array([10, -15, 8])), 25)


class SweepTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = load_settings(
            ROOT / "eod_pipeline" / "config" / "eod_settings.json"
        )
        cls.data = snapshots(
            time_ns=[SESSION_START_NS, SESSION_START_NS + 60_000_000_000],
            bid=[99, 99],
            ask=[101, 101],
        )

    def test_default_grid_sizes_and_regime_mapping(self) -> None:
        self.assertEqual(len(parameter_grid("momentum", self.settings)), 27)
        self.assertEqual(len(parameter_grid("mean_reversion", self.settings)), 27)
        self.assertEqual(len(parameter_grid("defensive", self.settings)), 9)

    def test_all_null_defensive_uses_first_placeholder(self) -> None:
        result = run_sweep("volatile", self.settings, self.data)
        self.assertEqual(result["selection_status"], "NOT_OPTIMIZED")
        self.assertEqual(result["selection_reason"], "ALL_SHARPE_UNDEFINED")
        self.assertEqual(result["winner"]["candidate_index"], 0)
        self.assertIn("activity", result["winner"])
        self.assertIn("risk", result["winner"])
        self.assertEqual(
            result["winner"]["metrics"]["total_pnl_cad"],
            result["winner"]["metrics"]["total_pnl_half_cents"] / 200,
        )
        self.assertEqual(
            result["winner"]["metrics"]["max_drawdown_cad"],
            result["winner"]["metrics"]["max_drawdown_half_cents"] / 200,
        )
        self.assertEqual(len(result["results"]), 9)

    def test_equal_sharpe_keeps_dictionary_order_first(self) -> None:
        fixed = BacktestMetrics(
            sharpe=1.0,
            max_drawdown_half_cents=0,
            total_pnl_half_cents=0,
            minute_pnl_half_cents=np.zeros(390, dtype=np.int64),
        )
        with patch(
            "eod_pipeline.backtest.sweep.calculate_metrics",
            return_value=fixed,
        ):
            result = run_sweep("trending", self.settings, self.data)
        self.assertEqual(result["winner"]["candidate_index"], 0)
        self.assertEqual(result["selection_status"], "OPTIMIZED")

    def test_canonical_json_is_standard_and_repeatable(self) -> None:
        result = run_sweep("volatile", self.settings, self.data)
        first = canonical_json(result)
        second = canonical_json(result)
        self.assertEqual(first, second)
        self.assertEqual(json.loads(first), result)
        self.assertNotIn("NaN", first)
        self.assertNotIn("Infinity", first)

    def test_cli_accepts_print_winner(self) -> None:
        with patch(
            "sys.argv",
            [
                "run_sweep",
                "--regime",
                "trending",
                "--expected-book",
                "book.csv",
                "--timing",
                "timing.csv",
                "--print-winner",
            ],
        ):
            args = parse_args()
        self.assertTrue(args.print_winner)


if __name__ == "__main__":
    unittest.main()
