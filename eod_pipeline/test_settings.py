"""Contract and validation tests for EOD settings."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import tempfile
import unittest

from eod_pipeline.settings import (
    EODSettings,
    HARD_SAFETY_LIMITS,
    SettingsError,
    load_settings,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SETTINGS = PROJECT_ROOT / "eod_pipeline/config/eod_settings.json"
SAFETY_HEADER = PROJECT_ROOT / "ps_trade_core_logic/safety_limits.h"


class SettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.valid = json.loads(DEFAULT_SETTINGS.read_text(encoding="utf-8"))

    def load_dict(self, value: dict) -> EODSettings:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            return load_settings(path)

    def assert_invalid(self, value: dict, message: str) -> None:
        with self.assertRaisesRegex(SettingsError, message):
            self.load_dict(value)

    def test_loads_default_and_hashes_canonical_content(self) -> None:
        settings = load_settings(DEFAULT_SETTINGS)
        rewritten = self.load_dict(
            json.loads(json.dumps(self.valid, sort_keys=True))
        )

        self.assertEqual(settings.base_lot, 50)
        self.assertEqual(settings.momentum.entry_thresh, (0.0003, 0.0004, 0.0005))
        self.assertEqual(
            settings.review_thresholds.max_drawdown_warning_cad,
            25_000,
        )
        self.assertEqual(settings.review_thresholds.min_trades, 10)
        self.assertEqual(settings.sha256(), rewritten.sha256())
        self.assertEqual(len(settings.sha256()), 64)

    def test_rejects_missing_and_unknown_fields(self) -> None:
        missing = copy.deepcopy(self.valid)
        del missing["base_lot"]
        self.assert_invalid(missing, "missing required keys")

        unknown = copy.deepcopy(self.valid)
        unknown["new_option"] = 1
        self.assert_invalid(unknown, "unknown keys")

    def test_rejects_duplicate_json_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text(
                '{"schema_version":1,"schema_version":1}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(SettingsError, "duplicate key"):
                load_settings(path)

    def test_rejects_invalid_candidate_arrays(self) -> None:
        duplicate = copy.deepcopy(self.valid)
        duplicate["strategy_grids"]["momentum"]["entry_thresh"] = [0.0003, 0.0003]
        self.assert_invalid(duplicate, "must not contain duplicates")

        non_positive = copy.deepcopy(self.valid)
        non_positive["strategy_grids"]["mean_reversion"]["dev_thresh"] = [0]
        self.assert_invalid(non_positive, "finite and positive")

        empty = copy.deepcopy(self.valid)
        empty["strategy_grids"]["defensive"]["spread_floor"] = []
        self.assert_invalid(empty, "non-empty array")

    def test_rejects_window_outside_ring_buffer(self) -> None:
        invalid = copy.deepcopy(self.valid)
        invalid["strategy_grids"]["mean_reversion"]["window"] = [64]
        self.assert_invalid(invalid, "exceeds hard maximum 63")

    def test_rejects_fractional_share_quantities(self) -> None:
        invalid = copy.deepcopy(self.valid)
        invalid["strategy_grids"]["momentum"]["pos_scalar"] = [0.333]
        self.assert_invalid(invalid, "must produce whole shares")

    def test_each_risk_limit_can_tighten_but_not_exceed_hard_cap(self) -> None:
        for key, maximum in HARD_SAFETY_LIMITS.items():
            with self.subTest(key=key):
                tighter = copy.deepcopy(self.valid)
                tighter["risk_limits"][key] = maximum - 1
                self.load_dict(tighter)

                excessive = copy.deepcopy(self.valid)
                excessive["risk_limits"][key] = maximum + 1
                self.assert_invalid(excessive, "exceeds hard maximum")

    def test_rejects_invalid_review_thresholds(self) -> None:
        bad_drawdown = copy.deepcopy(self.valid)
        bad_drawdown["review_thresholds"]["max_drawdown_warning_cad"] = 0
        self.assert_invalid(bad_drawdown, "finite and positive")

        bad_trades = copy.deepcopy(self.valid)
        bad_trades["review_thresholds"]["min_trades"] = 1.5
        self.assert_invalid(bad_trades, "must be an integer")

    def test_python_limits_match_c_header(self) -> None:
        header = SAFETY_HEADER.read_text(encoding="utf-8")
        macro_by_key = {
            "max_notional_cad": "FS3_MAX_NOTIONAL_CAD",
            "max_position_shares": "FS3_MAX_POSITION_SHARES",
            "max_order_rate": "FS3_MAX_ORDER_RATE",
            "max_in_flight": "FS3_MAX_IN_FLIGHT",
        }
        for key, macro in macro_by_key.items():
            with self.subTest(key=key):
                match = re.search(
                    rf"^#define\s+{macro}\s+(\d+)u\s*$",
                    header,
                    flags=re.MULTILINE,
                )
                self.assertIsNotNone(match, f"missing {macro} in safety_limits.h")
                self.assertEqual(int(match.group(1)), HARD_SAFETY_LIMITS[key])


if __name__ == "__main__":
    unittest.main()
