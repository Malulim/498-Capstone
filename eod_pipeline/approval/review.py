"""Advisory risk checks and operator approval report rendering."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from eod_pipeline.settings import EODSettings


@dataclass(frozen=True)
class EffectiveReviewThresholds:
    max_drawdown_warning_cad: float
    min_trades: int
    sources: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_drawdown_warning_cad": self.max_drawdown_warning_cad,
            "min_trades": self.min_trades,
            "sources": dict(sorted(self.sources.items())),
        }


def resolve_review_thresholds(
    settings: EODSettings,
    *,
    max_drawdown_warning_cad: float | None = None,
    min_trades: int | None = None,
) -> EffectiveReviewThresholds:
    drawdown = (
        settings.review_thresholds.max_drawdown_warning_cad
        if max_drawdown_warning_cad is None
        else max_drawdown_warning_cad
    )
    trades = (
        settings.review_thresholds.min_trades
        if min_trades is None
        else min_trades
    )
    if isinstance(drawdown, bool) or not isinstance(drawdown, (int, float)):
        raise ValueError("max drawdown warning threshold must be numeric")
    drawdown = float(drawdown)
    if not math.isfinite(drawdown) or drawdown <= 0:
        raise ValueError("max drawdown warning threshold must be finite and positive")
    if type(trades) is not int or trades <= 0:
        raise ValueError("minimum trades threshold must be a positive integer")
    return EffectiveReviewThresholds(
        max_drawdown_warning_cad=drawdown,
        min_trades=trades,
        sources={
            "max_drawdown_warning_cad": (
                "settings" if max_drawdown_warning_cad is None else "cli_override"
            ),
            "min_trades": "settings" if min_trades is None else "cli_override",
        },
    )


def _warning(code: str, message: str, observed: Any, limit: Any) -> dict[str, Any]:
    return {
        "code": code,
        "severity": "WARNING",
        "message": message,
        "observed": observed,
        "limit": limit,
    }


def review_winner(
    result: dict[str, Any],
    settings: EODSettings,
    thresholds: EffectiveReviewThresholds,
) -> list[dict[str, Any]]:
    winner = result["winner"]
    findings: list[dict[str, Any]] = []

    rejection_counts = winner["risk"]["rejection_counts"]
    rejected = {key: value for key, value in rejection_counts.items() if value > 0}
    if rejected:
        findings.append(
            _warning(
                "RISK_ATTEMPTS_REJECTED",
                "Strategy attempted orders that the risk guard rejected.",
                rejected,
                0,
            )
        )

    maxima = winner["risk"]["actual_maxima"]
    actual_checks = (
        (
            "ACTUAL_NOTIONAL_EXCEEDED",
            "max_order_notional_cad",
            settings.risk_limits.max_notional_cad,
        ),
        (
            "ACTUAL_POSITION_EXCEEDED",
            "max_abs_position_shares",
            settings.risk_limits.max_position_shares,
        ),
        (
            "ACTUAL_ORDER_RATE_EXCEEDED",
            "max_order_rate_per_second",
            settings.risk_limits.max_order_rate,
        ),
        (
            "ACTUAL_IN_FLIGHT_EXCEEDED",
            "max_in_flight",
            settings.risk_limits.max_in_flight,
        ),
    )
    for code, field, limit in actual_checks:
        observed = maxima[field]
        if observed > limit:
            findings.append(
                _warning(
                    code,
                    f"Observed {field} exceeded its configured limit.",
                    observed,
                    limit,
                )
            )

    drawdown = winner["metrics"]["max_drawdown_cad"]
    if drawdown > thresholds.max_drawdown_warning_cad:
        findings.append(
            _warning(
                "MAX_DRAWDOWN_HIGH",
                "Maximum drawdown exceeded the operator review threshold.",
                drawdown,
                thresholds.max_drawdown_warning_cad,
            )
        )

    fills = winner["activity"]["fills"]
    if fills < thresholds.min_trades:
        findings.append(
            _warning(
                "TRADE_COUNT_LOW",
                "Filled trade count is below the operator review threshold.",
                fills,
                thresholds.min_trades,
            )
        )

    if result["selection_status"] == "NOT_OPTIMIZED":
        findings.append(
            _warning(
                "NOT_OPTIMIZED",
                "The parameter sweep selected a deterministic placeholder, "
                "not optimized parameters.",
                result["selection_reason"],
                "OPTIMIZED",
            )
        )

    for index, message in enumerate(result["warnings"]):
        findings.append(
            _warning(
                f"SWEEP_WARNING_{index + 1}",
                str(message),
                True,
                False,
            )
        )
    return findings


def build_approval_report(
    result: dict[str, Any],
    candidate: dict[str, Any],
    thresholds: EffectiveReviewThresholds,
    findings: list[dict[str, Any]],
    *,
    run_id: str,
    operator_id: str,
    approval_status: str,
    rejection_reason: str | None = None,
    dispatch_status: str = "NOT_ATTEMPTED",
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "operator_id": operator_id,
        "approval_status": approval_status,
        "rejection_reason": rejection_reason,
        "dispatch_status": dispatch_status,
        "regime": result["regime"],
        "strategy_id": result["strategy_id"],
        "selection_status": result["selection_status"],
        "selection_reason": result["selection_reason"],
        "winner": result["winner"],
        "candidate_config": candidate,
        "review_thresholds": thresholds.to_dict(),
        "findings": findings,
        "has_warnings": bool(findings),
        "ps_differences": result["ps_differences"],
    }


def report_markdown(report: dict[str, Any]) -> str:
    winner = report["winner"]
    metrics = winner["metrics"]
    activity = winner["activity"]
    parameters = winner["parameters"]
    lines = [
        "# Operator Approval Report",
        "",
        f"- Run ID: `{report['run_id']}`",
        f"- Operator: `{report['operator_id']}`",
        f"- Approval status: **{report['approval_status']}**",
        f"- Dispatch status: **{report['dispatch_status']}**",
        f"- Regime / strategy: `{report['regime']}` / `{report['strategy_id']}`",
        f"- Sweep selection: `{report['selection_status']}` "
        f"(`{report['selection_reason']}`)",
        "",
        "## Winner",
        "",
        f"- Candidate index: {winner['candidate_index']}",
        f"- Parameters: `{parameters}`",
        f"- Sharpe: {metrics['sharpe']}",
        f"- Total P&L: CAD {metrics['total_pnl_cad']}",
        f"- Maximum drawdown: CAD {metrics['max_drawdown_cad']}",
        f"- Signals / accepted / rejected / fills: "
        f"{activity['signals']} / {activity['accepted']} / "
        f"{activity['rejected']} / {activity['fills']}",
        "",
        "## Review thresholds",
        "",
        f"- Maximum drawdown warning: CAD "
        f"{report['review_thresholds']['max_drawdown_warning_cad']}",
        f"- Minimum filled trades: {report['review_thresholds']['min_trades']}",
        f"- Sources: `{report['review_thresholds']['sources']}`",
        "",
        "## Findings",
        "",
    ]
    if report["findings"]:
        for finding in report["findings"]:
            lines.append(
                f"- **{finding['code']}**: {finding['message']} "
                f"(observed: `{finding['observed']}`, limit: `{finding['limit']}`)"
            )
    else:
        lines.append("- No warnings.")

    lines.extend(["", "## PS compatibility differences", ""])
    for difference in report["ps_differences"]:
        lines.append(f"- `{difference}`")
    if report["rejection_reason"] is not None:
        lines.extend(
            ["", "## Rejection", "", f"- Reason: {report['rejection_reason']}"]
        )
    return "\n".join(lines) + "\n"
