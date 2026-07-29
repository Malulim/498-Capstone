"""Metric definitions for deterministic parameter ranking."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from eod_pipeline.backtest.engine import BacktestRun


MINUTES_PER_SESSION = 390
SESSION_START_NS = 34_200 * 1_000_000_000
MINUTE_NS = 60 * 1_000_000_000
ANNUALIZATION_FACTOR = math.sqrt(252 * MINUTES_PER_SESSION)


@dataclass(frozen=True)
class BacktestMetrics:
    sharpe: float | None
    max_drawdown_half_cents: int
    total_pnl_half_cents: int
    minute_pnl_half_cents: np.ndarray


def minute_pnl_buckets(
    time_ns: np.ndarray,
    equity_half_cents: np.ndarray,
) -> np.ndarray:
    """Return exactly 390 minute P&L changes, carrying equity through gaps."""

    if len(time_ns) != len(equity_half_cents):
        raise ValueError("time and equity arrays must have equal length")
    if len(time_ns) == 0:
        raise ValueError("metric input cannot be empty")
    if np.any(np.diff(time_ns) < 0):
        raise ValueError("timestamps must be monotonic")

    minute_ends = SESSION_START_NS + (
        np.arange(1, MINUTES_PER_SESSION + 1, dtype=np.int64) * MINUTE_NS
    )
    indices = np.searchsorted(time_ns, minute_ends, side="right") - 1
    minute_equity = np.zeros(MINUTES_PER_SESSION, dtype=np.int64)
    available = indices >= 0
    minute_equity[available] = equity_half_cents[indices[available]]
    return np.diff(
        np.concatenate((np.array([0], dtype=np.int64), minute_equity))
    )


def annualized_sharpe(
    minute_pnl_half_cents: np.ndarray,
    *,
    fills: int,
) -> float | None:
    if fills == 0:
        return None
    values = minute_pnl_half_cents.astype(np.float64)
    sample_std = float(np.std(values, ddof=1))
    if sample_std == 0.0 or not math.isfinite(sample_std):
        return None
    sharpe = float(np.mean(values) / sample_std * ANNUALIZATION_FACTOR)
    return sharpe if math.isfinite(sharpe) else None


def maximum_drawdown(equity_half_cents: np.ndarray) -> int:
    """Compute peak-to-trough loss from every tick, including initial equity 0."""

    with_initial = np.concatenate(
        (np.array([0], dtype=np.int64), equity_half_cents)
    )
    peaks = np.maximum.accumulate(with_initial)
    return int(np.max(peaks - with_initial))


def calculate_metrics(run: BacktestRun) -> BacktestMetrics:
    minute_pnl = minute_pnl_buckets(run.time_ns, run.equity_half_cents)
    return BacktestMetrics(
        sharpe=annualized_sharpe(minute_pnl, fills=run.fills),
        max_drawdown_half_cents=maximum_drawdown(run.equity_half_cents),
        total_pnl_half_cents=run.total_pnl_half_cents,
        minute_pnl_half_cents=minute_pnl,
    )
