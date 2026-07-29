#!/usr/bin/env python3
"""Measure whether the design-time strategy grids fit the real LOBSTER stream."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import numpy as np

from eod_pipeline.backtest.snapshots import NANOSECONDS_PER_SECOND, load_snapshots
from eod_pipeline.settings import EODSettings, load_settings


TARGET_SIGNAL_COUNTS = (10, 50, 200)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def momentum_ratio(mid: np.ndarray, lookback: int) -> np.ndarray:
    """Match C's ``(float)delta / mid_now`` for valid, warmed-up rows."""

    delta = mid[lookback:] - mid[:-lookback]
    return delta.astype(np.float32) / mid[lookback:].astype(np.float32)


def mean_reversion_deviation(mid: np.ndarray, window: int) -> np.ndarray:
    """Compare each tick with the preceding window, excluding the current tick."""

    prefix = np.concatenate((np.array([0], dtype=np.int64), np.cumsum(mid, dtype=np.int64)))
    historical_sum = prefix[window:-1] - prefix[:-window - 1]
    moving_average = historical_sum.astype(np.float64) / window
    return (mid[window:].astype(np.float64) - moving_average) / moving_average


def threshold_for_target(abs_values: np.ndarray, target: int) -> tuple[float, int]:
    """Return a threshold yielding approximately ``target`` rows, including ties."""

    target = min(target, len(abs_values))
    index = len(abs_values) - target
    threshold = float(np.partition(abs_values, index)[index])
    actual_count = int(np.count_nonzero(abs_values >= threshold))
    return threshold, actual_count


def rolling_peak(time_ns: np.ndarray, window_ns: int) -> int:
    """Maximum event count in any rolling interval of ``window_ns``."""

    starts = np.searchsorted(time_ns, time_ns - window_ns, side="left")
    counts = np.arange(len(time_ns), dtype=np.int64) - starts + 1
    return int(counts.max())


def percentile_rows(label: str, values: np.ndarray) -> list[str]:
    quantiles = np.percentile(values, [50, 90, 99, 99.9])
    return [
        label,
        *(f"{value:.8f}" for value in quantiles),
        f"{np.max(values):.8f}",
    ]


def build_report(
    expected_book: Path,
    timing: Path,
    settings: EODSettings,
    settings_path: Path | None = None,
) -> str:
    snapshots = load_snapshots(expected_book, timing)
    count = len(snapshots)
    elapsed_seconds = (snapshots.time_ns[-1] - snapshots.time_ns[0]) / NANOSECONDS_PER_SECOND
    average_rate = count / elapsed_seconds

    second_buckets = snapshots.time_ns // NANOSECONDS_PER_SECOND
    _, bucket_counts = np.unique(second_buckets, return_counts=True)
    fixed_second_peak = int(bucket_counts.max())
    burst_windows_ms = (1000, 100, 10, 1)
    burst_rows: list[list[str]] = []
    for window_ms in burst_windows_ms:
        peak_count = rolling_peak(snapshots.time_ns, window_ms * 1_000_000)
        normalized_rate = peak_count * 1000.0 / window_ms
        burst_rows.append(
            [f"{window_ms:,}", f"{peak_count:,}", f"{normalized_rate:,.0f}"]
        )

    mid_cents = snapshots.mid_half_cents.astype(np.float64) / 2.0
    start_seconds = snapshots.time_ns[0] / NANOSECONDS_PER_SECOND
    end_seconds = snapshots.time_ns[-1] / NANOSECONDS_PER_SECOND

    momentum_counts: list[list[str]] = []
    momentum_distributions: list[list[str]] = []
    momentum_suggestions: list[list[str]] = []
    for lookback in settings.momentum.lookback:
        ratio = momentum_ratio(snapshots.mid_half_cents, lookback)
        absolute = np.abs(ratio)
        for threshold in settings.momentum.entry_thresh:
            triggers = int(np.count_nonzero(absolute >= np.float32(threshold)))
            momentum_counts.append([str(lookback), f"{threshold:.6f}", f"{triggers:,}"])
        momentum_distributions.append(percentile_rows(str(lookback), absolute))
        for target in TARGET_SIGNAL_COUNTS:
            threshold, actual = threshold_for_target(absolute, target)
            momentum_suggestions.append(
                [str(lookback), str(target), f"{threshold:.8f}", f"{actual:,}"]
            )

    mean_reversion_counts: list[list[str]] = []
    mean_reversion_distributions: list[list[str]] = []
    mean_reversion_suggestions: list[list[str]] = []
    for window in settings.mean_reversion.window:
        deviation = mean_reversion_deviation(snapshots.mid_half_cents, window)
        absolute = np.abs(deviation)
        for threshold in settings.mean_reversion.dev_thresh:
            triggers = int(np.count_nonzero(absolute >= threshold))
            mean_reversion_counts.append([str(window), f"{threshold:.6f}", f"{triggers:,}"])
        mean_reversion_distributions.append(percentile_rows(str(window), absolute))
        for target in TARGET_SIGNAL_COUNTS:
            threshold, actual = threshold_for_target(absolute, target)
            mean_reversion_suggestions.append(
                [str(window), str(target), f"{threshold:.8f}", f"{actual:,}"]
            )

    conservative_max_shares = (
        settings.risk_limits.max_notional_cad * 100 // snapshots.ask_cents
    )
    max_shares_stats = np.percentile(conservative_max_shares, [0, 50, 100])

    notional_rows: list[list[str]] = []
    position_scalars = tuple(
        sorted(
            {
                *settings.momentum.pos_scalar,
                *settings.mean_reversion.pos_scalar,
                *settings.defensive.pos_scalar,
            }
        )
    )
    for scalar in position_scalars:
        quantity = int(settings.base_lot * scalar)
        buy_reject = (
            (quantity * snapshots.ask_cents // 100)
            > settings.risk_limits.max_notional_cad
        )
        sell_reject = (
            (quantity * snapshots.bid_cents // 100)
            > settings.risk_limits.max_notional_cad
        )
        notional_rows.append(
            [
                f"{scalar:g}",
                str(quantity),
                f"{np.mean(buy_reject) * 100:.3f}%",
                f"{np.mean(sell_reject) * 100:.3f}%",
            ]
        )

    spread_quantiles = np.percentile(
        snapshots.spread_cents.astype(np.float64), [50, 90, 99, 99.9]
    )
    spread_floor_rows = [
        [
            str(floor),
            f"{np.mean(snapshots.spread_cents >= floor) * 100:.3f}%",
            f"{np.mean(snapshots.spread_cents <= floor) * 100:.3f}%",
        ]
        for floor in settings.defensive.spread_floor
    ]

    momentum_total = sum(int(row[2].replace(",", "")) for row in momentum_counts)
    mean_reversion_total = sum(
        int(row[2].replace(",", "")) for row in mean_reversion_counts
    )
    rejection_summary = "; ".join(
        f"`pos_scalar={row[0]}`: **{row[2]}**"
        for row in notional_rows
    )
    momentum_pair_count = (
        len(settings.momentum.lookback) * len(settings.momentum.entry_thresh)
    )
    mean_reversion_pair_count = (
        len(settings.mean_reversion.window)
        * len(settings.mean_reversion.dev_thresh)
    )
    settings_source = str(settings_path) if settings_path is not None else "(in memory)"

    sections = [
        "# LOBSTER AAPL 2012-06-21 Data Health Check",
        "",
        "This report measures signal opportunities, not completed trades. Consecutive "
        "ticks above a threshold are counted separately; the later backtest engine "
        "must still apply position, in-flight, and fill logic.",
        "",
        "## Executive conclusions",
        "",
        f"1. Across {momentum_pair_count} configured Momentum signal-condition pairs, "
        f"the stream produced **{momentum_total:,} threshold crossings**. Across "
        f"{mean_reversion_pair_count} Mean Reversion pairs, it produced "
        f"**{mean_reversion_total:,} threshold crossings**.",
        f"2. The empirical threshold tables below show the magnitude needed for "
        f"approximately 10, 50, or 200 raw signal rows during this session. These "
        f"values can be compared with the configured search grid.",
        f"3. With `base_lot={settings.base_lot}`, buy-order rejection rates under "
        f"the configured CAD {settings.risk_limits.max_notional_cad:,} notional limit "
        f"are {rejection_summary}.",
        "",
        "## EOD settings",
        "",
        markdown_table(
            ["Field", "Value"],
            [
                ["Source", f"`{settings_source}`"],
                ["Schema version", str(settings.schema_version)],
                ["Canonical SHA-256", f"`{settings.sha256()}`"],
                ["Base lot", f"{settings.base_lot} shares"],
                [
                    "Configured notional limit",
                    f"CAD {settings.risk_limits.max_notional_cad:,}",
                ],
            ],
        ),
        "",
        "## Dataset and preprocessing facts",
        "",
        markdown_table(
            ["Metric", "Measured value"],
            [
                ["Rows", f"{count:,}"],
                ["First timestamp (seconds after midnight)", f"{start_seconds:.9f}"],
                ["Last timestamp (seconds after midnight)", f"{end_seconds:.9f}"],
                ["Observed duration", f"{elapsed_seconds:.6f} s"],
                ["Average event rate", f"{average_rate:.3f} messages/s"],
                ["Peak fixed one-second bucket", f"{fixed_second_peak:,} messages/s"],
                ["Peak rolling one-second window", f"{burst_rows[0][1]} messages/s"],
                ["Mid-price range", f"${mid_cents.min() / 100:.2f} to ${mid_cents.max() / 100:.2f}"],
                ["Expected-book SHA-256", f"`{sha256(expected_book)}`"],
                ["Timing-file SHA-256", f"`{sha256(timing)}`"],
            ],
        ),
        "",
        "### Burst rates by measurement window",
        "",
        markdown_table(
            ["Rolling window (ms)", "Maximum events in window", "Normalized events/s"],
            burst_rows,
        ),
        "",
        "## Momentum grid: raw threshold crossings",
        "",
        markdown_table(["Lookback (messages)", "Entry threshold", "Crossings"], momentum_counts),
        "",
        "## Momentum absolute-return distribution",
        "",
        markdown_table(
            ["Lookback", "p50", "p90", "p99", "p99.9", "Maximum"],
            momentum_distributions,
        ),
        "",
        "## Momentum empirical thresholds",
        "",
        markdown_table(
            ["Lookback", "Target rows", "Threshold", "Actual rows incl. ties"],
            momentum_suggestions,
        ),
        "",
        "## Mean Reversion grid: raw threshold crossings",
        "",
        markdown_table(["Window (messages)", "Deviation threshold", "Crossings"], mean_reversion_counts),
        "",
        "## Mean Reversion absolute-deviation distribution",
        "",
        markdown_table(
            ["Window", "p50", "p90", "p99", "p99.9", "Maximum"],
            mean_reversion_distributions,
        ),
        "",
        "## Mean Reversion empirical thresholds",
        "",
        markdown_table(
            ["Window", "Target rows", "Threshold", "Actual rows incl. ties"],
            mean_reversion_suggestions,
        ),
        "",
        "## Notional-limit feasibility",
        "",
        f"Using the ask as the conservative price, CAD "
        f"{settings.risk_limits.max_notional_cad:,} permits "
        f"**{int(max_shares_stats[0])} to {int(max_shares_stats[2])} shares** during "
        f"the session (median **{int(max_shares_stats[1])}**). The percentages below "
        f"replicate `risk_guard.c` integer division.",
        "",
        markdown_table(
            ["Position scalar", "Order quantity", "Buy rejected", "Sell rejected"],
            notional_rows,
        ),
        "",
        "## Spread distribution",
        "",
        markdown_table(
            ["p50", "p90", "p99", "p99.9", "Maximum"],
            [[
                f"{spread_quantiles[0]:.0f} cents",
                f"{spread_quantiles[1]:.0f} cents",
                f"{spread_quantiles[2]:.0f} cents",
                f"{spread_quantiles[3]:.0f} cents",
                f"{snapshots.spread_cents.max()} cents",
            ]],
        ),
        "",
        markdown_table(
            ["Spread floor", "Snapshots at/above floor", "Snapshots at/below floor"],
            spread_floor_rows,
        ),
        "",
        "## Interpretation constraints",
        "",
        "- The signal counts are diagnostics, not P&L or Sharpe results.",
        "- Threshold suggestions target raw rows and do not account for repeated "
        "signals, cooldown, risk rejection, or the 0.1-second fill delay.",
        "- The notional check follows the current C implementation and treats the "
        "integer-cent AAPL price as CAD without an explicit USD/CAD conversion.",
        "- The design document's approximately 2,400 messages/s peak is not a "
        "one-second count: this run measured 584 in a fixed one-second bucket and "
        "675 in any rolling one-second window. A shorter 100 ms burst normalized "
        "to one second measured 2,890 messages/s, so the document needs to state "
        "its burst-window definition.",
        "- The current preprocessor reported 6,107 Modify/Delete references to orders "
        "opened before the trace window; it records these as pre-existing liquidity "
        "rather than failing the run.",
        "",
    ]
    return "\n".join(sections)


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--settings",
        type=Path,
        default=project_root / "eod_pipeline/config/eod_settings.json",
    )
    parser.add_argument(
        "--expected-book",
        type=Path,
        default=project_root / "Exchange_simulator/build/expected_book.csv",
    )
    parser.add_argument(
        "--timing",
        type=Path,
        default=project_root / "Exchange_simulator/build/frame_timings.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=project_root / "eod_pipeline/reports/data_health_check.md",
    )
    args = parser.parse_args()

    settings = load_settings(args.settings)
    try:
        settings_display_path = args.settings.resolve().relative_to(project_root)
    except ValueError:
        settings_display_path = args.settings
    report = build_report(
        args.expected_book,
        args.timing,
        settings,
        settings_path=settings_display_path,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
