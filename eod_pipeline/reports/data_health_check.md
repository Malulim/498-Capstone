# LOBSTER AAPL 2012-06-21 Data Health Check

This report measures signal opportunities, not completed trades. Consecutive ticks above a threshold are counted separately; the later backtest engine must still apply position, in-flight, and fill logic.

## Executive conclusions

1. Across 9 configured Momentum signal-condition pairs, the stream produced **974 threshold crossings**. Across 9 Mean Reversion pairs, it produced **2,943 threshold crossings**.
2. The empirical threshold tables below show the magnitude needed for approximately 10, 50, or 200 raw signal rows during this session. These values can be compared with the configured search grid.
3. With `base_lot=50`, buy-order rejection rates under the configured CAD 50,000 notional limit are `pos_scalar=0.2`: **0.000%**; `pos_scalar=0.5`: **0.000%**; `pos_scalar=1`: **0.000%**; `pos_scalar=1.5`: **0.000%**.

## EOD settings

| Field | Value |
| --- | --- |
| Source | `eod_pipeline/config/eod_settings.json` |
| Schema version | 1 |
| Canonical SHA-256 | `f796d39e3541a71480b74adccdef6e019adf2352e13d929ed0232c2d3e936354` |
| Base lot | 50 shares |
| Configured notional limit | CAD 50,000 |

## Dataset and preprocessing facts

| Metric | Measured value |
| --- | --- |
| Rows | 400,391 |
| First timestamp (seconds after midnight) | 34200.004241176 |
| Last timestamp (seconds after midnight) | 57599.913117637 |
| Observed duration | 23399.908876 s |
| Average event rate | 17.111 messages/s |
| Peak fixed one-second bucket | 584 messages/s |
| Peak rolling one-second window | 675 messages/s |
| Mid-price range | $577.48 to $588.18 |
| Expected-book SHA-256 | `0b7212d798db8d348d9c7d94bf7c182a937b2ef76c35a20db3c961607e100b45` |
| Timing-file SHA-256 | `3fa23c3e15c609306921f2a736495e5043cd9a405cba60cfc6901c1cd6ec5917` |

### Burst rates by measurement window

| Rolling window (ms) | Maximum events in window | Normalized events/s |
| --- | --- | --- |
| 1,000 | 675 | 675 |
| 100 | 289 | 2,890 |
| 10 | 113 | 11,300 |
| 1 | 48 | 48,000 |

## Momentum grid: raw threshold crossings

| Lookback (messages) | Entry threshold | Crossings |
| --- | --- | --- |
| 5 | 0.000300 | 117 |
| 5 | 0.000400 | 11 |
| 5 | 0.000500 | 3 |
| 10 | 0.000300 | 207 |
| 10 | 0.000400 | 40 |
| 10 | 0.000500 | 9 |
| 20 | 0.000300 | 473 |
| 20 | 0.000400 | 92 |
| 20 | 0.000500 | 22 |

## Momentum absolute-return distribution

| Lookback | p50 | p90 | p99 | p99.9 | Maximum |
| --- | --- | --- | --- | --- | --- |
| 5 | 0.00000000 | 0.00005122 | 0.00012899 | 0.00023886 | 0.00052869 |
| 10 | 0.00000865 | 0.00006880 | 0.00015432 | 0.00027283 | 0.00054512 |
| 20 | 0.00002572 | 0.00009462 | 0.00018947 | 0.00031118 | 0.00059696 |

## Momentum empirical thresholds

| Lookback | Target rows | Threshold | Actual rows incl. ties |
| --- | --- | --- | --- |
| 5 | 10 | 0.00040870 | 10 |
| 5 | 50 | 0.00034124 | 50 |
| 5 | 200 | 0.00027352 | 203 |
| 10 | 10 | 0.00048730 | 10 |
| 10 | 50 | 0.00037530 | 51 |
| 10 | 200 | 0.00030677 | 200 |
| 20 | 10 | 0.00055427 | 11 |
| 20 | 50 | 0.00045275 | 51 |
| 20 | 200 | 0.00034979 | 201 |

## Mean Reversion grid: raw threshold crossings

| Window (messages) | Deviation threshold | Crossings |
| --- | --- | --- |
| 10 | 0.000200 | 326 |
| 10 | 0.000300 | 38 |
| 10 | 0.000500 | 2 |
| 20 | 0.000200 | 509 |
| 20 | 0.000300 | 69 |
| 20 | 0.000500 | 3 |
| 50 | 0.000200 | 1,722 |
| 50 | 0.000300 | 252 |
| 50 | 0.000500 | 22 |

## Mean Reversion absolute-deviation distribution

| Window | p50 | p90 | p99 | p99.9 | Maximum |
| --- | --- | --- | --- | --- | --- |
| 10 | 0.00000687 | 0.00004208 | 0.00010597 | 0.00019129 | 0.00053011 |
| 20 | 0.00001419 | 0.00005718 | 0.00012449 | 0.00021003 | 0.00054246 |
| 50 | 0.00002951 | 0.00008715 | 0.00016610 | 0.00027173 | 0.00064935 |

## Mean Reversion empirical thresholds

| Window | Target rows | Threshold | Actual rows incl. ties |
| --- | --- | --- | --- |
| 10 | 10 | 0.00037538 | 10 |
| 10 | 50 | 0.00028375 | 50 |
| 10 | 200 | 0.00022140 | 200 |
| 20 | 10 | 0.00041464 | 10 |
| 20 | 50 | 0.00031828 | 50 |
| 20 | 200 | 0.00024471 | 200 |
| 50 | 10 | 0.00053227 | 10 |
| 50 | 50 | 0.00042701 | 50 |
| 50 | 200 | 0.00031599 | 200 |

## Notional-limit feasibility

Using the ask as the conservative price, CAD 50,000 permits **85 to 86 shares** during the session (median **85**). The percentages below replicate `risk_guard.c` integer division.

| Position scalar | Order quantity | Buy rejected | Sell rejected |
| --- | --- | --- | --- |
| 0.2 | 10 | 0.000% | 0.000% |
| 0.5 | 25 | 0.000% | 0.000% |
| 1 | 50 | 0.000% | 0.000% |
| 1.5 | 75 | 0.000% | 0.000% |

## Spread distribution

| p50 | p90 | p99 | p99.9 | Maximum |
| --- | --- | --- | --- | --- |
| 15 cents | 24 cents | 36 cents | 61 cents | 92 cents |

| Spread floor | Snapshots at/above floor | Snapshots at/below floor |
| --- | --- | --- |
| 1 | 100.000% | 0.520% |
| 2 | 99.480% | 1.757% |
| 4 | 96.771% | 5.165% |

## Interpretation constraints

- The signal counts are diagnostics, not P&L or Sharpe results.
- Threshold suggestions target raw rows and do not account for repeated signals, cooldown, risk rejection, or the 0.1-second fill delay.
- The notional check follows the current C implementation and treats the integer-cent AAPL price as CAD without an explicit USD/CAD conversion.
- The design document's approximately 2,400 messages/s peak is not a one-second count: this run measured 584 in a fixed one-second bucket and 675 in any rolling one-second window. A shorter 100 ms burst normalized to one second measured 2,890 messages/s, so the document needs to state its burst-window definition.
- The current preprocessor reported 6,107 Modify/Delete references to orders opened before the trace window; it records these as pre-existing liquidity rather than failing the run.
