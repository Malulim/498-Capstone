"""Strict, deterministic loader for EOD search and risk settings."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 2
RING_SIZE = 64
HARD_SAFETY_LIMITS = {
    "max_notional_cad": 50_000,
    "max_position_shares": 1_000,
    "max_order_rate": 1_000,
    "max_in_flight": 100,
}


class SettingsError(ValueError):
    """Raised when EOD settings do not satisfy the configuration contract."""


@dataclass(frozen=True)
class MomentumGrid:
    lookback: tuple[int, ...]
    entry_thresh: tuple[float, ...]
    pos_scalar: tuple[float, ...]


@dataclass(frozen=True)
class MeanReversionGrid:
    window: tuple[int, ...]
    dev_thresh: tuple[float, ...]
    pos_scalar: tuple[float, ...]


@dataclass(frozen=True)
class DefensiveGrid:
    spread_floor: tuple[int, ...]
    pos_scalar: tuple[float, ...]


@dataclass(frozen=True)
class RiskLimits:
    max_notional_cad: int
    max_position_shares: int
    max_order_rate: int
    max_in_flight: int


@dataclass(frozen=True)
class ReviewThresholds:
    max_drawdown_warning_cad: float
    min_trades: int


@dataclass(frozen=True)
class EODSettings:
    schema_version: int
    base_lot: int
    momentum: MomentumGrid
    mean_reversion: MeanReversionGrid
    defensive: DefensiveGrid
    risk_limits: RiskLimits
    review_thresholds: ReviewThresholds

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "base_lot": self.base_lot,
            "strategy_grids": {
                "momentum": {
                    "lookback": list(self.momentum.lookback),
                    "entry_thresh": list(self.momentum.entry_thresh),
                    "pos_scalar": list(self.momentum.pos_scalar),
                },
                "mean_reversion": {
                    "window": list(self.mean_reversion.window),
                    "dev_thresh": list(self.mean_reversion.dev_thresh),
                    "pos_scalar": list(self.mean_reversion.pos_scalar),
                },
                "defensive": {
                    "spread_floor": list(self.defensive.spread_floor),
                    "pos_scalar": list(self.defensive.pos_scalar),
                },
            },
            "risk_limits": {
                "max_notional_cad": self.risk_limits.max_notional_cad,
                "max_position_shares": self.risk_limits.max_position_shares,
                "max_order_rate": self.risk_limits.max_order_rate,
                "max_in_flight": self.risk_limits.max_in_flight,
            },
            "review_thresholds": {
                "max_drawdown_warning_cad": (
                    self.review_thresholds.max_drawdown_warning_cad
                ),
                "min_trades": self.review_thresholds.min_trades,
            },
        }

    def canonical_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SettingsError(f"duplicate key '{key}'")
        result[key] = value
    return result


def _require_object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SettingsError(f"{path} must be an object")
    return value


def _require_exact_keys(value: dict[str, Any], expected: set[str], path: str) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing:
        raise SettingsError(f"{path} missing required keys: {missing}")
    if unknown:
        raise SettingsError(f"{path} contains unknown keys: {unknown}")


def _require_positive_int(value: Any, path: str, *, maximum: int | None = None) -> int:
    if type(value) is not int:
        raise SettingsError(f"{path} must be an integer")
    if value <= 0:
        raise SettingsError(f"{path} must be positive")
    if maximum is not None and value > maximum:
        raise SettingsError(f"{path}={value} exceeds hard maximum {maximum}")
    return value


def _require_positive_number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SettingsError(f"{path} must be a number")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise SettingsError(f"{path} must be finite and positive")
    return number


def _positive_int_tuple(
    value: Any,
    path: str,
    *,
    maximum: int | None = None,
) -> tuple[int, ...]:
    if not isinstance(value, list) or not value:
        raise SettingsError(f"{path} must be a non-empty array")
    result = tuple(
        _require_positive_int(item, f"{path}[{index}]", maximum=maximum)
        for index, item in enumerate(value)
    )
    if len(set(result)) != len(result):
        raise SettingsError(f"{path} must not contain duplicates")
    return result


def _positive_number_tuple(value: Any, path: str) -> tuple[float, ...]:
    if not isinstance(value, list) or not value:
        raise SettingsError(f"{path} must be a non-empty array")
    result: list[float] = []
    for index, item in enumerate(value):
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise SettingsError(f"{path}[{index}] must be a number")
        number = float(item)
        if not math.isfinite(number) or number <= 0:
            raise SettingsError(f"{path}[{index}] must be finite and positive")
        result.append(number)
    if len(set(result)) != len(result):
        raise SettingsError(f"{path} must not contain duplicates")
    return tuple(result)


def _validate_integer_quantities(
    base_lot: int,
    grids: tuple[tuple[str, tuple[float, ...]], ...],
) -> None:
    for path, scalars in grids:
        for scalar in scalars:
            quantity = base_lot * scalar
            if not math.isclose(quantity, round(quantity), rel_tol=0.0, abs_tol=1e-9):
                raise SettingsError(
                    f"base_lot * {path} value {scalar:g} must produce whole shares"
                )


def load_settings(path: str | Path) -> EODSettings:
    path = Path(path)
    try:
        raw = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_object_without_duplicate_keys,
        )
    except OSError as error:
        raise SettingsError(f"could not read settings file {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise SettingsError(f"invalid JSON in {path}: {error}") from error

    root = _require_object(raw, "settings")
    _require_exact_keys(
        root,
        {
            "schema_version",
            "base_lot",
            "strategy_grids",
            "risk_limits",
            "review_thresholds",
        },
        "settings",
    )
    schema_version = _require_positive_int(root["schema_version"], "schema_version")
    if schema_version != SCHEMA_VERSION:
        raise SettingsError(
            f"unsupported schema_version {schema_version}; expected {SCHEMA_VERSION}"
        )
    base_lot = _require_positive_int(root["base_lot"], "base_lot")

    grids = _require_object(root["strategy_grids"], "strategy_grids")
    _require_exact_keys(
        grids,
        {"momentum", "mean_reversion", "defensive"},
        "strategy_grids",
    )

    momentum_raw = _require_object(grids["momentum"], "strategy_grids.momentum")
    _require_exact_keys(
        momentum_raw,
        {"lookback", "entry_thresh", "pos_scalar"},
        "strategy_grids.momentum",
    )
    momentum = MomentumGrid(
        lookback=_positive_int_tuple(
            momentum_raw["lookback"],
            "strategy_grids.momentum.lookback",
            maximum=RING_SIZE - 1,
        ),
        entry_thresh=_positive_number_tuple(
            momentum_raw["entry_thresh"],
            "strategy_grids.momentum.entry_thresh",
        ),
        pos_scalar=_positive_number_tuple(
            momentum_raw["pos_scalar"],
            "strategy_grids.momentum.pos_scalar",
        ),
    )

    mean_reversion_raw = _require_object(
        grids["mean_reversion"],
        "strategy_grids.mean_reversion",
    )
    _require_exact_keys(
        mean_reversion_raw,
        {"window", "dev_thresh", "pos_scalar"},
        "strategy_grids.mean_reversion",
    )
    mean_reversion = MeanReversionGrid(
        window=_positive_int_tuple(
            mean_reversion_raw["window"],
            "strategy_grids.mean_reversion.window",
            maximum=RING_SIZE - 1,
        ),
        dev_thresh=_positive_number_tuple(
            mean_reversion_raw["dev_thresh"],
            "strategy_grids.mean_reversion.dev_thresh",
        ),
        pos_scalar=_positive_number_tuple(
            mean_reversion_raw["pos_scalar"],
            "strategy_grids.mean_reversion.pos_scalar",
        ),
    )

    defensive_raw = _require_object(grids["defensive"], "strategy_grids.defensive")
    _require_exact_keys(
        defensive_raw,
        {"spread_floor", "pos_scalar"},
        "strategy_grids.defensive",
    )
    defensive = DefensiveGrid(
        spread_floor=_positive_int_tuple(
            defensive_raw["spread_floor"],
            "strategy_grids.defensive.spread_floor",
        ),
        pos_scalar=_positive_number_tuple(
            defensive_raw["pos_scalar"],
            "strategy_grids.defensive.pos_scalar",
        ),
    )

    risk_raw = _require_object(root["risk_limits"], "risk_limits")
    _require_exact_keys(risk_raw, set(HARD_SAFETY_LIMITS), "risk_limits")
    risk_values = {
        key: _require_positive_int(
            risk_raw[key],
            f"risk_limits.{key}",
            maximum=maximum,
        )
        for key, maximum in HARD_SAFETY_LIMITS.items()
    }
    risk_limits = RiskLimits(**risk_values)

    review_raw = _require_object(root["review_thresholds"], "review_thresholds")
    _require_exact_keys(
        review_raw,
        {"max_drawdown_warning_cad", "min_trades"},
        "review_thresholds",
    )
    review_thresholds = ReviewThresholds(
        max_drawdown_warning_cad=_require_positive_number(
            review_raw["max_drawdown_warning_cad"],
            "review_thresholds.max_drawdown_warning_cad",
        ),
        min_trades=_require_positive_int(
            review_raw["min_trades"],
            "review_thresholds.min_trades",
        ),
    )

    _validate_integer_quantities(
        base_lot,
        (
            ("momentum.pos_scalar", momentum.pos_scalar),
            ("mean_reversion.pos_scalar", mean_reversion.pos_scalar),
            ("defensive.pos_scalar", defensive.pos_scalar),
        ),
    )

    return EODSettings(
        schema_version=schema_version,
        base_lot=base_lot,
        momentum=momentum,
        mean_reversion=mean_reversion,
        defensive=defensive,
        risk_limits=risk_limits,
        review_thresholds=review_thresholds,
    )
