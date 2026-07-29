"""Fixed-order parameter sweep and deterministic result serialization."""

from __future__ import annotations

from hashlib import sha256
from itertools import product
import json
from pathlib import Path
from typing import Any

from eod_pipeline.backtest.engine import run_backtest
from eod_pipeline.backtest.metrics import calculate_metrics
from eod_pipeline.backtest.snapshots import SnapshotArrays
from eod_pipeline.backtest.strategies import build_signals
from eod_pipeline.settings import EODSettings


SCHEMA_VERSION = 1
CODE_VERSION = "deterministic-backtest-v1"
REGIME_STRATEGY = {
    "trending": "momentum",
    "ranging": "mean_reversion",
    "volatile": "defensive",
}
PS_DIFFERENCES = [
    "MEAN_REVERSION_AGGRESSIVE_PRICE",
    "MARKET_TIME_FILL_DELAY",
    "EOD_ENFORCES_ORDER_RATE",
    "HOLD_LATCH_NOT_SIMULATED",
    "IN_FLIGHT_EXCLUDED_FROM_POSITION_RISK",
]


def file_sha256(path: str | Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parameter_grid(strategy_id: str, settings: EODSettings) -> list[dict[str, Any]]:
    """Build candidates in the declared configuration-array order."""

    if strategy_id == "momentum":
        return [
            {
                "lookback": lookback,
                "entry_thresh": entry_thresh,
                "pos_scalar": pos_scalar,
            }
            for lookback, entry_thresh, pos_scalar in product(
                settings.momentum.lookback,
                settings.momentum.entry_thresh,
                settings.momentum.pos_scalar,
            )
        ]
    if strategy_id == "mean_reversion":
        return [
            {
                "window": window,
                "dev_thresh": dev_thresh,
                "pos_scalar": pos_scalar,
            }
            for window, dev_thresh, pos_scalar in product(
                settings.mean_reversion.window,
                settings.mean_reversion.dev_thresh,
                settings.mean_reversion.pos_scalar,
            )
        ]
    if strategy_id == "defensive":
        return [
            {
                "spread_floor": spread_floor,
                "pos_scalar": pos_scalar,
            }
            for spread_floor, pos_scalar in product(
                settings.defensive.spread_floor,
                settings.defensive.pos_scalar,
            )
        ]
    raise ValueError(f"unknown strategy_id '{strategy_id}'")


def run_sweep(
    regime: str,
    settings: EODSettings,
    snapshots: SnapshotArrays,
    *,
    source_hashes: dict[str, str] | None = None,
) -> dict[str, Any]:
    regime = regime.lower()
    if regime not in REGIME_STRATEGY:
        raise ValueError(f"unknown regime '{regime}'")
    strategy_id = REGIME_STRATEGY[regime]
    candidates = parameter_grid(strategy_id, settings)
    results: list[dict[str, Any]] = []

    winner_index: int | None = None
    winner_sharpe: float | None = None
    for candidate_index, parameters in enumerate(candidates):
        signals = build_signals(
            strategy_id,
            snapshots,
            parameters,
            settings.base_lot,
        )
        run = run_backtest(snapshots, signals, settings.risk_limits)
        metrics = calculate_metrics(run)
        result = {
            "candidate_index": candidate_index,
            "parameters": parameters,
            "metrics": {
                "sharpe": metrics.sharpe,
                "max_drawdown_half_cents": metrics.max_drawdown_half_cents,
                "total_pnl_half_cents": metrics.total_pnl_half_cents,
            },
            "activity": {
                "signals": run.signals,
                "accepted": run.accepted,
                "rejected": run.rejected,
                "fills": run.fills,
            },
            "risk": {
                "rejection_counts": run.rejection_counts,
                "actual_maxima": {
                    "max_abs_position_shares": run.max_abs_position,
                    "max_in_flight": run.max_in_flight,
                    "max_order_rate_per_second": run.max_order_rate,
                    "max_order_notional_cad": run.max_order_notional_cad,
                },
            },
            "final_state": {
                "cash_cents": run.final_cash_cents,
                "position_shares": run.final_position,
            },
        }
        results.append(result)
        if metrics.sharpe is not None and (
            winner_sharpe is None or metrics.sharpe > winner_sharpe
        ):
            winner_index = candidate_index
            winner_sharpe = metrics.sharpe

    if winner_index is None:
        winner_index = 0
        selection_status = "NOT_OPTIMIZED"
        selection_reason = "ALL_SHARPE_UNDEFINED"
        warnings = [
            "No candidate had a defined Sharpe ratio; candidate 0 is a "
            "deterministic placeholder, not an optimized winner."
        ]
    else:
        selection_status = "OPTIMIZED"
        selection_reason = "HIGHEST_SHARPE"
        warnings = []

    winner_result = results[winner_index]
    winner_metrics = {
        **winner_result["metrics"],
        "max_drawdown_cad": (
            winner_result["metrics"]["max_drawdown_half_cents"] / 200
        ),
        "total_pnl_cad": winner_result["metrics"]["total_pnl_half_cents"] / 200,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "code_version": CODE_VERSION,
        "regime": regime,
        "strategy_id": strategy_id,
        "selection_status": selection_status,
        "selection_reason": selection_reason,
        "warnings": warnings,
        "winner": {
            **winner_result,
            "metrics": winner_metrics,
        },
        "results": results,
        "metric_definitions": {
            "sharpe": {
                "buckets": 390,
                "bucket_size": "1 minute",
                "empty_bucket_pnl": 0,
                "standard_deviation_ddof": 1,
                "annualization": "sqrt(252*390)",
                "undefined_when": ["fills=0", "sample_std=0"],
            },
            "maximum_drawdown": "tick-level mark-to-market equity",
            "pnl_unit": "half-cent",
        },
        "assumptions": {
            "fill_delay_ms": 100,
            "fill_model": "unconditional_at_submission_price",
            "end_of_day": "settle_all_in_flight_then_mark_at_last_mid",
            "fees_and_extra_slippage": 0,
            "price_currency_conversion": "USD treated as CAD 1:1",
            "short_selling": True,
        },
        "ps_differences": PS_DIFFERENCES,
        "provenance": {
            "settings_sha256": settings.sha256(),
            "source_sha256": dict(sorted((source_hashes or {}).items())),
            "snapshot_rows": len(snapshots),
        },
    }


def canonical_json(result: dict[str, Any]) -> str:
    return json.dumps(
        result,
        sort_keys=True,
        indent=2,
        ensure_ascii=True,
        allow_nan=False,
    ) + "\n"


def write_sweep_result(result: dict[str, Any], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(canonical_json(result), encoding="utf-8")
