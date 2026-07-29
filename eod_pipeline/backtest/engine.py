"""Sequential PS-style execution simulation for one parameter combination."""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass

import numpy as np

from eod_pipeline.backtest.risk import RATE_WINDOW_NS, RiskReason, check_risk
from eod_pipeline.backtest.snapshots import SnapshotArrays
from eod_pipeline.backtest.strategies import Side, StrategySignals
from eod_pipeline.settings import RiskLimits


FILL_DELAY_NS = 100_000_000


@dataclass(frozen=True)
class PendingOrder:
    submit_time_ns: int
    side: Side
    quantity: int
    price_cents: int


@dataclass(frozen=True)
class BacktestRun:
    time_ns: np.ndarray
    equity_half_cents: np.ndarray
    total_pnl_half_cents: int
    final_cash_cents: int
    final_position: int
    signals: int
    accepted: int
    rejected: int
    fills: int
    rejection_counts: dict[str, int]
    max_abs_position: int
    max_in_flight: int
    max_order_rate: int
    max_order_notional_cad: int


def run_backtest(
    snapshots: SnapshotArrays,
    signals: StrategySignals,
    risk_limits: RiskLimits,
    *,
    fill_delay_ns: int = FILL_DELAY_NS,
) -> BacktestRun:
    """Run one strategy/parameter stream.

    For each snapshot, strategy/risk processing happens before matured orders
    are filled, matching the ordering in the current PS ``main.c`` loop.
    """

    if len(snapshots) != len(signals):
        raise ValueError("snapshots and signals must have the same length")
    if fill_delay_ns < 0:
        raise ValueError("fill_delay_ns must be non-negative")

    in_flight: deque[PendingOrder] = deque()
    accepted_times: deque[int] = deque()
    rejection_counter: Counter[str] = Counter()
    equity_half_cents = np.zeros(len(snapshots), dtype=np.int64)

    position = 0
    cash_cents = 0
    signal_count = 0
    accepted_count = 0
    rejected_count = 0
    fill_count = 0
    max_abs_position = 0
    max_in_flight = 0
    max_order_rate = 0
    max_order_notional_cad = 0

    def fill_order(order: PendingOrder) -> None:
        nonlocal position, cash_cents, fill_count, max_abs_position
        if order.side == Side.BUY:
            position += order.quantity
            cash_cents -= order.quantity * order.price_cents
        else:
            position -= order.quantity
            cash_cents += order.quantity * order.price_cents
        fill_count += 1
        max_abs_position = max(max_abs_position, abs(position))

    for index in range(len(snapshots)):
        now_ns = int(snapshots.time_ns[index])
        side = Side(int(signals.side[index]))

        while accepted_times and accepted_times[0] <= now_ns - RATE_WINDOW_NS:
            accepted_times.popleft()

        if side != Side.HOLD:
            signal_count += 1
            quantity = int(signals.quantity[index])
            price_cents = int(signals.price_cents[index])
            decision = check_risk(
                risk_limits,
                position=position,
                side=side,
                quantity=quantity,
                price_cents=price_cents,
                in_flight_count=len(in_flight),
                accepted_orders_in_window=len(accepted_times),
            )
            if decision.accepted:
                in_flight.append(
                    PendingOrder(
                        submit_time_ns=now_ns,
                        side=side,
                        quantity=quantity,
                        price_cents=price_cents,
                    )
                )
                accepted_times.append(now_ns)
                accepted_count += 1
                max_in_flight = max(max_in_flight, len(in_flight))
                max_order_rate = max(max_order_rate, len(accepted_times))
                max_order_notional_cad = max(
                    max_order_notional_cad,
                    decision.order_notional_cad,
                )
            else:
                rejected_count += 1
                rejection_counter.update(reason.value for reason in decision.reasons)

        while (
            in_flight
            and in_flight[0].submit_time_ns + fill_delay_ns <= now_ns
        ):
            fill_order(in_flight.popleft())

        equity_half_cents[index] = (
            2 * cash_cents + position * int(snapshots.mid_half_cents[index])
        )

    while in_flight:
        fill_order(in_flight.popleft())

    final_mid_half_cents = int(snapshots.mid_half_cents[-1])
    total_pnl_half_cents = 2 * cash_cents + position * final_mid_half_cents
    equity_half_cents[-1] = total_pnl_half_cents

    return BacktestRun(
        time_ns=snapshots.time_ns.copy(),
        equity_half_cents=equity_half_cents,
        total_pnl_half_cents=total_pnl_half_cents,
        final_cash_cents=cash_cents,
        final_position=position,
        signals=signal_count,
        accepted=accepted_count,
        rejected=rejected_count,
        fills=fill_count,
        rejection_counts={
            reason.value: rejection_counter.get(reason.value, 0)
            for reason in RiskReason
        },
        max_abs_position=max_abs_position,
        max_in_flight=max_in_flight,
        max_order_rate=max_order_rate,
        max_order_notional_cad=max_order_notional_cad,
    )
