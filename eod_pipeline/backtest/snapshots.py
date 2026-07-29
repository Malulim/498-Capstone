"""Load the LOBSTER-derived top-of-book stream used by the EOD backtest."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


NANOSECONDS_PER_SECOND = 1_000_000_000


@dataclass(frozen=True)
class SnapshotArrays:
    """Columnar, integer-valued snapshot data aligned by sequence number."""

    seq: np.ndarray
    time_ns: np.ndarray
    bid_cents: np.ndarray
    ask_cents: np.ndarray
    mid_half_cents: np.ndarray
    spread_cents: np.ndarray

    def __len__(self) -> int:
        return len(self.seq)


def _integer_sequence(values: pd.Series, source: Path) -> np.ndarray:
    numeric = pd.to_numeric(values, errors="raise").to_numpy(dtype=np.float64)
    if not np.isfinite(numeric).all() or not np.equal(numeric, np.floor(numeric)).all():
        raise ValueError(f"{source}: seq must contain finite integers")
    return numeric.astype(np.int64)


def load_snapshots(
    expected_book_path: str | Path,
    timing_path: str | Path,
) -> SnapshotArrays:
    """Join expected-book and timing artifacts and validate their invariants.

    ``mid_half_cents`` intentionally equals ``bid + ask`` rather than their
    average. This exactly matches the PS strategy kernel's integer convention.
    """

    expected_book_path = Path(expected_book_path)
    timing_path = Path(timing_path)

    book = pd.read_csv(
        expected_book_path,
        usecols=["seq", "best_bid_cents", "best_ask_cents"],
    )
    timing = pd.read_csv(timing_path, usecols=["seq", "time"])

    book["seq"] = _integer_sequence(book["seq"], expected_book_path)
    timing["seq"] = _integer_sequence(timing["seq"], timing_path)

    if book["seq"].duplicated().any():
        raise ValueError(f"{expected_book_path}: duplicate seq values")
    if timing["seq"].duplicated().any():
        raise ValueError(f"{timing_path}: duplicate seq values")

    joined = book.merge(
        timing,
        on="seq",
        how="outer",
        validate="one_to_one",
        indicator=True,
        sort=True,
    )
    unmatched = joined["_merge"] != "both"
    if unmatched.any():
        sample = joined.loc[unmatched, ["seq", "_merge"]].head().to_dict("records")
        raise ValueError(f"snapshot/timing seq mismatch; examples: {sample}")
    joined = joined.drop(columns="_merge")

    seq = joined["seq"].to_numpy(dtype=np.int64)
    if len(seq) == 0:
        raise ValueError("snapshot stream is empty")
    if not np.all(np.diff(seq) == 1):
        raise ValueError("seq must be contiguous and strictly increasing")

    bid = pd.to_numeric(joined["best_bid_cents"], errors="raise").to_numpy(dtype=np.int64)
    ask = pd.to_numeric(joined["best_ask_cents"], errors="raise").to_numpy(dtype=np.int64)
    if np.any(bid <= 0) or np.any(ask <= 0):
        raise ValueError("bid and ask prices must be positive")
    if np.any(ask < bid):
        raise ValueError("ask price must not be below bid price")

    time_seconds = pd.to_numeric(joined["time"], errors="raise").to_numpy(dtype=np.float64)
    if not np.isfinite(time_seconds).all():
        raise ValueError("timestamps must be finite")
    time_ns = np.rint(time_seconds * NANOSECONDS_PER_SECOND).astype(np.int64)
    if np.any(np.diff(time_ns) < 0):
        raise ValueError("timestamps must be monotonic")

    return SnapshotArrays(
        seq=seq,
        time_ns=time_ns,
        bid_cents=bid,
        ask_cents=ask,
        mid_half_cents=bid + ask,
        spread_cents=ask - bid,
    )
