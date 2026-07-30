"""Strict sweep-result validation and PS-compatible candidate generation."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from eod_pipeline.backtest.sweep import REGIME_STRATEGY
from eod_pipeline.settings import EODSettings


APPROVAL_SCHEMA_VERSION = 1
APPROVAL_PIPELINE_VERSION = "approval-pipeline-v1"
VALID_SELECTION_STATUSES = {"OPTIMIZED", "NOT_OPTIMIZED"}


class ApprovalError(ValueError):
    """Raised when approval cannot safely consume or emit a configuration."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ApprovalError(f"duplicate JSON key '{key}'")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ApprovalError(f"non-standard JSON number '{value}' is not allowed")


def _require_dict(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ApprovalError(f"{path} must be an object")
    return value


def _require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ApprovalError(f"{path} must be an array")
    return value


def _require_keys(value: dict[str, Any], required: set[str], path: str) -> None:
    missing = sorted(required - set(value))
    if missing:
        raise ApprovalError(f"{path} missing required keys: {missing}")


def _require_nonnegative_int(value: Any, path: str) -> int:
    if type(value) is not int or value < 0:
        raise ApprovalError(f"{path} must be a non-negative integer")
    return value


def _require_finite_number(value: Any, path: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ApprovalError(f"{path} must be a finite number")
    return float(value)


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_sweep_result(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    try:
        result = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except OSError as error:
        raise ApprovalError(f"could not read sweep result {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise ApprovalError(f"invalid sweep result JSON: {error}") from error
    return _require_dict(result, "sweep_result")


def validate_sweep_result(result: dict[str, Any], settings: EODSettings) -> None:
    _require_keys(
        result,
        {
            "schema_version",
            "code_version",
            "regime",
            "strategy_id",
            "selection_status",
            "selection_reason",
            "warnings",
            "winner",
            "results",
            "provenance",
            "ps_differences",
        },
        "sweep_result",
    )
    if result["schema_version"] != 1:
        raise ApprovalError("unsupported parameter-sweep schema_version")

    regime = result["regime"]
    strategy_id = result["strategy_id"]
    if not isinstance(regime, str) or regime not in REGIME_STRATEGY:
        raise ApprovalError("invalid sweep regime")
    if strategy_id != REGIME_STRATEGY[regime]:
        raise ApprovalError("sweep regime and strategy_id do not match")

    status = result["selection_status"]
    if status not in VALID_SELECTION_STATUSES:
        raise ApprovalError(f"unknown selection_status '{status}'")
    if not isinstance(result["selection_reason"], str):
        raise ApprovalError("selection_reason must be a string")
    _require_list(result["warnings"], "warnings")
    _require_list(result["ps_differences"], "ps_differences")

    provenance = _require_dict(result["provenance"], "provenance")
    if provenance.get("settings_sha256") != settings.sha256():
        raise ApprovalError(
            "settings hash mismatch; regenerate the sweep with the supplied settings"
        )

    results = _require_list(result["results"], "results")
    if not results:
        raise ApprovalError("sweep results cannot be empty")
    expected_count = {
        "momentum": (
            len(settings.momentum.lookback)
            * len(settings.momentum.entry_thresh)
            * len(settings.momentum.pos_scalar)
        ),
        "mean_reversion": (
            len(settings.mean_reversion.window)
            * len(settings.mean_reversion.dev_thresh)
            * len(settings.mean_reversion.pos_scalar)
        ),
        "defensive": (
            len(settings.defensive.spread_floor)
            * len(settings.defensive.pos_scalar)
        ),
    }[strategy_id]
    if len(results) != expected_count:
        raise ApprovalError(
            f"sweep result count {len(results)} does not match expected {expected_count}"
        )
    for result_index, candidate in enumerate(results):
        candidate = _require_dict(candidate, f"results[{result_index}]")
        if candidate.get("candidate_index") != result_index:
            raise ApprovalError("sweep candidate indexes must be contiguous and ordered")

    winner = _require_dict(result["winner"], "winner")
    _require_keys(
        winner,
        {
            "candidate_index",
            "parameters",
            "metrics",
            "activity",
            "risk",
            "final_state",
        },
        "winner",
    )
    index = winner["candidate_index"]
    if type(index) is not int or not 0 <= index < len(results):
        raise ApprovalError("winner candidate_index is out of range")
    selected = _require_dict(results[index], f"results[{index}]")
    for key in ("candidate_index", "parameters", "activity", "risk", "final_state"):
        if winner[key] != selected.get(key):
            raise ApprovalError(f"winner.{key} does not match results[{index}]")

    winner_metrics = _require_dict(winner["metrics"], "winner.metrics")
    selected_metrics = _require_dict(selected.get("metrics"), f"results[{index}].metrics")
    for key in ("sharpe", "max_drawdown_half_cents", "total_pnl_half_cents"):
        if winner_metrics.get(key) != selected_metrics.get(key):
            raise ApprovalError(f"winner.metrics.{key} does not match results[{index}]")

    sharpe = winner_metrics.get("sharpe")
    if sharpe is not None and (
        isinstance(sharpe, bool)
        or not isinstance(sharpe, (int, float))
        or not math.isfinite(float(sharpe))
    ):
        raise ApprovalError("winner Sharpe must be finite or null")
    if status == "OPTIMIZED" and sharpe is None:
        raise ApprovalError("OPTIMIZED winner must have a defined Sharpe")
    if status == "NOT_OPTIMIZED" and result["selection_reason"] != "ALL_SHARPE_UNDEFINED":
        raise ApprovalError("NOT_OPTIMIZED must use ALL_SHARPE_UNDEFINED reason")

    _require_finite_number(
        winner_metrics.get("max_drawdown_cad"),
        "winner.metrics.max_drawdown_cad",
    )
    _require_nonnegative_int(
        winner_metrics.get("max_drawdown_half_cents"),
        "winner.metrics.max_drawdown_half_cents",
    )
    if (
        winner_metrics["max_drawdown_cad"]
        != winner_metrics["max_drawdown_half_cents"] / 200
    ):
        raise ApprovalError("winner max drawdown units are inconsistent")

    activity = _require_dict(winner["activity"], "winner.activity")
    for key in ("signals", "accepted", "rejected", "fills"):
        _require_nonnegative_int(activity.get(key), f"winner.activity.{key}")
    if activity["accepted"] + activity["rejected"] != activity["signals"]:
        raise ApprovalError("winner activity counts are inconsistent")
    if activity["fills"] != activity["accepted"]:
        raise ApprovalError("all accepted backtest orders must settle by end of day")

    risk = _require_dict(winner["risk"], "winner.risk")
    maxima = _require_dict(risk.get("actual_maxima"), "winner.risk.actual_maxima")
    for key in (
        "max_abs_position_shares",
        "max_in_flight",
        "max_order_notional_cad",
        "max_order_rate_per_second",
    ):
        _require_nonnegative_int(maxima.get(key), f"winner.risk.actual_maxima.{key}")
    rejection_counts = _require_dict(
        risk.get("rejection_counts"),
        "winner.risk.rejection_counts",
    )
    if set(rejection_counts) != {"IN_FLIGHT", "NOTIONAL", "ORDER_RATE", "POSITION"}:
        raise ApprovalError("winner risk rejection reason set is invalid")
    for key, value in rejection_counts.items():
        _require_nonnegative_int(value, f"winner.risk.rejection_counts.{key}")


def _parameters_for_ps(
    strategy_id: str,
    winner_parameters: dict[str, Any],
    settings: EODSettings,
) -> dict[str, Any]:
    expected_by_strategy = {
        "momentum": {"lookback", "entry_thresh", "pos_scalar"},
        "mean_reversion": {"window", "dev_thresh", "pos_scalar"},
        "defensive": {"spread_floor", "pos_scalar"},
    }
    if set(winner_parameters) != expected_by_strategy[strategy_id]:
        raise ApprovalError(
            f"winner parameters do not match {strategy_id} strategy contract"
        )
    configured_values = {
        "momentum": {
            "lookback": settings.momentum.lookback,
            "entry_thresh": settings.momentum.entry_thresh,
            "pos_scalar": settings.momentum.pos_scalar,
        },
        "mean_reversion": {
            "window": settings.mean_reversion.window,
            "dev_thresh": settings.mean_reversion.dev_thresh,
            "pos_scalar": settings.mean_reversion.pos_scalar,
        },
        "defensive": {
            "spread_floor": settings.defensive.spread_floor,
            "pos_scalar": settings.defensive.pos_scalar,
        },
    }[strategy_id]
    for key, allowed in configured_values.items():
        if winner_parameters[key] not in allowed:
            raise ApprovalError(
                f"winner parameter {key}={winner_parameters[key]} is not in settings grid"
            )
    parameters: dict[str, Any] = {
        "lookback": settings.momentum.lookback[0],
        "window": settings.mean_reversion.window[0],
        "entry_thresh": settings.momentum.entry_thresh[0],
        "dev_thresh": settings.mean_reversion.dev_thresh[0],
        "spread_floor": settings.defensive.spread_floor[0],
        "base_lot": settings.base_lot,
        "pos_scalar": winner_parameters["pos_scalar"],
    }
    parameters.update(winner_parameters)
    return parameters


def build_candidate_config(
    result: dict[str, Any],
    settings: EODSettings,
    *,
    sweep_result_sha256: str,
    review_thresholds: dict[str, Any],
) -> dict[str, Any]:
    validate_sweep_result(result, settings)
    winner = result["winner"]
    parameters = _parameters_for_ps(
        result["strategy_id"],
        _require_dict(winner["parameters"], "winner.parameters"),
        settings,
    )
    limits = settings.risk_limits
    return {
        "schema_version": APPROVAL_SCHEMA_VERSION,
        "strategy_id": result["strategy_id"],
        "regime_label": result["regime"],
        "parameters": parameters,
        "risk_limits": {
            "max_notional_cad": limits.max_notional_cad,
            "max_position_shares": limits.max_position_shares,
            "max_order_rate": limits.max_order_rate,
            "max_in_flight": limits.max_in_flight,
        },
        "provenance": {
            "backtest_code_version": result["code_version"],
            "approval_pipeline_version": APPROVAL_PIPELINE_VERSION,
            "backtest_sharpe": winner["metrics"]["sharpe"],
            "review_thresholds": review_thresholds,
            "selection_reason": result["selection_reason"],
            "selection_status": result["selection_status"],
            "settings_sha256": settings.sha256(),
            "source_sha256": result["provenance"].get("source_sha256", {}),
            "sweep_result_sha256": sweep_result_sha256,
            "winner_candidate_index": winner["candidate_index"],
        },
    }


def approved_config(
    candidate: dict[str, Any],
    *,
    operator_id: str,
    timestamp: str,
) -> dict[str, Any]:
    if "approval" in candidate:
        raise ApprovalError("candidate config already contains approval")
    return {
        **candidate,
        "approval": {
            "operator_id": operator_id,
            "timestamp": timestamp,
        },
    }


def pretty_json(value: dict[str, Any]) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        indent=2,
        ensure_ascii=True,
        allow_nan=False,
    ) + "\n"


def write_json(value: dict[str, Any], path: str | Path) -> None:
    Path(path).write_text(pretty_json(value), encoding="utf-8")
