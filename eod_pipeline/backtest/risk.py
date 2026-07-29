"""Backtest risk checks matching the current PS semantics."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from eod_pipeline.backtest.strategies import Side
from eod_pipeline.settings import RiskLimits


RATE_WINDOW_NS = 1_000_000_000


class RiskReason(str, Enum):
    NOTIONAL = "NOTIONAL"
    POSITION = "POSITION"
    ORDER_RATE = "ORDER_RATE"
    IN_FLIGHT = "IN_FLIGHT"


@dataclass(frozen=True)
class RiskDecision:
    accepted: bool
    reasons: tuple[RiskReason, ...]
    order_notional_cad: int
    projected_position: int


def check_risk(
    limits: RiskLimits,
    *,
    position: int,
    side: Side,
    quantity: int,
    price_cents: int,
    in_flight_count: int,
    accepted_orders_in_window: int,
) -> RiskDecision:
    """Evaluate all four checks and preserve every rejection reason.

    Position intentionally excludes pending orders, and notional intentionally
    covers only the new order. These choices match the current PS prototype.
    """

    if side not in (Side.BUY, Side.SELL):
        raise ValueError("risk check requires BUY or SELL")
    if quantity <= 0 or price_cents <= 0:
        raise ValueError("quantity and price must be positive")

    order_notional_cad = quantity * price_cents // 100
    signed_quantity = quantity if side == Side.BUY else -quantity
    projected_position = position + signed_quantity

    reasons: list[RiskReason] = []
    if order_notional_cad > limits.max_notional_cad:
        reasons.append(RiskReason.NOTIONAL)
    if abs(projected_position) > limits.max_position_shares:
        reasons.append(RiskReason.POSITION)
    if accepted_orders_in_window + 1 > limits.max_order_rate:
        reasons.append(RiskReason.ORDER_RATE)
    if in_flight_count + 1 > limits.max_in_flight:
        reasons.append(RiskReason.IN_FLIGHT)

    return RiskDecision(
        accepted=not reasons,
        reasons=tuple(reasons),
        order_notional_cad=order_notional_cad,
        projected_position=projected_position,
    )
