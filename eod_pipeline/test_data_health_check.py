"""Unit tests for the A.3 real-data health-check primitives."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from eod_pipeline.backtest.snapshots import load_snapshots
from eod_pipeline.settings import load_settings
from eod_pipeline.tools.data_health_check import (
    build_report,
    mean_reversion_deviation,
    momentum_ratio,
    rolling_peak,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SnapshotLoaderTests(unittest.TestCase):
    def test_loads_aligned_integer_arrays_and_ps_mid_convention(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            book = root / "book.csv"
            timing = root / "timing.csv"
            book.write_text(
                "seq,best_bid_cents,best_ask_cents\n"
                "1,100,102\n"
                "2,101,103\n",
                encoding="utf-8",
            )
            timing.write_text(
                "seq,time\n"
                "1.0,34200.000000001\n"
                "2.0,34200.000000003\n",
                encoding="utf-8",
            )

            snapshots = load_snapshots(book, timing)

            np.testing.assert_array_equal(snapshots.seq, [1, 2])
            np.testing.assert_array_equal(snapshots.mid_half_cents, [202, 204])
            np.testing.assert_array_equal(snapshots.spread_cents, [2, 2])
            self.assertEqual(snapshots.time_ns[1] - snapshots.time_ns[0], 2)
            self.assertEqual(snapshots.mid_half_cents.dtype, np.dtype(np.int64))

    def test_rejects_unmatched_sequences(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            book = root / "book.csv"
            timing = root / "timing.csv"
            book.write_text(
                "seq,best_bid_cents,best_ask_cents\n1,100,102\n",
                encoding="utf-8",
            )
            timing.write_text("seq,time\n2,34200\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "seq mismatch"):
                load_snapshots(book, timing)


class StrategyDiagnosticTests(unittest.TestCase):
    def test_momentum_uses_requested_message_lookback(self) -> None:
        mid = np.array([100, 102, 104, 108], dtype=np.int64)
        result = momentum_ratio(mid, lookback=2)
        expected = np.array([4 / 104, 6 / 108], dtype=np.float32)
        np.testing.assert_allclose(result, expected)

    def test_mean_reversion_average_excludes_current_tick(self) -> None:
        mid = np.array([100, 102, 104, 110], dtype=np.int64)
        result = mean_reversion_deviation(mid, window=2)
        expected = np.array([(104 - 101) / 101, (110 - 103) / 103])
        np.testing.assert_allclose(result, expected)

    def test_rolling_peak_is_not_tied_to_wall_clock_buckets(self) -> None:
        times = np.array([900_000_000, 1_000_000_000, 1_100_000_000], dtype=np.int64)
        self.assertEqual(rolling_peak(times, 300_000_000), 3)


class ConfiguredReportTests(unittest.TestCase):
    def test_report_records_settings_and_uses_configured_base_lot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            book = root / "book.csv"
            timing = root / "timing.csv"
            book_rows = ["seq,best_bid_cents,best_ask_cents"]
            timing_rows = ["seq,time"]
            for index in range(1, 101):
                book_rows.append(f"{index},{10_000 + index},{10_002 + index}")
                timing_rows.append(f"{index},{34_200 + index / 100}")
            book.write_text("\n".join(book_rows) + "\n", encoding="utf-8")
            timing.write_text("\n".join(timing_rows) + "\n", encoding="utf-8")

            settings = load_settings(
                PROJECT_ROOT / "eod_pipeline/config/eod_settings.json"
            )
            report = build_report(
                book,
                timing,
                settings,
                settings_path=Path("eod_pipeline/config/eod_settings.json"),
            )

            self.assertIn(f"`{settings.sha256()}`", report)
            self.assertIn("`base_lot=50`", report)
            self.assertIn("eod_pipeline/config/eod_settings.json", report)


if __name__ == "__main__":
    unittest.main()
