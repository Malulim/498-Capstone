"""Command-line entry point for the deterministic parameter sweep."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from eod_pipeline.backtest.snapshots import load_snapshots
from eod_pipeline.backtest.sweep import (
    file_sha256,
    run_sweep,
    write_sweep_result,
)
from eod_pipeline.settings import load_settings


EOD_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--regime",
        required=True,
        choices=("trending", "ranging", "volatile"),
    )
    parser.add_argument(
        "--settings",
        type=Path,
        default=EOD_DIR / "config" / "eod_settings.json",
    )
    parser.add_argument("--expected-book", type=Path, required=True)
    parser.add_argument("--timing", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=EOD_DIR / "output" / "sweep_result.json",
    )
    parser.add_argument(
        "--print-winner",
        action="store_true",
        help="print the complete selected candidate after writing the result",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = load_settings(args.settings)
    snapshots = load_snapshots(args.expected_book, args.timing)
    result = run_sweep(
        args.regime,
        settings,
        snapshots,
        source_hashes={
            "expected_book": file_sha256(args.expected_book),
            "frame_timings": file_sha256(args.timing),
        },
    )
    write_sweep_result(result, args.output)
    print(
        f"{result['selection_status']}: {result['strategy_id']} "
        f"candidate {result['winner']['candidate_index']} -> {args.output}"
    )
    for warning in result["warnings"]:
        print(f"WARNING: {warning}")
    if args.print_winner:
        print(
            json.dumps(
                {
                    "regime": result["regime"],
                    "selection_reason": result["selection_reason"],
                    "selection_status": result["selection_status"],
                    "strategy_id": result["strategy_id"],
                    "warnings": result["warnings"],
                    "winner": result["winner"],
                },
                sort_keys=True,
                indent=2,
                ensure_ascii=True,
                allow_nan=False,
            )
        )


if __name__ == "__main__":
    main()
