"""Approval contract, review gate, and PS integration tests."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from eod_pipeline.approval.config import (
    ApprovalError,
    build_candidate_config,
    pretty_json,
    validate_sweep_result,
)
from eod_pipeline.approval.review import (
    resolve_review_thresholds,
    review_winner,
)
from eod_pipeline.approval.workflow import run_approval_workflow
from eod_pipeline.run_approval import parse_args
from eod_pipeline.settings import load_settings
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SETTINGS_PATH = PROJECT_ROOT / "eod_pipeline/config/eod_settings.json"
PS_DIR = PROJECT_ROOT / "ps_trade_core_logic"
FIXED_TIME = datetime(2026, 7, 29, 22, 0, 0, tzinfo=timezone.utc)


def make_result(settings, strategy_id: str = "momentum", *, optimized: bool = True):
    regime_by_strategy = {
        "momentum": "trending",
        "mean_reversion": "ranging",
        "defensive": "volatile",
    }
    parameters_by_strategy = {
        "momentum": {"lookback": 5, "entry_thresh": 0.0005, "pos_scalar": 1.5},
        "mean_reversion": {"window": 20, "dev_thresh": 0.0003, "pos_scalar": 1.0},
        "defensive": {"spread_floor": 2, "pos_scalar": 0.5},
    }
    metrics = {
        "sharpe": 2.5 if optimized else None,
        "max_drawdown_half_cents": 200_000,
        "max_drawdown_cad": 1_000.0,
        "total_pnl_half_cents": 400_000,
        "total_pnl_cad": 2_000.0,
    }
    candidate = {
        "candidate_index": 0,
        "parameters": parameters_by_strategy[strategy_id],
        "metrics": {
            "sharpe": metrics["sharpe"],
            "max_drawdown_half_cents": metrics["max_drawdown_half_cents"],
            "total_pnl_half_cents": metrics["total_pnl_half_cents"],
        },
        "activity": {"signals": 20, "accepted": 20, "rejected": 0, "fills": 20},
        "risk": {
            "actual_maxima": {
                "max_abs_position_shares": 100,
                "max_in_flight": 2,
                "max_order_notional_cad": 10_000,
                "max_order_rate_per_second": 2,
            },
            "rejection_counts": {
                "IN_FLIGHT": 0,
                "NOTIONAL": 0,
                "ORDER_RATE": 0,
                "POSITION": 0,
            },
        },
        "final_state": {"cash_cents": 0, "position_shares": 0},
    }
    winner = copy.deepcopy(candidate)
    winner["metrics"] = metrics
    candidate_count = 9 if strategy_id == "defensive" else 27
    results = []
    for candidate_index in range(candidate_count):
        item = copy.deepcopy(candidate)
        item["candidate_index"] = candidate_index
        results.append(item)
    return {
        "schema_version": 1,
        "code_version": "deterministic-backtest-v1",
        "regime": regime_by_strategy[strategy_id],
        "strategy_id": strategy_id,
        "selection_status": "OPTIMIZED" if optimized else "NOT_OPTIMIZED",
        "selection_reason": (
            "HIGHEST_SHARPE" if optimized else "ALL_SHARPE_UNDEFINED"
        ),
        "warnings": [] if optimized else ["placeholder"],
        "winner": winner,
        "results": results,
        "provenance": {
            "settings_sha256": settings.sha256(),
            "source_sha256": {"book": "abc"},
        },
        "ps_differences": ["MARKET_TIME_FILL_DELAY"],
    }


class FakeSender:
    def __init__(self) -> None:
        self.paths: list[Path] = []

    def send(self, approved_config_path: Path) -> dict[str, str]:
        self.paths.append(approved_config_path)
        return {"transport": "fake", "status": "ok"}


class InputSequence:
    def __init__(self, values: list[str]) -> None:
        self.values = iter(values)

    def __call__(self, prompt: str) -> str:
        del prompt
        try:
            return next(self.values)
        except StopIteration as error:
            raise AssertionError("workflow requested unexpected input") from error


def eof_input(prompt: str) -> str:
    del prompt
    raise EOFError


class ConfigContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = load_settings(SETTINGS_PATH)

    def build(self, strategy_id: str):
        result = make_result(self.settings, strategy_id)
        return build_candidate_config(
            result,
            self.settings,
            sweep_result_sha256="f" * 64,
            review_thresholds={
                "max_drawdown_warning_cad": 25_000.0,
                "min_trades": 10,
                "sources": {
                    "max_drawdown_warning_cad": "settings",
                    "min_trades": "settings",
                },
            },
        )

    def test_all_strategies_emit_complete_ps_parameters(self) -> None:
        for strategy_id in ("momentum", "mean_reversion", "defensive"):
            with self.subTest(strategy_id=strategy_id):
                config = self.build(strategy_id)
                self.assertEqual(
                    set(config["parameters"]),
                    {
                        "lookback",
                        "window",
                        "entry_thresh",
                        "dev_thresh",
                        "spread_floor",
                        "base_lot",
                        "pos_scalar",
                    },
                )
                self.assertEqual(config["parameters"]["base_lot"], 50)
                self.assertEqual(config["parameters"]["lookback"], 5)
                self.assertEqual(
                    config["parameters"]["window"],
                    20 if strategy_id == "mean_reversion" else 10,
                )
                self.assertEqual(config["risk_limits"]["max_in_flight"], 100)
                self.assertEqual(
                    config["provenance"]["backtest_code_version"],
                    "deterministic-backtest-v1",
                )
                self.assertEqual(
                    config["provenance"]["approval_pipeline_version"],
                    "approval-pipeline-v1",
                )
                self.assertNotIn("approval", config)

    def test_active_values_override_inactive_defaults(self) -> None:
        config = self.build("mean_reversion")
        self.assertEqual(config["parameters"]["window"], 20)
        self.assertEqual(config["parameters"]["dev_thresh"], 0.0003)
        self.assertEqual(config["parameters"]["lookback"], 5)

    def test_hash_and_regime_mismatches_are_rejected(self) -> None:
        bad_hash = make_result(self.settings)
        bad_hash["provenance"]["settings_sha256"] = "bad"
        with self.assertRaisesRegex(ApprovalError, "settings hash mismatch"):
            validate_sweep_result(bad_hash, self.settings)

        bad_regime = make_result(self.settings)
        bad_regime["strategy_id"] = "defensive"
        with self.assertRaisesRegex(ApprovalError, "do not match"):
            validate_sweep_result(bad_regime, self.settings)

    def test_candidate_serialization_is_deterministic(self) -> None:
        config = self.build("momentum")
        self.assertEqual(pretty_json(config), pretty_json(copy.deepcopy(config)))
        self.assertNotIn("NaN", pretty_json(config))


class ReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = load_settings(SETTINGS_PATH)

    def test_config_and_cli_threshold_sources(self) -> None:
        configured = resolve_review_thresholds(self.settings)
        self.assertEqual(configured.max_drawdown_warning_cad, 25_000)
        self.assertEqual(configured.sources["min_trades"], "settings")

        overridden = resolve_review_thresholds(
            self.settings,
            max_drawdown_warning_cad=500,
            min_trades=25,
        )
        self.assertEqual(overridden.max_drawdown_warning_cad, 500)
        self.assertEqual(overridden.min_trades, 25)
        self.assertEqual(
            set(overridden.sources.values()),
            {"cli_override"},
        )

    def test_review_reports_rejections_actual_breaches_drawdown_and_trades(self) -> None:
        result = make_result(self.settings)
        result["winner"]["risk"]["rejection_counts"]["POSITION"] = 3
        maxima = result["winner"]["risk"]["actual_maxima"]
        maxima.update(
            {
                "max_abs_position_shares": 1001,
                "max_in_flight": 101,
                "max_order_notional_cad": 50_001,
                "max_order_rate_per_second": 1001,
            }
        )
        result["winner"]["metrics"]["max_drawdown_cad"] = 30_000
        result["winner"]["activity"]["fills"] = 3
        codes = {
            finding["code"]
            for finding in review_winner(
                result,
                self.settings,
                resolve_review_thresholds(self.settings),
            )
        }
        self.assertEqual(
            codes,
            {
                "RISK_ATTEMPTS_REJECTED",
                "ACTUAL_NOTIONAL_EXCEEDED",
                "ACTUAL_POSITION_EXCEEDED",
                "ACTUAL_ORDER_RATE_EXCEEDED",
                "ACTUAL_IN_FLIGHT_EXCEEDED",
                "MAX_DRAWDOWN_HIGH",
                "TRADE_COUNT_LOW",
            },
        )


class WorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = load_settings(SETTINGS_PATH)

    def run_workflow(
        self,
        result,
        answers: list[str],
        sender: FakeSender,
        directory: str,
        **overrides,
    ):
        sweep_path = Path(directory) / "sweep.json"
        sweep_path.write_text(pretty_json(result), encoding="utf-8")
        return run_approval_workflow(
            sweep_result_path=sweep_path,
            settings_path=SETTINGS_PATH,
            output_root=Path(directory) / "approval_runs",
            operator_id="hanyu.test",
            sender=sender,
            input_fn=InputSequence(answers),
            output_fn=lambda message: None,
            clock=lambda: FIXED_TIME,
            **overrides,
        )

    def test_warning_ack_then_approve_calls_sender_once(self) -> None:
        result = make_result(self.settings)
        low_activity = {"signals": 3, "accepted": 3, "rejected": 0, "fills": 3}
        result["winner"]["activity"] = low_activity
        result["results"][0]["activity"] = copy.deepcopy(low_activity)
        sender = FakeSender()
        with tempfile.TemporaryDirectory() as directory:
            outcome = self.run_workflow(
                result,
                ["ACKNOWLEDGE WARNINGS", "APPROVE"],
                sender,
                directory,
            )
            self.assertEqual(outcome.approval_status, "APPROVED")
            self.assertEqual(outcome.dispatch_status, "SENT")
            self.assertEqual(len(sender.paths), 1)
            approved = json.loads(
                outcome.approved_config_path.read_text(encoding="utf-8")
            )
            self.assertEqual(
                set(approved["approval"]),
                {"operator_id", "timestamp"},
            )
            self.assertTrue(outcome.report_markdown_path.exists())
            stages = [
                json.loads(line)
                for line in (outcome.run_directory / "stage_log.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(len(stages), 12)
            self.assertTrue(
                (Path(directory) / "approval_runs/latest_run.json").exists()
            )

    def test_no_warning_approves_without_acknowledgement(self) -> None:
        sender = FakeSender()
        with tempfile.TemporaryDirectory() as directory:
            outcome = self.run_workflow(
                make_result(self.settings),
                ["APPROVE"],
                sender,
                directory,
            )
        self.assertEqual(outcome.approval_status, "APPROVED")
        self.assertEqual(len(sender.paths), 1)

    def test_not_optimized_override_covers_warnings(self) -> None:
        sender = FakeSender()
        with tempfile.TemporaryDirectory() as directory:
            outcome = self.run_workflow(
                make_result(self.settings, "defensive", optimized=False),
                ["OVERRIDE NOT_OPTIMIZED", "APPROVE"],
                sender,
                directory,
            )
        self.assertEqual(outcome.approval_status, "APPROVED")
        self.assertEqual(len(sender.paths), 1)

    def test_missing_override_never_calls_sender(self) -> None:
        sender = FakeSender()
        with tempfile.TemporaryDirectory() as directory:
            outcome = self.run_workflow(
                make_result(self.settings, "defensive", optimized=False),
                ["APPROVE"],
                sender,
                directory,
            )
            self.assertEqual(outcome.approval_status, "NO_APPROVAL")
            self.assertIsNone(outcome.approved_config_path)
            self.assertTrue(outcome.rejection_record_path.exists())
        self.assertEqual(sender.paths, [])

    def test_eof_records_no_approval_and_never_calls_sender(self) -> None:
        sender = FakeSender()
        with tempfile.TemporaryDirectory() as directory:
            result = make_result(self.settings)
            sweep_path = Path(directory) / "sweep.json"
            sweep_path.write_text(pretty_json(result), encoding="utf-8")
            outcome = run_approval_workflow(
                sweep_result_path=sweep_path,
                settings_path=SETTINGS_PATH,
                output_root=Path(directory) / "approval_runs",
                operator_id="hanyu.test",
                sender=sender,
                input_fn=eof_input,
                output_fn=lambda message: None,
                clock=lambda: FIXED_TIME,
            )
            rejection = json.loads(
                outcome.rejection_record_path.read_text(encoding="utf-8")
            )
        self.assertEqual(outcome.approval_status, "NO_APPROVAL")
        self.assertIn("EOF", rejection["reason"])
        self.assertEqual(sender.paths, [])

    def test_reject_requires_nonempty_reason_and_never_calls_sender(self) -> None:
        sender = FakeSender()
        with tempfile.TemporaryDirectory() as directory:
            outcome = self.run_workflow(
                make_result(self.settings),
                ["REJECT", "", "insufficient evidence"],
                sender,
                directory,
            )
            rejection = json.loads(
                outcome.rejection_record_path.read_text(encoding="utf-8")
            )
            self.assertEqual(rejection["status"], "REJECTED")
            self.assertEqual(rejection["reason"], "insufficient evidence")
        self.assertEqual(sender.paths, [])

    def test_cli_threshold_overrides_parse(self) -> None:
        with patch(
            "sys.argv",
            [
                "run_approval",
                "--operator-id",
                "hanyu",
                "--max-drawdown-warning-cad",
                "1000.5",
                "--min-trades",
                "20",
            ],
        ):
            args = parse_args()
        self.assertEqual(args.max_drawdown_warning_cad, 1000.5)
        self.assertEqual(args.min_trades, 20)
        self.assertEqual(args.output_root.name, "approval_runs")


class PSLoaderContractTests(unittest.TestCase):
    def test_generated_config_is_accepted_by_real_c_loader(self) -> None:
        compiler = shutil.which("cc")
        if compiler is None:
            self.skipTest("C compiler is unavailable")
        settings = load_settings(SETTINGS_PATH)
        config = build_candidate_config(
            make_result(settings),
            settings,
            sweep_result_sha256="a" * 64,
            review_thresholds=resolve_review_thresholds(settings).to_dict(),
        )
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            config_path = directory_path / "approved_config.json"
            config["approval"] = {
                "operator_id": "contract-test",
                "timestamp": "2026-07-29T22:00:00.000Z",
            }
            config_path.write_text(pretty_json(config), encoding="utf-8")
            harness_path = directory_path / "harness.c"
            harness_path.write_text(
                """
#include "config_loader.h"
#include <stdio.h>
int main(void) {
    StrategyParams s = get_strategy_params_from_config();
    RiskParams r = get_risk_params_from_config();
    printf("%d %d %d %d %u\\n", get_active_strategy_id_from_config(),
           s.lookback_ticks, s.window, s.base_lot, r.max_in_flight_orders);
    return 0;
}
""",
                encoding="utf-8",
            )
            executable = directory_path / "loader_contract"
            compile_result = subprocess.run(
                [
                    compiler,
                    "-std=c11",
                    f"-I{PS_DIR}",
                    f'-DCONFIG_PATH="{config_path}"',
                    str(harness_path),
                    str(PS_DIR / "config_loader.c"),
                    "-o",
                    str(executable),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            run_result = subprocess.run(
                [str(executable)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(run_result.returncode, 0, run_result.stderr)
            self.assertIn("0 5 10 50 100", run_result.stdout)


if __name__ == "__main__":
    unittest.main()
