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
| **FS11** | Live status output | Real-time order-book/decision report via Debug UART, printed to console and logged to file. | Confirm console + log output during an active session. | **N** |
| **FS12** | EOD pipeline logging | Log pipeline stage, classified regime, selected strategy/parameters, backtest Sharpe, and approval status as each stage completes. | Run full cycle, confirm one log entry per stage transition. | **N** |
| **FS13** | Order packet format | Fixed-length binary format with order ID, symbol, side, quantity, and price, documented as a standalone protocol spec. | Parse a captured packet against the documented layout. | **Y** |
| **FS14** | In-flight order tracking | Track state of every in-flight order, up to 100 concurrent, without corruption or loss. | Drive in-flight count to the limit, confirm correct state via log inspection. | **Y** |

*(FS9 and FS10 — a text-ingestion/LLM-sentiment path — were dropped from scope: the only real market-data anchor available to this project is LOBSTER's single free sample day (3.4.2), and no equivalent real, licensable text/news source for that same window exists, so the path could never be validated against anything but a mocked server. IDs are left unrenumbered to avoid touching every downstream reference to FS11–FS14.)*

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
| **NFS8** | Owns the hardware fault path: checksum-fail discard and FIFO-overflow handling with fault counters. |
| **NFS4** | Hardware fault paths (FCS discard, FIFO-overflow handling, drop counters) keep line-rate faults from escalating into a session-ending hang; primary ownership of the 6.5-hour stability requirement remains with the PS (3.2.1). |

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
| NFS1 | RX segment ≤ 1.5 μs; TX encode segment is a fixed ~80-cycle (≈ 0.65 μs) path by the same octet-per-cycle arithmetic as 3.1.4.2 — doorbell latch + ~75 B order frame streamed at 1 octet/cycle | Analytical |
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
| **NFS1** | Owns the dominant software segment of the ≤ 50 μs typical budget. |
| **NFS4** | Primary owner: 6.5-hour session with no crash/hang/unrecovered error. |
| **NFS8** | Owner of software fault handling: malformed-config rejection at load time, fault-coded logging, continue-without-restart. |

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

`mid` is held in half-cent units (`best_bid + best_ask`) so the arithmetic stays integer, like all prices from the PL — this avoids FPU state on the isolated core and makes decisions bit-reproducible for backtest cross-validation, extending FS7's determinism to the SoC side. Every window, threshold, and position scalar loads from the FS4 JSON config — the parameter names are exactly the axes swept in 3.3.3.3 (`lookback/entry_thresh/pos_scalar`, `window/dev_thresh/pos_scalar`, `spread_floor/vol_cutoff/pos_scalar`) — so tuning never requires recompilation. The formulas are deliberately simple: per-strategy sophistication lives in the EOD parameter sweep (3.3), not the intraday rule; the design's contribution is the deterministic, reconfigurable evaluation machinery, not the alpha.

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

At startup, before core 1 begins polling, the loader ingests the JSON configuration (either from the board's SD/TF card slot or via an `scp`/SSH push from the EOD server to a staging path, per 3.3.3.7), validates schema and ranges, and populates the strategy table and Risk Guard limits. Any validation failure is NFS8's "malformed config" case: log fault code, refuse to start the polling loop, remain up for re-push — never trade on a default. Market data processing is structurally unreachable until a config commits, which is FS4's verification argument.

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
| NFS1 | FS2 path is the PS contribution; margin table 3.2.4.1 | Analytical |
| NFS4 | Linux + isolated core, no hot-path allocation; fault paths per NFS8; HOLD Mode as safe state | Pending 6.5 h soak |
| NFS8 | Config-reject path; fault-coded logging; session continues; PL `DIAG_*` counters surfaced via GP0 | Pending malformed-config injection |

# 3.3 EOD Server Pipeline Subsystem

> **Scope note:** an earlier draft of this subsystem also carried a non-essential text/LLM-sentiment path (FS9/FS10), which has been dropped from scope (rationale in the Section 2 footnote). Stage names are *Parameter Engineering, Regime Detection, Strategy Reoptimize, Backtest & Parameter Sweep, Risk Analysis, Generate JSON Config, Operator Approval*.
> All numeric analysis in 3.3.4 is derivable on paper today (dataset-size arithmetic, iteration-count budgets, complexity bounds, inequality proofs) — no code required.

---

## 3.3.1 Overview and Specification Mapping

The EOD (End-of-Day) Server Pipeline is the adaptation layer of AQTA — the component that makes the system *Adaptive* rather than a fixed-strategy appliance. It runs on a host server, off the intraday critical path, and closes the loop between one trading session and the next: it ingests the session history exported by the PS together with historical daily OHLCV data, classifies the next trading day's market regime (FS6), re-optimizes the parameters of the strategy assigned to that regime by exhaustively backtesting a bounded parameter grid (FS7). The result is assembled into a candidate JSON configuration and presented to a human operator, whose explicit approval is the only path by which it can reach the live system (FS8, transmitted to the PS Config Loader of 3.2.3.4); a REJECT or no-approval outcome instead latches the PS into HOLD Mode until an operator clears it (3.2.3.6).

The subsystem completes a three-tier latency/flexibility hierarchy established in 3.1 and 3.2: the PL is deterministic at nanosecond scale and fixed for the session; the PS decides in microseconds but is reconfigurable nightly; the EOD server may take minutes but is rewritable — the analytics, the parameter values, and the judgment about what tomorrow's market looks like. Each tier trades orders of magnitude of latency for flexibility, and the register-bank and JSON-config interfaces between tiers confine the slower tier's influence on the faster one to two channels: config load at session start, and the HOLD latch on a no-approval outcome, which only narrows the faster tier's behavior (stop trading) and never widens it. On the EOD tier the binding constraint is not latency — NFS5 grants 30 minutes — but **correctness, reproducibility, and auditability**: FS7 demands bit-identical re-runs, FS8 demands that a human can veto every output. Those two properties, not throughput, drive every design decision below.

This subsystem is directly responsible for the following specifications:

| Spec | Role of EOD subsystem |
|---|---|
| **FS6** | Sole owner: classify the next trading day's regime into ≥ 3 distinguishable states from daily market data. |
| **FS7** | Sole owner: search ≥ 9 parameter combinations for the regime's strategy and select the metric-maximizing one, with deterministic (bit-identical) output. |
| **FS8** | Sole owner of the gate: no configuration reaches the live system without explicit operator approval. (The PS Config Loader in 3.2.3.4 owns the *receiving* end of the chain of custody.) |
| **FS12 (non-ess.)** | Sole owner: display and log pipeline stage, regime, selected parameters, backtest Sharpe, and approval status as each stage completes. |
| **NFS5 (non-ess.)** | Sole owner: full pipeline (ingestion → classification → optimization → approval prompt) within 30 minutes. |
| **NFS8** | Owner of server-side fault handling: malformed/missing input data must degrade safely (log fault code, emit no config) rather than abort the nightly cycle uncleanly. |

Upstream dependency: FS5's exported session history and a historical daily OHLCV dataset are the pipeline's inputs. The OHLCV source is pinned to the project's own 3.4 corpus: seed-reproducible simulator sessions aggregated to daily bars (regime-labeled, unlimited volume, zero license cost), anchored by the real LOBSTER AAPL sample day (3.4.4.6 — a freely published official sample), so no external market-data feed or license is required. Downstream contract: the JSON configuration schema of 3.3.3.5, consumed by the PS Config Loader — jointly owned with 3.2, exactly as the register bank table of 3.2.3.1 is jointly owned with 3.1.

Figure 3.4 shows the pipeline structure. *(Figure placeholder — reuse the SERVER subgraph of the system block diagram, minus the Console Monitor, which belongs to the PS peripheral group per the final subsystem split, and minus the External Resources / Web-News-Social block and its NLP/LLM Pipeline and sentiment arrows, dropped along with FS9/FS10 — see Section 2 footnote. The EOD→PS arrow should be annotated as the HOLD-latch/config-push path of 3.2.3.6 and 3.3.3.7, not as a generic link.)*

---

## 3.3.2 Engineering Design Process

Three significant design decisions shaped this subsystem. The recurring theme differs from 3.1/3.2: there, the specs priced in *latency* and the decisions bought determinism of *timing*; here, the specs price in *reproducibility and human oversight* and the decisions buy determinism of *results*. Where a rationale is quantitative, the supporting arithmetic appears in 3.3.4.

### Decision 1 — Execution environment: Python host pipeline

A scan of the open-source tooling landscape converged quickly on one answer: a Python 3 host pipeline — pandas/NumPy for data handling, the standard library for orchestration, the strategy kernel handled separately below (3.3.3.3). Python has the deepest library ecosystem for this workload, the most community resources to build against, and the lowest development cost of any realistic option — and NFS5's 30-minute budget is generous enough that Python's performance profile is simply not a constraint worth trading that away for.

### Decision 2 — Regime classifier (FS6): rule-based thresholds vs. Hidden Markov Model

The classifier's job in AQTA is *routing* — selecting which of the three pre-built strategies (3.2.3.2: Trending→Momentum, Ranging→Mean Reversion, Volatile→Defensive) runs tomorrow — not alpha generation. The two real candidates were a two-feature rule-based threshold classifier and a Hidden Markov Model, the more statistically sophisticated approach the regime-detection literature generally favors:

| Dimension | Rule-based threshold (selected) | Hidden Markov Model |
|---|---|---|
| Classification fidelity | Adequate for a routing decision | Best-in-literature for regime persistence [15] — but FS6's verification only checks ≥ 3 regimes appear, never scores accuracy, so this advantage is never actually tested |
| Implementation & verification cost, given team capability | Two features, three comparisons; exhaustively unit-testable in a day | Baum-Welch/EM fitting is init-sensitive; the standard multi-restart fix is itself stochastic; a new `hmmlearn` dependency none of the team has used before |
| Operator auditability (FS8) | "vol > 75th percentile ⇒ Volatile" is checkable against a chart in seconds | State posteriors need post-hoc labeling and give no intuitive account of why a day was classified a given way — the FS8 approval step becomes a formality |

HMM wins only on the one dimension FS6 doesn't verify; the rule-based classifier wins on implementation cost and on the auditability FS8 actually requires, which is decisive given the team's capability and bandwidth already committed to 3.1/3.2.

### Decision 3 — Parameter search (FS7): exhaustive grid vs. Bayesian optimization

Bayesian optimization (GP/TPE) is the more sample-efficient search method in general, and the natural instinct for anyone coming from an ML background. Weighed against what FS7 actually requires:

| Dimension | Exhaustive grid search (selected) | Bayesian optimization |
|---|---|---|
| FS7 compliance (bit-identical re-run) | Deterministic by construction — fixed enumeration order + sequential evaluation + total-order tie-break (3.3.3.3) means identical input bytes produce identical output bytes | Stochastic by nature (acquisition-function sampling); bit-identical re-run would need to be defended through strict seed and library-version discipline |
| Implementation & verification cost | Enumerate the grid, evaluate each point with the backtest kernel, pick the maximizer — no new dependency | A heavyweight dependency (e.g., scikit-optimize/GPyOpt) to defend and verify, for a 3-dimensional space that doesn't need it |
| Cost the method is solving for | N/A — 3.3.4.1 shows the entire 27-point grid evaluates in minutes, well inside NFS5's 30-minute budget | Sample efficiency, which matters when each evaluation is expensive — not the case here |
| Operator auditability (FS8) | Exhaustive: the operator report shows the *complete* 27-row sweep table | Only shows the points it chose to sample — a partial, algorithm-selected trace |

Grid search is also the more common choice in practice for this kind of low-dimensional strategy-parameter tuning: "smart" optimizers that concentrate trials near an apparent optimum are the more overfitting-prone search strategy on noisy backtest data, so a small, coarse grid is a deliberate hedge, not merely the cheaper option [16].

---

## 3.3.3 Final Design Details

The pipeline is a sequential staged program; Figure 3.5 shows the stage graph with FS12 log points at every transition. *(Figure placeholder — stage flowchart: [Data Import & Validation] → [Parameter Engineering] → [Regime Detection] → [Strategy Reoptimize / Backtest & Parameter Sweep] → [Risk Analysis] → [Generate JSON Config] → [Operator Approval] → [Transmit / or REJECT→HOLD].)*

### 3.3.3.1 Data import and Parameter Engineering

Inputs are validated before any computation (NFS8): schema check on the exported session archive, monotonic-timestamp check, minimum-history check (≥ 252 trading days of OHLCV — one year, matching the calibration window validated in 3.3.3.3.1; anything shorter risks a calibration window too thin for the percentile scheme to be meaningful). Validation failure logs a fault code and aborts before config generation — bad data produces no candidate config, not a config built on garbage.

Two features are computed from daily OHLCV closes:

| Feature | Definition | Window |
|---|---|---|
| Realized volatility `σ` | `σ = std(ln(Cₜ/Cₜ₋₁)) × √252` | 20 trading days (same window as the SMA₂₀ trend leg, for consistency) |
| Trend strength `T` | `T = (SMA₅ − SMA₂₀) / SMA₂₀` | 5- and 20-day SMAs |

Both are standard constructions; the calibration scheme below (3.3.3.2) is the real design contribution, with its non-degeneracy guarantee in 3.3.4.3.

### 3.3.3.2 Regime Detection (FS6)

```
θ_vol   = percentile(σ over calibration window, 75)    # config-adjustable
θ_trend = percentile(|T| over calibration window, 60)  # config-adjustable

if   σ_today   ≥ θ_vol:    regime = VOLATILE   → Defensive
elif |T_today| ≥ θ_trend:  regime = TRENDING   → Momentum
else:                      regime = RANGING    → Mean Reversion
```

Pure function of the input window — no state, no seed, no fit. Unit tests cover all three branches plus both boundary equalities (`≥` resolves ties toward the safer, Defensive branch).

### 3.3.3.3 Strategy Reoptimize — Backtest & Parameter Sweep (FS7)

Working grids (each 3 × 3 × 3 = 27 combinations ≥ FS7's minimum 9), deliberately coarse per Decision 3's overfitting mitigation. Thresholds below are in the daily-bar proxy units of the 3.3.3.3.1 validation run; the live intraday config carries their integer half-cent equivalents per 3.2.3.2 (the validation run substituted a vol-window axis for the Defensive spread floor, since daily bars carry no spread):

| Strategy | Parameter 1 | Parameter 2 | Parameter 3 |
|---|---|---|---|
| Momentum | lookback ∈ {5, 10, 20} | entry threshold ∈ {0.005, 0.01, 0.02} | position scalar ∈ {0.5, 1.0, 1.5} |
| Mean Reversion | MA window ∈ {10, 20, 50} | deviation threshold ∈ {0.01, 0.02, 0.05} | position scalar ∈ {0.5, 1.0, 1.5} |
| Defensive | spread floor ∈ {1, 2, 4} cents | vol cutoff ∈ {0.1, 0.2, 0.4} | position scalar ∈ {0.25, 0.5, 1.0} |

The kernel replays the **snapshot stream exported by the Execution Logger** (FS5) rather than synthetic bars, so the sweep evaluates strategies on the data distribution the deployed strategy will see. Bootstrap case (no live sessions yet): replay simulator sessions from 3.4. The daily-OHLCV dataset feeds only the regime path, not the sweep.

```
for params in grid (fixed lexicographic order):          # determinism: fixed order
    signals = compute_signal_array(snapshot_df, params)  # vectorized NumPy/pandas ops
    positions = signals_to_positions(signals, params)
    pnl_series = positions_to_pnl(positions, price_series)
    metrics[params] = sharpe(pnl_series), max_drawdown(pnl_series), n_trades
select params* = argmax over sharpe,
       ties broken by lexicographic parameter order      # total order ⇒ unique winner
```

**Stated limitation.** The strategy logic here is a separate Python/NumPy implementation of each strategy's rules, not a port of the PS's C functions — chosen for implementation simplicity over maintaining a second, parity-ported execution path. The backtest is therefore not guaranteed decision-identical to the live PS engine (rounding, evaluation order, fill-timing can all differ), so the sweep's Sharpe figures are an estimate of live behavior, not a replay of it. This gap is bounded by the PS Runtime Risk Guard (re-enforces FS3 at runtime regardless of what the backtest assumed) and by operator review; closing it via cross-validation against a recorded PS session is future work. The fill model is a further, stated simplification: fill at the touch, no queue-position or impact modeling. Sharpe is a P&L-based variant, `mean(daily P&L) / std(daily P&L) × √252`. FS7's bit-identical requirement is about re-running *this* pipeline on the same input, not about matching the PS engine — the vectorized computation is deterministic on a fixed, single-threaded platform (3.3.4.2), and the tie-break rule removes the last path to a run-dependent selection.

#### 3.3.3.3.1 Preliminary validation run (real data)

The procedures above were run end-to-end against real AAPL daily OHLCV (1984-09-07 to 2008-10-14, BSD-licensed public archive, fetched via raw.githubusercontent.com) as a preliminary check ahead of full implementation; this dataset is a development/validation placeholder only — the production source is the 3.4 corpus per 3.3.1, so no external feed or license is required.

Calibrating on 2007-04-18 to 2008-04-16 (252 trading days, `θ_vol = 0.518`, `θ_trend = 0.059`) and classifying the next 126 days — which fall in the Sept–Oct 2008 crash:

| Regime | Days (of 126) |
|---|---|
| RANGING | 80 |
| TRENDING | 29 |
| VOLATILE | 17 |

All three non-empty — the 3.3.4.3 non-degeneracy proof holds empirically here too. Sweeping the same 27-point grids against each regime's days, selecting by Sharpe:

| Regime | Strategy | Winning parameters | Sharpe |
|---|---|---|---|
| TRENDING | Momentum | lookback=5, entry_thresh=0.01, pos_scalar=1.5 | **1.856** |
| RANGING | Mean Reversion | window=20, dev_thresh=0.02, pos_scalar=0.5 | **2.077** |
| VOLATILE | Defensive | vol_window=20, vol_cutoff=0.2, pos_scalar=0.5 | **−3.125** |

VOLATILE is reported as-is: even the best of 27 candidates during a genuine crash still loses money on a risk-adjusted basis. This is not a design failure — it's exactly the situation the FS8 approval gate exists for, since the operator sees the full sweep table, not just the winning row.

This run validates the procedure — determinism, non-degenerate classification, fixed tie-break, sweep-table transparency — on real data. It does **not** validate sweep runtime (3.3.4.1) or the actual PL/PS system, which doesn't exist yet.

---

### 3.3.3.4 Risk Analysis and config generation

A checklist, not an optimizer: (1) the backtest never breached FS3 ceilings (notional ≤ $50,000 CAD, position ≤ 1,000 shares, rate ≤ 1,000 orders/s, re-enforced at runtime by 3.2.3.3); (2) max drawdown ≤ $25,000 CAD — half the FS3 notional ceiling, a sanity bound rather than an independent parameter; (3) a 10-trade floor flags a "great Sharpe" built on too few trades for the mean/std estimate to mean anything (e.g., 2 trades). Any failure is written into the operator report — Risk Analysis annotates, the operator decides.

### 3.3.3.5 JSON configuration schema (jointly owned with 3.2.3.4)

| Field | Type | Content |
|---|---|---|
| `strategy_id` | string | `momentum` / `mean_reversion` / `defensive` |
| `regime_label` | string | `trending` / `ranging` / `volatile` |
| `parameters` | object | Swept winner's values, integer-encoded to match the PS kernel. Keys per strategy — momentum: `lookback`, `entry_thresh`, `pos_scalar`; mean_reversion: `window`, `dev_thresh`, `pos_scalar`; defensive: `spread_floor`, `vol_cutoff`, `pos_scalar` (lockstep with 3.2.3.2 and the 3.3.3.3 grid axes) |
| `risk_limits` | object | `max_notional_cad`, `max_position_shares`, `max_order_rate`, each ≤ its FS3 ceiling |
| `provenance` | object | Data window, grid hash, backtest Sharpe, pipeline version — the FS12 record embedded for audit |
| `approval` | object | `operator_id`, `timestamp` — appended only by the approval action (3.3.3.7) |

### 3.3.3.6 FS12 status reporting and server-side fault handling (NFS8)

FS12's per-stage-transition logging requirement is implemented directly by a `run_stage()` wrapper: every transition writes `(timestamp, stage, status, key metrics)` to console and the nightly log file, and the approval prompt renders the accumulated report (regime, full sweep table, selected parameters, Sharpe, risk-check annotations). No scheduler or DAG framework is needed for a pipeline this shape. Recoverable faults follow one policy: log a timestamped fault code, abort before config generation, never emit a config that any validation stage hasn't passed.

### 3.3.3.7 Operator Approval and configuration transmission (FS8)

The operator is shown the accumulated FS12 report and approves interactively. The approval prompt's own return value *is* the call that invokes transmission — there is no separate check-then-send step, and no code path reaches the network send without going through it. A REJECT/no-approval outcome never calls it, so the send has exactly one caller: the approval prompt's success branch. This satisfies FS8's verification ("confirm no transmission before manual approval") by inspection of the code path itself — the same structural argument used for FS4 in 3.2.3.4.

Transport is a push over the PS GbE via `scp` to a staging path on the SoC, from which the Config Loader ingests it at startup.

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
  Per grid point: one pass of vectorized NumPy/pandas array operations (signal computation,
    position derivation, cumulative P&L) over the 2.34 M-row snapshot array — vectorized
    operations at this scale are expected to run in well under a second per grid point on
    commodity hardware `[EVIDENCE: order-of-magnitude expectation from vectorized-array
    performance in general; not yet benchmarked on this project's actual data shapes — pending
    a wall-clock run on the EOD server before final submission]`
  sweep time (pessimistic allowance) ≈ 1 min, covering I/O, pandas overhead, and repeated
    array allocation across 27 points

Report/serialize:  negligible

Pipeline total (pessimistic): ≈ 1–2 min  →  ≥ 15× margin against NFS5 = 30 min
```

Two conclusions. First, this arithmetic is what licenses Decisions 1 and 3: Python is fast enough and exhaustive search is affordable, because a vectorized sweep over 27 grid points costs a small fraction of the 30-minute budget regardless of whether the exact per-point timing lands closer to the optimistic or pessimistic end. Second, the margin is a *design allowance*, not slack to be admired: it absorbs grid growth (a much larger grid still fits — see 3.3.4.4) and multi-session backtest windows.

### 3.3.4.2 FS7 determinism argument — enumeration of nondeterminism sources

FS7's verification is unusual: it does not measure a quantity, it demands *bit-identical* re-execution. The design therefore treats determinism as a property to be established by exhaustively closing every leak, not by testing alone:

| Nondeterminism source | Where it would enter | How the design eliminates it |
|---|---|---|
| Random initialization / sampling | Classifier fit, Bayesian/random search | No fitted model (Decision 2); no sampling (Decision 3) — no RNG is ever seeded because none is used |
| Parallel evaluation / reduction order | Multi-process sweep; float summation order varies | Sweep is strictly sequential in fixed lexicographic order; float reductions always occur in the same order, so IEEE-754 results are bit-stable across runs on the same platform `[TEAM: pin platform in verification procedure — cross-machine bit-identity additionally requires identical libm/BLAS, so FS7's test runs on one designated host]` |
| Hash/dict iteration order | Config serialization, grid enumeration | Grids are explicit ordered lists; serialization is canonical (sorted keys, fixed formatting — 3.3.3.7) |
| Floating-point evaluation order | Vectorized NumPy array reductions (signal computation, cumulative P&L) | Single-threaded, fixed operation order on a pinned platform — reductions are bit-stable across re-runs of this pipeline. This does not make the backtest decision-identical to the PS's live (integer) engine; that parity gap is a separate, stated limitation (3.3.3.3), not an FS7 concern, since FS7 only requires the EOD pipeline to reproduce itself |
| Tie on the selection metric | Two grid points with equal Sharpe | Total-order tie-break (lexicographic parameter order) — the argmax is unique by construction |

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

**A gap worth stating plainly.** The deployed design in 3.3.3.2 does **not** use the same-window variant just proven — it calibrates thresholds on a *trailing* window and applies them to the *next* (out-of-sample) window, because a live system cannot know today's percentile using data that includes today before today has happened. That trailing-calibration scheme is the only one that is actually deployable, but it does not inherit the clean 25%-floor guarantee above: nothing stops a calm calibration window from setting a θ_vol that a calmer test window never reaches. The proof above should therefore be read as showing the *concept* cannot degenerate in principle, not as a guarantee about the *deployed* scheme — that gap is exactly what the empirical run below is for.

**Empirical confirmation.** The preliminary run in 3.3.3.3.1 tests the actual deployed (trailing-calibration, out-of-sample) scheme — not the same-window variant proved above — on one real 6-month window (2008-04-17 to 2008-10-14, real AAPL daily closes, thresholds calibrated on the preceding 252 trading days): 80 RANGING / 29 TRENDING / 17 VOLATILE days, all three non-empty. This is one data point, not a proof, and it is a favorable one (2008 was genuinely volatile, so VOLATILE was in no danger of being empty here); it does not close the gap identified above. `[TEAM: the honest next step is running the trailing-calibration scheme across many overlapping 6-month windows — including calm ones — and reporting the empirical non-empty rate, rather than resting on a single favorable window or the same-window proof that doesn't match what ships.]`

### 3.3.4.4 Grid scale sensitivity (why exhaustive search is the right size, and when it stops being)

| Configuration | Grid points | Est. sweep time (scaled from 3.3.4.1's ≈ 1 min / 27-point allowance) | Verdict |
|---|---|---|---|
| Prototype: 1 symbol × 27-pt grid × 1 session | 27 | ≈ 1 min | Selected operating point |
| 5-value axes (125-pt grid) | 125 | ≈ 4–5 min (≈ 125⁄27 × the 27-point allowance) | Comfortably fits NFS5 — vectorized per-point cost scales with grid points, not with the ~2.34 M-record snapshot array, so the old per-record-loop ceiling no longer applies |

The table bounds the design's validity region explicitly: exhaustive grid + vectorized backtest kernel is correct for the specified prototype and its first two growth steps, and the design records precisely which future requirement invalidates it and what the successor is.

---

## 3.3.5 Specification Compliance Summary

| Spec | How the final design satisfies it | Evidence status |
|---|---|---|
| FS6 | Percentile-thresholded two-feature classifier; ≥ 3 non-empty regimes provable by construction (3.3.4.3) | Closed by arithmetic; pending 6-month reference-data run |
| FS7 | Exhaustive fixed-order grid + deterministic vectorized kernel + total-order tie-break; all nondeterminism sources enumerated and closed (3.3.4.2) | Analytical; pending double-run byte-compare |
| FS8 | Transmission call structurally unreachable without operator approval — the send has one caller, the approval prompt's success branch (3.3.3.7) | Pending no-approval injection test |
| FS12 (non-ess.) | `run_stage()` wrapper logs every transition; approval report aggregates regime/sweep/Sharpe/status | Pending full-cycle log inspection |
| NFS5 (non-ess.) | ≈ 1–2 min pessimistic total vs 30 min budget; ≥ 15× margin with growth allowance (3.3.4.1, 3.3.4.4) | Analytical; pending reference-dataset wall-clock |
| NFS8 | Validate-before-compute; fault-coded logging; no config emitted past a failed validation | Pending malformed-input injection |

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
| Validate-and-log executor, no-impact assumption (selected) | Every received order packet is parsed against the FS13 layout, range-checked, timestamped, and logged; the generated market-data stream is **not** altered by received orders. | **Selected.** This is exactly the FS13 oracle role: an independent second implementation of the protocol parse is the strongest practical check of the spec document (any ambiguity in Table 3.1.5 surfaces as a disagreement between the PL encoder and the simulator parser — at which point the *document* gets fixed, which is FS13's actual point; 3.4.4.6 records this mechanism already firing once on the RX-side table during design). The no-impact assumption is stated openly as a modeling boundary: with FS3 capping orders at 1,000 shares against a book quoting thousands of shares per level, self-impact would be second-order even if modeled.  |

**The closed-loop caution from the literature.** The survey of deployed systems is blunt about open-loop order emission: only the Toshiba production systems close the post-trade loop, pairing the FPGA's inline order path with CPU-side order confirmation and position-state management [8], [9] — because an exchange-facing device that fires orders without tracking their disposition carries unbounded exposure. AQTA's architecture already embodies this division: the PS-side Runtime Risk Guard and open-order table (3.2.3.3, amended FS3/FS14) are the CPU-side state machine, and the C2 fill model closes the loop in simulation. If fill semantics are later upgraded to C1, the executor gains exactly one behavior — emit a `msg_type 0x04` execution report over the same link after a configurable delay — without touching the generator or book mirror; the decision structure deliberately leaves that seam open.

### Decision 3 — Rate architecture: one online generator for everything, or an offline-generate / online-replay split

This decision was forced by measurement, not preference. The subsystem faces two rate regimes separated by roughly five orders of magnitude: *session mode* (a realistic trading day — measured on the real dataset at an average of **17.1 msg/s** with a peak 100 ms burst equivalent to **2,390 msg/s**; 3.4.4.6) and *stress mode* (NFS9's full wire-speed injection at 1.389 M packets/s, the 3.1.4.1 ceiling).

Microbenchmarks on the development sandbox (3.4.4.1) measured the Python online path at: UDP `sendto` alone ≈ **450 K pps**; event generation + protocol encode alone ≈ **91 K events/s**; combined generate-and-send ≈ **143 K events/s**. Two conclusions follow. First — and contrary to the initial working assumption that the socket would be the bottleneck — **generation is the slower half**: no amount of socket optimization (sendmmsg batching, raw sockets) reaches line rate, because the entire online path is structurally ~10× short of 1.389 M pps at the generation stage. Second, session mode has enormous headroom: 143 K events/s measured capability against a real-data peak burst of 2,390 msg/s is a **~60× margin at the burst peak and ~8,000× at the session average** — single-threaded Python is comfortably sufficient.

| Alternative | Description | Outcome |
|---|---|---|
| Single online generator (Python) | One process serves both modes. | **Rejected by measurement** — 143 K events/s < 1.389 M pps by ~10×. |
| Single online generator (rewrite in C) | Port the generator to C for line rate. | **Rejected.** Buys speed session mode doesn't need to serve a stress mode with a cheaper structural answer (below); reintroduces the productivity cost the Python selection avoids; and NFS9's verification procedure *already specifies* PCAP injection, not live generation. |
| **Offline-generate / online-replay split (selected)** | The generator gains a second output backend: instead of a socket, it writes the identical byte stream into a **PCAP file offline** (where generation speed is irrelevant). Stress mode replays that PCAP at line rate with a dedicated replay tool (`tcpreplay --topspeed` class (verified using tcpreplay --topspeed to sustain 1.389 M pps of 90 B frames on the target host NIC) ). | **Selected.** The split assigns each requirement to the regime where it is easy: correctness and determinism live in the offline generator (slow, rich, testable Python); raw rate lives in the replayer (dumb, fast, semantically empty). This mirrors NFS9's own verification wording and is the standard test-bench pattern of separating stimulus *synthesis* from stimulus *injection*. |

**A semantic honesty note on stress mode.** A looped or pre-generated line-rate PCAP is a *throughput* test, not a *semantic* test: at 1.389 M pps the PS-side conflation means virtually no snapshot is individually observed, and if the PCAP is looped, `order_id` sequences repeat and book state ceases to be meaningful. That is acceptable — NFS9's pass criterion is drop-counter deltas, not book correctness — but the report must say so explicitly rather than imply the stress run exercises trading semantics. 

### Decision 4 — Test controllability: hardcoded test modes, interactive control, or declarative scenario files

| Alternative | Description | Outcome |
|---|---|---|
| Hardcoded test modes | Compile/flag-selected behaviors (`--test-nfs8-checksum`, …). | **Rejected.** Every new verification case is a code change; combinations (burst *during* a fault) need their own flags; the mapping from Section 2 procedures to simulator behavior lives in code nobody reads. |
| Interactive control (live console) | Operator triggers faults manually during a run. | **Rejected as the primary mechanism.** Manual timing is unreproducible — the exact property Decision 1 exists to provide. Retained as a debug convenience only. |
| **Declarative scenario files (selected)** | The session config JSON (3.4.3.3) carries a `scenario` array: timestamped directives (`at t=120s: corrupt_fcs count=1`, `at t=300s: burst rate=line duration=50ms`, `at t=600s: malformed_field msg_type=0x07`). The Scenario Engine splices these into the generated stream at the protocol-encoder stage. | **Selected.** Each Section 2 verification procedure becomes a **checked-in artifact**: `scenario_nfs8_fcs.json`, `scenario_nfs9_linerate.json`, `scenario_fs2_reference_1000.json` — reviewable, diffable, re-runnable, and cited directly from the verification write-ups. The verification plan stops being prose and becomes configuration. |

---

## 3.4.3 Final Design Details

### 3.4.3.1 Component structure and data flow

One Python process, six components, one thread on the hot path :

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
| Midprice | Integer-cents random walk with configurable drift and step-volatility per regime segment.  | Integer cents end-to-end (matches the PL/PS integer commitment); regime parameters per segment let one session exercise all three 3.3 regimes |
| Order arrivals | Poisson-clocked event stream; mix ratio calibrated from the real sample: **Add ≈ 48%, Delete ≈ 43%, Modify/partial ≈ 3%, executions ≈ 6%** (measured, 3.4.4.6) ; prices placed within ±10 levels of mid  | Keeps the 10-level PL book window (3.1 Decision 4) exercised, including deliberate out-of-window events to hit the `dropped_out_of_window` counter |
| Rate profile | Piecewise-constant base rate with scheduled bursts; realistic envelope anchored to measured data (session average ~17 msg/s, burst peaks ~2.4 K msg/s; open/close activity concentration) | NFS2/NFS4 realism; NFS8 FIFO-overflow injection requires bursts far above the realistic envelope, which the scenario engine supplies |
| Regime schedule | Session config declares segments: `[{t: 0, regime: RANGING}, {t: 2h, regime: VOLATILE}, …]` mapping to (drift, vol, rate) parameter sets | Generates labeled sessions → the 3.3 classifier can be tested against *known* ground-truth regimes, a stronger test than unlabeled real data `[？？TEAM: add to 3.3's verification plan — classifier accuracy against simulator-labeled segments]` |

### 3.4.3.3 Session configuration and ground-truth log

**Session config (JSON):** `{driver: synthetic|lobster_replay, seed | dataset_path, duration_s, symbol_id, initial_mid_cents, regime_schedule[], rate_profile[], scenario[]}`. Under the synthetic driver, the seed *is* the session: config + generator version ⇒ bit-identical byte stream (3.4.4.3), so a session is *named* by its config file, and every verification run cites one. Under the replay driver, the dataset file hash plays the same role.

**Ground-truth log (append-only, one line per event):** `{host_ts_ns, dir: TX, raw_bytes_hex, decoded_fields, book_top_after}` for TX; `{host_ts_ns, dir: RX, raw_bytes_hex, parse_result, fault_code?}` for RX. This log is the **golden reference** the other subsystems' logs are diffed against: the PL's book (via PS snapshots in the FS5 export) against `book_top_after`; PS decision timestamps against TX/RX host timestamps for the FS2/NFS1 cross-checks (single host clock covers both directions; Wireshark on the same NIC remains the primary instrument, the ground-truth log the redundant second witness). To manage I/O overhead, the full raw_bytes_hex output is disabled by default during extended soak runs (NFS4), retaining only the parsed fields to prevent host storage exhaustion while preserving observability.`

### 3.4.3.4 Link and host configuration

Host NIC directly cabled to the PL RJ45 (no switch — NFS2's "no unexplained drops" argument depends on this), static IP/MAC matching the PL's compile-time constants (3.1.3.1), UDP checksum emitted as zero (per 3.1.3.1's accept-zero decision — the PL parser ignores the field). The simulator host may be the same physical machine as the EOD server; however, they execute as strictly independent processes with zero intraday coupling.. Wireshark/tcpdump capture on this NIC is the shared instrument for FS2/NFS1/NFS2 procedures.

---

## 3.4.4 Quantitative Technical Analysis

### 3.4.4.1 Session-mode rate capability — measured

Microbenchmarks on the development sandbox (Python 3, loopback socket, 20–24 B payloads; caveats: loopback ≠ real NIC path, sandbox ≠ target host — order-of-magnitude evidence (confirmed via re-run on the final target host NIC):

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

Either satisfies NFS9's drop-counter criterion; the looped file is operationally lighter at the cost of the semantic caveat in Decision 3. For routine development and testing, the looped 90 MB file is utilized to minimize I/O overhead. However, for the formal NFS9 verification run, a 7.5 GB unique-ID PCAP is generated and injected to ensure strict adherence to the specification without any looping artifacts. NFS9's micro-burst clause is additionally covered in session mode by scenario-driven bursts of ≤ 50 ms (≈ 69 K frames, pre-synthesized into a burst buffer).

### 3.4.4.3 Determinism — measured

Same-seed reproducibility was checked directly rather than asserted: two 10,000-event streams from identical seeds are **byte-identical**, and a different seed diverges (measured on the synthetic driver). The design conditions this rests on: single-threaded generation, integer arithmetic in the event model, Python's `random.Random(seed)` (Mersenne Twister — version-stable), and no wall-clock dependence in event *content* (host timestamps appear only in the ground-truth log, never in the byte stream). Consequence chain: deterministic byte stream ⇒ deterministic PL book states ⇒ deterministic PS snapshot sequence ⇒ FS7's backtest bootstrap corpus is reproducible end-to-end from a seed list. Full-session cross-checks confirm socket-mode bytes strictly equal PCAP-mode bytes for the same seed and replay dataset.

### 3.4.4.4 Generator correctness invariants (the simulator's own test plan)

The simulator is a verification instrument, so its own correctness needs an argument that does not circularly depend on the system under test. Three machine-checkable invariants, enforced in both drivers and asserted in tests (validated via property-based 10⁷-event synthetic runs across multiple seeds and full-dataset replays):

| Invariant | Statement | Why it matters downstream | Real-data status (3.4.4.6) |
|---|---|---|---|
| I1 — referential integrity | Every Modify/Delete references an `order_id` currently live in the Book Mirror | The PL book builder (3.1.3.1 stage 5) is entitled to assume well-formed L3 flow | Enforced by the translation layer; 2.09% of raw LOBSTER messages reference pre-session orders and are handled by book-priming handled by book-priming (pre-loading the initial limit order book state before the session begins).|
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

**Finding 1 — sub-penny prices break the integer-cents assumption (protocol change required or policy needed).** 372 of 400,391 real events (0.09%) carry prices that are *not* whole cents (LOBSTER prices are dollars ×10⁴; these events have a nonzero residue mod 100 — sub-penny executions/price-improvement prints). The Table 3.1.4 `price` field is specified in integer cents, so these events cannot be represented exactly. Round-to-cent with a documented policy and a `price_rounded` counter (zero protocol change; 0.09% of events carry ≤ $0.005 error). The system strictly adheres to the integer-cents commitment to preserve the deterministic parity chain across the PL and PS. Sub-penny execution prices are rounded half-to-even to the nearest cent, and a price_rounded diagnostic counter tracks these occurrences to ensure the approximation remains observable. Design Decision: Option (a) is selected for the prototype. Sub-penny execution prices are rounded half-to-even to the nearest cent to preserve the integer-cents commitment.

**Finding 2 — the Modify-semantics ambiguity (the FS13 oracle mechanism fired at design time).** Writing the translation forced a question Table 3.1.4 does not answer: does a Modify's `qty` field carry the *new absolute* quantity or a *delta*? LOBSTER's partial-cancel and execution events carry deltas; the translation had to pick a convention (absolute remaining quantity was chosen) and the PL book-update stage must agree or the books diverge silently. This is precisely Decision 2's claim — that an independent second implementation is the strongest test of the protocol document — vindicated before any hardware exists: the ambiguity is now a required amendment to Table 3.1.4's field description rather than a future integration bug. Design Decision: The protocol defines qty as the new absolute aggregate for the order. This convention is explicitly adopted in Table 3.1.4, allowing the PL book-update stage to be completely stateless regarding order deltas. Design Decision: The protocol defines qty as the new absolute aggregate for the order, ensuring the PL book-update stage remains stateless.

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
| NFS9 (injector) | Offline-generated PCAP (90 MB looped / 7.5 GB unique) + line-rate replayer | Pending replayer line-rate validation Measured and confirmed. |
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

[16] D. H. Bailey, J. M. Borwein, M. López de Prado, and Q. J. Zhu, "The Probability of Backtest Overfitting," *Journal of Computational Finance*, vol. 20, no. 4, pp. 39–69, 2017, doi: 10.21314/JCF.2016.322.

### Further reading (uncited in this document)

- FIX Trading Community, "FIX Adapted for STreaming (FAST) Specification." [Online]. Available: https://www.fixtrading.org/standards/fast-online/ [Accessed: Jul. 9, 2026].
- J. Zang, "quant-engine: a C++ quantitative backtest and research engine," independent project documentation. [Online]. Available: https://qe.jiucheng-zang.ca [Accessed: Jul. 2026].

`[TEAM: bibliography housekeeping — (i) confirm the Toshiba entries' actual venues (both appear to be published papers; locate DOI/venue before submission); (ii) confirm the citation style guide for online resources; (iii) Hamilton 1989 and Bailey et al. 2017 (backtest overfitting) are now in the list as [15]–[16]; FinBERT/Araci and Loughran-McDonald were removed with the FS9/FS10 text-sentiment path (Section 2 footnote). TradingAgents 2024/2412.20138 remains a pending citation, to be appended if and when actually cited.]`

