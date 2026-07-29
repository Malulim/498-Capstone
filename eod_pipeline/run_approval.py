"""Run risk review, configuration generation, and local approval gating."""

from __future__ import annotations

import argparse
from pathlib import Path

from eod_pipeline.approval.workflow import run_approval_workflow


EOD_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sweep-result",
        type=Path,
        default=EOD_DIR / "output" / "sweep_result.json",
    )
    parser.add_argument(
        "--settings",
        type=Path,
        default=EOD_DIR / "config" / "eod_settings.json",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=EOD_DIR / "output" / "approval_runs",
    )
    parser.add_argument("--operator-id", required=True)
    parser.add_argument("--max-drawdown-warning-cad", type=float)
    parser.add_argument("--min-trades", type=int)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    outcome = run_approval_workflow(
        sweep_result_path=args.sweep_result,
        settings_path=args.settings,
        output_root=args.output_root,
        operator_id=args.operator_id,
        max_drawdown_warning_cad=args.max_drawdown_warning_cad,
        min_trades=args.min_trades,
    )
    print(
        f"{outcome.approval_status}: dispatch={outcome.dispatch_status} "
        f"artifacts={outcome.run_directory}"
    )


if __name__ == "__main__":
    main()
