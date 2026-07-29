"""Deterministic strategy kernels aligned with the PS prototype."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

import numpy as np

from eod_pipeline.backtest.snapshots import SnapshotArrays


class Side(IntEnum):
    HOLD = 0
    BUY = 1
    SELL = 2


@dataclass(frozen=True)
class StrategySignals:
    side: np.ndarray
    quantity: np.ndarray
    price_cents: np.ndarray

    def __len__(self) -> int:
        return len(self.side)


def _empty_signals(length: int) -> StrategySignals:
    return StrategySignals(
        side=np.full(length, Side.HOLD, dtype=np.int8),
        quantity=np.zeros(length, dtype=np.int64),
        price_cents=np.zeros(length, dtype=np.int64),
    )


def _order_quantity(base_lot: int, pos_scalar: float) -> int:
    quantity = base_lot * pos_scalar
    rounded = round(quantity)
    if not np.isclose(quantity, rounded, rtol=0.0, atol=1e-9):
        raise ValueError("base_lot * pos_scalar must produce whole shares")
    return int(rounded)


def momentum_signals(
    snapshots: SnapshotArrays,
    *,
    lookback: int,
    entry_thresh: float,
    base_lot: int,
    pos_scalar: float,
) -> StrategySignals:
    """Match the PS Momentum threshold arithmetic and aggressive prices."""

    signals = _empty_signals(len(snapshots))
    if lookback <= 0 or lookback >= len(snapshots):
        return signals

    mid = snapshots.mid_half_cents
    delta = mid[lookback:] - mid[:-lookback]
    ratio = delta.astype(np.float32) / mid[lookback:].astype(np.float32)
    buy = ratio >= np.float32(entry_thresh)
    sell = ratio <= np.float32(-entry_thresh)
    valid_side = signals.side[lookback:]
    valid_side[buy] = Side.BUY
    valid_side[sell] = Side.SELL

    quantity = _order_quantity(base_lot, pos_scalar)
    active = signals.side != Side.HOLD
    signals.quantity[active] = quantity
    buy_active = signals.side == Side.BUY
    sell_active = signals.side == Side.SELL
    signals.price_cents[buy_active] = snapshots.ask_cents[buy_active]
    signals.price_cents[sell_active] = snapshots.bid_cents[sell_active]
    return signals


def mean_reversion_signals(
    snapshots: SnapshotArrays,
    *,
    window: int,
    dev_thresh: float,
    base_lot: int,
    pos_scalar: float,
) -> StrategySignals:
    """Use the preceding window and aggressive prices for deterministic fills.

    The PS prototype currently uses BUY at bid and SELL at ask for this strategy.
    EOD intentionally follows the common Decision contract instead: BUY at ask
    and SELL at bid. The difference is documented in ``PS_COMPATIBILITY.md``.
    """

    signals = _empty_signals(len(snapshots))
    if window <= 0 or window >= len(snapshots):
        return signals

    mid = snapshots.mid_half_cents
    prefix = np.concatenate(
        (np.array([0], dtype=np.int64), np.cumsum(mid, dtype=np.int64))
    )
    historical_sum = prefix[window:-1] - prefix[: -window - 1]
    moving_average = historical_sum.astype(np.float64) / window
    deviation = (mid[window:].astype(np.float64) - moving_average) / moving_average

    valid_side = signals.side[window:]
    valid_side[deviation >= dev_thresh] = Side.SELL
    valid_side[deviation <= -dev_thresh] = Side.BUY

    quantity = _order_quantity(base_lot, pos_scalar)
    active = signals.side != Side.HOLD
    signals.quantity[active] = quantity
    buy_active = signals.side == Side.BUY
    sell_active = signals.side == Side.SELL
    signals.price_cents[buy_active] = snapshots.ask_cents[buy_active]
    signals.price_cents[sell_active] = snapshots.bid_cents[sell_active]
    return signals


def defensive_signals(
    snapshots: SnapshotArrays,
    *,
    spread_floor: int,
    base_lot: int,
    pos_scalar: float,
) -> StrategySignals:
    """Return HOLD until the PS Defensive strategy is implemented."""

    del spread_floor, base_lot, pos_scalar
    return _empty_signals(len(snapshots))


def build_signals(
    strategy_id: str,
    snapshots: SnapshotArrays,
    parameters: dict[str, Any],
    base_lot: int,
) -> StrategySignals:
    if strategy_id == "momentum":
        return momentum_signals(
            snapshots,
            lookback=int(parameters["lookback"]),
            entry_thresh=float(parameters["entry_thresh"]),
            base_lot=base_lot,
            pos_scalar=float(parameters["pos_scalar"]),
        )
    if strategy_id == "mean_reversion":
        return mean_reversion_signals(
            snapshots,
            window=int(parameters["window"]),
            dev_thresh=float(parameters["dev_thresh"]),
            base_lot=base_lot,
            pos_scalar=float(parameters["pos_scalar"]),
        )
    if strategy_id == "defensive":
        return defensive_signals(
            snapshots,
            spread_floor=int(parameters["spread_floor"]),
            base_lot=base_lot,
            pos_scalar=float(parameters["pos_scalar"]),
        )
    raise ValueError(f"unknown strategy_id '{strategy_id}'")
