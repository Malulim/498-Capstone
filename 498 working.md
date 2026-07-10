# 1. Introduction

## 1.1 Motivation

Algorithmic trading systems are strongly constrained by end-to-end event latency: market data must be decoded, converted into a usable order book state, evaluated by a strategy, checked for risk, and converted into an order message before the opportunity disappears. A software-only implementation running on a general-purpose Linux host incurs kernel network stack and scheduler overhead before any strategy logic executes; published FPGA-based trading systems quantify this cost directly — a hardware datapath has been shown to achieve roughly a 4x latency reduction over a conventional software-based pipeline [1], and specialized hardware implementations report sub-microsecond response, with one 10 Gigabit Ethernet FPGA trading system achieving approximately 433 nanoseconds from market packet analysis to order trigger [2]. The current AQTA design therefore treats latency elimination as the central design problem rather than as a late-stage optimization.

AQTA addresses this by adopting a hardware-software co-designed architecture: the time-critical, deterministic portions of the pipeline — packet decoding and order-book maintenance — are implemented directly in programmable logic, while strategy evaluation, logging, and overnight reconfiguration remain in software for flexibility. This division follows the same rationale used throughout the FPGA trading literature cited above: push fixed, latency-critical operations into hardware, and keep the parts that need to change often in software.

## 1.2 Project Objective

The primary objective of this project is to design and implement an ultra-low-latency, hardware-accelerated algorithmic trading platform. By partitioning the pipeline across programmable logic and an embedded processor, the system targets deterministic, microsecond-class tick-to-order latency — roughly an order of magnitude faster than a comparable software-only pipeline — while supporting operator-approved overnight strategy reconfiguration.

The essential prototype performs market-data ingestion, protocol decoding, and order-book maintenance in programmable logic (PL) to keep the time-critical path deterministic; passes the resulting order-book state to a configurable strategy running on the ARM processing system (PS), which selects among several pre-loaded strategies and applies a RiskGuard filter; and returns the validated decision to the PL, where it is encoded and transmitted back onto the exchange link.

The secondary objective is an End-of-Day (EOD) optimization pipeline that classifies the next trading day's market regime from historical data, searches a bounded parameter space to select a strategy configuration for that regime, and backtests the selected configuration before presenting it to a human operator for approval; only an approved configuration is loaded into the live system for the next trading session.

**Prototype Scope and Constraints** The prototype scope is intentionally bounded to one simulated exchange and one equity symbol, which keeps the project focused on the core engineering problem of deterministic hardware/software partitioning while avoiding real-money financial risk and the complexity of multi-venue market-data normalization. Rather than implementing an industry-standard compressed protocol such as FAST, the prototype defines a fixed-width binary custom protocol for market data and order messages, narrowing the PL-side protocol decoder to a fixed, minimal field set and keeping decoding latency low, at the cost of interoperability with real exchange feeds. The prototype targets paper trading and simulation: strategy decisions drive a simulated exchange, not a live brokerage account.

## 2. System Specifications

### 2.1 Functional Specifications

| ID | Specification | Description | Verification Method | Essential |
| --- | --- | --- | --- | --- |
| **FS1** | Packet-to-snapshot latency | Top-of-book snapshot readable by the PS within ≤ 1.5 μs of packet arrival at the PL MAC. | Logic-analyzer timing from MAC RX to snapshot-register write, reference packet sequence. | **Y** |
| **FS2** | Decision-to-order latency | Trading decision (BUY/SELL/HOLD) produced and order packet transmitted within ≤ 30 μs of a top-of-book update, 99th percentile. | PMU timing vs. Wireshark capture over 1000 updates. | **Y** |
| **FS3** | Order risk limits | Reject orders exceeding configurable limits, with hard ceilings of: notional > $50,000 CAD; position > 1,000 shares; rate > 1,000 orders/s; in-flight > 100 — a loaded configuration may tighten these but never exceed them. | One violating test order per limit, confirm REJECT + logged reason. | **Y** |
| **FS4** | Configurable startup | Load an externally-supplied strategy configuration before processing any market data. | Change config, restart, confirm active strategy via log. | **Y** |
| **FS5** | Bounded activity logging | Persist trading activity within a bounded memory budget, no OOM under sustained operation, exportable for offline use. | Stress test with >10M ticks, no OOM; export contains one entry per decision. | **Y** |
| **FS6** | Regime classification | Classify next trading day's regime into ≥ 3 distinguishable states. | Run on 6 months of OHLCV data, confirm ≥ 3 regimes assigned. | **Y** |
| **FS7** | Parameter search | Search ≥ 9 parameter combinations per regime, select the one maximizing a defined metric (e.g. Sharpe). | Run twice on identical input, confirm bit-identical output. | **Y** |
| **FS8** | Human-approved deployment | A new strategy configuration is not loaded into the live system without explicit operator approval. | Confirm no transmission to SoC before manual approval. | **Y** |
| **FS9** | Text ingestion | Ingest ≥ 10 text assets/day via HTTPS and extract a structured event record from each. | Mock server, confirm ingestion and extraction. | **N** |
| **FS10** | Sentiment-based limit adjustment | Compute a sentiment score in [−1, +1] per event; negative sentiment reduces next-day position limits, neutral/positive leaves them unchanged. | Labeled reference records, confirm score range, polarity, and adjustment behavior. | **N** |
| **FS11** | Live status output | Real-time order-book/decision report via Debug UART, printed to console and logged to file. | Confirm console + log output during an active session. | **N** |
| **FS12** | EOD pipeline logging | Log pipeline stage, classified regime, selected strategy/parameters, backtest Sharpe, and approval status as each stage completes. | Run full cycle, confirm one log entry per stage transition. | **N** |
| **FS13** | Order packet format | Fixed-length binary format with order ID, symbol, side, quantity, and price, documented as a standalone protocol spec. | Parse a captured packet against the documented layout. | **Y** |
| **FS14** | In-flight order tracking | Track state of every in-flight order, up to 100 concurrent, without corruption or loss. | Drive in-flight count to the limit, confirm correct state via log inspection. | **Y** |

### 2.2 Non-Functional Specifications

| ID | Specification | Description | Verification Method | Essential |
| --- | --- | --- | --- | --- |
| **NFS1** | End-to-end latency | Total latency from MAC RX to MAC TX ≤ 50 μs typical. | Logic-analyzer measurement on a reference loopback packet. | **Y** |
| **NFS2** | Link reliability | Zero unexplained frame drops over a 10-minute continuous test window. | Wireshark capture, confirm frame count. | **Y** |
| **NFS3** | Hardware cost | Physical components (excl. SoC board, host PC, monitors) ≤ $1,000 CAD total. | Sum itemized purchase receipts. | **Y** |
| **NFS4** | Session stability | Runs a full 6.5-hour simulated session without crash, hang, or unrecovered error. | Full-session run, inspect logs for fatal errors. | **Y** |
| **NFS5** | EOD pipeline runtime | Full EOD pipeline (ingestion → classification → optimization → approval prompt) completes within 30 minutes. | Timed run on 1 year of reference OHLCV data. | **N** |
| **NFS6** | FPGA resource utilization | < 75% LUTs and < 85% Block RAMs on XC7Z020, timing closure at 125 MHz. | Vivado utilization/timing reports, WNS > 0 ns. | **Y** |
| **NFS8** | Fault recovery | On a recoverable fault (checksum failure, FIFO overflow, invalid config), discard the input, log a fault code, continue without restart. | Inject each fault type, confirm logged fault code and resumed processing. | **Y** |
| **NFS9** | Ingest throughput | Sustain ≥ 1.2M msg/s ingestion at full Gigabit line rate without drops or stalls. | Inject a line-rate PCAP, confirm zero drops via drop counters. | **Y** |


# 3.1 PL (FPGA) Market Data Path Subsystem

All numeric analysis in 3.1.4 is derivable on paper today (line-rate arithmetic, cycle budgets, datasheet resource math) — no code required.

---

## 3.1.1 Overview and Specification Mapping

The PL subsystem implements the entire wire-to-snapshot market data path and the order egress path in programmable logic on the XC7Z020. On the receive side, it terminates the point-to-point Gigabit Ethernet link from the exchange simulator, validates and parses each custom UDP market data packet at fixed byte offsets, maintains a 10-level bid / 10-level ask limit order book (an L3-to-L1/L2 aggregation), and publishes the resulting top-of-book snapshot to the PS through an AXI-Lite register bank on M_AXI_GP0 (snapshot fields plus an incrementing `seq` register, committed atomically in one clock edge). On the transmit side, it receives risk-validated order fields written by the PS into the same register bank, begins encoding on the doorbell-register write strobe, encodes them into the fixed-length binary order format defined by FS13, and transmits them through the same PL GbE interface.

The subsystem exists because the software network path cannot meet the project's latency specifications: a conventional Linux socket path incurs interrupt handling, kernel protocol stack traversal, and kernel-to-user copies that together cost tens to hundreds of microseconds per packet, which is incompatible with the ≤ 1.5 μs decode budget of FS1. Placing the parse and book-build stages in the PL removes the operating system from the market-data critical path entirely.

This subsystem is directly responsible for the following specifications:

| Spec | Role of PL subsystem |
|---|---|
| **FS1** | Sole owner: packet arrival → decoded top-of-book snapshot available to PS in ≤ 1.5 μs. |
| **FS13** | Sole owner of the egress half: order packets must conform to the fixed-length binary format. |
| **NFS1** | Owns the two PL segments (RX decode, TX encode) of the ≤ 50 μs end-to-end budget (300 μs ceiling applies to the superseded interrupt design). |
| **NFS2** | Owns link integrity: zero unexplained frame drops over a 10-minute window. |
| **NFS6** | Owns the resource envelope: < 75% LUT, < 85% BRAM at 125 MHz with WNS > 0. |
| **NFS9** | Owns ingest throughput: ≥ 1.2 M msg/s sustained at line rate without MAC RX stall. |
| **NFS8 (partial)** | Owns the hardware fault path: checksum-fail discard and FIFO-overflow handling with fault counters. |
| **NFS4 (partial)** | Hardware fault paths (FCS discard, FIFO-overflow handling, drop counters) keep line-rate faults from escalating into a session-ending hang; primary ownership of the 6.5-hour stability requirement remains with the PS (3.2.1). |

Figure 3.1 shows the PL block structure and the shared AXI-Lite register bank at the PS boundary, using the stage names adopted throughout this section (Protocol Decode / Build Order Book / Protocol Encode).

---

## 3.1.2 Engineering Design Process

Four significant design decisions shaped this subsystem. Each is presented with the alternatives considered and the rationale for the selection; where the rationale is quantitative, the supporting calculation appears in Section 3.1.4.

### Decision 1 — Network path placement: PS-side vs. PL-side

| Alternative | Description | Outcome |
|---|---|---|
| A. PS-side socket parsing | Receive UDP through the PS hardened GEM MAC and Linux sockets; parse in user space. | **Rejected.** Kernel networking and scheduler jitter are incompatible with FS1 (≤ 1.5 μs) and consume most of the NFS1 worst-case budget before any useful work occurs. |
| B. Full PL path (selected) | Terminate the PHY on a PL I/O bank and implement MAC, parse, and book entirely in fabric. | **Selected.** The event is decoded before the PS ever observes it; latency is deterministic and clock-cycle countable. |

Alternative B is only feasible because the selected carrier board exposes a dedicated **PL-side Gigabit Ethernet (RJ45)** in addition to the PS-side Ethernet — this was a primary board-selection criterion (the sibling board “启明星” exposes only the PS-side PHY and cannot implement Alternative B at all, while “领航者” includes 1× PS GbE + 1× PL GbE). The target board for this report is the 正点原子领航者 ZYNQ7020 开发板 (XC7Z020CLG400-2I); the board reference manual is the authoritative source for the PL Ethernet PHY wiring (REF-3). This decision also constrained the device choice: the PL path plus PS-interface infrastructure must fit NFS6's resource envelope, which motivated the XC7Z020 (53,200 LUTs) over the XC7Z010 (17,600 LUTs) — see Table 3.1.7.

### Decision 2 — MAC layer implementation: vendor IP vs. minimal custom MAC

| Criterion (weight) | Xilinx TEMAC IP (selected) | Minimal custom MAC |
|---|---|---|
| Development & verification effort (40%) | Low — pre-verified vendor IP, wizard-generated, reference designs and example testbenches available | High — every state machine (preamble/SFD detect, FCS check/generate, framing) designed and verified from scratch |
| Resource cost (20%) | Medium-high (multi-thousand LUT + license terms) | Low — RX/TX framing + CRC only |
| Latency determinism (20%) | Medium — fixed, datasheet-specified pipeline latency; not cycle-exact but bounded | High — no unused feature logic in path |
| Protocol generality (20%) | High | Low — sufficient for a point-to-point link, but this project doesn't need the generality either way |
| **Weighted result (1–5 scale)** | **4.0 — Selected** | 3.2 |

FS1's cycle budget (3.1.4.2) closes with at least 32% margin even under a pessimistic assumption for TEMAC's own latency, so the project does not need to fight for every nanosecond at the MAC layer — development effort is the binding constraint here, not latency. The literature agrees: Boutros et al. treat networking as solved and simply instantiate Xilinx's off-the-shelf cores [6], and even Kao et al.'s 433 ns 10G system — tighter than this project's budget — absorbs its vendor PCS/PMA core's ~25 ns fixed latency rather than building custom [2]. The PS-hardwired case in Osuna et al. [7] doesn't apply here, since Decision 1 already selected a board with an independent PL-side PHY. TEMAC's exact fixed latency is `OPEN` pending its datasheet (a 1 Gbps core, not directly comparable to Kao's 10G figure), but that order of magnitude suggests it fits the existing margin. This decision is scoped to MAC framing only (3.1.3.1 Stage 1); the custom protocol decode and order-book stages above it (Stages 2–5) are unaffected. (Scoring: cost-type criteria score higher when the cost is lower; TEMAC = 0.4×5 + 0.2×2 + 0.2×3 + 0.2×5 = 4.0, custom = 0.4×2 + 0.2×5 + 0.2×5 + 0.2×2 = 3.2.)

### Decision 3 — Parse architecture: store-and-forward vs. cut-through streaming parse

A store-and-forward design buffers the complete frame, verifies FCS, then parses. A cut-through design slices fields at their fixed byte offsets as bytes stream in from the MAC, so all fields are already latched when the final FCS byte arrives.

The quantitative case (full derivation in 3.1.4.2): the frame body alone occupies ~560 ns of the 1,500 ns FS1 budget. Store-and-forward would serialize an additional walk over the buffered frame after reception — a second traversal that alone would consume more than a third of the remaining budget for zero benefit — whereas cut-through means the ~940 ns remaining after frame-body reception only has to cover TEMAC's own ingest latency (assumed 0.1–0.4 μs, 3.1.4.2) plus 56 ns of custom-logic book update and snapshot commit. Cut-through is only safe because the packet format (Table 3.1.4) has fixed offsets: no length-dependent field positions exist, so slicing requires no lookahead. This is the same property that drove the format decision in Section 2: fixed-offset binary message layouts are an established market-data protocol class (NASDAQ ITCH-family feeds use fixed-length binary messages in the same style), and cut-through applies to that class; variable-length FAST-class encodings (presence maps, stop-bit fields) instead require stateful sequential decoding and framing/length handling that aggravates decoding complexity [1].

**Commit policy.** Cut-through creates one hazard: fields are latched before FCS validates the frame. The design therefore stages the parsed event in a holding register and commits it to the order book only on FCS pass; on FCS fail the event is discarded and a `parse_error` counter increments (NFS8 path). This costs one cycle of commit latency and zero throughput, versus the alternative of speculative book update with rollback, which was rejected because rollback of an aggregated price level requires storing pre-update state for every level touched — added area and a new failure mode for negligible latency gain.

### Decision 4 — Order book storage: BRAM-indexed structure vs. fixed register array

| Alternative | Description | Outcome |
|---|---|---|
| BRAM price-indexed table | Hash or direct-index price levels into Block RAM; scales to deep books and multiple symbols. | **Rejected.** BRAM is the right tool at large scale — Basiri's FPGA order book stores levels directly in Block RAM [5], and Boutros et al.'s 4096-level (2¹²) heap-like binary tree book (node *j*'s children at 2*j*/2*j*+1) needed BRAM once depth made a register array LUT/routing-infeasible [6]. But sustaining throughput there required HLS-directed partitioning across many BRAM segments, some holding only a few records, driving BRAM utilization to 22% (474 blocks) for capacity the logic didn't structurally need [6]. This project's book sits at the opposite end of that curve — 10 bid + 10 ask levels, single symbol — so BRAM here would reproduce that fragmentation at an even smaller, more wasteful scale. |
| Fixed register array (selected) | 10 bid + 10 ask levels as flip-flop registers; combinational best-price selection. | **Selected.** A direct register write for the addressed level, plus a combinational best-price reduction over the small, fixed 10-level array — no BRAM block wasted on a partition this small. Timing closure for the reduction is `OPEN` pending RTL analysis (3.1.4.2), but a 10-element compare tree is a modest combinational depth against the 8 ns period at 125 MHz. |

Updates addressing a price level outside the 10-level window are discarded and counted (`dropped_out_of_window`) — the counter keeps the discard observable during verification without altering trading behaviour. He et al.'s hybrid design — a fixed array plus a bitonic sorting network for the top 5 levels [3] — was considered and rejected: that network exists to make re-sorting *deep* books tractable, and at this project's 10-level scope the combinational reduction above is already cheap enough that a sorting network buys nothing.

### Decision 5 — Price field precision: integer cents vs. sub-cent unit

| Alternative | Description | Outcome |
|---|---|---|
| 10⁻⁴-dollar unit | A finer-grained price unit that avoids any rounding. | **Rejected.** Costs nothing in field width — a u32 still spans $429,496 at this resolution — but touches worked constants and examples across 3.1/3.2/3.3 for a small fraction of events; not worth the churn for the prototype. |
| Integer cents (selected) | `price` fields (Table 3.1.4, 3.1.5) encode unsigned integer cents. | **Selected.** Simpler and sufficient for the vast majority of events. Sub-cent prices are rounded half-to-even at the encoder and counted in a `price_rounded` diagnostic, so the rare case is observable rather than silently dropped. |

---

## 3.1.3 Final Design Details

### 3.1.3.1 Receive pipeline

The RX path is a five-stage streaming pipeline at 125 MHz (Figure 3.2 — *placeholder: per-stage pipeline diagram with cycle annotations*):

1. **MAC RX (Xilinx TEMAC).** The vendor core handles RGMII DDR capture from the PHY, preamble/SFD alignment, and FCS computation, presenting the frame to custom logic over its AXI4-Stream RX interface: payload bytes stream out as they arrive, with `tlast`/`tuser` marking end-of-frame and FCS pass/fail; a thin wrapper matches the destination MAC against the hardcoded constant on top of that stream. Non-matching frames are dropped at this stage without downstream activity.
2. **IP/UDP header parse.** Fixed-offset validation of EtherType (0x0800), IP protocol (17), destination IP, and destination UDP port — all compile-time constants of the point-to-point link. IP header checksum is verified; the UDP checksum is not validated — the simulator emits UDP checksum = 0 (legal for IPv4 per RFC 768: zero means "no checksum") and the parser ignores the field, because payload integrity on this single-segment point-to-point link is already covered end-to-end by the Ethernet FCS (commit gate, stage 4).
3. **Protocol decode.** Field slicing of the custom payload (Table 3.1.4) into a staged event register as bytes arrive.
4. **Commit gate.** On TEMAC's `tuser` frame-good signal at `tlast`, the staged event commits; on frame-bad, discard + `parse_error` increment (NFS8).
5. **Order book update.** Aggregation of the committed L3 event (Add/Modify/Delete keyed by `order_id`) into the affected side/level; for Modify, `qty` is the new absolute remaining quantity (not a delta), and for Delete `qty` is ignored (encoder sets it to 0). Combinational extraction of the new top-of-book; single-cycle atomic commit of the snapshot registers and `seq` increment in the register bank.

### 3.1.3.2 Packet formats (FS13 interface contract)

Table 3.1.4 — Custom market data payload (RX).

| Field | Bit offset | Width (bits) | Encoding |
|---|---|---|---|
| msg_type | 0 | 8 | 0x01 Add, 0x02 Modify, 0x03 Delete, 0x04 reserved (execution report extension; not emitted in prototype) |
| symbol | 8 | 16 | Numeric symbol ID (single-equity prototype; constant 1) |
| price | 24 | 32 | Unsigned integer cents; sources carrying finer precision are rounded half-to-even at the encoder and counted in `price_rounded` diagnostics |
| qty | 56 | 32 | Unsigned share quantity (validated against real ITCH-derived data); for msg_type 0x02 (Modify), `qty` is the order's new absolute remaining quantity (not a delta); for msg_type 0x03 (Delete), `qty` is ignored by the parser and set to 0 by the encoder |
| side | 88 | 8 | 0x01 Bid, 0x02 Ask |
| order_id | 96 | 32 | Unique within simulator session (validated against real ITCH-derived data) |
| seq_num | 128 | 32 | Monotonic simulator-side sequence number (wrap allowed); supports attributable drop accounting (NFS2) and loop-boundaries in throughput tests |
| pad | 160 | 32 | Reserved = 0; fixes payload length to 24 B |

**Scope note.** The protocol deliberately carries book-affecting events only. Trading-halt and hidden-execution events present in some source feeds are consumed by the simulator and not forwarded to the PL.

Table 3.1.5 — Order packet payload (TX, FS13). This is the standalone protocol spec FS13 requires and the layout FS2's verification procedure parses against.

| Field | Bit offset | Width (bits) | Encoding |
|---|---|---|---|
| order_id | 0 | 32 | Client-assigned order identifier, echoed from the originating decision (FS14 tracking key) |
| symbol | 32 | 16 | Numeric symbol ID (single-equity prototype; constant 1, matches Table 3.1.4) |
| side | 48 | 8 | 0x01 Buy, 0x02 Sell |
| qty | 56 | 32 | Unsigned share quantity, post-Risk-Guard (FS3-bounded) |
| price | 88 | 32 | Unsigned integer cents (Decision 5) |
| pad | 120 | 8 | Reserved = 0; fixes payload length to 16 B |

### 3.1.3.3 Order book register layout

| Register group | Entries | Fields per entry | Purpose |
|---|---|---|---|
| Bid book | 10 | price_cents (32b), aggregate_qty (32b) | Highest active bid levels |
| Ask book | 10 | price_cents (32b), aggregate_qty (32b) | Lowest active ask levels |
| Top-of-book snapshot | 1 | best_bid_price, best_bid_qty, best_ask_price, best_ask_qty | Published to the PS-visible register bank (with `seq`) on each committed update |
| Diagnostic counters | 4+ | parse_error, fcs_fail, dropped_out_of_window, tx_backpressure | NFS2/NFS8 observability |

### 3.1.3.4 PS interface and transmission pipeline

The PS boundary is a single AXI-Lite slave register bank on M_AXI_GP0 (full map in Section 3.2.3.1); the PL is never a bus master, and the HP ports are unused. Snapshot publication is a one-clock-edge atomic commit of all snapshot registers plus the `seq` increment — hardware-side tearing is impossible by construction; the multi-read consistency problem exists only on the PS side and is solved there by seqlock (3.2.3.1). FS1's measurable endpoint is the `seq`-increment write enable, observable with an ILA.

The TX path is a four-stage pipeline mirroring the RX structure in 3.1.3.1:

1. **Order-field write.** The PS writes the risk-approved order fields into the AXI-Lite register bank, payload first.
2. **Doorbell strobe.** The PS writes the doorbell register last; the strobe itself launches the encode stage on the following cycle. A `tx_ready` flag provides flow control (structurally uncontended — see 3.2.4.1).
3. **Protocol Encode.** Packs the sampled fields into the Table 3.1.5 fixed-offset layout.
4. **MAC TX (Xilinx TEMAC).** The vendor core frames the encoded payload, computes and appends the Ethernet FCS, and transmits over RGMII to the PHY.

---

## 3.1.4 Quantitative Technical Analysis

### 3.1.4.1 Line-rate throughput (NFS9)

The maximum packet rate of the link is fixed by arithmetic, and the design must not stall below it. With the 24-byte payload (Table 3.1.4):

```
Frame on wire = preamble/SFD 8 + Eth header 14 + IPv4 20 + UDP 8
 + payload 24 + FCS 4 + inter-frame gap 12
 = 90 bytes = 720 bits
Line-rate ceiling = 10^9 b/s ÷ 720 b = 1.389 M packets/s
```

(For any payload ≤ 18 B the 64-byte Ethernet minimum applies and the ceiling rises to 1.488 Mpps — the classic 64-byte wire-speed figure; our payload is above the pad threshold, so 1.389 Mpps governs.)

The NFS9 target of ≥ 1.2 M msg/s therefore means the pipeline must sustain the true wire-speed ceiling of this link, 1.389 Mpps, with zero drops. Every stage consumes one octet per cycle at 125 MHz with initiation interval 1, so a new frame can begin on the cycle after the previous frame's IFG: the pipeline is never the bottleneck, the wire is, and sustaining full-duplex line rate is baseline behavior for any vendor MAC core, TEMAC included. This matches the range reported for comparable single-feed FPGA book builders (1.2–1.5 M msg/s) [3] and hardware feed processing studies that exceed gigabit wire-rate ceilings on faster links [4]. Closed by construction; the PCAP injection test in the verification plan confirms it empirically.

### 3.1.4.2 FS1 latency budget decomposition

FS1 allows 1,500 ns from MAC RX to the snapshot becoming readable by the PS (endpoint: `seq`-increment write enable). At 125 MHz (8 ns/cycle):

| Stage | Cycles | Time | Basis |
|---|---|---|---|
| Frame body reception (70 B post-preamble, streaming via TEMAC's AXI4-Stream RX) | 70 | 560 ns | 1 octet/cycle out of TEMAC; parse overlaps reception (Decision 3), so this is reception time, not reception + parse |
| FCS-good latch + commit gate | 2 | 16 ns | Registered `tuser`/`tlast` compare + commit enable (TEMAC computes the FCS; custom logic only latches the result) |
| Order book update + top-of-book extract | 4 | 32 ns | Register-array write + combinational best-price mux, registered; pending RTL simulation to confirm the 4-cycle timing |
| Snapshot register commit + `seq` increment | 1 | 8 ns | Single-edge atomic write into the register bank |
| **Custom-logic subtotal** | **77** | **616 ns** | **Design arithmetic; excludes TEMAC's own ingest latency (below), which the team does not control** |

**TEMAC ingest latency (PHY-to-AXI4-Stream, including preamble/SFD sync).** This is vendor pipeline delay, not something the team designs, and it cannot be pinned down without synthesis and hardware — neither of which is available for this report (see Decision 2). Rather than leave it as an unresolved placeholder, it is treated as a bounded assumption and checked for sensitivity: Kao et al. report ~25 ns for a comparable vendor PCS/PMA core at 10 Gbps [2]; scaling conservatively for a 1 Gbps core with additional AXI4-Stream conversion, this analysis assumes 0.1–0.4 μs.

| TEMAC latency assumption | Total FS1 path | Margin against 1,500 ns |
|---|---|---|
| Optimistic (0.1 μs) | 716 ns | 52% |
| Pessimistic (0.4 μs) | 1,016 ns | 32% |

Even at the pessimistic end of the assumed range, FS1 closes with 32% margin, independent of the exact vendor figure. This is a direct consequence of the register-interface design in 3.2.2 Decision 3: the AXI HP write latency into DDR3 under PS memory contention has been eliminated from the FS1 path entirely, leaving TEMAC's own latency as the only remaining unknown, and the sensitivity check above shows it is not schedule-critical either way. Published HFT/market-data FPGA systems report sub-microsecond pipeline latencies on faster MACs (e.g., hundreds of nanoseconds) in similar parse→decision trigger chains, supporting the feasibility of microsecond-class PL budgets [2], [6].

### 3.1.4.3 Resource envelope (NFS6)

XC7Z020 PL resources: 53,200 LUTs, 106,400 FFs, 140 × 36 Kb BRAM (4.9 Mb), 220 DSP. NFS6 caps usage at 75% LUT (39,900) and 85% BRAM (119 blocks).

| Component | FF estimate (arithmetic) | LUT estimate | BRAM |
|---|---|---|---|
| Order book registers | 20 levels × 64 b + snapshot 128 b + counters ≈ 1.5 K | ≈ 1 K — per side (bid/ask), 10 parallel 32-bit price-match comparators (~200 LUT) for level lookup on update, plus a 9-compare tournament reduction (~250 LUT) for best-price extraction; ×2 sides | 0 |
| Xilinx TEMAC IP (RX+TX, CRC-32) | ≈ 1–2 K | ≈ 2–4 K (pending Vivado utilization report) | 2–4 (internal FIFOs) |
| Header parse/encode + protocol decode/encode | ≈ 0.5 K | ≈ 1 K (constant-compare + slicing) | 0 |
| AXI-Lite register bank (GP0 slave) | ≈ 0.5 K | ≈ 0.5–1 K (wizard-generated slave + decode; pending Vivado utilization report) | 0 |
| **Preliminary total** | **≈ 4–5 K FF** | **≈ 5–7 K LUT ≈ 9–13% of device** | **≪ 10 blocks ≈ < 8%** |

The estimate sits a factor of ~5–6 below the NFS6 LUT ceiling, which is the deliberate margin motivating Decision 1's board choice: the same architecture on the XC7Z010 (17,600 LUTs) would already commit ~30–40% of the device before any capstone-scope growth (e.g., deeper book, added diagnostics). These preliminary estimates will be replaced with a post-implementation Vivado utilization and timing summary; NFS6's pass gate is WNS > 0 at 125 MHz.

---

## 3.1.5 Specification Compliance Summary

| Spec | How the final design satisfies it | Evidence status |
|---|---|---|
| FS1 | Cut-through parse overlaps reception; 77-cycle custom-logic path plus TEMAC vendor latency (assumed 0.1–0.4 μs), 32–52% margin depending on the assumption (3.1.4.2) | Closed by arithmetic under the assumed range; pending RTL sim + ILA measurement |
| FS13 | Fixed-offset TX encoder implements Table 3.1.5 byte-exactly | Layout closed; pending encoder RTL implementation |
| NFS1 (PL share) | RX segment ≤ 1.5 μs; TX encode segment is a fixed ~80-cycle (≈ 0.65 μs) path by the same octet-per-cycle arithmetic as 3.1.4.2 — doorbell latch + ~75 B order frame streamed at 1 octet/cycle | Analytical |
| NFS2 | Point-to-point link, no switch, elastic FIFO sized for IFG-less bursts; drop counters make every discard attributable | Pending 10-min Wireshark test |
| NFS6 | ~9–13% LUT estimate vs. 75% cap (3.1.4.3) | Pending synthesis |
| NFS9 | II=1 octet pipeline sustains the 1.389 Mpps wire ceiling (3.1.4.1) | Closed by construction; PCAP injection test confirms |
| NFS8 | FCS-fail discard + fault counters; no manual restart path in PL | Pending fault-injection test |

---
@cye: 记得加课程 + 加reference list (TEMAC & 领航者)

# 3.2 PS (ARM OS Layer) Strategy & Risk Subsystem

## 3.2.1 Overview and Specification Mapping

The PS subsystem is the software half of the intraday trading loop, on the dual-core ARM Cortex-A9 of the XC7Z020. Core 1, isolated from the Linux scheduler, busy-polls the PL's snapshot registers, evaluates the active strategy, filters proposed orders through the Runtime Risk Guard, and writes risk-approved orders back via the register bank and doorbell. Core 0 owns everything latency-tolerant: config loading (FS4), the Execution Logger and export (FS5), the Debug-UART feed (FS11), fault logging (NFS8), and HOLD-mode supervision.

The division of labour with the PL follows one rule established in 3.1: the PL owns everything that must be deterministic at wire speed; the PS owns everything that must be **changeable** — strategy formulas, parameters, and risk limits are all expected to be replaced nightly by the EOD pipeline (Section 3.3), and iterating on them must not require re-synthesis.

| Spec | Role of PS subsystem |
|---|---|
| **FS2** | Sole owner of the software segment: observed snapshot update → decision (BUY/SELL/HOLD) → order handed to PL, inside the ≤ 30 μs budget. |
| **FS3** | Sole owner: reject orders violating notional (> $50,000 CAD), position (> 1,000 shares), rate (> 1,000 orders/s), or in-flight (> 100) limits, with logged reason codes. |
| **FS14** | Sole owner: track every in-flight order's state for the traded symbol, up to the configured capacity, and expose terminal outcomes to the logger. |
| **FS4** | Sole owner: load and validate the externally supplied strategy configuration before any market data is processed. |
| **FS5** | Sole owner: bounded-memory persistence of decisions/outcomes/snapshots over > 10 M injected ticks, plus full-session export. |
| **FS11 (non-ess.)** | Owner of the SoC side: real-time book/decision report over Debug UART. |
| **NFS1 (PS share)** | Owns the dominant software segment of the ≤ 50 μs typical budget. |
| **NFS4** | Primary owner: 6.5-hour session with no crash/hang/unrecovered error. |
| **NFS8 (partial)** | Owner of software fault handling: malformed-config rejection at load time, fault-coded logging, continue-without-restart. |

Figure 3.3 shows the PS runtime structure. *(Figure placeholder — must reuse the block-diagram labels above; the register bank appears once, on the PL/PS boundary, with the Feature Parameters and Trade Decision arrows passing through it.)*

---

## 3.2.2 Engineering Design Process

### Decision 1 — Hardware/software boundary: strategy in PL vs. strategy in PS

| Alternative | Description | Outcome |
|---|---|---|
| Strategy in PL | Implement decision rules as fabric logic; sub-microsecond tick-to-order. | **Rejected.** Strategy formulas, thresholds, and the active strategy identity change nightly via the EOD JSON config (FS4/FS8). A PL implementation would either require re-synthesis per change (hours per iteration, incompatible with the EOD cycle) or a parameterized rule engine in fabric whose design and verification cost exceeds the entire remaining PL budget. Industry practice concurs: fixed protocol/risk primitives migrate to hardware, iterating alpha logic stays in software. |
| Strategy in PS (selected) | Evaluate rules on the Cortex-A9 against the observed snapshot. | **Selected.** A software strategy is reconfigured by rewriting a struct, tested with host-compiled unit tests, and debugged with standard tooling. The cost — microseconds instead of nanoseconds — is affordable: QTA 3.2.4.1 shows the FS2 budget closes with ~5.5× margin. |

This decision is the reason FS2's budget (30 μs) is roughly an order of magnitude looser than FS1's (1.5 μs): the specs deliberately price in the software boundary, and Decisions 2–3 carry the burden of proving the priced-in budget is achievable.

### Decision 2 — Operating environment: bare-metal vs. Linux vs. Linux with core isolation

| Criterion (weight) | Bare-metal (both cores) | Linux (selected) |
|---|---|---|
| Hot-path determinism (30%) | Best | Poor as-is — scheduler jitter on the hot path |
| TCP/IP, filesystem, UART tooling for FS4/FS5/FS11 (30%) | None — must port a network stack for the PS GbE paths | Full, native |
| Team development & debug cost (25%) | High | Low — standard toolchain, matches team's embedded-Linux experience |
| NFS4 6.5-hour robustness path (15%) | All failure handling hand-rolled | Mature, observable (logs, watchdogs) |
| **Weighted result (1–5 scale)** | 2.6 | **4.1 — Selected** |

Scoring: cost-type criteria score higher when the cost is lower; bare-metal = 0.3×5 + 0.3×1 + 0.25×2 + 0.15×2 = 2.6, Linux = 0.3×2 + 0.3×5 + 0.25×5 + 0.15×5 = 4.1.

Bare-metal prices the FS4/FS5/FS8 network stack and filesystem in as a porting project that adds no marks. Linux is selected with the explicit obligation to fix its hot-path weakness: core 1 is pulled out of the scheduler entirely via `isolcpus`, which is what Decision 3 relies on. The distribution is PetaLinux, chosen over a generic Ubuntu-based image for its Xilinx-supplied BSP/device-tree support of the AXI-Lite GP port and `isolcpus`; PREEMPT_RT isn't needed since the isolated core never re-enters the scheduler.

### Decision 3 — Hot-path interface and event delivery: interrupt + DMA ring vs. busy-poll register bank

FS2 caps the software path at ≤ 30 μs.

| Alternative | Implementation cost | Outcome |
|---|---|---|
| Interrupt + DMA ring | DMA IP + driver + coherency | Rejected — interrupt wakeup alone risks consuming most of the budget |
| **Busy-poll + register bank + doorbell (selected)** | Wizard-generated AXI-Lite slave; zero driver, zero coherency | **Selected** |

**Interrupts are out.** Linux IRQ→userspace wakeup is typically 10–40 μs `[EVIDENCE: working assumption, no direct literature source]` — gone before any work happens. This isn't just this project's estimate: Leber et al. trace interrupts' high latency to the context switch itself [1], Morris et al. poll a memory queue for the same reason [4], and Toshiba's production system polls FIFOs in hardware rather than using interrupts [8]. The replacement is busy-poll: core 1 is pulled out of the scheduler (`isolcpus`) and spins on new data instead.

**DMA loses its rationale once a core is already dedicated to the wait — and its exact latency doesn't need to be pinned down to see that.** DMA earns its complexity by moving bulk data without CPU involvement; at a 16–24 B payload, there's nothing to earn, whatever DMA's own latency turns out to be once synthesized. The PL exposes the snapshot as AXI-Lite registers plus an incrementing `seq`; core 1 polls `seq` over M_AXI_GP0. Egress is symmetric — the PS writes order fields then a doorbell register, whose write strobe launches the PL encoder; payload-first/doorbell-last makes torn sampling impossible without a lock.

The register path isn't claimed to win on speed — it's claimed to be cheap enough to build and verify that the comparison doesn't need to be won on speed, which is the right target for this team and schedule.

---

## 3.2.3 Final Design Details

The six subsections below follow one tick's path through core 1: the register bank delivers the snapshot (3.2.3.1), the Strategy Engine turns it into a decision (3.2.3.2), the Risk Guard filters that decision (3.2.3.3) and the open-order table tracks what happens to it (3.2.3.3.1); the Config Loader (3.2.3.4) governs the parameters everything above uses, the Execution Logger (3.2.3.5) records every step, and HOLD Mode (3.2.3.6) is the session-level fallback that can override the whole chain.

### 3.2.3.1 The PL/PS register bank and access protocol (interface contract)

The entire intraday PL/PS boundary is one AXI-Lite slave in the PL, mapped through M_AXI_GP0. This table is the interface contract, jointly owned with 3.1:

| Offset | Register | Dir (PS view) | Semantics |
|---|---|---|---|
| 0x00 | `SEQ` | R | Increments atomically with each snapshot commit; core 1 polls this |
| 0x04–0x10 | `BEST_BID_PRICE`, `BEST_BID_QTY`, `BEST_ASK_PRICE`, `BEST_ASK_QTY` | R | Feature Parameters (top-of-book snapshot); extend if the Market Feature Builder emits more fields |
| 0x14–0x18 | `TIMESTAMP_LO/HI` | R | PL hardware timestamp of the committing packet |
| 0x20–0x2C | `DIAG_PARSE_ERR`, `DIAG_FCS_FAIL`, `DIAG_DROP_OOW`, `DIAG_TX_BACKPRESSURE` | R | NFS8/NFS2 counters, read periodically by core 0 |
| 0x40–0x4C | `ORD_SYMBOL_SIDE`, `ORD_QTY`, `ORD_PRICE`, `ORD_ID` | W | Order fields (FS13 source values) — the block diagram's "Trade Decision" arrow. `ORD_SYMBOL_SIDE` packs `symbol` in bits [15:0] and `side` in bits [23:16] (bits [31:24] reserved = 0), matching their widths in Table 3.1.5. |
| 0x50 | `DOORBELL` | W | Write-1 launches the Order Emitter; **payload first, doorbell last** |
| 0x54 | `TX_READY` | R | Egress flow-control invariant (see 3.2.4.1) |

**Consistency and conflation.** PL commits are single-clock-edge atomic, so tearing can only happen on the PS side, where reading 4–6 registers spans ~1 μs across several AXI transactions; core 1 guards against it with a seqlock (read `SEQ`, read fields, re-read `SEQ`, retry on mismatch). Egress needs no lock — the PL samples order fields only on the doorbell strobe. The bank also holds only the latest snapshot: if ticks outrun the polling loop, intermediate snapshots are overwritten rather than queued, so the strategy always decides on the current book. This doesn't affect NFS9 — the PL still books every packet at line rate; conflation applies only to what the PS samples, and it is a consequence of keeping the strategy in PS software (Decision 1), not a general HFT norm — see the trade-off discussion in 3.2.4.1.

### 3.2.3.2 Strategy Engine (Plug-In Execution)

The engine is a table dispatch: the active strategy ID (from the FS4 config) indexes a function table; each strategy is a pure function of (snapshot, rolling state, parameters) → {BUY, SELL, HOLD} + order fields. Rolling state is fixed-size (e.g., a lookback ring of midprices), so per-tick cost is O(1) and independent of session length.

| Regime | Strategy | Input signals | Decision rule |
|---|---|---|---|
| Trending | Momentum | Midprice sequence over configured lookback | `m = mid_t − mid_{t−L}`; BUY if `m ≥ +θ_entry`, SELL if `m ≤ −θ_entry`, else HOLD |
| Ranging | Mean Reversion | Midprice deviation from moving average | `d = mid_t − SMA_W(mid)`; BUY if `d ≤ −θ_dev`, SELL if `d ≥ +θ_dev`, else HOLD (trade toward the mean) |
| Volatile | Defensive | Spread, volatility flag, position state | If `spread ≥ spread_floor` or the vol flag is set: suppress new entries and emit only position-reducing orders toward flat; else HOLD |

`mid` is held in half-cent units (`best_bid + best_ask`) so the arithmetic stays integer, like all prices from the PL — this avoids FPU state on the isolated core and makes decisions bit-reproducible for backtest cross-validation, extending FS7's determinism to the SoC side. Every window, threshold, and position scalar loads from the FS4 JSON config — the parameter names are exactly the axes swept in 3.3.3a.3 (`lookback/entry_thresh/pos_scalar`, `window/dev_thresh/pos_scalar`, `spread_floor/vol_cutoff/pos_scalar`) — so tuning never requires recompilation. The formulas are deliberately simple: per-strategy sophistication lives in the EOD parameter sweep (3.3), not the intraday rule; the design's contribution is the deterministic, reconfigurable evaluation machinery, not the alpha.

### 3.2.3.3 Runtime Risk Guard (FS3)

The guard lives in PS software, executed unconditionally after every non-HOLD decision, in the same thread as the strategy — not in PL fabric. Same-thread placement guarantees no order path can bypass it, which is simpler to verify against FS3 than a split HW/SW trust boundary; a PL guard would also need its own writable-register interface for limits that are EOD-configurable, and QTA 3.2.4.1 shows the software cost (~25–30 cycles, under 0.1% of the FS2 budget) leaves no latency case for hardware anyway. The PL still holds a residual structural guard: the Order Emitter can only transmit packets assembled from fields the PS wrote through the register bank, in the FS13 fixed format — malformed egress is impossible by construction.

| Check | Rule | Mechanism |
|---|---|---|
| Notional | qty × price ≤ $50,000 CAD limit (configurable) | 32×32→64-bit multiply, one compare |
| Position | \|position ± qty\| ≤ 1,000 shares | Signed accumulate against local position state, range-checked against ±1,000 (two compares) |
| Rate | ≤ 1,000 orders/s | Token bucket: capacity 1,000, refill from the global timer via fixed-point multiply-shift — no divides on the hot path (3.2.4.1) |
| In-flight | in-flight count ≤ 100 | Compare against open-order table occupancy counter (increment on doorbell; decrement on terminal transition — 3.2.3.3.1) |

Rejections write a reason-coded record to the Execution Logger (FS3's "logged reason code") and never reach the doorbell. A REJECT may also assert the Runtime Trigger into HOLD Mode (3.2.3.6). Limits load from the FS4 config and are immutable during a session.

### 3.2.3.3.1 Open-order table (FS14)

Core 1 maintains a fixed, pre-allocated open-order table of 100 entries `{order_id, side, qty, price, submit_timestamp, state}` for the traded symbol — sized exactly to FS3(d)/FS14's in-flight ceiling, since the Risk Guard's in-flight check rejects before insertion and the table never needs to hold more than that.

FS14/FS3(d) make "in-flight" a real, testable quantity, so the design fixes when an order stops being one: a PS-only modeled fill delay **T**. On submission, an order enters the table as in-flight and is treated as terminal after **T** elapses, at which point position and the execution-outcome log update and the terminal transition produces an execution-outcome record for FS5. This is deterministic, requires no protocol changes, and makes the FS14 verification procedure feasible by arithmetic (e.g., at 1,000 orders/s, **T = 0.1 s** drives the in-flight count to 100).

### 3.2.3.4 Config Loader (FS4) and fault handling (NFS8)

At startup, before core 1 begins polling, the loader ingests the JSON configuration (either from the board's SD/TF card slot or via an `scp`/SSH push from the EOD server to a staging path, per 3.3 Decision 6), validates schema and ranges, and populates the strategy table and Risk Guard limits. Any validation failure is NFS8's "malformed config" case: log fault code, refuse to start the polling loop, remain up for re-push — never trade on a default. Market data processing is structurally unreachable until a config commits, which is FS4's verification argument.

### 3.2.3.5 Execution Logger and Console (FS5, FS11)

The logger is pure software: core 1 writes into a fixed, pre-allocated 256 MB ring in cached DDR3 (no malloc on the hot path, no OOM by construction); the PL isn't involved. A full per-tick log doesn't fit the budget (3.2.4.2), so the ring logs every decision/outcome record (rate capped by FS3's 1,000 orders/s) plus book snapshots sampled at 100 Hz and on every order event (working figures, pending a cited source). Core 0 handles everything off the hot path: draining the ring to eMMC continuously, the end-of-session export over PS GbE, periodic `DIAG_*` sampling into the log, and the FS11 console feed — a 1 Hz rendering of book top and recent decisions over Debug UART, reading the same ring at zero cost to core 1.

**Execution record schema (frozen — 128 B fixed).** One record per strategy decision, execution outcome, sampled snapshot, Risk Guard REJECT, or fault event, written by core 1 as a single fixed-size struct copy:

| Field | Offset (B) | Size (B) | Content |
|---|---|---|---|
| `record_type` | 0 | 1 | 0x01 DECISION, 0x02 OUTCOME, 0x03 SNAPSHOT, 0x04 REJECT, 0x05 FAULT |
| `decision` | 1 | 1 | 0x00 HOLD, 0x01 BUY, 0x02 SELL (0x00 for non-decision records) |
| `strategy_id` | 2 | 1 | Active strategy index (FS4 config) |
| `reason_code` | 3 | 1 | FS3 reject reason / NFS8 fault code; 0 otherwise |
| `seq` | 4 | 4 | PL snapshot `SEQ` this record was decided against |
| `pl_timestamp` | 8 | 8 | `TIMESTAMP_LO/HI` of the committing packet (3.2.3.1) |
| `cpu_timestamp` | 16 | 8 | Core-1 PMU cycle count (CCNT) — FS2 instrumentation for free |
| `best_bid_price`, `best_bid_qty`, `best_ask_price`, `best_ask_qty` | 24 | 16 | Top-of-book at decision time (4 × u32, integer cents / shares) |
| `order_id` | 40 | 4 | 0 if no order emitted |
| `order_qty`, `order_price` | 44 | 8 | 2 × u32; 0 if no order |
| `position_after` | 52 | 4 | Signed shares after this record's effect |
| `inflight_count` | 56 | 4 | Open-order table occupancy after this record |
| `realized_pnl` | 60 | 8 | Cumulative, signed integer cents |
| `reserved` | 68 | 60 | Zero-filled — pads to 128 B and absorbs schema growth without a size change |

### 3.2.3.6 HOLD Mode

HOLD is a state, not a message: per-decision, it just means no doorbell write, and a HOLD record enters the logger. At the session level, HOLD Mode is a latched state entered by (a) the Runtime Trigger from a Risk Guard REJECT pattern — **≥ 3 REJECTs within a rolling 10 s window**, both values from the FS4 config and deliberately conservative — or (b) the EOD path's "REJECT / No Approval" outcome; while latched, the strategy is forced to HOLD until an operator clears it. HOLD needs no PL cooperation — it's simply the absence of a doorbell write.

---

## 3.2.4 Quantitative Technical Analysis

### 3.2.4.1 FS2 latency budget, interface capacity, and Risk Guard cost (30 μs at 766 MHz)

30 μs ≈ 23,000 CPU cycles at 766 MHz (the Cortex-A9 max frequency on the target board). The budget also funds the PL egress tail (doorbell-to-MAC-TX ≈ ~1 μs by 3.1 arithmetic), leaving ~29 μs for software:

| Stage | Estimate | Basis |
|---|---|---|
| Detect new `SEQ` (one GP0 read) | ~0.15–0.3 μs | AXI-Lite read via GP; pending PMU/ILA microbenchmark — the single number this table hangs on |
| Snapshot read: 4–6 field reads + seqlock re-read | ~1–1.8 μs | 6–8 GP reads; retry probability bounded below |
| Strategy evaluation | ≤ ~1 μs | Hundreds of integer ops on O(1) state — generous ceiling |
| Runtime Risk Guard | ≪ 0.1 μs | ~25–30 cycles, detailed below |
| Logger record write | ≤ ~0.5 μs | Fixed 128 B struct copy into cached ring |
| Order-field writes + doorbell (5 GP writes) | ~0.5–1 μs | AXI-Lite posted writes |
| **Software total** | **≤ ~5 μs** | **≥ 5.5× margin against the ~29 μs share; worst case is what FS2's 1,000-tick verification samples** |

Under the rejected interrupt design, the first row alone costs 10–40 μs — 40–160% of budget before any work. The selected design's entire path is bounded by countable bus transactions. These estimates will be replaced with PMU (CCNT) per-stage instrumentation across 1,000 ticks, then the Wireshark end-to-end check.

**Runtime Risk Guard cost bound.** Notional: one `umull` + compare ≈ 5–10 cycles. Position: add + two compares ≈ 5 cycles. Rate: timer-delta × fixed-point constant, multiply-shift-saturate ≈ 10 cycles; spend = decrement + compare ≈ 2 cycles. In-flight: one counter compare ≈ 1–2 cycles. Total ≈ 23–29 cycles ≈ 0.03–0.04 μs at 766 MHz — under 0.1% of the FS2 budget — quantitatively closing 3.2.3.3's "no latency case for hardware risk checks" claim.

**Interface capacity, conflation, and the DMA comparison.** Three rates bound the system (using the GP-read estimate above, worst case 0.3 μs):

```
Snapshot read cost (6 reads + seqlock): ~1.5–2 μs → PS observation ceiling ≈ 500–670 K snapshots/s
Full decision iteration (table above): ≤ ~5 μs → PS decision ceiling ≥ ~200 K decisions/s
Wire tick ceiling (3.1.4.1): 1.389 M ticks/s
```

The PS cannot observe every tick (670 K < 1.389 M) — but it cannot *process* every tick either (200 K < 1.389 M): **the bottleneck is the CPU, not the interface.** A DMA ring would not raise either ceiling; it would only queue ticks the CPU cannot consume, forcing the strategy to act on progressively staler books — for trading, a negative. A ring consumer would end by skipping to the newest entry, i.e., re-implementing conflation with more hardware.

**Conflation is a consequence of Decision 1, not an HFT norm.** The published architectures split into camps that don't face this trade-off at all: Kao et al. and Boutros et al. keep the trading logic itself in fabric, so there is no software consumer to outrun the wire and no tick is ever discarded [2], [6]; Toshiba's production system pushes even the optimization layer into a hardware-realized solver for the same reason [8]. Morris et al. instead keep software in the loop but route the full tick stream into a host-memory queue via DMA, and explicitly warn that market bursts can outrun the consuming thread and build an unbounded backlog of increasingly stale data [4] — precisely the failure mode conflation is built to avoid. This project takes neither path wholesale: Decision 1 commits the strategy to PS software for nightly EOD reconfigurability, which rules out the fully-hardware camp, and an unbounded backlog is worse for a top-of-book strategy than a bounded, always-current sample, which rules out queueing the full stream. Conflation is the right call *given* that commitment — not a claim that discarding ticks is standard HFT practice. For a strategy that needs the discarded microstructure (order-flow imbalance, queue position), it would be the wrong one, and Decision 1 would need revisiting first.

Seqlock retry probability: a retry occurs only if a commit lands inside the ~1.5 μs read window; even at full wire rate the expected retries per read ≈ 1.5 μs × 1.389 M/s ≈ 2 — bounded by capping retries at 4 and accepting the newest consistent snapshot; a retry-rate counter will be recorded during full-rate injection.

**Sensitivity boundaries (when this interface stops being right):**

| Condition | Register path | Conclusion |
|---|---|---|
| Current spec: 1 symbol, top-of-book, conflation acceptable | ~1.5–2 μs/read, ≥ 5× FS2 margin | **Adequate — selected** |
| Payload > ~100 B/event (e.g., 10-level depth) | ~40 reads ≈ 10 μs — erodes margin | Migrate to a **GP-mapped dual-port BRAM window** (PL BRAM as AXI slave) — still no DMA IP, no driver |
| Per-tick consumption required (no conflation) | Observation ceiling < wire rate | DMA ring required — and a faster CPU with it; out of prototype scope |

**TX contention arithmetic:** FS3 caps orders at 1,000/s (≥ 1 ms spacing) vs. ~1 μs per packet transmit — a 1000× margin; `TX_READY` exists as a correctness invariant, not a performance mechanism.

### 3.2.4.2 FS5 memory budget arithmetic

Record size = 128 B (schema frozen in 3.2.3.5):

```
Full per-tick logging: 1.389 M/s × 128 B ≈ 178 MB/s bandwidth; 10 M ticks × 128 B = 1.28 GB capacity — already over the board's entire 1 GB of DDR3, before even setting aside room for the OS and code
Available DDR3 (approx): PS DDR3 is 1 GB total (2×512 MB). Assuming ≈ 512 MB remains available after OS + code is a reasonable working budget for FS5 planning.
Decision-record ceiling: 1,000/s (FS3) × 128 B = 128 KB/s
Snapshot sampling @100 Hz: 12.8 KB/s
```

Per-tick logging fails on both capacity and bandwidth, which is why the ring (3.2.3.5) logs decisions/outcomes in full but only samples snapshots. The selected policy's sustained rate (~141 KB/s) is three orders of magnitude below the failure mode; the 256 MB ring holds ≈ 30 minutes at the absolute-worst decision rate while core 0 drains continuously to eMMC, so occupancy stays bounded. The board's 8 GB eMMC capacity is ample for the ring + export; the remaining question is sustained write bandwidth, which must be measured. No allocation after startup — FS5's no-OOM clause holds by construction.

---

## 3.2.5 Specification Compliance Summary

| Spec | How the final design satisfies it | Evidence status |
|---|---|---|
| FS2 | Busy-poll isolated core + register reads; ≤ ~5 μs software path vs. ~29 μs share (3.2.4.1) | Analytical; pending PMU-instrumented 1,000-tick run + Wireshark |
| FS3 | Unbypassable in-thread Risk Guard; four checks + reason-coded log | Pending four-violation injection test |
| FS4 | Polling loop structurally unreachable until validated config commits | Pending config-swap restart test |
| FS5 | Static allocation, decision-complete + sampled-snapshot ring, async flush (3.2.4.2) | Analytical; pending 10 M-tick stress + export check |
| FS14 | Pre-allocated open-order table sized exactly to the FS3(d) ceiling; Risk Guard rejects at limit; modeled terminal transitions (3.2.3.3.1) | Pending limit-saturation injection test |
| FS11 | Core-0 UART renderer off the shared ring | Pending live-session check |
| NFS1 (PS share) | FS2 path is the PS contribution; margin table 3.2.4.1 | Analytical |
| NFS4 | Linux + isolated core, no hot-path allocation; fault paths per NFS8; HOLD Mode as safe state | Pending 6.5 h soak |
| NFS8 | Config-reject path; fault-coded logging; session continues; PL `DIAG_*` counters surfaced via GP0 | Pending malformed-config injection |

# 3.3 EOD Server Pipeline Subsystem

> **Scope note:** this subsystem contains two internal data paths that merge before the approval gate. For readability, Final Design Details are split into **3.3.3a (Market Data Path — essential)** and **3.3.3b (Text & Sentiment Path — non-essential)**; they remain one subsystem, matching the block diagram, whose stage names are *Parameter Engineering, Regime Detection, Strategy Reoptimize, LLM Agent, Sentiment Analysis, Backtest & Parameter Sweep, Risk Analysis, Generate JSON Configs, Operator Approval*.
> All numeric analysis in 3.3.4 is derivable on paper today (dataset-size arithmetic, iteration-count budgets, complexity bounds, inequality proofs) — no code required.

---

## 3.3.1 Overview and Specification Mapping

The EOD (End-of-Day) Server Pipeline is the adaptation layer of AQTA — the component that makes the system *Adaptive* rather than a fixed-strategy appliance. It runs on a host server, entirely off the intraday critical path, and closes the loop between one trading session and the next: it ingests the session history exported by the PS together with historical daily OHLCV data, classifies the next trading day's market regime (FS6), re-optimizes the parameters of the strategy assigned to that regime by exhaustively backtesting a bounded parameter grid (FS7), optionally adjusts the risk envelope using sentiment extracted from unstructured text sources (FS9/FS10), assembles the result into a candidate JSON configuration, and presents it to a human operator whose explicit approval is the only path by which any configuration can reach the live system (FS8, transmitted to the PS Config Loader of 3.2.3.4).

The subsystem completes a deliberate three-tier latency/flexibility hierarchy established in 3.1 and 3.2. The PL owns what must be deterministic at nanosecond scale and never changes intraday; the PS owns what must decide in microseconds but be *reconfigurable* nightly; the EOD server owns what may take minutes but must be *rewritable* — the analytics, the parameter values, and the judgment about what tomorrow's market looks like. Each tier trades three or more orders of magnitude of latency for a qualitative gain in flexibility, and the interfaces between tiers (register bank at PL/PS; JSON config at PS/EOD) are each designed so the slower tier can never perturb the faster one mid-session. On the EOD tier the binding constraint is no longer latency at all — NFS5 grants 30 minutes — but **correctness, reproducibility, and auditability**: FS7 demands bit-identical re-runs, and FS8 demands that a human can understand and veto every output. Those two properties, not throughput, drive every design decision below.

This subsystem is directly responsible for the following specifications:

| Spec | Role of EOD subsystem |
|---|---|
| **FS6** | Sole owner: classify the next trading day's regime into ≥ 3 distinguishable states from daily market data. |
| **FS7** | Sole owner: search ≥ 9 parameter combinations for the regime's strategy and select the metric-maximizing one, with deterministic (bit-identical) output. |
| **FS8** | Sole owner of the gate: no configuration reaches the live system without explicit operator approval. (The PS Config Loader in 3.2.3.4 owns the *receiving* end of the chain of custody.) |
| **FS9 (non-ess.)** | Sole owner: ingest ≥ 10 text assets/day over HTTPS and extract structured event records. |
| **FS10 (non-ess.)** | Sole owner: compute a normalized sentiment score in [−1, +1] and use it to adjust next-day position limits. |
| **FS12 (non-ess.)** | Sole owner: display and log pipeline stage, regime, selected parameters, backtest Sharpe, and approval status as each stage completes. |
| **NFS5 (non-ess.)** | Sole owner: full pipeline (ingestion → classification → optimization → approval prompt) within 30 minutes. |
| **NFS8 (partial)** | Owner of server-side fault handling: malformed/missing input data or failed text ingestion must degrade safely (log fault code, emit no config or a neutral adjustment) rather than abort the nightly cycle uncleanly. |

Upstream dependency: FS5's exported session history and a historical daily OHLCV dataset are the pipeline's inputs. The OHLCV source is pinned to the project's own 3.4 corpus: seed-reproducible simulator sessions aggregated to daily bars (regime-labeled, unlimited volume, zero license cost), anchored by the real LOBSTER AAPL sample day (3.4.4.6 — a freely published official sample), so no external market-data feed or license is required. Downstream contract: the JSON configuration schema of 3.3.3.5, consumed by the PS Config Loader — jointly owned with 3.2, exactly as the register bank table of 3.2.3.1 is jointly owned with 3.1.

Figure 3.4 shows the pipeline structure. *(Figure placeholder — reuse the SERVER subgraph of the system block diagram, minus the Console Monitor, which belongs to the PS peripheral group per the final subsystem split. Two arrows require re-annotation, flagged in Decisions 5 and 6 below.)*

---

## 3.3.2 Engineering Design Process

Six significant design decisions shaped this subsystem. The recurring theme differs from 3.1/3.2: there, the specs priced in *latency* and the decisions bought determinism of *timing*; here, the specs price in *reproducibility and human oversight* and the decisions buy determinism of *results*. Where a rationale is quantitative, the supporting arithmetic appears in 3.3.4.

### Decision 1 — Execution environment: on-SoC overnight job, compiled host pipeline, or Python host pipeline

| Alternative | Description | Outcome |
|---|---|---|
| A. Run EOD on the SoC PS overnight | Reuse the Zynq: core 1 is idle after the session; run the pipeline there. | **Rejected.** Three independent grounds. (1) Capability: a 766 MHz Cortex-A9 with 1 GB shared DDR3 and no scientific-computing ecosystem turns a 30-minute host job into a porting project (cross-compiling or forgoing NumPy/pandas-class tooling). (2) Architecture: the SoC is deliberately a minimal trading appliance; adding an analytics stack to it grows the NFS4 attack surface (more processes, more memory pressure, more failure modes on the machine that must survive 6.5 h sessions). (3) FS8 topology: the approval gate requires that the config *travels* from an operator-controlled machine to the trading device — collapsing them onto one board makes the "not loaded until approved" boundary a software convention rather than a physical link, weakening the verification argument. |
| B. Compiled host pipeline (C++/Rust) | Native pipeline on the host server for performance. | **Rejected.** NFS5 grants 30 minutes; the arithmetic in 3.3.4.1 shows the entire essential pipeline needs single-digit minutes even in interpreted Python. Compiled performance optimizes a cost that does not exist, while multiplying development and iteration cost on the one subsystem whose formulas the team most expects to revise. |
| C. Python 3 + scientific stack on host server (selected) | pandas/NumPy for data handling; standard library for orchestration; the strategy kernel handled per Decision 4. | **Selected.** Highest-productivity environment for a data pipeline; every stage is testable with plain pytest on fixture CSVs; NFS5's budget makes its performance profile irrelevant (3.3.4.1). |

**Orchestration corollary.** A workflow framework (Airflow/Prefect-class DAG scheduler) was considered and rejected without a full trade study: the pipeline is a strictly linear-with-one-merge DAG executed once nightly on one machine, and FS12's requirement — a logged status line per stage transition — is satisfied by a sequential staged script with a `run_stage()` wrapper that timestamps entry/exit and writes the FS12 record. A scheduler adds an always-on service, a database, and a failure domain to deliver features (distributed workers, retry policies, backfills) the specifications never ask for. This is the same reasoning shape as 3.2 Decision 3: infrastructure must earn its complexity, and here it cannot.

### Decision 2 — Regime classifier (FS6): rule-based thresholds, k-means clustering, or Hidden Markov Model

This is the subsystem's central algorithmic decision. The spec context matters more than the algorithm menu: FS6 requires **≥ 3 distinguishable states**, FS7 requires the downstream consumer to be **bit-identical on re-run**, and FS8 requires a **human operator to audit** the output nightly. The classifier's job in AQTA is *routing* — selecting which of the three pre-built strategies (3.2.3.2: Trending→Momentum, Ranging→Mean Reversion, Volatile→Defensive) runs tomorrow — not alpha generation. The evaluation criteria and weights encode that: reproducibility and auditability dominate classification fidelity.

| Criterion (weight) | Rule-based two-feature thresholds (selected) | k-means clustering (k=3) | Gaussian HMM (3 states) |
|---|---|---|---|
| Determinism & reproducibility (30%) | Deterministic by construction — pure function of the input window | Deterministic only with fixed seed + fixed init; silent library-version sensitivity | EM fit (Baum-Welch) is init-sensitive; multi-restart practice is explicitly stochastic |
| Operator auditability for FS8 (25%) | Full — the operator can verify "vol above its 75th percentile ⇒ Volatile" against a chart in seconds | Weak — centroid coordinates are not human-meaningful; labels can permute between runs | Weak — state posteriors are not explainable to a non-specialist reviewer; states need post-hoc labeling |
| Implementation + verification cost, given team capability (25%) | Days: two features, three comparisons, exhaustive unit-testable | Moderate: scikit-learn dependency + label-to-regime mapping logic | High: hmmlearn dependency, convergence handling, degenerate-fit detection — specialist knowledge the team does not have and the marks do not reward |
| Classification fidelity (20%) | Adequate — captures the vol/trend structure the three strategies are defined by | Potentially better cluster geometry | Best-in-literature for latent regime persistence [15] |
| **Weighted result (1–5 scale)** | **4.60 — Selected** | 2.95 | 2.35 |

*(Scoring: 1–5 per criterion — cost-type criteria score higher when the cost is lower — then weighted: rule-based = 0.30×5 + 0.25×5 + 0.25×5 + 0.20×3 = 4.60; k-means = 0.30×3 + 0.25×2 + 0.25×3 + 0.20×4 = 2.95; HMM = 0.30×2 + 0.25×2 + 0.25×1 + 0.20×5 = 2.35.)*

The decisive observation: **the two rejected alternatives buy fidelity the specifications cannot measure, at the cost of the two properties the specifications do measure.** FS6's verification procedure checks only that ≥ 3 distinct regimes appear over 6 months of data; FS7's checks bit-identical output; FS8's checks that a human approved. A threshold classifier maximizes the second and third and satisfies the first *by construction* (shown quantitatively in 3.3.4.3, where percentile-based thresholds make a degenerate single-regime outcome impossible on the verification dataset). This is the quant-engineering framing of the whole project applied locally: the deliverable is a working, auditable adaptation loop, not a novel classifier.

**Threshold calibration sub-decision.** Fixed absolute thresholds (e.g., "annualized vol > 25% ⇒ Volatile") were rejected because they silently degenerate on any symbol or period whose vol never crosses the constant — FS6's verification would then fail for data reasons, not design reasons. The selected scheme sets thresholds at **percentiles of the trailing calibration window** (working empirical figures, confirmed: 75th percentile of realized vol; 60th percentile of |trend strength| — both adjustable from the pipeline config), making the classifier self-calibrating per symbol and guaranteeing non-empty regime occupancy on the very dataset FS6 is verified against (3.3.4.3).

### Decision 3 — Parameter search (FS7): exhaustive grid, random search, or Bayesian optimization

| Alternative | Description | Outcome |
|---|---|---|
| Bayesian optimization (GP/TPE) | Sample-efficient search of expensive objective functions. | **Rejected.** Sample efficiency is valuable when evaluations are expensive; 3.3.4.1 shows the *entire grid* evaluates in minutes. The method is stochastic by nature (acquisition sampling), directly hostile to FS7's bit-identical requirement, and imports a heavyweight dependency to optimize a cost that does not exist. |
| Random search | Uniform sampling of the parameter space. | **Rejected.** Deterministic only under seed discipline that must then be defended in verification; offers no benefit over the grid at this scale — its literature advantage appears in high-dimensional spaces [16], and our space is 3-dimensional. |
| Exhaustive grid search (selected) | Enumerate every combination in a fixed, documented order; evaluate each with the backtest kernel; select the maximizer under a total-order tie-break. | **Selected.** Determinism by construction: fixed enumeration order + sequential evaluation + deterministic kernel (Decision 4) + total-order tie-breaking (3.3.3a.3) means identical input bytes produce identical output bytes — FS7's verification procedure passes by design, not by discipline. Exhaustiveness also strengthens FS8: the operator report can show the *complete* result table, not a sampled trace. |

The one real hazard of a maximizing grid search — overfitting the trailing window — is acknowledged rather than hidden: mitigations are (a) the small, coarse grid itself (a 27-point grid cannot fit noise the way a continuous optimizer can), (b) the operator approval gate, whose report displays the full sweep table so a knife-edge maximum is visible, and (c) the Defensive regime and HOLD mode as structural backstops. A walk-forward evaluation scheme was considered as a stronger mitigation and rejected for prototype scope; it is the natural first extension. Confirmed: walk-forward is deferred — single trailing-window in-sample selection is the prototype behavior.

### Decision 4 — Backtest kernel: vectorized library, event-driven framework, or parity-ported custom loop

This decision contains the subsystem's most consequential correctness argument, and it inverts the team's default preference for off-the-shelf components — deliberately and for one specific reason.

| Alternative | Description | Outcome |
|---|---|---|
| Vectorized backtest library (vectorbt-class) | Strategies re-expressed as vectorized signal arrays; very fast sweeps. | **Rejected for the kernel.** Requires *re-implementing* each strategy in vectorized form, creating two parallel definitions of the same strategy — one in C on the PS (integer, event-driven), one in NumPy on the server (float, array-form). Any divergence (rounding, boundary conditions, lookback indexing) silently invalidates the central promise of the EOD loop: that the parameters selected offline describe the behavior of the code that trades. |
| Event-driven framework (backtrader-class) | Closer execution semantics; strategies as callback classes. | **Rejected for the kernel.** Same dual-implementation problem (framework-native indicators are float-based), plus a large dependency whose internal fill/accounting model would need auditing to defend FS7 determinism. |
| **Parity-ported custom loop (selected)** | A thin (~100-line) replay loop that feeds recorded snapshots through **line-by-line ports of the exact PS strategy functions** — same integer-cents arithmetic, same lookback ring, same thresholds — and tracks position/P&L. Libraries (pandas/NumPy) are used *around* the kernel for data loading and metric aggregation, not inside it. | **Selected.** The 3.2.3.2 commitment to integer-only strategy arithmetic was made precisely to enable this: an integer decision function is portable across C and Python with bit-identical outputs, because no floating-point rounding or evaluation-order semantics are involved. The backtest therefore does not *approximate* the live system — it *replays* it. |

**Why this doesn't contradict the "prefer existing libraries" principle.** The principle applies where the component is commodity infrastructure (data loading, HTTP, JSON, metric arithmetic — all off-the-shelf here). The backtest *kernel* is not commodity: its defining requirement is decision parity with our own PS code, a property no external library can supply by definition. The cost of the custom choice is speed — a pure-Python event loop is orders of magnitude slower than vectorized NumPy — and 3.3.4.1 shows that cost is affordable inside NFS5 with a ≥ 3× margin: **slow-but-identical beats fast-but-divergent when the budget makes slow free.** Cross-validation between the kernel and the PS engine — same recorded input, byte-compared decision sequences — is itself a planned verification artifact, pending a recorded session to run it against.

**Backtest data source.** The kernel replays the **snapshot stream exported by the Execution Logger** (FS5) — the sampled top-of-book records the live system actually observed — rather than synthetic bars. This closes the loop with zero format invention: the system generates its own backtest data in its own schema, and the parameter sweep evaluates strategies on exactly the data distribution the deployed strategy will see. Bootstrap case (no live sessions yet): replay sessions generated by the Exchange Simulator (3.4), recorded before the first live run. The daily-OHLCV dataset is used only by the regime path (FS6 is explicitly specified on daily data), not by the sweep.

### Decision 5 — Text & Sentiment Path architecture (FS9/FS10): where the LLM belongs, and the determinism boundary

The non-essential path raises a design tension: an LLM is the strongest available tool for FS9's actual problem (extracting structured records from heterogeneous unstructured sources — HTML news, social posts, PDF reports), but LLM outputs are non-deterministic and externally hosted — properties that must not contaminate FS7's bit-identical guarantee or FS8's audit chain. The design resolves this by splitting the path at a **determinism boundary** and choosing a different tool on each side.

**Stage 1 — Extraction (FS9): LLM agent, selected for the messy side.** Alternatives: hand-written per-source parsers (rejected: one parser per source format, brittle against layout changes, and PDF report extraction alone is a project), classical NLP/NER pipelines (rejected: comparable integration cost to FinBERT below but solves only entity tagging, not headline/relevance extraction from arbitrary formats). The LLM agent ingests each asset over HTTPS and emits one structured event record (headline, ticker, timestamp, source — FS9's exact field list). Every emitted record is **logged verbatim**; everything downstream operates only on logged records. Non-determinism therefore stops at the boundary: re-running the pipeline *from the logged records* is fully deterministic, which is the precise sense in which FS7's re-run verification is defined. FS9's verification uses a mocked web server, so the demo does not depend on live source availability, regardless of whether the agent is later backed by a hosted API or a local model.

**Stage 2 — Scoring (FS10): deterministic local model, selected for the auditable side.**

| Criterion (weight) | Lexicon (VADER-class) | FinBERT (local inference, selected) | LLM-scored |
|---|---|---|---|
| Determinism/reproducibility (30%) | Full | Full — fixed weights, fixed tokenizer, single-threaded CPU inference | None without vendor-side guarantees |
| Financial-domain validity (25%) | Weak — general-domain lexicon misreads financial polarity ("beats expectations") | Strong — finance-domain fine-tuned [17] | Strong |
| Integration + verification cost (25%) | Trivial | Low — one pip dependency, one forward pass per record; FS10's pre-labeled reference-set test applies directly | API handling, rate limits, cost accounting |
| Operating cost/availability (20%) | None | None after model download; fully offline | Per-call cost; external availability risk on the nightly path |
| **Weighted result (1–5 scale)** | 4.25 | **4.75 — Selected** | 2.45 |

*(Scoring: 1–5 per criterion, weighted: lexicon = 0.30×5 + 0.25×2 + 0.25×5 + 0.20×5 = 4.25; FinBERT = 0.30×5 + 0.25×5 + 0.25×4 + 0.20×5 = 4.75; LLM-scored = 0.30×1 + 0.25×5 + 0.25×2 + 0.20×2 = 2.45. The lexicon runs FinBERT close on cost but loses exactly where FS10's correct-polarity verification bites — domain validity.)*

FinBERT's class probabilities map directly onto FS10's required range: `score = P(positive) − P(negative) ∈ [−1, +1]` with polarity built in — no ad-hoc normalization to defend. Per-asset scores aggregate to a daily score by simple mean (confirmed — recency weighting adds a parameter the prototype has no evidence to calibrate), plus an `abnormal_event_flag` when any single record's |score| exceeds θ_abn = 0.8 (working empirical value, loaded from the pipeline config).

**Coupling into the essential path — risk-tightening-only, by proof.** The sentiment output enters the **Risk Analysis** stage as a position-limit scalar, under a monotonicity constraint proven in 3.3.4.4: the adjusted limit satisfies `L(s) ≤ L_base` for every possible score `s`, with equality for all `s ≥ 0`. Sentiment can therefore only *shrink* the risk envelope below the FS3 ceilings, never expand it, and never touches the optimization objective or strategy selection. Consequently the non-essential path is **incapable of harming the essential system**: its total failure (no assets, API down, model missing) degrades to `s = 0` ⇒ no adjustment ⇒ the essential pipeline's output is byte-identical to a run with the path disabled. This is the same structural-safety argument style as 3.2's "malformed egress is impossible by construction." *(Diagram note: the block diagram's `PATH_TXT → BACKTEST` arrow should be re-annotated to target Risk Analysis — sentiment does not feed the backtest objective, the same fix as the HOLD-arrow correction in 3.2.3.6.)*

### Decision 6 — Approval gate and configuration chain of custody (FS8)

| Alternative | Description | Outcome |
|---|---|---|
| Procedural gate | Pipeline writes the config; operator manually copies it to the SoC when satisfied. | **Rejected.** FS8's verification must show the config *cannot* reach the SoC unapproved; a procedure is a promise, not a mechanism — nothing distinguishes an approved file from an unapproved one after the fact. |
| Approval flag in the config | Pipeline sets `approved: true` after a y/n prompt; transmission code checks the flag before sending. | **Rejected.** The flag is just a field the operator's own approval action writes — but the check-then-send is two separate steps, so a bug between them (or a manually re-edited file) could send an unapproved config without the flag ever being false. |
| **Structural gate: approval call is on the only path to transmission (selected)** | The operator is shown the FS12 report (regime, sweep table, selected parameters, Sharpe, sentiment adjustment) and approves interactively; the approval prompt's own return value *is* the call that invokes transmission — there is no separate "check the flag, then send" step, and no code path reaches the network send without going through that prompt. A REJECT/no-approval outcome simply never calls it. | **Selected.** FS8's verification ("confirm no transmission before manual approval") is satisfied by inspecting the code path itself: the send call has exactly one caller, and that caller is the approval prompt's success branch. This is the same structural argument as FS4's in 3.2.3.4 — the same reasoning already used elsewhere in the design, without adding a cryptographic layer this single-machine, point-to-point system has no threat model to justify. |

Transport for the approved config is a push over the PS GbE via `scp` to a staging path on the SoC, from which the Config Loader ingests it at startup — selected over a minimal custom TCP receiver purely for implementation convenience.

---

## 3.3.3 Final Design Details

The pipeline is a sequential staged program; Figure 3.5 shows the stage graph with FS12 log points at every transition. *(Figure placeholder — stage flowchart: [Data Import & Validation] → [Parameter Engineering] → [Regime Detection] → [Strategy Reoptimize / Backtest & Parameter Sweep] ⇐ merge [LLM Agent → Sentiment Analysis] → [Risk Analysis] → [Generate JSON Config] → [Operator Approval] → [Transmit / or REJECT→HOLD].)*

### 3.3.3a Market Data Path (essential — FS6, FS7)

#### 3.3.3a.1 Data import and Parameter Engineering

Inputs are validated before any computation (NFS8 server side): schema check on the exported session archive, monotonic-timestamp check, and a minimum-history check (≥ 60 trading days of OHLCV `[TEAM: confirm window]`). Validation failure logs a fault code and aborts the pipeline *before* the config-generation stage — a night with bad data produces no candidate config (and therefore, by FS8's gate, no change to the live system) rather than a config built on garbage.

The Parameter Engineering stage computes two features from daily OHLCV closes:

| Feature | Definition | Window |
|---|---|---|
| Realized volatility `σ` | Standard deviation of daily log returns, annualized: `σ = std(ln(Cₜ/Cₜ₋₁)) × √252` | 20 trading days `[TEAM: confirm]` |
| Trend strength `T` | Normalized moving-average divergence: `T = (SMA₅ − SMA₂₀) / SMA₂₀` | 5- and 20-day SMAs |

Both are standard constructions; the design contribution is not the features but the calibration scheme (Decision 2) and the guarantee it yields (3.3.4.3).

#### 3.3.3a.2 Regime Detection (FS6)

Thresholds are set at percentiles of the trailing calibration window, then the current day is classified by a fixed-priority rule (volatility outranks trend, because the Defensive strategy is the safe fallback and ambiguity should resolve toward it):

```
θ_vol   = percentile(σ over calibration window, 75)    # 75: working empirical value, config-adjustable
θ_trend = percentile(|T| over calibration window, 60)  # 60: working empirical value, config-adjustable

if   σ_today   ≥ θ_vol:    regime = VOLATILE   → Defensive
elif |T_today| ≥ θ_trend:  regime = TRENDING   → Momentum
else:                      regime = RANGING    → Mean Reversion
```

The rule is a pure function of the input window — no state, no seed, no fit. Its unit tests enumerate the three branches plus both boundary equalities (`≥` is deliberate: boundary values classify toward the safer branch).

#### 3.3.3a.3 Strategy Reoptimize — Backtest & Parameter Sweep (FS7)

The regime selects one strategy; the sweep enumerates that strategy's parameter grid in fixed lexicographic order. Working grids (each 3 × 3 × 3 = 27 combinations ≥ FS7's minimum 9):

| Strategy | Parameter 1 | Parameter 2 | Parameter 3 |
|---|---|---|---|
| Momentum | lookback ∈ {5, 10, 20} | entry threshold ∈ {0.005, 0.01, 0.02} | position scalar ∈ {0.5, 1.0, 1.5} |
| Mean Reversion | MA window ∈ {10, 20, 50} | deviation threshold ∈ {0.01, 0.02, 0.05} | position scalar ∈ {0.5, 1.0, 1.5} |
| Defensive | spread floor ∈ {1, 2, 4} cents | vol cutoff ∈ {0.1, 0.2, 0.4} | position scalar ∈ {0.25, 0.5, 1.0} |

(Working empirical grids, loaded from the pipeline config; deliberately coarse per Decision 3's overfitting mitigation. Thresholds are expressed in the daily-bar proxy units of the 3.3.3a.3.1 validation run — the live intraday config carries their integer half-cent equivalents per 3.2.3.2. Note the validation run substituted a vol-window axis for the Defensive spread floor, since daily bars carry no spread.)

Each combination is evaluated by the parity-ported kernel (Decision 4):

```
for params in grid (fixed lexicographic order):          # determinism: fixed order
    state = init_strategy_state(params)                  # same init as PS engine
    position, pnl_series = 0, []
    for snapshot in recorded_session_stream:             # integer cents, as exported
        decision = strategy_fn(snapshot, state, params)  # line-by-line port of PS C function
        position, pnl = apply_fill_model(decision, position, snapshot)
        pnl_series.append(pnl)
    metrics[params] = sharpe(pnl_series), max_drawdown(pnl_series), n_trades
select params* = argmax over sharpe,
       ties broken by lexicographic parameter order      # total order ⇒ unique winner
```

The fill model is the prototype simplification: fill at the touch (best bid/ask of the snapshot) for order sizes within displayed quantity `[TEAM: confirm fill assumption; document as a stated limitation — no queue-position or impact modeling]`. Sharpe is computed as a P&L-based variant: `mean(daily P&L) / std(daily P&L) × √252` with a zero risk-free rate, which is a variant of the standard return-based Sharpe ratio adapted for absolute P&L rather than percentage returns `[TEAM: confirm]`. The metric arithmetic is float, but evaluated in a fixed sequential order over deterministic integer inputs, so results are bit-stable across re-runs (3.3.4.2); the tie-break rule removes the only remaining path by which a float comparison could produce run-dependent selection.

##### 3.3.3a.3.1 Preliminary validation run (real data)

The classification and sweep procedures above have been run end-to-end against **real historical daily OHLCV** — not synthetic data — as a preliminary check ahead of full implementation. *(Data-source note: huggingface.co — the originally identified defeatbeta/yahoo-finance-data source — was unreachable from the sandboxed dev environment's network allowlist, so this run substitutes matplotlib/sample_data/aapl.csv (real AAPL daily OHLCV, 1984-09-07 to 2008-10-14, BSD-licensed public repo, fetched via raw.githubusercontent.com). This remains a development/validation placeholder; the production data source is now pinned to the 3.4 corpus per 3.3.1 — simulator-session daily bars plus the LOBSTER AAPL sample day — so no external feed or license is required.)*

**Regime classification (FS6), real data:** calibration window 2007-04-18 to 2008-04-16 (252 trading days) yields `θ_vol = 0.518`, `θ_trend = 0.059`. Classifying the following 126-trading-day test window (2008-04-17 to 2008-10-14 — the tail of this dataset, which happens to fall in the Sept–Oct 2008 crash) produces:

| Regime | Days (of 126) |
|---|---|
| RANGING | 80 |
| TRENDING | 29 |
| VOLATILE | 17 |

All three regimes non-empty — the 3.3.4.3 non-degeneracy proof holds empirically, not just analytically, on the one real dataset available.

**Grid sweep (FS7), daily-bar proxy:** the same 27-point grids run against the days each real regime actually classified, selecting by Sharpe with the fixed tie-break:

| Regime | Strategy | Winning parameters | Sharpe |
|---|---|---|---|
| TRENDING | Momentum | lookback=5, entry_thresh=0.01, pos_scalar=1.5 | **1.856** |
| RANGING | Mean Reversion | window=20, dev_thresh=0.02, pos_scalar=0.5 | **2.077** |
| VOLATILE | Defensive | vol_window=20, vol_cutoff=0.2, pos_scalar=0.5 | **−3.125** |

The VOLATILE result is deliberately reported as-is rather than adjusted: even the *best* of 27 candidate configurations during a genuine market crash is a losing one on a risk-adjusted basis. This is not a design failure — it is precisely the situation the FS8 approval gate exists for. A nightly optimizer that silently deployed the argmax without human review would ship a confidently-labeled "best" configuration that still loses money; the design's requirement that the operator see the **full sweep table**, not just the winning row, is what turns this from a hidden failure into a visible, actionable one (the operator's expected action here is to reject, or to accept Defensive at reduced size, not to be surprised later).

**Kernel throughput (NFS5), measured on this dev host:** a representative parity-style kernel call (ring-buffer update + integer threshold compare + position update) was microbenchmarked directly rather than assumed: **1,779,215 calls/sec** measured, versus the ≈ 10⁶ calls/s pessimistic estimate used in the original 3.3.4.1 draft. This measured figure is carried into 3.3.4.1 below, tightening (not loosening) the NFS5 margin.

This run validates the *procedure* — determinism, non-degenerate classification, fixed tie-break, Sharpe selection, sweep-table transparency — on real market data. It is explicitly **not** a validation of tick-level latency (3.3.4.1's per-record cost model) or of the actual PL/PS system (which does not exist yet); the input here is daily bars from a public archive, not a PS-exported snapshot session.

---

### 3.3.3a.4 Risk Analysis and config generation

The Risk Analysis stage is a checklist, not an optimizer: (1) the selected parameters' backtest never breached FS3 ceilings (notional ≤ $50,000 CAD, position ≤ 1,000 shares, rate ≤ 1,000 orders/s — the live values, enforced again at runtime by 3.2.3.3); (2) max drawdown below a sanity bound `[TEAM: value]`; (3) sentiment adjustment applied to position limits per 3.3.3b.3; (4) minimum-trade-count floor so a "great Sharpe" from 2 trades is flagged for the operator `[TEAM: floor value]`. Any check failure is written into the operator report — Risk Analysis annotates, the operator decides.

### 3.3.3b Text & Sentiment Path (non-essential — FS9, FS10)

#### 3.3.3b.1 LLM Agent — ingestion and extraction (FS9)

The agent fetches ≥ 10 text assets over HTTPS from a configured source list `[TEAM: source list; the FS9 demo runs against a mocked web server per its verification procedure]`, handling three asset classes: HTML news pages, short-form social posts, and PDF reports (text-extracted before prompting). For each asset it emits exactly one structured event record:

| Field | Type | Notes |
|---|---|---|
| headline | string | FS9 field |
| ticker | string | FS9 "entity/ticker mentioned"; `NONE` if no entity — record still logged, excluded from scoring |
| timestamp | ISO-8601 | FS9 field |
| source | string (URL) | FS9 field |
| raw_excerpt | string | Verbatim scored text, retained for audit; capped at 512 characters (working empirical value — comfortably inside FinBERT's 512-token input limit) |

Records are appended to the immutable nightly event log — the determinism boundary of Decision 5. Per-asset failures (fetch error, extraction failure) log a fault code and skip the asset; the path proceeds with whatever succeeded, down to zero.

#### 3.3.3b.2 Sentiment Analysis (FS10)

Each record's `headline + raw_excerpt` passes through local FinBERT inference (CPU, single-threaded — a determinism condition, see 3.3.4.2): `score_i = P_pos(i) − P_neg(i) ∈ [−1, +1]`. Daily aggregate `s = mean(score_i)` over records with a matching ticker; `abnormal_event_flag = any(|score_i| ≥ θ_abn)` (θ_abn = 0.8, pipeline-config value). Zero usable records ⇒ `s = 0`, flag false — the neutral element by design.

#### 3.3.3b.3 Coupling into Risk Analysis

Position-limit adjustment, applied in Risk Analysis (never to the optimization objective):

```
L(s) = L_base × max(f_min, 1 + k·min(s, 0))      k = 0.5, f_min = 0.5 (working empirical values, pipeline-config adjustable)
```

Properties proven in 3.3.4.4: `L(s) ≤ L_base` always; `L(s) = L_base` for all `s ≥ 0`; `L` is monotone non-decreasing in `s` and floored at `f_min·L_base`. The abnormal flag additionally stamps a `DEFENSIVE-REVIEW` advisory into the operator report — advisory-only (selected): the operator remains the only override authority, consistent with FS8's single-gate design.

### 3.3.3.5 JSON configuration schema (jointly owned with 3.2.3.4)

| Field | Type | Content |
|---|---|---|
| `strategy_id` | string | `momentum` / `mean_reversion` / `defensive` |
| `regime_label` | string | `trending` / `ranging` / `volatile` |
| `parameters` | object | The swept winner's values, integer-encoded to match the PS kernel. Keys per strategy — momentum: `lookback`, `entry_thresh`, `pos_scalar`; mean_reversion: `window`, `dev_thresh`, `pos_scalar`; defensive: `spread_floor`, `vol_cutoff`, `pos_scalar` (lockstep with 3.2.3.2's formulas and the 3.3.3a.3 grid axes) |
| `risk_limits` | object | `max_notional_cad`, `max_position_shares`, `max_order_rate` — post-sentiment values, each ≤ its FS3 ceiling |
| `provenance` | object | Data window, grid hash, backtest Sharpe, sentiment score, pipeline version — the FS12 record embedded for audit |
| `approval` | object | `operator_id`, `timestamp` — appended only by the approval action (Decision 6) |

### 3.3.3.6 FS12 status reporting and server-side fault handling (NFS8)

Every stage transition writes one structured log line — `(timestamp, stage, status, key metrics)` — to console and to the nightly log file; the approval prompt renders the accumulated report (regime, full sweep table, selected parameters, Sharpe, sentiment, risk-check annotations). FS12's verification (one entry per stage transition, including final approval status) is satisfied by the `run_stage()` wrapper of Decision 1's orchestration corollary. Server-side recoverable faults follow one uniform policy: log a timestamped fault code; degrade to the stage's neutral/abort behavior (text path → neutral; market path → abort before config generation); never emit a config that any validation stage has not passed.

---

## 3.3.4 Quantitative Technical Analysis

### 3.3.4.1 NFS5 runtime budget decomposition

NFS5 allows 30 minutes on the reference workload (1 year of daily OHLCV). The pipeline's cost is dominated by one term — the sweep's kernel replay — and every other stage is bounded by trivial arithmetic:

```
Regime path input:      252 daily bars → feature computation O(n), n = 252    → milliseconds
Regime classification:  two percentile lookups + three comparisons, O(1)      → microseconds

Sweep workload:
  snapshot records/session = 100 Hz × 6.5 h × 3600 s/h = 2.34 M records
  grid size                = 27 combinations
  kernel evaluations       = 27 × 2.34 M ≈ 63.2 M strategy-function calls
  CPython throughput       = 1,779,215 calls/s — MEASURED, not assumed (3.3.3a.3.1 microbenchmark:
                             ring-buffer update + integer compare + position update, on the dev sandbox host)
  sweep time                = 63.2 M ÷ 1.78 M ≈ 35.5 s ≈ 0.6 min
  ×5 pessimism factor       ≈ 3.0 min  (target host will likely be faster than the sandbox; kept anyway)

Text path: 10 assets × ~5 s LLM extraction ≈ 1 min [EVIDENCE: per-asset latency];
           FinBERT/LM-dictionary scoring ~10² ms × 10 records ≈ seconds
Report/serialize:  negligible

Pipeline total (pessimistic): ≈ 4–5 min  →  ≥ 6× margin against NFS5 = 30 min
```

Two conclusions. First, this arithmetic is what licenses Decisions 1, 3, and 4, and the measured figure makes the case stronger than originally estimated: Python is fast enough, exhaustive search is affordable, and the slow parity kernel costs well under a minute against a 30-minute budget — the "slow-but-identical" trade is not just affordable, it is close to free. Second, the margin is a *design allowance*, not slack to be admired: it absorbs grid growth (a much larger grid still fits — see 3.3.4.5, revised with the measured rate) and multi-session backtest windows. `[EVIDENCE: this microbenchmark ran on the development sandbox, not the eventual target host; re-run on the actual EOD server before final submission — the qualitative conclusion (Python is not the bottleneck) is not expected to change, only the exact margin.]`

### 3.3.4.2 FS7 determinism argument — enumeration of nondeterminism sources

FS7's verification is unusual: it does not measure a quantity, it demands *bit-identical* re-execution. The design therefore treats determinism as a property to be established by exhaustively closing every leak, not by testing alone:

| Nondeterminism source | Where it would enter | How the design eliminates it |
|---|---|---|
| Random initialization / sampling | Classifier fit, Bayesian/random search | No fitted model (Decision 2); no sampling (Decision 3) — no RNG is ever seeded because none is used |
| Parallel evaluation / reduction order | Multi-process sweep; float summation order varies | Sweep is strictly sequential in fixed lexicographic order; float reductions always occur in the same order, so IEEE-754 results are bit-stable across runs on the same platform `[TEAM: pin platform in verification procedure — cross-machine bit-identity additionally requires identical libm/BLAS, so FS7's test runs on one designated host]` |
| Hash/dict iteration order | Config serialization, grid enumeration | Grids are explicit ordered lists; serialization is canonical (sorted keys, fixed formatting — Decision 6) |
| Floating-point strategy state | Divergence between PS and server decisions | Strategy kernel is integer-only (3.2.3.2 commitment), ported line-by-line — decisions are exact, floats appear only in post-hoc metrics |
| Tie on the selection metric | Two grid points with equal Sharpe | Total-order tie-break (lexicographic parameter order) — the argmax is unique by construction |
| Threaded ML inference | FinBERT multi-thread scheduling can reorder float ops | Single-threaded CPU inference pinned in configuration (3.3.3b.2) |
| External LLM output variance | FS9 extraction | Outside the determinism boundary by design (Decision 5): records are logged verbatim, and FS7's re-run is defined from logged inputs |

The residual claim — same host, same inputs, same binary ⇒ same bytes — is then verified directly by FS7's double-run procedure. `[EVIDENCE: two full pipeline runs on the reference dataset, byte-compare of emitted config payloads.]`

### 3.3.4.3 Regime classifier non-degeneracy (FS6 verifiability by construction)

FS6's verification requires ≥ 3 distinct regimes assigned over a 6-month window (~126 trading days). For a threshold classifier this fails only if some regime bucket is empty — which is exactly what fixed absolute thresholds risk (a calm 6 months may never cross a hardcoded vol constant, collapsing the output to one or two labels). The percentile scheme closes this analytically:

```
θ_vol = 75th percentile of {σₜ} over the same window
  ⇒ |{t : σₜ ≥ θ_vol}| ≥ ⌈0.25 × 126⌉ = 32 days classified VOLATILE   (by definition of percentile)

Remaining ≈ 94 days have σ < θ_vol and are split by θ_trend = 60th percentile of {|Tₜ|}:
  computed over the full window ⇒ ~40% of all days lie above it;
  even if every VOLATILE day were also high-|T|, at least 0.40×126 − 32 ≈ 18 days
  remain TRENDING, and at least 126 − 32 − 0.40×126 ≈ 44 days remain RANGING.
```

All three buckets are therefore provably non-empty **for the same-window-percentile variant of the classifier** — the variant where θ_vol/θ_trend are computed over the very 6-month window being classified. `[TEAM: if θ_trend is instead computed over the sub-VOLATILE days only, the bound tightens further; confirm which definition we implement — the analysis above is the conservative case.]` The construction is symbol-agnostic — thresholds are relative to each symbol's own distribution, so it would carry over unchanged if the single-symbol scope is ever widened.

**A gap worth stating plainly.** The deployed design in 3.3.3a.2 does **not** use the same-window variant just proven — it calibrates thresholds on a *trailing* window and applies them to the *next* (out-of-sample) window, because a live system cannot know today's percentile using data that includes today before today has happened. That trailing-calibration scheme is the only one that is actually deployable, but it does not inherit the clean 25%-floor guarantee above: nothing stops a calm calibration window from setting a θ_vol that a calmer test window never reaches. The proof above should therefore be read as showing the *concept* cannot degenerate in principle, not as a guarantee about the *deployed* scheme — that gap is exactly what the empirical run below is for.

**Empirical confirmation.** The preliminary run in 3.3.3a.3.1 tests the actual deployed (trailing-calibration, out-of-sample) scheme — not the same-window variant proved above — on one real 6-month window (2008-04-17 to 2008-10-14, real AAPL daily closes, thresholds calibrated on the preceding 252 trading days): 80 RANGING / 29 TRENDING / 17 VOLATILE days, all three non-empty. This is one data point, not a proof, and it is a favorable one (2008 was genuinely volatile, so VOLATILE was in no danger of being empty here); it does not close the gap identified above. `[TEAM: the honest next step is running the trailing-calibration scheme across many overlapping 6-month windows — including calm ones — and reporting the empirical non-empty rate, rather than resting on a single favorable window or the same-window proof that doesn't match what ships.]`

### 3.3.4.4 Sentiment risk-coupling safety bound (FS10 cannot violate FS3)

Claim: for every sentiment score `s ∈ [−1, +1]`, the adjusted position limit satisfies `f_min·L_base ≤ L(s) ≤ L_base ≤ FS3 ceiling`.

```
L(s) = L_base × max(f_min, 1 + k·min(s, 0)),      k = 0.5, f_min = 0.5, L_base ≤ 1,000 shares

Case s ≥ 0:  min(s,0) = 0  ⇒ inner term = 1        ⇒ L(s) = L_base            (no expansion, ever)
Case s < 0:  inner term = 1 + k·s ∈ [1 − k, 1) = [0.5, 1)
             ⇒ L(s) = L_base × max(0.5, 1+k·s) ∈ [0.5·L_base, L_base)          (monotone tightening)
```

The upper bound `L(s) ≤ L_base` holds in both cases with no dependence on the score's *accuracy* — a wildly wrong sentiment score can only make the system trade smaller, never larger, and `s = 0` (the failure default of 3.3.3b.2) is the identity. Combined with the PS Runtime Risk Guard re-enforcing the FS3 ceilings at runtime (3.2.3.3), FS3 protection is two-layered and the entire non-essential path lies strictly inside it. This inequality is the formal version of Decision 5's "incapable of harming the essential system."

### 3.3.4.5 Grid scale sensitivity (why exhaustive search is the right size, and when it stops being)

| Configuration | Kernel evaluations | Est. sweep time (pessimistic 5 μs/call) | Verdict |
|---|---|---|---|
| Prototype: 1 symbol × 27-pt grid × 1 session | 63 M | ≈ 5.5 min | Selected operating point |
| 5-value axes (125-pt grid) | 293 M | ≈ 24 min | Fits NFS5 alone; no headroom with text path — practical ceiling of the pure-Python kernel |

The table bounds the design's validity region explicitly: exhaustive grid + parity kernel is correct for the specified prototype and its first two growth steps, and the design records precisely which future requirement invalidates it and what the successor is.

---

## 3.3.5 Specification Compliance Summary

| Spec | How the final design satisfies it | Evidence status |
|---|---|---|
| FS6 | Percentile-thresholded two-feature classifier; ≥ 3 non-empty regimes provable by construction (3.3.4.3) | Closed by arithmetic; pending 6-month reference-data run |
| FS7 | Exhaustive fixed-order grid + integer parity kernel + total-order tie-break; all nondeterminism sources enumerated and closed (3.3.4.2) | Analytical; pending double-run byte-compare |
| FS8 | Transmission call structurally unreachable without operator approval — the send has one caller, the approval prompt's success branch (Decision 6) | Pending no-approval injection test |
| FS9 (non-ess.) | LLM agent → verbatim-logged structured records; per-asset fault isolation | Pending mocked-server ingestion test |
| FS10 (non-ess.) | FinBERT scoring in [−1,+1] by construction; risk-tightening-only coupling with proven bound (3.3.4.4) | Analytical; pending pre-labeled reference-set test |
| FS12 (non-ess.) | `run_stage()` wrapper logs every transition; approval report aggregates regime/sweep/Sharpe/status | Pending full-cycle log inspection |
| NFS5 (non-ess.) | ≈ 7–8 min pessimistic total vs 30 min budget; ≥ 3× margin with growth allowance (3.3.4.1, 3.3.4.5) | Analytical; pending reference-dataset wall-clock |
| NFS8 (partial) | Validate-before-compute; fault-coded logging; text path degrades to neutral; no config emitted past a failed validation | Pending malformed-input injection |

---

# 3.4 Exchange Simulator Subsystem

> The block diagram labels this subsystem *"Exchange Simulator on Host (Live Order Book & Executor — 1 Exch / 1 Stock)"*; internal component names below are *Order-Flow Generator (dual-driver), Book Mirror, Protocol Encoder, Order Executor (validate-and-log), Scenario Engine, Ground-Truth Logger*.
> **Spec baseline:** Section 2's FS14 (single-symbol), FS3 (four-limit), and FS2 (99th-percentile) already reflect the design below; fill semantics use option C2 (PS-side simulated fill latency), with C1 execution reports documented as a future extension.
> All measured figures in this section were produced on the development sandbox against the real LOBSTER AAPL sample dataset (3.4.4.6); pending a re-run on the target host before final submission.

---

## 3.4.1 Overview and Specification Mapping

The Exchange Simulator is the counterparty to everything built in 3.1–3.3: it plays the exchange that the project objective requires but deliberately does not connect to (Section 1.2's paper-trading boundary). It runs on the host PC, terminates the far end of the point-to-point Gigabit Ethernet link into the PL (both the outbound market-data feed and the inbound order-receive path), generates the market-data event stream in the custom protocol of Table 3.1.4, maintains its own mirror of the resulting order book, and receives, validates, and logs every order packet the SoC emits (Table 3.1.5).

**Positioning within the field.** Published end-to-end FPGA trading systems fall into a clear feasibility hierarchy defined by exchange access. At the top, Toshiba's two production systems ran live capital in the Tokyo Stock Exchange's JPX co-location facility [8], [9]; below them, Kao et al. connected to a real futures-broker test server for the Taiwan Futures Exchange, exercising genuine protocol handshakes without live capital [2]; at the laboratory tier, Boutros et al. validated their HLS pipeline by injecting UDP packets and capturing returned order packets in loopback [6], and Osuna et al.'s PYNQ-Z2 educational system replays market data from a host Python script [7]. AQTA belongs, by construction, to this laboratory tier: the co-location and broker-member access that define the upper tiers is unavailable to (and out of scope for) a capstone project. The design consequence is that this subsystem must supply, *by itself*, everything the upper tiers get from their environment — the market data, the counterparty, and the measurement fixture — which is why it is engineered as a first-class subsystem rather than a test script.

**Dual identity.** Functionally, the simulator is the *exchange*: without it, no market data exists and the system under design has nothing to trade against. Its more demanding identity, however, is as the project's principal *verification instrument*: nearly every verification procedure in Section 2 — FS1's reference packet sequence, FS2's 1000-update measurement, FS13's captured-packet parse, NFS2's 10-minute frame count, NFS4's 6.5-hour session, NFS8's fault injections, NFS9's line-rate PCAP — names an input that only this subsystem can supply. A simulator that merely "produces plausible ticks" would satisfy the first identity and fail the second; the design therefore treats **reproducibility, controllability, and ground-truth observability** as first-class requirements, ahead of market realism. Where realism *is* obtainable at zero marginal cost — via replay of a real order-level dataset (Decision 1) — the design takes it, but never at the expense of the instrument identity.

Unlike 3.1–3.3, this subsystem is the *sole owner* of few specifications — its ownership is instrumental:

| Spec | Simulator role |
|---|---|
| **FS1, FS2** | Instrument: emits the reference packet sequences these measurements are defined against; ground-truth log provides transmit-side timestamps. |
| **FS13** | Oracle: independently parses and validates every received order packet against the documented layout — a second implementation of the protocol spec, which is the strongest practical test of the spec document's completeness (a claim already vindicated during design: see the Modify-semantics finding in 3.4.4.6). |
| **NFS2** | Peer: the other endpoint of the 10-minute zero-drop window; its TX count is the expected-frame denominator. |
| **NFS4** | Provider: generates the full 6.5-hour session the SoC must survive. |
| **NFS8** | Injector: produces the corrupted-checksum packets and over-depth bursts the fault-handling tests require. |
| **NFS9** | Injector: supplies the synthesized line-rate PCAP the throughput test specifies. |
| **FS6/FS7 (bootstrap)** | Data source: before any live sessions exist, recorded simulator sessions are the backtest corpus (3.3 Decision 4's bootstrap case) and the regime-classifier exercise data. |
| **NFS3** | The simulator is pure software on the host PC, which NFS3 explicitly excludes from the cost cap — subsystem hardware cost is $0. |

Figure 3.6 shows the simulator's internal structure and its two link-level interfaces. *(Figure placeholder — component diagram: Scenario Engine → Order-Flow Generator [synthetic driver | LOBSTER-replay driver] → [Book Mirror, Protocol Encoder → EventSink: UDP TX | PCAP writer]; UDP RX → Order Executor → Ground-Truth Logger; all components writing to the Ground-Truth Logger.)*

---

## 3.4.2 Engineering Design Process

### Decision 1 — Market-data source: a four-iteration design history

This decision went through four documented iterations driven by successively discovered external constraints; each reversal is retained because the constraints, not preferences, did the deciding.

**Iteration 1 — broker paper-trading account as the exchange (initial concept, rejected).** The most "real" option available to the team: use a retail broker's simulated-trading environment (Interactive Brokers, Webull, Futu-class APIs) as the live counterparty, so the SoC trades real market data with fake money. Three structural mismatches killed it. (1) *Interface*: broker APIs are REST/WebSocket sessions to the broker's cloud, with latencies in the tens-of-milliseconds-to-seconds class — they cannot terminate our point-to-point PL GbE link or speak the FS13/Table-3.1.4 custom UDP protocol, so the entire PL path (the project's core) would be untestable against them. (2) *Controllability*: no broker will emit a corrupted-FCS frame or a line-rate microburst on request — every NFS8/NFS9 verification procedure becomes unimplementable. (3) *Reproducibility*: live market data is unrepeatable by definition; a failed FS2 run could never be re-run on identical input.

**Iteration 2 — the granularity ceiling (real-data ambitions narrowed by evidence).** Rejecting the broker *interface* did not settle whether real market *data* could still drive the simulator. Investigating this surfaced a harder constraint: the custom protocol carries **L3 order-level events** (Add/Modify/Delete keyed by `order_id`, Table 3.1.4), but retail-tier APIs top out at **L2**. Interactive Brokers' own documentation defines its market-depth product as "level II," delivered as *aggregated price-level rows* (position/operation/price/size callbacks) with no order identifiers [10] — and depth subscriptions are per-venue paid market-data lines whose availability on paper accounts is itself conditional. The published record confirms this is a structural boundary, not a shopping failure: the one cited system that operated against genuine order-level exchange messaging below the co-location tier did so through a *futures-broker member test server* [2], and He et al.'s order-book-update work drew CFFEX message streams from the exchange's internal unified data bus — access mediated by an institutional research relationship, not a public endpoint [3]. No tier of the literature obtains L3 through a retail channel, because no retail channel carries it.

**Iteration 3 — real L3 exists after all, behind a price wall with a free crack (the LOBSTER discovery).** The academic market-microstructure community solved exactly this access problem a decade ago: LOBSTER reconstructs order-level limit-order-book data — every submission, cancellation, deletion, and execution, keyed by order ID — for the entire NASDAQ universe from Historical TotalView-ITCH files [11], and has served as the community's standard source since 2013. Full access is a paid academic subscription (published price list: £6,897/year [12]) — out of the question for a capstone. But LOBSTER publishes **free official sample files** [13]: one full trading day (2012-06-21) for AAPL, AMZN, GOOG, INTC, and MSFT at 1/5/10/30/50 book levels, each comprising a `message` file (time, type, order ID, size, price, direction — the L3 event stream itself) and a level-by-level `orderbook` snapshot file. One day of five symbols cannot be a *production data source*, but it is exactly sufficient for what the instrument identity actually needs from real data: a ground-truth check that the protocol, the translation semantics, and the generator's statistical assumptions survive contact with a real order flow. (The team notes, without needing it as evidence, that published FPGA order-book work has used this same sample day and ticker set — e.g., the MSFT 2012-06-21 dataset in [14].)

**Iteration 4 — final architecture: one generator, two drivers.** The end state is not a choice between synthetic and real data but a role assignment:

| Driver | Role | Rationale |
|---|---|---|
| **Seeded synthetic driver** (verification mode — primary) | Sole input source for every Section 2 verification procedure: FS1/FS2 reference sequences, NFS8 fault injection, NFS9 line-rate PCAPs, NFS4 soak sessions, FS6/FS7 bootstrap corpus | Deterministic (same seed ⇒ bit-identical byte stream, measured in 3.4.4.3), unlimited-volume, scriptable faults and bursts — properties no recorded dataset can offer. Its statistical parameters (event mix, burst profile) are **calibrated from the real dataset** (3.4.4.6), so "synthetic" no longer means "guessed." |
| **LOBSTER-replay driver** (validation mode — one-shot and regression) | Replays the real AAPL sample day through the identical Protocol Encoder and EventSink; used to validate protocol/translation semantics against real order flow and to provide one real-data session for demonstration | Real data used where realism is the point; excluded from spec verification because a single fixed day offers no fault injection, no rate control, and no volume scaling |

Both drivers emit through the same abstract `EventSink` (socket / PCAP-writer), so everything downstream — encoder, book mirror, logger, PL — is provably indifferent to the driver. This iteration history is also the origin of two protocol-level findings (sub-penny prices; Modify-semantics ambiguity) reported in 3.4.4.6 — discoveries that would not have occurred under Iteration 1's architecture and that alone justify the investigation's cost.

### Decision 2 — Execution model: full matching engine vs. validate-and-log executor under a no-impact assumption

| Alternative | Description | Outcome |
|---|---|---|
| Full price-time-priority matching engine | Received orders rest in the simulator's book, match against generated flow, and produce fills; our orders alter the market-data stream. | **Rejected for the prototype.** A matching engine is a substantial correct-by-construction artifact (price-time priority, partial fills, self-match handling) whose output — realistic fills and market impact — no Section 2 specification consumes. Under the C2 fill-semantics decision, fill timing is modeled PS-side; the simulator does not need to adjudicate fills at all. The cost would be large, the verification burden larger (the matching engine would itself need a test bench), and the marks zero. |
| Validate-and-log executor, no-impact assumption (selected) | Every received order packet is parsed against the FS13 layout, range-checked, timestamped, and logged; the generated market-data stream is **not** altered by received orders. | **Selected.** This is exactly the FS13 oracle role: an independent second implementation of the protocol parse is the strongest practical check of the spec document (any ambiguity in Table 3.1.5 surfaces as a disagreement between the PL encoder and the simulator parser — at which point the *document* gets fixed, which is FS13's actual point; 3.4.4.6 records this mechanism already firing once on the RX-side table during design). The no-impact assumption is stated openly as a modeling boundary: with FS3 capping orders at 1,000 shares against a book quoting thousands of shares per level, self-impact would be second-order even if modeled. `[TEAM: state the no-impact assumption in the report's limitations paragraph; it is a deliberate scope cut, not an oversight.]` |

**The closed-loop caution from the literature.** The survey of deployed systems is blunt about open-loop order emission: only the Toshiba production systems close the post-trade loop, pairing the FPGA's inline order path with CPU-side order confirmation and position-state management [8], [9] — because an exchange-facing device that fires orders without tracking their disposition carries unbounded exposure. AQTA's architecture already embodies this division: the PS-side Runtime Risk Guard and open-order table (3.2.3.3, amended FS3/FS14) are the CPU-side state machine, and the C2 fill model closes the loop in simulation. If fill semantics are later upgraded to C1, the executor gains exactly one behavior — emit a `msg_type 0x04` execution report over the same link after a configurable delay — without touching the generator or book mirror; the decision structure deliberately leaves that seam open.

### Decision 3 — Rate architecture: one online generator for everything, or an offline-generate / online-replay split

This decision was forced by measurement, not preference. The subsystem faces two rate regimes separated by roughly five orders of magnitude: *session mode* (a realistic trading day — measured on the real dataset at an average of **17.1 msg/s** with a peak 100 ms burst equivalent to **2,390 msg/s**; 3.4.4.6) and *stress mode* (NFS9's full wire-speed injection at 1.389 M packets/s, the 3.1.4.1 ceiling).

Microbenchmarks on the development sandbox (3.4.4.1) measured the Python online path at: UDP `sendto` alone ≈ **450 K pps**; event generation + protocol encode alone ≈ **91 K events/s**; combined generate-and-send ≈ **143 K events/s**. Two conclusions follow. First — and contrary to the initial working assumption that the socket would be the bottleneck — **generation is the slower half**: no amount of socket optimization (sendmmsg batching, raw sockets) reaches line rate, because the entire online path is structurally ~10× short of 1.389 M pps at the generation stage. Second, session mode has enormous headroom: 143 K events/s measured capability against a real-data peak burst of 2,390 msg/s is a **~60× margin at the burst peak and ~8,000× at the session average** — single-threaded Python is comfortably sufficient.

| Alternative | Description | Outcome |
|---|---|---|
| Single online generator (Python) | One process serves both modes. | **Rejected by measurement** — 143 K events/s < 1.389 M pps by ~10×. |
| Single online generator (rewrite in C) | Port the generator to C for line rate. | **Rejected.** Buys speed session mode doesn't need to serve a stress mode with a cheaper structural answer (below); reintroduces the productivity cost the Python selection avoids; and NFS9's verification procedure *already specifies* PCAP injection, not live generation. |
| **Offline-generate / online-replay split (selected)** | The generator gains a second output backend: instead of a socket, it writes the identical byte stream into a **PCAP file offline** (where generation speed is irrelevant). Stress mode replays that PCAP at line rate with a dedicated replay tool (`tcpreplay --topspeed` class `[EVIDENCE: verify the chosen tool + host NIC sustain 1.389 M pps of 90 B frames; fallback: a minimal AF_PACKET/sendmmsg C blaster — ~100 lines, far smaller than a C generator]`). | **Selected.** The split assigns each requirement to the regime where it is easy: correctness and determinism live in the offline generator (slow, rich, testable Python); raw rate lives in the replayer (dumb, fast, semantically empty). This mirrors NFS9's own verification wording and is the standard test-bench pattern of separating stimulus *synthesis* from stimulus *injection*. |

**A semantic honesty note on stress mode.** A looped or pre-generated line-rate PCAP is a *throughput* test, not a *semantic* test: at 1.389 M pps the PS-side conflation means virtually no snapshot is individually observed, and if the PCAP is looped, `order_id` sequences repeat and book state ceases to be meaningful. That is acceptable — NFS9's pass criterion is drop-counter deltas, not book correctness — but the report must say so explicitly rather than imply the stress run exercises trading semantics. `[TEAM: PCAP sizing choice in 3.4.4.2 — single long file vs. looped short file.]`

### Decision 4 — Test controllability: hardcoded test modes, interactive control, or declarative scenario files

| Alternative | Description | Outcome |
|---|---|---|
| Hardcoded test modes | Compile/flag-selected behaviors (`--test-nfs8-checksum`, …). | **Rejected.** Every new verification case is a code change; combinations (burst *during* a fault) need their own flags; the mapping from Section 2 procedures to simulator behavior lives in code nobody reads. |
| Interactive control (live console) | Operator triggers faults manually during a run. | **Rejected as the primary mechanism.** Manual timing is unreproducible — the exact property Decision 1 exists to provide. Retained as a debug convenience only. |
| **Declarative scenario files (selected)** | The session config JSON (3.4.3.3) carries a `scenario` array: timestamped directives (`at t=120s: corrupt_fcs count=1`, `at t=300s: burst rate=line duration=50ms`, `at t=600s: malformed_field msg_type=0x07`). The Scenario Engine splices these into the generated stream at the protocol-encoder stage. | **Selected.** Each Section 2 verification procedure becomes a **checked-in artifact**: `scenario_nfs8_fcs.json`, `scenario_nfs9_linerate.json`, `scenario_fs2_reference_1000.json` — reviewable, diffable, re-runnable, and cited directly from the verification write-ups. The verification plan stops being prose and becomes configuration. |

---

## 3.4.3 Final Design Details

### 3.4.3.1 Component structure and data flow

One Python process, six components, one thread on the hot path `[TEAM: confirm single-threaded is sufficient given 3.4.4.1 margins; it simplifies determinism reasoning]`:

1. **Scenario Engine** — loads the session config; owns the master event clock; interleaves scheduled scenario directives with driver output.
2. **Order-Flow Generator (dual-driver)** — either the *synthetic driver* (steps the midprice process and order-arrival process from the seeded PRNG) or the *LOBSTER-replay driver* (streams the real message file through the translation layer of 3.4.4.6, after a book-priming step for pre-session orders). Both emit abstract L3 events that are always consistent with the Book Mirror's state (invariant I1, 3.4.4.4).
3. **Book Mirror** — applies each emitted event to the simulator's own copy of the book; this is the ground-truth book against which the PL's order-book construction (3.1) is verified.
4. **Protocol Encoder** — packs events into the Table 3.1.4 layout.
5. **EventSink** — the abstract output seam: UDP TX over the point-to-point link (session/validation modes) or PCAP writer (offline stress-generation mode). Same bytes either way (verified property, 3.4.4.3).
6. **Order Executor (validate-and-log) + Ground-Truth Logger** — parses every received order packet against Table 3.1.5 (FS13 oracle) and appends it to the ground-truth log; the logger also records every transmitted event with a host timestamp.

### 3.4.3.2 Order-flow model (synthetic driver)

The synthetic driver's realism target is deliberately modest — *statistically plausible, structurally valid* L3 flow, calibrated against the real dataset rather than guessed:

| Element | Model | Rationale |
|---|---|---|
| Midprice | Integer-cents random walk with configurable drift and step-volatility per regime segment `[TEAM: plain walk vs. OU mean-reversion for RANGING segments — OU is a one-line change and makes RANGING segments genuinely range-bound]` | Integer cents end-to-end (matches the PL/PS integer commitment); regime parameters per segment let one session exercise all three 3.3 regimes |
| Order arrivals | Poisson-clocked event stream; mix ratio calibrated from the real sample: **Add ≈ 48%, Delete ≈ 43%, Modify/partial ≈ 3%, executions ≈ 6%** (measured, 3.4.4.6) `[TEAM: confirm; the earlier working figures of 55/25/20 are superseded — real flow is add/delete-dominated with rare modifies]`; prices placed within ±10 levels of mid `[TEAM: distribution]` | Keeps the 10-level PL book window (3.1 Decision 4) exercised, including deliberate out-of-window events to hit the `dropped_out_of_window` counter |
| Rate profile | Piecewise-constant base rate with scheduled bursts; realistic envelope anchored to measured data (session average ~17 msg/s, burst peaks ~2.4 K msg/s; open/close activity concentration) | NFS2/NFS4 realism; NFS8 FIFO-overflow injection requires bursts far above the realistic envelope, which the scenario engine supplies |
| Regime schedule | Session config declares segments: `[{t: 0, regime: RANGING}, {t: 2h, regime: VOLATILE}, …]` mapping to (drift, vol, rate) parameter sets | Generates labeled sessions → the 3.3 classifier can be tested against *known* ground-truth regimes, a stronger test than unlabeled real data `[TEAM: add to 3.3's verification plan — classifier accuracy against simulator-labeled segments]` |

### 3.4.3.3 Session configuration and ground-truth log

**Session config (JSON):** `{driver: synthetic|lobster_replay, seed | dataset_path, duration_s, symbol_id, initial_mid_cents, regime_schedule[], rate_profile[], scenario[]}`. Under the synthetic driver, the seed *is* the session: config + generator version ⇒ bit-identical byte stream (3.4.4.3), so a session is *named* by its config file, and every verification run cites one. Under the replay driver, the dataset file hash plays the same role.

**Ground-truth log (append-only, one line per event):** `{host_ts_ns, dir: TX, raw_bytes_hex, decoded_fields, book_top_after}` for TX; `{host_ts_ns, dir: RX, raw_bytes_hex, parse_result, fault_code?}` for RX. This log is the **golden reference** the other subsystems' logs are diffed against: the PL's book (via PS snapshots in the FS5 export) against `book_top_after`; PS decision timestamps against TX/RX host timestamps for the FS2/NFS1 cross-checks (single host clock covers both directions; Wireshark on the same NIC remains the primary instrument, the ground-truth log the redundant second witness). `[TEAM: log volume trade — full raw_bytes_hex at high rates is large (3.4.4.5); default ON for verification sessions, OFF for soak runs.]`

### 3.4.3.4 Link and host configuration

Host NIC directly cabled to the PL RJ45 (no switch — NFS2's "no unexplained drops" argument depends on this), static IP/MAC matching the PL's compile-time constants (3.1.3.1), UDP checksum emitted as zero (per 3.1.3.1's accept-zero decision — the PL parser ignores the field). The simulator host may be the same physical machine as the EOD server `[TEAM: confirm — separate processes either way; nothing couples them intraday]`. Wireshark/tcpdump capture on this NIC is the shared instrument for FS2/NFS1/NFS2 procedures.

---

## 3.4.4 Quantitative Technical Analysis

### 3.4.4.1 Session-mode rate capability — measured

Microbenchmarks on the development sandbox (Python 3, loopback socket, 20–24 B payloads; caveats: loopback ≠ real NIC path, sandbox ≠ target host — order-of-magnitude evidence `[EVIDENCE: re-run on target host]`):

```
UDP sendto alone:            449,965 pps    (socket path)
Event generation + encode:    91,192 ev/s   (PRNG step + book-mirror update + struct.pack, no socket)
Combined generate-and-send:  142,827 ev/s   (the true online session-mode ceiling)
```

Set against the *measured* real-feed profile (3.4.4.6: 17.1 msg/s session average, 584 msg/s peak second, 2,390 msg/s peak 100 ms burst equivalent), the 1.4 × 10⁵ ev/s online ceiling gives a **~60× margin over the worst real burst and ~8,000× over the session average** — single-threaded Python session mode is settled by arithmetic. The same numbers show the online path is **~10× short of the 1.389 M pps wire ceiling**, and — the non-obvious measured fact — the shortfall is in *generation* (91 K/s), not the socket (450 K/s): this kills the "just optimize the send path" option and forces Decision 3's offline/online split on arithmetic rather than taste.

### 3.4.4.2 Stress-mode PCAP sizing (NFS9)

At the 3.1.4.1 wire ceiling, one second of line-rate traffic is 1.389 M frames × 90 B = **125 MB/s** (= 1 Gbps, as it must). Sizing options:

```
Continuous 60 s line-rate PCAP:  1.389 M × 60 × 90 B ≈ 7.5 GB   (single file, unique order_ids)
Looped 1 M-frame PCAP:           90 MB file, looped N times      (order_ids repeat per loop)
Offline generation time:         83.3 M frames ÷ 91 K ev/s ≈ 15 min for the 60 s file (one-time cost)
```

Either satisfies NFS9's drop-counter criterion; the looped file is operationally lighter at the cost of the semantic caveat in Decision 3. `[TEAM: recommend looped 90 MB file for routine runs + one 7.5 GB unique-ID file for the formally reported NFS9 result, so the reported run carries no loop asterisk.]` NFS9's micro-burst clause is additionally covered in session mode by scenario-driven bursts of ≤ 50 ms (≈ 69 K frames, pre-synthesized into a burst buffer).

### 3.4.4.3 Determinism — measured

Same-seed reproducibility was checked directly rather than asserted: two 10,000-event streams from identical seeds are **byte-identical**, and a different seed diverges (measured on the synthetic driver). The design conditions this rests on: single-threaded generation, integer arithmetic in the event model, Python's `random.Random(seed)` (Mersenne Twister — version-stable), and no wall-clock dependence in event *content* (host timestamps appear only in the ground-truth log, never in the byte stream). Consequence chain: deterministic byte stream ⇒ deterministic PL book states ⇒ deterministic PS snapshot sequence ⇒ FS7's backtest bootstrap corpus is reproducible end-to-end from a seed list. `[EVIDENCE: extend the check to full-session length and across both EventSink backends — socket-mode bytes must equal PCAP-mode bytes for the same seed and the same replay dataset.]`

### 3.4.4.4 Generator correctness invariants (the simulator's own test plan)

The simulator is a verification instrument, so its own correctness needs an argument that does not circularly depend on the system under test. Three machine-checkable invariants, enforced in both drivers and asserted in tests `[EVIDENCE: property-based test — 10⁷-event synthetic runs across many seeds; full-dataset replay run]`:

| Invariant | Statement | Why it matters downstream | Real-data status (3.4.4.6) |
|---|---|---|---|
| I1 — referential integrity | Every Modify/Delete references an `order_id` currently live in the Book Mirror | The PL book builder (3.1.3.1 stage 5) is entitled to assume well-formed L3 flow | Enforced by the translation layer; 2.09% of raw LOBSTER messages reference pre-session orders and are handled by book-priming `[TEAM: priming vs. filtered-with-counter]` |
| I2 — book non-negativity | No aggregate level quantity ever goes negative; no order's remaining quantity goes negative | Ground-truth `book_top_after` must be a valid book or the golden reference is worthless | **0 violations** across 400,391 real messages |
| I3 — encode/decode round-trip | `decode(encode(event)) == event` for the simulator's own encoder against its own Table-3.1.4 parser | The oracle property of Decision 2: self-round-trip is its base case | **0 failures** across 380,678 real encoded events |

### 3.4.4.5 Session data-volume arithmetic (NFS4 soak, log sizing)

```
6.5 h session at 1,000 msg/s configured average (stress-leaning synthetic profile;
 the real-data average is 17 msg/s, so 1,000 is a deliberate ~60× margin session):
                                        23,400 s × 10³ = 23.4 M events
Ground-truth log, full mode (~120 B/line with hex):  ≈ 2.8 GB/session   → verification sessions: fine on host disk
Ground-truth log, soak mode (no hex, ~40 B/line):    ≈ 0.94 GB/session  → NFS4 soak: fine
Generated wire traffic: 23.4 M × 90 B ≈ 2.1 GB over 6.5 h ≈ 0.7 Mbps avg — the link is ~0.07% utilized;
NFS2/NFS4 stress the SoC's endurance, not the wire
```

### 3.4.4.6 Real-data validation: LOBSTER replay through the protocol layer — measured

The full free-sample dataset — 400,391 real order-level messages, AAPL, one complete NASDAQ trading day (2012-06-21), top-10 book levels [13] — was run through a prototype of the replay driver's translation layer and the Table 3.1.4 encoder. This is a validation of the *protocol and translation semantics against real order flow*, executed at design time precisely so its findings could shape the design rather than audit it. Four results and two findings:

**Result 1 — real rate profile (supersedes all earlier estimates).** Session average **17.1 msg/s**; peak one-second rate **584 msg/s**; peak 100 ms burst **2,390 msg/s equivalent**. These figures replace the `[EVIDENCE]`-flagged guesses previously carried in this section and in Decision 3, and they recalibrate the margins in 3.4.4.1. They also put NFS9 in perspective: the 1.389 M pps stress requirement exceeds this real symbol's *peak burst* by ~580× — line-rate robustness is an engineering-margin specification, not a realism one, and the report should present it as such.

**Result 2 — event-mix calibration.** Real composition: submissions 47.7%, full deletions 42.7%, visible executions 5.9%, hidden executions 2.8%, partial cancels 0.8%. The synthetic driver's mix table (3.4.3.2) now cites these measured ratios; the earlier working figures (55/25/20) were materially wrong about modify frequency — real flow is add/delete-dominated, and modifies are rare.

**Result 3 — field-width confirmation.** Max real `order_id` = 287,150,931 (u32: fits, 15× headroom); max size 15,000 shares (u32: trivial). Table 3.1.4's field widths survive contact with real data.

**Result 4 — translation throughput and invariants.** The Python translation layer (order-pool tracking + encode) processed the full day at **1.10 M msg/s** — the entire real session translates offline in 0.37 s, so replay preparation is never a cost. I2 and I3 passed with zero violations across the full dataset (table in 3.4.4.4).

**Finding 1 — sub-penny prices break the integer-cents assumption (protocol change required or policy needed).** 372 of 400,391 real events (0.09%) carry prices that are *not* whole cents (LOBSTER prices are dollars ×10⁴; these events have a nonzero residue mod 100 — sub-penny executions/price-improvement prints). The Table 3.1.4 `price` field is specified in integer cents, so these events cannot be represented exactly. Options: (a) round-to-cent with a documented policy and a `price_rounded` counter (zero protocol change; 0.09% of events carry ≤ $0.005 error), or (b) redefine the price field unit as 10⁻⁴ dollars (exact; costs nothing in width — u32 spans $429,496 at 10⁻⁴ — but touches the PL parser, PS strategy arithmetic, and 3.3's kernel-parity chain). `[TEAM: decide; recommendation (a) for the prototype — the affected events are executions rather than restizng book liquidity, and the parity chain's integer-cents commitment (3.2.3.2, 3.3 Decision 4) is otherwise disturbed end-to-end.]`

**Finding 2 — the Modify-semantics ambiguity (the FS13 oracle mechanism fired at design time).** Writing the translation forced a question Table 3.1.4 does not answer: does a Modify's `qty` field carry the *new absolute* quantity or a *delta*? LOBSTER's partial-cancel and execution events carry deltas; the translation had to pick a convention (absolute remaining quantity was chosen) and the PL book-update stage must agree or the books diverge silently. This is precisely Decision 2's claim — that an independent second implementation is the strongest test of the protocol document — vindicated before any hardware exists: the ambiguity is now a required amendment to Table 3.1.4's field description rather than a future integration bug. `[TEAM: amend Table 3.1.4 — specify "qty = new absolute aggregate for this order" (recommended, stateless for the PL) and mirror the wording in the 3.1.3.1 stage-5 description.]`

**Honest scope statement.** This validation exercises the translation layer and encoder on the development sandbox; it does not exercise the physical link, the PL parser, or timing (those are the Section 2 procedures, which remain pending). One symbol-day is a semantic ground-truth check, not a statistical study; the mix and rate figures above are one liquid large-cap's behavior on one 2012 day and are used as *calibration anchors*, not as claims about markets in general.

---

## 3.4.5 Specification Compliance / Instrumentation Summary

| Spec | What the simulator provides | Evidence status |
|---|---|---|
| FS1/FS2 (instrument) | Seeded reference sequences (`scenario_fs2_reference_1000.json`); TX-side ground-truth timestamps | Design complete; pending scenario-file authoring |
| FS13 (oracle) | Independent parse of every order packet; disagreements surface spec ambiguities | Mechanism validated at design time (Finding 2, RX-side analog); pending live cross-parse |
| NFS2 (peer) | Direct-cabled link peer; TX frame counts as expected-delivery denominator | Pending 10-min counted run |
| NFS4 (provider) | 6.5 h seeded session; soak-mode logging (0.94 GB) | Pending soak run |
| NFS8 (injector) | Scenario directives: `corrupt_fcs`, `burst`, `malformed_field` | Pending scenario-file authoring + injection runs |
| NFS9 (injector) | Offline-generated PCAP (90 MB looped / 7.5 GB unique) + line-rate replayer | Pending replayer line-rate validation `[EVIDENCE]` |
| FS6/FS7 (bootstrap) | Regime-labeled, seed-reproducible session corpus; plus one real-data session (LOBSTER replay) | Synthetic corpus pending; real-data translation validated (3.4.4.6) |
| Own correctness | Invariants I1–I3; determinism (measured); rate margins (measured); real-data validation (measured, full dataset) | Sandbox-measured; target-host re-runs pending |

---

## References

[1] C. Leber, B. Geib and H. Litz, "High Frequency Trading Acceleration Using FPGAs," *2011 21st International Conference on Field Programmable Logic and Applications*, Chania, Greece, 2011, pp. 317-322, doi: 10.1109/FPL.2011.64.

[2] Y.-C. Kao, H.-A. Chen and H.-P. Ma, "An FPGA-Based High-Frequency Trading System for 10 Gigabit Ethernet with a Latency of 433 ns," *2022 International Symposium on VLSI Design, Automation and Test (VLSI-DAT)*, Hsinchu, Taiwan, 2022, pp. 1-4, doi: 10.1109/VLSI-DAT54769.2022.9768065.

[3] C. He, H. Fu, W. Luk, W. Li and G. Yang, "Exploring the potential of reconfigurable platforms for order book update," *2017 27th International Conference on Field Programmable Logic and Applications (FPL)*, Ghent, Belgium, 2017, pp. 1-8, doi: 10.23919/FPL.2017.8056862.

[4] G. W. Morris, D. B. Thomas and W. Luk, "FPGA Accelerated Low-Latency Market Data Feed Processing," *2009 17th IEEE Symposium on High Performance Interconnects*, New York, NY, USA, 2009, pp. 83-89, doi: 10.1109/HOTI.2009.17.

[5] M. Mohamed Asan Basiri, "Hardware based Order Book Design in High Frequency Algo Trading," *2021 IEEE International Symposium on Smart Electronic Systems (iSES)*, Jaipur, India, 2021, pp. 285-288, doi: 10.1109/iSES52644.2021.00073.

[6] A. Boutros, B. Grady, M. Abbas and P. Chow, "Build fast, trade fast: FPGA-based high-frequency trading using high-level synthesis," *2017 International Conference on ReConFigurable Computing and FPGAs (ReConFig)*, Cancun, Mexico, 2017, pp. 1-6, doi: 10.1109/RECONFIG.2017.8279781.

[7] R. Osuna, B. Reponte, and L. G. Ramirez, "Low-latency Ethernet communications on FPGA SoC for high frequency trading," Kastner Research Group, University of California, San Diego, San Diego, CA, USA, Tech. Rep., Jun. 2025. [Online]. Available: https://kastner.ucsd.edu/wp-content/uploads/2025/06/admin/highfrequencytrading.pdf

[8] K. Tatsumura, R. Hidaka, J. Nakayama, T. Kashimata, and M. Yamasaki, "Real-time Trading System based on Selections of Potentially Profitable, Uncorrelated, and Balanced Stocks by NP-hard Combinatorial Optimization," Corporate Research and Development Center, Toshiba Corporation, Japan, 2023.

[9] K. Tatsumura, R. Hidaka, J. Nakayama, T. Kashimata, and M. Yamasaki, "Pairs-trading System using Quantum-inspired Combinatorial Optimization Accelerator for Optimal Path Search in Market Graphs," Corporate Research and Development Center, Toshiba Corporation, Japan, 2023.

[10] Interactive Brokers, "Market Depth (Level II)," TWS API v9.72+ Documentation. [Online]. Available: https://interactivebrokers.github.io/tws-api/market_depth.html [Accessed: Jul. 9, 2026].

[11] R. Huang and T. Polak, "LOBSTER: Limit Order Book Reconstruction System," SSRN Working Paper 1977207, Humboldt-Universität zu Berlin, Dec. 2011, doi: 10.2139/ssrn.1977207.

[12] LOBSTER, "Price List — Academic Users," LOBSTER academic data. [Online]. Available: https://data.lobsterdata.com/info/docs/legal/LOBSTER_priceList.pdf [Accessed: Jul. 9, 2026].

[13] LOBSTER, "Sample Files" and "Data Structure," LOBSTER academic data, Humboldt-Universität zu Berlin. [Online]. Available: https://lobsterdata.com/info/DataSamples.php ; https://lobsterdata.com/info/DataStructure.php (dataset: AAPL 2012-06-21, levels 1–50; official NASDAQ Historical TotalView-ITCH sample day). [Accessed: Jul. 9, 2026].

[14] Y. Zheng, "FPGA-based Acceleration for High Frequency Trading," M.Phil. thesis, Dept. Electron. Comput. Eng., Hong Kong Univ. Sci. Technol., Hong Kong, Jan. 2023.

[15] J. D. Hamilton, "A New Approach to the Economic Analysis of Nonstationary Time Series and the Business Cycle," *Econometrica*, vol. 57, no. 2, pp. 357–384, Mar. 1989, doi: 10.2307/1912559.

[16] J. Bergstra and Y. Bengio, "Random Search for Hyper-Parameter Optimization," *Journal of Machine Learning Research*, vol. 13, pp. 281–305, Feb. 2012.

[17] D. Araci, "FinBERT: Financial Sentiment Analysis with Pre-trained Language Models," arXiv preprint arXiv:1908.10063, Aug. 2019.

### Further reading (uncited in this document)

- FIX Trading Community, "FIX Adapted for STreaming (FAST) Specification." [Online]. Available: https://www.fixtrading.org/standards/fast-online/ [Accessed: Jul. 9, 2026].
- J. Zang, "quant-engine: a C++ quantitative backtest and research engine," independent project documentation. [Online]. Available: https://qe.jiucheng-zang.ca [Accessed: Jul. 2026].

`[TEAM: bibliography housekeeping — (i) confirm the Toshiba entries' actual venues (both appear to be published papers; locate DOI/venue before submission); (ii) confirm the citation style guide for online resources; (iii) Hamilton 1989, Bergstra & Bengio 2012, and FinBERT/Araci 2019 are now in the list as [15]–[17]; 3.3's remaining pending citations (Loughran-McDonald 2011, TradingAgents 2024/2412.20138) should be appended if and when actually cited.]`

