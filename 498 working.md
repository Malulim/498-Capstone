# 1. Introduction

## 1.1 Motivation

Algorithmic trading systems are strongly constrained by end-to-end event latency: market data must be decoded, converted into a usable order book state, evaluated by a strategy, checked for risk, and converted into an order message before the opportunity disappears. A software-only implementation running on a general-purpose Linux host incurs kernel network stack and scheduler overhead before any strategy logic executes; published FPGA-based trading systems quantify this cost directly — a hardware datapath has been shown to achieve roughly a 4x latency reduction over a conventional software-based pipeline [1], and specialized hardware implementations report sub-microsecond response, with one 10 Gigabit Ethernet FPGA trading system achieving approximately 433 nanoseconds from market packet analysis to order trigger [2]. The current AQTA design therefore treats latency elimination as the central design problem rather than as a late-stage optimization.

AQTA addresses this by adopting a hardware-software co-designed architecture: the time-critical, deterministic portions of the pipeline — packet decoding and order-book maintenance — are implemented directly in programmable logic, while strategy evaluation, logging, and overnight reconfiguration remain in software for flexibility. This division follows the same rationale used throughout the FPGA trading literature cited above: push fixed, latency-critical operations into hardware, and keep the parts that need to change often in software.

## 1.2 Project Objective

The primary objective of this project is to design and implement an ultra-low-latency, hardware-accelerated algorithmic trading platform. By partitioning the pipeline across programmable logic and an embedded processor, the system targets deterministic, microsecond-class tick-to-order latency — roughly an order of magnitude faster than a comparable software-only pipeline — while supporting operator-approved overnight strategy reconfiguration.

The essential prototype performs market-data ingestion, protocol decoding, and order-book maintenance in programmable logic (PL) to keep the time-critical path deterministic; passes the resulting order-book state to a configurable strategy running on the ARM processing system (PS), which selects among several pre-loaded strategies and applies a RiskGuard filter; and returns the validated decision to the PL, where it is encoded and transmitted back onto the exchange link.

The secondary objective is an End-of-Day (EOD) optimization pipeline that classifies the next trading day's market regime from historical data, searches a bounded parameter space to select a strategy configuration for that regime, and backtests the selected configuration before presenting it to a human operator for approval; only an approved configuration is loaded into the live system for the next trading session.

**Prototype Scope and Constraints** The prototype scope is intentionally bounded to one simulated exchange and one equity symbol, which keeps the project focused on the core engineering problem of deterministic hardware/software partitioning while avoiding real-money financial risk and the complexity of multi-venue market-data normalization. Rather than implementing an industry-standard compressed protocol such as FAST, the prototype defines a fixed-width binary custom protocol for market data and order messages, narrowing the PL-side protocol decoder to a fixed, minimal field set and keeping decoding latency low, at the cost of interoperability with real exchange feeds. The prototype targets paper trading and simulation: strategy decisions drive a simulated exchange, not a live brokerage account.

# 2. System Specifications

## 2.1 Functional Specifications

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

## 2.2 Non-Functional Specifications

| ID | Specification | Description | Verification Method | Essential |
| --- | --- | --- | --- | --- |
| **NFS1** | End-to-end latency | Total latency from MAC RX to MAC TX ≤ 50 μs typical. | Logic-analyzer measurement on a reference loopback packet. | **Y** |
| **NFS2** | Link reliability | Zero unexplained frame drops over a 10-minute continuous test window. | Wireshark capture, confirm frame count. | **Y** |
| **NFS3** | Hardware cost | Physical components (excl. SoC board, host PC, monitors) ≤ $1,000 CAD total. | Sum itemized purchase receipts. | **Y** |
| **NFS4** | Session stability | Runs a full 6.5-hour simulated session without crash, hang, or unrecovered error. | Full-session run, inspect logs for fatal errors. | **Y** |
| **NFS5** | EOD pipeline runtime | Full EOD pipeline (ingestion → classification → optimization → approval prompt) completes within 30 minutes. | Timed run on 1 year of reference OHLCV data. | **N** |
| **NFS6** | FPGA resource utilization | < 75% LUTs and < 85% Block RAMs on XC7Z020, timing closure at 125 MHz. | Vivado utilization/timing reports, WNS > 0 ns. | **Y** |

*(NFS8 and NFS9 — fault-recovery and line-rate ingest-throughput acceptance specs — were dropped from scope: their verification procedures (scripted fault injection, line-rate PCAP stress) require a test-injection apparatus whose build-and-verify cost is disproportionate to the project's core objective, and the exchange simulator that would have supplied it is deliberately a replay-based instrument (3.4.2 Decision 1). The underlying engineering survives as design features without acceptance criteria: the PL fault-handling path and line-rate throughput analysis (3.1.3.1, 3.1.2 Decision 2), PS-side config validation (3.2.3.4), and EOD input validation (3.3.3.6). IDs are left unrenumbered, as with FS9/FS10.)*


# 3. Detailed Design

## 3.1 PL (FPGA) Market Data Path Subsystem

All numeric analysis in 3.1.4 is derivable on paper today (line-rate arithmetic, cycle budgets, datasheet resource math) — no code required.

---

### 3.1.1 Overview and Specification Mapping

The PL subsystem implements the entire wire-to-snapshot market data path and the order egress path in programmable logic on the XC7Z020[17]. On the receive side, it terminates the point-to-point Gigabit Ethernet link from the exchange simulator, validates and parses each custom UDP market data packet at fixed byte offsets, maintains a 10-level bid / 10-level ask limit order book (an L3-to-L1/L2 aggregation), and publishes the resulting top-of-book snapshot to the PS through an AXI-Lite register bank on M_AXI_GP0 (snapshot fields plus an incrementing `seq` register, committed atomically in one clock edge). On the transmit side, it receives risk-validated order fields written by the PS into the same register bank, begins encoding on the doorbell-register write strobe, encodes them into the fixed-length binary order format defined by FS13, and transmits them through the same PL GbE interface.

The subsystem exists because the software network path cannot meet the project's latency specifications: a conventional Linux socket path incurs interrupt handling, kernel protocol stack traversal, and kernel-to-user copies that together cost tens to hundreds of microseconds per packet, which is incompatible with the ≤ 1.5 μs decode budget of FS1. By hardware/software partitioning, implementing the critical data path in the PL is structurally superior to the PS because programmable logic processes incoming packets with deterministic, microsecond-class, clock-cycle-exact latency, achieving nearly an order of magnitude faster tick-to-order response than a comparable software-only pipeline running on the PS. Placing the parse and book-build stages in the PL removes the operating system from the market-data critical path entirely.

This subsystem is directly responsible for the following specifications:

| Spec | Role of PL subsystem |
| :--- | :--- |
| **FS1** | Sole owner: packet arrival → decoded top-of-book snapshot available to PS in ≤ 1.5 μs. |
| **FS13** | Sole owner of the egress half: order packets must conform to the fixed-length binary format. |
| **NFS1** | Owns the two PL segments (RX decode, TX encode) of the ≤ 50 μs end-to-end budget (300 μs ceiling applies to the superseded interrupt design). |
| **NFS2** | Owns link integrity: zero unexplained frame drops over a 10-minute window. |
| **NFS6** | Owns the resource envelope: < 75% LUT, < 85% BRAM at 125 MHz with WNS > 0. |
| **Fault handling (partial)** | Owns the hardware fault path: checksum-fail discard and FIFO-overflow handling with fault counters. |
| **NFS4 (partial)** | Hardware fault paths (FCS discard, FIFO-overflow handling, drop counters) keep line-rate faults from escalating into a session-ending hang; primary ownership of the 6.5-hour stability requirement remains with the PS (3.2.1). |

Figure 3.1 shows the PL block structure and the shared AXI-Lite register bank at the PS boundary, using the stage names adopted throughout this section (Protocol Decode / Build Order Book / Protocol Encode).

---

### 3.1.2 Engineering Design Process

Four significant design decisions shaped this subsystem. Quantitative justifications regarding line-rate throughput, cycle budgets, and resource envelopes are integrated directly into each decision to confirm design feasibility.

#### Decision 1 — MAC layer implementation: vendor IP vs. minimal custom MAC

| Criterion (weight) | Xilinx TEMAC IP (selected) | Minimal custom MAC |
| :--- | :--- | :--- |
| Development & verification effort (40%) | 5 (Low — pre-verified vendor IP, wizard-generated) | 2 (High — custom preamble/FCS designed from scratch) |
| Resource cost (20%) | 2 (Medium-high — multi-thousand LUT baseline footprint) | 5 (Low — minimal RX/TX framing and CRC only) |
| Latency determinism (20%) | 3 (Medium — bounded, datasheet-specified pipeline delay) | 5 (High — zero unused feature logic overhead) |
| Protocol generality (20%) | 5 (High — robust standard interface ecosystem) | 2 (Low — limited point-to-point link only) |
| **Weighted result (1.0–5.0 scale)** | **4.0 — Selected** | 3.2 |

*   **Rationale:** Development and verification speed represent the binding constraints because the pipeline cycle budget closes comfortably. Standard engineering literature[6] supports instantiating off-the-shelf cores over custom layout verification.
*   **Integrated MAC Resource Envelope Analysis (NFS6):** Per Xilinx product guide specifications (PG051 [16]), the Tri-Mode Ethernet MAC core utilizes ≈1,500 registers and ≈3,000 LUTs along with 3 Block RAM blocks for internal streaming FIFOs. While a custom MAC would minimize this footprint, the XC7Z020's spacious resource profile allows us to absorb this overhead safely.
*   **Integrated MAC Latency Impact:** The core introduces a deterministic internal pipeline delay of ≈20 clock cycles during RGMII DDR capture, which scales to roughly 160 ns at 125 MHz. This delay is thoroughly accounted for in the available safety margins calculated under Decision 2.

#### Decision 2 — Parse architecture: store-and-forward vs. cut-through streaming parse

*   **Alternatives:** Store-and-forward buffers the complete frame before decoding; cut-through streams and slices fields in real time at fixed byte offsets.
*   **Integrated Line-Rate Throughput Analysis :** The maximum theoretical packet rate of a 1 Gbps link for our 24-byte payload configuration is derived below:
    $$\text{Frame Over Wire} = 8\ \text{Preamble} + 14\ \text{Ethernet} + 20\ \text{IPv4} + 8\ \text{UDP} + 24\ \text{Payload} + 4\ \text{FCS} + 12\ \text{IFG} = 90\ \text{bytes} = 720\ \text{bits}$$
    $$\text{Line Rate Saturation Limit} = 10^9\ \text{bits/sec} \div 720\ \text{bits} = 1,388,888\ \text{packets/second}$$
    Serializing frame buffering under a store-and-forward design adds a 560 ns transmission serialization penalty (70 bytes post-preamble streaming at 1 octet/cycle), consuming over a third of the remaining budget.
*   **Integrated Latency Path Decomposition (FS1):** Cut-through parsing is selected because fixed offsets permit deterministic bit slicing concurrently with line arrival, removing Look-Ahead serialization. The absolute step-by-step custom hardware logic latency totals exactly 77 clock cycles (616 ns): (1) Frame reception streaming: 560 ns (70 bytes), (2) FCS validation latch: 16 ns, (3) Tournament compare network reduction: 32 ns, and (4) Register bank synchronization: 8 ns. Accounting for the vendor-spec MAC core ingestion delay, sensitivity analysis establishes the following final path budgets against the 1.5 μs functional specification ceiling:
    *   *Optimistic Ingest Assumption (100 ns):* $616\ \text{ns} + 100\ \text{ns} = 716\ \text{ns}$ (**52% Safety Margin**).
    *   *Pessimistic Ingest Assumption (400 ns):* $616\ \text{ns} + 400\ \text{ns} = 1,016\ \text{ns}$ (**32% Safety Margin**).
*   **Commit Policy:** To ensure data integrity, fields are held in speculative staging registers and committed to the order book only upon an Ethernet Frame Check Sequence (FCS) pass signal. On FCS fail, the frame is safely discarded, and a `parse_error` counter increments, fulfilling the fault-tolerant criteria of the fault-handling path.

#### Decision 3 — Order book storage: BRAM-indexed structure vs. fixed register array

*   **Alternatives:** Hashing price levels into distributed Block RAM (BRAM), or instantiating a dedicated flip-flop register array.
*   **Integrated Resource Footprint Projections (NFS6):** BRAM structures incur significant memory block fragmentation and address-lookup pipeline stalls at small depths. Because our prototype scope is bounded to a single symbol with a 10-level bid and 10-level ask depth, a fixed flip-flop register array is selected. This requires ≈1,500 registers (20 levels × 64 bits + snapshot 128 bits + counters) and ≈1,000 LUTs (to implement 20 parallel comparators and a 9-compare tournament reduction tree). This allows parallel combinational best-price extraction within a single 8 ns clock edge (125 MHz), ensuring clean timing closure (WNS > 0 ns) while utilizing 0 Block RAM blocks. Updates addressing a price level outside the 10-level working window are discarded and tracked via internal diagnostic counters (`dropped_out_of_window`).

---

### 📝 Final Resource Envelope Summary

To provide a high-level view of our overall hardware constraints across all combined decisions, Table 3.1.6 summarizes the estimated gate-level allocations on the XC7Z020 fabric.

Table 3.1.6: Gate-Level Hardware Resource Footprint Projections (XC7Z020 / NFS6)
| Component | Flip-Flop (FF) Estimate | Look-Up Table (LUT) Estimate | Block RAM (BRAM) |
| :--- | :--- | :--- | :--- |
| **Order Book Register Logic** | ≈1,500 registers | ≈1,000 LUTs (20 comparators) | 0 blocks |
| **Xilinx TEMAC Core** | ≈1,500 registers | ≈3,000 LUTs (datasheet base) | 3 blocks (internal buffers) |
| **Slicing & Header Decoders** | ≈500 registers | ≈1,000 LUTs (combinational masks) | 0 blocks |
| **AXI-Lite GP0 Slave Bus Interface** | ≈500 registers | ≈800 LUTs (address decoding) | 0 blocks |
| **Projected Footprint Totals** | **≈4,000 FFs (< 4%)** | **≈5,800 LUTs (≈11% of device)** | **3 Blocks (< 3%)** |

> **Strategic Disclaimer regarding Page Constraints:** Detailed analytical modeling regarding long-term history ring buffer allocation bounds, EOD walks, and server hyper-parameter search spaces are omitted in this subsection due to report page constraints; full quantitative technical analysis for those software-side blocks is handled in Section 3.9.

---

### 3.1.3 Final Design Details

#### 3.1.3.1 Receive pipeline

The receive path is structured as a five-stage streaming pipeline running at a clock frequency of 125 MHz:

1. **MAC RX (Xilinx TEMAC):** Handles RGMII DDR capture from the external PHY, preamble alignment, and FCS tracking, streaming data out over its AXI4-Stream RX interface. Non-matching destination MAC addresses are filtered out immediately.
2. **IP/UDP Header Parse:** Fixed-offset validation of EtherType (0x0800), IP protocol (17), destination IP, and destination UDP port against compile-time constants. The UDP checksum is bypassed because payload integrity on this single-segment point-to-point link is covered by the Ethernet FCS.
3. **Protocol Decode:** Executes real-time bit-slicing of the incoming custom payload directly into staging registers as bytes arrive.
4. **Commit gate:** On TEMAC's `tuser` frame-good signal at `tlast`, the staged event commits; on frame-bad, discard + `parse_error` increment (fault-handling path).
5. **Order book update:** Aggregates the committed L3 event (keyed by `order_id`) into the affected side/level. Extracting the new top-of-book occurs via combinational reduction, driving an atomic commit to the register bank and a single-cycle increment of the `seq` register.

#### 3.1.3.2 Packet formats (FS13 interface contract)

All market data and order messages within the intraday critical path are bound to a strict fixed-width protocol specification. To minimize hardware design complexity and latency within the custom PL arithmetic blocks, the system enforces a strict integer cent assumption (`price_cents`) rather than utilizing sub-cent or floating-point precision units. Integer field encoding avoids multi-cycle floating-point conversion logic, keeping parsing and book aggregation fully deterministic. While standard equity price values map natively to integer cents, any incoming sub-cent prices from external feed simulations are systematically rounded half-to-even at the system ingress boundary and logged using localized diagnostic counters (`price_rounded`) to guarantee full data observability without degrading hardware cycle-time.

Table 3.1.3 serves as the protocol interface contract for incoming market updates, and Table 3.1.4 establishes the exact byte-level layout required for outbound order packet verification under FS13.

Table 3.1.3: Custom Market Data Payload Layout (RX Ingress Contract)
| Field | Bit offset | Width (bits) | Protocol Encoding & Meaning |
| :--- | :--- | :--- | :--- |
| **msg_type** | 0 | 8 | 0x01 = Add, 0x02 = Modify, 0x03 = Delete |
| **symbol** | 8 | 16 | Numeric symbol identifier for single equity (constant = 1) |
| **price** | 24 | 32 | Unsigned fixed-point integer representing cents |
| **qty** | 56 | 32 | Unsigned share quantity; absolute volume for Modify commands |
| **side** | 88 | 8 | 0x01 = Bid, 0x02 = Ask |
| **order_id** | 96 | 32 | Unique transaction identifier within the simulator session |
| **seq_num** | 128 | 32 | Monotonic sequence tracker for drop accounting (NFS2) |
| **pad** | 160 | 32 | Reserved padding fields (hardcoded to 0x00) |

Table 3.1.4: Custom Order Packet Payload Layout (TX Egress Spec / FS13 Contract)
| Field | Bit offset | Width (bits) | Protocol Encoding & Meaning |
| :--- | :--- | :--- | :--- |
| **order_id** | 0 | 32 | Client-assigned order identifier, echoed from the originating decision (FS14 tracking key) |
| **symbol** | 32 | 16 | Numeric equity asset identifier (constant = 1, matches Table 3.1.3) |
| **side** | 48 | 8 | 0x01 = Buy, 0x02 = Sell |
| **qty** | 56 | 32 | RiskGuard-validated outbound order size |
| **price** | 88 | 32 | Executable order price mapped to integer cents |
| **pad** | 120 | 8 | Formatting padding field (hardcoded to 0x00) |

#### 3.1.3.3 Order book register layout

Table 3.1.5: Order Book Register Sizing & Diagnostic Layout
| Register group | Entries | Fields per entry | Structural Purpose |
| :--- | :--- | :--- | :--- |
| **Bid book** | 10 | price_cents (32b), aggregate_qty (32b) | Tracks highest active bid levels |
| **Ask book** | 10 | price_cents (32b), aggregate_qty (32b) | Tracks lowest active ask levels |
| **Top-of-book snapshot** | 1 | best_bid_price, best_bid_qty, best_ask_price, best_ask_qty | Committed atomically to AXI-Lite register bank on every tick |
| **Diagnostic counters** | 4+ | parse_error, fcs_fail, dropped_out_of_window, tx_backpressure | NFS2 / fault-path observability |

#### 3.1.3.4 PS interface and transmission pipeline

The PS boundary is structured as a single AXI-Lite slave register bank on M_AXI_GP0. Snapshot publication is executed via a one-clock-edge atomic commit of all snapshot registers plus the `seq` increment, removing the possibility of hardware-side tearing. The multi-read consistency problem is handled on the PS side via a seqlock design pattern. FS1's measurable endpoint is the `seq`-increment write enable, observable with an ILA.

The TX egress path operates as a four-stage pipeline:
1. **Order-field write:** The PS writes the risk-approved order fields into the AXI-Lite register bank, payload first.
2. **Doorbell strobe:** The PS writes to the doorbell register last; the strobe itself launches the encode stage on the following cycle. A `tx_ready` flag provides flow control.
3. **Protocol Encode:** Packs the sampled data fields into the Table 3.1.4 fixed-offset format.
4. **MAC TX (Xilinx TEMAC):** The vendor core frames the payload and transmits it over RGMII to the external PHY.

---

### 3.1.4 Specification Compliance Summary

Table 3.1.7: Subsystem Traceability and Core Specification Compliance
| Spec | How the final design satisfies it | Verification Metric | Status |
| :--- | :--- | :--- | :--- |
| **FS1** | Cut-through stream parsing completes custom book updates in 77 cycles, leaving a 32% margin under worst-case pipeline conditions. | Logic-analyzer trace from MAC valid to register latch. | **Y** |
| **FS13** | Egress formatting matching Table 3.1.4 byte-offsets is hardcoded into sequential register arrays. | Wireshark inspection of simulated order frame. | **Y** |
| **NFS1** | Hardware RX (0.61 μs) and TX (0.65 μs) path budgets consume less than 3% of the absolute system latency budget. | Synchronized hardware timestamp capture loop. | **Y** |
| **NFS6** | Gate-level resource footprints map to approximately 11% of available fabric resources on the target device. | Vivado post-implementation utilization summary report. | **Y** |
## 3.2 PS (ARM OS Layer) Strategy & Risk Subsystem

### 3.2.1 Overview and Specification Mapping

The PS subsystem is the software half of the intraday trading loop on the selected XC7Z020 Zynq-7000 device, whose family provides a dual-core ARM Cortex-A9 processing system [19]. Core 1 is isolated from the Linux scheduler and owns the hot path: busy-poll the PL snapshot registers, evaluate the active strategy, apply the Runtime Risk Guard, and write approved order fields back through the register bank and doorbell. Core 0 owns latency-tolerant work: configuration loading, log draining/export, Debug-UART reporting, and session supervision.

The division of labour with the PL follows one rule established in 3.1: the PL owns wire-speed determinism; the PS owns session-to-session changeability. Strategy formulas, parameters, and risk limits are replaced by the EOD pipeline (Section 3.3), so iterating on them must not require FPGA re-synthesis.

| Spec | Role of PS subsystem |
|---|---|
| **FS2** | Software segment: snapshot update -> BUY/SELL/HOLD -> PL order handoff within the 30 μs budget. |
| **FS3** | Risk rejection for notional, position, order-rate, and in-flight limits, with logged reason codes. |
| **FS14** | In-flight order state for up to 100 concurrent orders, including terminal outcomes. |
| **FS4** | Validated strategy configuration before any market data is processed. |
| **FS5** | Bounded-memory persistence of decisions/outcomes/snapshots over >10 M ticks, plus export. |
| **FS11 (non-ess.)** | Real-time book/decision report over Debug UART. |
| **NFS1** | Dominant software contribution to the 50 μs typical end-to-end budget. |
| **NFS4** | Primary 6.5-hour session-stability owner. |

Figure 3.2 shows the PS runtime structure. *(Figure placeholder — must reuse the block-diagram labels above; the register bank appears once, on the PL/PS boundary, with the Feature Parameters and Trade Decision arrows passing through it.)*

---

### 3.2.2 Engineering Design Process

#### Decision 1 — Hardware/software boundary: strategy in PL vs. strategy in PS

| Alternative | Description | Outcome |
|---|---|---|
| Strategy in PL | Implement decision rules as fabric logic; sub-microsecond tick-to-order. | **Rejected.** Strategy formulas, thresholds, and the active strategy identity change nightly via the EOD JSON config (FS4/FS8). A PL implementation would either require re-synthesis per change (hours per iteration, incompatible with the EOD cycle) or a parameterized rule engine in fabric whose design and verification cost exceeds the remaining PL schedule. FPGA trading literature supports moving fixed protocol-processing primitives into hardware [1], [4]; this prototype keeps the changeable alpha logic in software. |
| Strategy in PS (selected) | Evaluate rules on the Cortex-A9 against the observed snapshot. | **Selected.** A software strategy is reconfigured by rewriting a struct, tested with host-compiled unit tests, and debugged with standard tooling. Decision 3's latency budget shows the software path still closes with about 5.5x margin. |

This decision explains why FS2's 30 μs budget is roughly an order of magnitude looser than FS1's 1.5 μs budget: the specification deliberately prices in the software boundary, and Decisions 2-3 prove that the priced-in boundary is still feasible.

#### Decision 2 — Operating environment: bare-metal vs. Linux vs. Linux with core isolation

| Criterion (weight) | Bare-metal (both cores) | Linux (selected) |
|---|---|---|
| Hot-path determinism (30%) | Best | Poor as-is — scheduler jitter on the hot path |
| TCP/IP, filesystem, UART tooling for FS4/FS5/FS11 (30%) | None — must port a network stack for the PS GbE paths | Full, native |
| Team development & debug cost (25%) | High | Low — standard toolchain, matches team's embedded-Linux experience |
| NFS4 6.5-hour robustness path (15%) | All failure handling hand-rolled | Mature, observable (logs, watchdogs) |
| **Weighted result (1–5 scale)** | 2.6 | **4.1 — Selected** |

Linux is selected only with the explicit constraint that the hot path does not run as ordinary scheduled userspace. Core 1 is removed from normal scheduling with `isolcpus`, which Decision 3 relies on; core 0 keeps Linux's filesystem, network, logging, and UART advantages for FS4/FS5/FS11/NFS4. The target image is PetaLinux because the implementation is board-specific; the design depends on Linux services and CPU isolation, not on PREEMPT_RT, because the isolated core is designed not to re-enter the scheduler during the hot path.

#### Decision 3 — Hot-path interface and event delivery: interrupt + DMA ring vs. busy-poll register bank

FS2 caps the software path at 30 μs. The selected design must therefore avoid any wakeup path whose latency is comparable to the whole budget.

| Alternative | Implementation cost | Outcome |
|---|---|---|
| Interrupt + DMA ring | DMA IP + driver + coherency | Rejected — interrupt wakeup alone risks consuming most of the budget |
| **Busy-poll + register bank + doorbell (selected)** | Wizard-generated AXI-Lite slave; zero driver, zero coherency | **Selected** |

Linux IRQ-to-userspace wakeup is treated as 10-40 μs: even the optimistic end consumes one third of FS2 before strategy logic begins. This is consistent with the broader low-latency pattern: Leber et al. identify context switching as a central software-latency cost [1], and Morris et al. use polling for host-side market data [4]. Core 1 therefore busy-polls `SEQ` over M_AXI_GP0 instead of sleeping.

DMA also loses its main benefit once a core is already dedicated to waiting: the snapshot is only 16-24 B, so bulk transfer hardware adds driver/coherency work without raising the strategy's processing ceiling. The PL exposes a register snapshot plus `SEQ`; egress is symmetric, with payload fields written first and `DOORBELL` last.

30 μs is about 23,000 cycles at the board's 766 MHz Cortex-A9 frequency [17]. Allowing about 1 μs for the PL egress tail leaves about 29 μs for software:

| Stage | Estimate |
|---|---|
| Detect new `SEQ` | ~0.15-0.3 μs |
| Snapshot read + seqlock re-read | ~1-1.8 μs |
| Strategy evaluation | <= ~1 μs |
| Runtime Risk Guard | << 0.1 μs |
| Logger record write | <= ~0.5 μs |
| Order-field writes + doorbell | ~0.5-1 μs |
| **Software total** | **<= ~5 μs, about 5.5x margin against the ~29 μs share** |

The same arithmetic explains why conflation is acceptable for the current prototype. Snapshot reads observe at roughly 500-670 K snapshots/s and full decision iterations run at >=200 K decisions/s, while the wire ceiling from 3.1 Decision 2 is 1.389 M ticks/s. The CPU, not the register interface, is the bottleneck; a DMA ring would mostly queue stale ticks. The selected register path therefore keeps only the latest snapshot.

| Condition | Register path conclusion |
|---|---|
| Current spec: 1 symbol, top-of-book, conflation acceptable | Adequate; ~1.5-2 μs/read with >=5x FS2 margin. |
| Payload > ~100 B/event, e.g., 10-level depth | Migrate to a GP-mapped dual-port BRAM window. |
| Per-tick consumption required, no conflation | DMA ring plus faster software consumer required; out of prototype scope. |

TX contention is non-binding: FS3 caps orders at 1,000/s, while a packet transmit is about 1 μs, giving roughly 1000x spacing margin. `TX_READY` is retained as a correctness invariant rather than a performance mechanism.

---

### 3.2.3 Final Design Details

The final design follows one tick through the software path: the register bank delivers the snapshot, the Strategy Engine decides, the Runtime Risk Guard filters and tracks orders, the Config Loader supplies all session parameters, and the Execution Logger records the result.

#### 3.2.3.1 The PL/PS register bank and access protocol (interface contract)

The entire intraday PL/PS boundary is one AXI-Lite slave in the PL, mapped through a 32-bit PS-to-PL AXI master port (`M_AXI_GP0` in the Vivado design) on the Zynq interconnect [19]. This table is the interface contract, jointly owned with 3.1:

| Offset | Register | Dir (PS view) | Semantics |
|---|---|---|---|
| 0x00 | `SEQ` | R | Atomic snapshot sequence; core 1 polls this |
| 0x04-0x10 | `BEST_BID_PRICE`, `BEST_BID_QTY`, `BEST_ASK_PRICE`, `BEST_ASK_QTY` | R | Top-of-book Feature Parameters |
| 0x14–0x18 | `TIMESTAMP_LO/HI` | R | PL hardware timestamp of the committing packet |
| 0x20–0x2C | `DIAG_PARSE_ERR`, `DIAG_FCS_FAIL`, `DIAG_DROP_OOW`, `DIAG_TX_BACKPRESSURE` | R | Diagnostic counters (NFS2), read periodically by core 0 |
| 0x40–0x4C | `ORD_SYMBOL_SIDE`, `ORD_QTY`, `ORD_PRICE`, `ORD_ID` | W | FS13 order fields; `symbol` and `side` packed into `ORD_SYMBOL_SIDE` |
| 0x50 | `DOORBELL` | W | Write-1 launches Order Emitter; payload first, doorbell last |
| 0x54 | `TX_READY` | R | Egress flow-control invariant |

PL commits are single-clock-edge atomic. PS-side multi-read consistency is protected by a seqlock: read `SEQ`, read fields, re-read `SEQ`, and retry if the value changed. Egress needs no lock because the PL samples order fields only on the doorbell strobe.

#### 3.2.3.2 Strategy Engine (Plug-In Execution)

The engine is a table dispatch: the active strategy ID (from the FS4 config) indexes a function table; each strategy is a pure function of (snapshot, rolling state, parameters) → {BUY, SELL, HOLD} + order fields. Rolling state is fixed-size (e.g., a lookback ring of midprices), so per-tick cost is O(1) and independent of session length.

| Regime | Strategy | Core rule |
|---|---|---|
| Trending | Momentum | BUY/SELL from configured midprice lookback delta. |
| Ranging | Mean Reversion | Trade toward the configured moving-average deviation band. |
| Volatile | Defensive | Suppress entries, allow only position-reducing orders toward flat. |

`mid` is held in half-cent units (`best_bid + best_ask`) so arithmetic remains integer and bit-reproducible on the isolated core. Every window, threshold, and position scalar loads from the FS4 JSON config using the same parameter names swept in 3.3.3.3, so tuning never requires recompilation. The design contribution is deterministic, reconfigurable evaluation machinery; alpha selection belongs to the EOD sweep.

#### 3.2.3.3 Runtime Risk Guard (FS3)

The guard executes unconditionally after every non-HOLD decision in the same thread as the strategy, so no order path can bypass it. Keeping the guard in PS software also keeps FS3 limits EOD-configurable; a PL guard would need its own writable-register interface. The software cost is bounded at about 23-29 cycles: multiply/compare for notional, add/compare for position, fixed-point token-bucket update for rate, and one occupancy compare for in-flight count. At 766 MHz this is about 0.03-0.04 μs, under 0.1% of the FS2 budget, leaving no latency case for hardware risk checks.

| Check | Rule | Mechanism |
|---|---|---|
| Notional | qty × price ≤ $50,000 CAD limit (configurable) | 32×32→64-bit multiply, one compare |
| Position | \|position ± qty\| ≤ 1,000 shares | Signed accumulate against local position state, range-checked against ±1,000 (two compares) |
| Rate | ≤ 1,000 orders/s | Token bucket with fixed-point refill; no divide on the hot path |
| In-flight | in-flight count ≤ 100 | Compare against open-order table occupancy |

Core 1 maintains a fixed, pre-allocated open-order table of 100 entries `{order_id, side, qty, price, submit_timestamp, state}` for the traded symbol — sized exactly to FS3(d)/FS14's in-flight ceiling, since the Risk Guard's in-flight check rejects before insertion and the table never needs to hold more than that.

FS14/FS3(d) require "in-flight" to be testable, so the design fixes terminal timing with a PS-only modeled fill delay **T**. On submission, an order enters the table as in-flight; after **T**, position and the outcome log update, producing the FS5 execution-outcome record. At 1,000 orders/s, **T = 0.1 s** drives the in-flight count to the 100-order ceiling for verification. Rejections write reason-coded records and never reach the doorbell. A configured rejection pattern, `>= 3` REJECTs within 10 s by default, latches HOLD Mode until operator clearance; an EOD "REJECT / No Approval" outcome uses the same latch. HOLD needs no PL cooperation because it is simply the absence of a doorbell write.

#### 3.2.3.4 Config Loader (FS4)

At startup, before core 1 begins polling, the loader validates the JSON configuration's schema, ranges, strategy parameters, and risk limits, then populates the strategy table and Risk Guard. Any validation failure is logged and the polling loop is refused to start: the system never trades on defaults. Market data processing is structurally unreachable until a config commits, which is FS4's verification argument and the PS receiving-side half of the FS8 chain of custody.

#### 3.2.3.5 Execution Logger and Console (FS5, FS11)

The logger is pure software: core 1 writes fixed 128 B records into a pre-allocated 256 MB cached-DDR ring, with no hot-path allocation and therefore no hot-path OOM. Each record is one of: decision, execution outcome, sampled snapshot, Risk Guard reject, or fault. The fixed schema groups type/decision metadata, strategy/reason codes, PL and CPU timestamps, top-of-book fields, emitted-order fields, position/in-flight/PnL state, and reserved growth space.

Full per-tick logging fails by arithmetic: `1.389 M/s × 128 B ≈ 178 MB/s`, and `10 M ticks × 128 B = 1.28 GB`, exceeding the practical memory budget before OS/code are considered. The selected policy instead logs all decision/outcome/reject/fault records, rate-capped by FS3 at 1,000/s, plus snapshots sampled at 100 Hz and on order events. The 100 Hz snapshot rate is a prototype observability policy: it gives 10 ms temporal resolution for session replay/debugging while contributing only 12.8 KB/s, small relative to the 128 KB/s decision-log ceiling. This is about 128 KB/s + 12.8 KB/s = **141 KB/s**, so the 256 MB ring holds about 30 minutes at the worst-case decision rate while core 0 drains continuously to eMMC. Core 0 also performs end-of-session export over PS GbE, periodic `DIAG_*` sampling, and the FS11 1 Hz Debug-UART console feed without charging core 1.

---

## 3.2.4 Specification Compliance Summary

| Spec | How the final design satisfies it | Evidence status |
|---|---|---|
| FS2 | Busy-poll isolated core + register reads; Decision 3 budgets software at <= ~5 μs vs. ~29 μs share | Analytical; GP0 read latency pending PMU/ILA confirmation, then end-to-end Wireshark check |
| FS3 | In-thread Risk Guard; four checks; 23-29 cycle bound; reason-coded reject log | Pending four-violation injection |
| FS4 | Polling loop unreachable until validated config commits | Pending config-swap restart |
| FS5 | Static 128 B records, 256 MB ring, ~141 KB/s selected logging policy | Analytical; pending 10 M-tick stress/export |
| FS14 | 100-entry open-order table, reject-at-limit guard, modeled terminal transitions | Pending limit-saturation injection |
| FS11 | Core-0 UART renderer reads the shared ring off the hot path | Pending live-session check |
| NFS1 | FS2 software path is the dominant PS contribution; Decision 3 shows margin | Analytical |
| NFS4 | Linux services on core 0, isolated hot path on core 1, no hot-path allocation, HOLD latch as safe state | Pending 6.5 h soak |

# 3.3 EOD Server Pipeline Subsystem

> **Scope note:** an earlier draft of this subsystem also carried a non-essential text/LLM-sentiment path (FS9/FS10), which has been dropped from scope (rationale in the Section 2 footnote). Stage names are *Parameter Engineering, Regime Detection, Strategy Reoptimize, Backtest & Parameter Sweep, Risk Analysis, Generate JSON Config, Operator Approval*.
> All numeric analysis in this section is derivable on paper today (dataset-size arithmetic, iteration-count budgets, complexity bounds, inequality proofs) — no code required. Quantitative analysis appears inline where each decision or design element needs it, not as a separate section.

---

## 3.3.1 Overview and Specification Mapping

The EOD (End-of-Day) Server Pipeline is the adaptation layer of AQTA — the component that makes the system *Adaptive* rather than a fixed-strategy appliance. It runs on a host server, off the intraday critical path, and closes the loop between one trading session and the next: it ingests the session history exported by the PS together with historical daily OHLCV data, classifies the next trading day's market regime (FS6), re-optimizes the parameters of the strategy assigned to that regime by exhaustively backtesting a bounded parameter grid (FS7). The result is assembled into a candidate JSON configuration and presented to a human operator, whose explicit approval is the only path by which it can reach the live system (FS8, transmitted to the PS Config Loader of 3.2.3.4); a REJECT or no-approval outcome instead uses the PS HOLD latch described in 3.2.3.3 until an operator clears it.

The subsystem completes a three-tier latency/flexibility hierarchy established in 3.1 and 3.2: the PL is deterministic at nanosecond scale and fixed for the session; the PS decides in microseconds but is reconfigurable nightly; the EOD server may take minutes but is rewritable — the analytics, the parameter values, and the judgment about what tomorrow's market looks like. Each tier trades orders of magnitude of latency for flexibility, and the register-bank and JSON-config interfaces between tiers confine the slower tier's influence on the faster one to two channels: config load at session start, and the HOLD latch on a no-approval outcome, which only narrows the faster tier's behavior (stop trading) and never widens it. On the EOD tier the binding constraint is not latency — NFS5 grants 30 minutes — but **correctness, reproducibility, and auditability**: FS7 demands bit-identical re-runs, FS8 demands that a human can veto every output. Those two properties, not throughput, drive every design decision below.

This subsystem is directly responsible for the following specifications:

| Spec | Role of EOD subsystem |
|---|---|
| **FS6** | Sole owner: classify the next trading day's regime into ≥ 3 distinguishable states from daily market data. |
| **FS7** | Sole owner: search ≥ 9 parameter combinations for the regime's strategy and select the metric-maximizing one, with deterministic (bit-identical) output. |
| **FS8** | Sole owner of the gate: no configuration reaches the live system without explicit operator approval. (The PS Config Loader in 3.2.3.4 owns the *receiving* end of the chain of custody.) |
| **FS12 (non-ess.)** | Sole owner: display and log pipeline stage, regime, selected parameters, backtest Sharpe, and approval status as each stage completes. |
| **NFS5 (non-ess.)** | Sole owner: full pipeline (ingestion → classification → optimization → approval prompt) within 30 minutes; input validation per 3.3.3.6. |

Upstream dependency: FS5's exported session history and a historical daily OHLCV dataset are the pipeline's inputs. The session history comes from sessions traded against 3.4's replay-based simulator, which carries tick-level (L3) event streams; it does not aggregate those streams into daily bars, so it is not the daily-OHLCV source. The daily OHLCV source is **Yahoo Finance** (free, no license required) — the same source already exercised in the preliminary validation run (3.3.3.3.1). Downstream contract: the JSON configuration schema of 3.3.3.5, consumed by the PS Config Loader — jointly owned with 3.2, exactly as the register bank table of 3.2.3.1 is jointly owned with 3.1.

Figure 3.3 shows the pipeline structure. *(Figure placeholder — reuse the SERVER subgraph of the system block diagram, minus the Console Monitor, which belongs to the PS peripheral group per the final subsystem split, and minus the External Resources / Web-News-Social block and its NLP/LLM Pipeline and sentiment arrows, dropped along with FS9/FS10 — see Section 2 footnote. The EOD→PS arrow should be annotated as the HOLD-latch/config-push path of 3.2.3.3 and 3.3.3.7, not as a generic link.)*

---

## 3.3.2 Engineering Design Process

Three significant design decisions shaped this subsystem. The recurring theme differs from 3.1/3.2: there, the specs priced in *latency* and the decisions bought determinism of *timing*; here, the specs price in *reproducibility and human oversight* and the decisions buy determinism of *results*. Where a rationale is quantitative, the supporting arithmetic appears inline with the decision it licenses.

### Decision 1 — Execution environment: Python host pipeline

A scan of the open-source tooling landscape converged quickly on one answer: a Python 3 host pipeline — pandas/NumPy for data handling, the standard library for orchestration, the strategy kernel handled separately below (3.3.3.3). Python has the deepest library ecosystem for this workload, the most community resources to build against, and the lowest development cost of any realistic option — and NFS5's 30-minute budget is generous enough that Python's performance profile is simply not a constraint worth trading that away for.

### Decision 2 — Regime classifier (FS6): rule-based thresholds vs. Hidden Markov Model

The classifier's job in AQTA is *routing* — selecting which of the three pre-built strategies (3.2.3.2: Trending→Momentum, Ranging→Mean Reversion, Volatile→Defensive) runs tomorrow — not alpha generation. The two real candidates were a two-feature rule-based threshold classifier and a Hidden Markov Model, the more statistically sophisticated approach the regime-detection literature generally favors:

| Dimension | Rule-based threshold (selected) | Hidden Markov Model |
|---|---|---|
| Classification fidelity | Adequate for a routing decision | Best-in-literature for regime persistence [15] — but FS6's verification only checks ≥ 3 regimes appear, never scores accuracy, so this advantage is never actually tested |
| Implementation & verification cost, given team capability | Two features, three comparisons; exhaustively unit-testable in a day | The HMM has to be *fit* to data (an iterative statistical procedure, not a fixed formula), it isn't guaranteed to converge to the same answer on every run, and it's a new dependency (`hmmlearn`) none of the team has used before |
| Operator auditability (FS8) | "vol > 75th percentile ⇒ Volatile" is checkable against a chart in seconds | State posteriors need post-hoc labeling and give no intuitive account of why a day was classified a given way — the FS8 approval step becomes a formality |

HMM wins only on the one dimension FS6 doesn't verify; the rule-based classifier wins on implementation cost and on the auditability FS8 actually requires, which is decisive given the team's capability and bandwidth already committed to 3.1/3.2.

### Decision 3 — Parameter search (FS7): exhaustive grid

We exhaustively enumerate the 27-point grid rather than using a smarter search method (e.g. Bayesian optimization): the grid is cheap enough to fully evaluate (arithmetic below), a full sweep is deterministic by construction — which "smart" search methods aren't, and directly satisfies FS7's bit-identical requirement — and it also gives the operator the *complete* result table for FS8 review, not just the points a search algorithm happened to sample.

**Runtime budget (NFS5) — the arithmetic behind "the grid is cheap."** NFS5 allows 30 minutes on the reference workload (1 year of daily OHLCV). The pipeline's cost is dominated by one term — the sweep — and every other stage is bounded by trivial arithmetic:

```
Regime path input:      252 daily bars → feature computation O(n), n = 252    → milliseconds
Regime classification:  two percentile lookups + three comparisons, O(1)      → microseconds

Sweep workload:
  snapshot records/session = 100 Hz × 6.5 h × 3600 s/h = 2.34 M records
  grid size                = 27 combinations
  Per grid point: one pass of vectorized NumPy/pandas array operations (signal computation,
    position derivation, cumulative P&L) over the 2.34 M-row snapshot array — vectorized
    operations at this scale are expected to run in well under a second per grid point on
    commodity hardware (order-of-magnitude expectation from vectorized-array performance;
    the wall-clock run on the EOD server is the pending compliance evidence, 3.3.4)
  sweep time (pessimistic allowance) ≈ 1 min, covering I/O, pandas overhead, and repeated
    array allocation across 27 points — a deliberate ~50× cushion over the expectation,
    so the NFS5 argument survives even a large miss in the per-point estimate

Report/serialize:  negligible

Pipeline total (pessimistic): ≈ 1–2 min  →  ≥ 15× margin against NFS5 = 30 min
```

This arithmetic is what licenses both Decision 1 and this one: Python is fast enough and exhaustive search is affordable, because a vectorized sweep over 27 grid points costs a small fraction of the 30-minute budget regardless of where the exact per-point timing lands. The margin is a *design allowance*, not slack to be admired — it absorbs grid growth and multi-session backtest windows, and the sensitivity table below bounds exactly how far:

| Configuration | Grid points | Est. sweep time (scaled from the ≈ 1 min / 27-point allowance above) | Verdict |
|---|---|---|---|
| Prototype: 1 symbol × 27-pt grid × 1 session | 27 | ≈ 1 min | Selected operating point |
| 5-value axes (125-pt grid) | 125 | ≈ 4–5 min (≈ 125⁄27 × the 27-point allowance) | Comfortably fits NFS5 — vectorized per-point cost scales with grid points, not with the ~2.34 M-record snapshot array |

The table bounds the design's validity region explicitly: exhaustive grid + vectorized backtest kernel is correct for the specified prototype and its first two growth steps.

---

## 3.3.3 Final Design Details

The pipeline is a sequential staged program; Figure 3.4 shows the stage graph with FS12 log points at every transition. *(Figure placeholder — stage flowchart: [Data Import & Validation] → [Parameter Engineering] → [Regime Detection] → [Strategy Reoptimize / Backtest & Parameter Sweep] → [Risk Analysis] → [Generate JSON Config] → [Operator Approval] → [Transmit / or REJECT→HOLD].)*

### 3.3.3.1 Data import and Parameter Engineering

Inputs are validated before any computation: schema check, monotonic-timestamp check, minimum-history check. The floor is defined as **calibration window + 126 trading days**, not a fixed number: the calibration window (config-adjustable, ~60–90 trading days is enough for the percentile scheme in 3.3.3.2 to be statistically meaningful) has to sit entirely *before* the earliest day being classified, and FS6's own verification method classifies a 6-month (126 trading day) span — so the floor is tied to whatever calibration window is configured, and can never be tighter than what FS6's own verification procedure needs to run at all. Validation failure aborts — no config from bad data.

Two features are computed from daily OHLCV closes:

| Feature | Definition | Window |
|---|---|---|
| Realized volatility `σ` | `σ = std(ln(Cₜ/Cₜ₋₁)) × √252` | 20 trading days (same window as the SMA₂₀ trend leg, for consistency) |
| Trend strength `T` | `T = (SMA₅ − SMA₂₀) / SMA₂₀` | 5- and 20-day SMAs |

Both are standard constructions; the calibration scheme below (3.3.3.2) is the real design contribution, with its non-degeneracy guarantee proven there.

### 3.3.3.2 Regime Detection (FS6)

```
θ_vol   = percentile(σ over calibration window, 75)    # config-adjustable
θ_trend = percentile(|T| over calibration window, 60)  # config-adjustable

if   σ_today   ≥ θ_vol:    regime = VOLATILE   → Defensive
elif |T_today| ≥ θ_trend:  regime = TRENDING   → Momentum
else:                      regime = RANGING    → Mean Reversion
```

Pure function of the input window — no state, no seed, no fit. Unit tests cover all three branches plus both boundary equalities (`≥` resolves ties toward the safer, Defensive branch).

**Non-degeneracy.** FS6 requires ≥ 3 distinct regimes over a 6-month test window. Fixed thresholds (e.g. "vol > 25% ⇒ Volatile") fail this on a calm stretch that never crosses the constant, collapsing every day to one label. Percentile-based thresholds don't have that failure mode: by definition, the top 25% of days by volatility in the calibration window are classified VOLATILE, and TRENDING/RANGING split the remainder — a single-label output is structurally impossible.

The classifier calibrates on a trailing window and applies that threshold to the next, out-of-sample window, since a live system cannot compute a threshold from data it hasn't seen yet. 3.3.3.3.1 validates this deployed trailing-window scheme directly on a real 6-month window and confirms all three regimes present (80/29/17). Extending that validation across additional historical windows is the scheduled next verification step, not an open design question — the classification rule itself is final.

### 3.3.3.3 Strategy Reoptimize — Backtest & Parameter Sweep (FS7)

Working grids (each 3 × 3 × 3 = 27 combinations ≥ FS7's minimum 9), deliberately coarse per Decision 3's overfitting mitigation. Thresholds below are in the daily-bar proxy units of the 3.3.3.3.1 validation run; the live intraday config carries their integer half-cent equivalents per 3.2.3.2 (the validation run substituted a vol-window axis for the Defensive spread floor, since daily bars carry no spread):

| Strategy | Parameter 1 | Parameter 2 | Parameter 3 |
|---|---|---|---|
| Momentum | lookback ∈ {5, 10, 20} | entry threshold ∈ {0.005, 0.01, 0.02} | position scalar ∈ {0.5, 1.0, 1.5} |
| Mean Reversion | MA window ∈ {10, 20, 50} | deviation threshold ∈ {0.01, 0.02, 0.05} | position scalar ∈ {0.5, 1.0, 1.5} |
| Defensive | spread floor ∈ {1, 2, 4} cents | vol cutoff ∈ {0.1, 0.2, 0.4} | position scalar ∈ {0.25, 0.5, 1.0} |

The kernel replays the **snapshot stream exported by the Execution Logger** (FS5) rather than synthetic bars, so the sweep evaluates strategies on the data distribution the deployed strategy will see. Bootstrap case (no live sessions yet): the recorded real-data replay session from 3.4 (LOBSTER replay) serves as the initial corpus — a single session, thin by construction, growing as live sessions accumulate. The daily-OHLCV dataset feeds only the regime path, not the sweep.

```
for params in grid (fixed lexicographic order):          # determinism: fixed order
    signals = compute_signal_array(snapshot_df, params)  # vectorized NumPy/pandas ops
    positions = signals_to_positions(signals, params)
    pnl_series = positions_to_pnl(positions, price_series)
    metrics[params] = sharpe(pnl_series), max_drawdown(pnl_series), n_trades
select params* = argmax over sharpe,
       ties broken by lexicographic parameter order      # total order ⇒ unique winner
```

**Scope.** The backtest strategy logic is a separate Python/NumPy implementation, not a port of the PS's C code — simpler to build, at the cost of not being an exact replay of live behavior. The PS Runtime Risk Guard and the operator's review at approval time already cover that gap, so it doesn't weaken FS3 or FS8. Fills are priced at the touch, with no queue or market-impact modeling. Grid points are ranked by a Sharpe-style score, `mean(daily P&L) / std(daily P&L) × √252` — steady profit scores higher than the same profit earned inconsistently. FS7's bit-identical requirement is about re-running this pipeline on the same input, not matching the PS — and the computation is deterministic and single-threaded, so that's satisfied.

**FS7 determinism.** FS7 requires bit-identical re-runs, not just correct output. Every source of nondeterminism is closed:

| Source | How it's eliminated |
|---|---|
| Random init / sampling | No fitted model, no sampling (Decisions 2–3) — no RNG is used |
| Parallel evaluation order | Sweep runs strictly sequential in a fixed order — stable summation |
| Hash/dict iteration | Grids are ordered lists; serialization is canonical (3.3.3.7) |
| Cross-machine float differences | Verification runs both re-run passes on one designated host |
| Tie on Sharpe | Lexicographic tie-break — winner is always unique |

Verified by running the pipeline twice on the same input and byte-comparing the output.

#### 3.3.3.3.1 Preliminary validation run (real data)

The procedures above were run end-to-end against real AAPL daily OHLCV (1984-09-07 to 2008-10-14, BSD-licensed public archive, fetched via raw.githubusercontent.com) as a preliminary check ahead of full implementation. This is a stand-in for the production source (Yahoo Finance, per 3.3.1) rather than a pull from Yahoo Finance itself; both are free daily-OHLCV sources with no license required, so the substitution does not change the data-access argument. This window predates and is unrelated to the LOBSTER anchor day (3.4.2 Decision 1); the two real-data checks in this report are independent by design — this one exercises the regime/sweep procedure on a full percentile-scheme-sized history, the other (3.4.2 Decision 1) exercises the tick-level protocol translation — and are not required to share a period.

Calibrating on 2007-04-18 to 2008-04-16 (252 trading days, `θ_vol = 0.518`, `θ_trend = 0.059`) and classifying the next 126 days — which fall in the Sept–Oct 2008 crash:

| Regime | Days (of 126) |
|---|---|
| RANGING | 80 |
| TRENDING | 29 |
| VOLATILE | 17 |

All three non-empty — the 3.3.3.2 non-degeneracy proof holds empirically here too. Sweeping the same 27-point grids against each regime's days, selecting by Sharpe:

| Regime | Strategy | Winning parameters | Sharpe |
|---|---|---|---|
| TRENDING | Momentum | lookback=5, entry_thresh=0.01, pos_scalar=1.5 | **1.856** |
| RANGING | Mean Reversion | window=20, dev_thresh=0.02, pos_scalar=0.5 | **2.077** |
| VOLATILE | Defensive | vol_window=20, vol_cutoff=0.2, pos_scalar=0.5 | **−3.125** |

VOLATILE is reported as-is: even the best of 27 candidates during a genuine crash still loses money on a risk-adjusted basis. This is not a design failure — it's exactly the situation the FS8 approval gate exists for, since the operator sees the full sweep table, not just the winning row.

This run validates the procedure — determinism, non-degenerate classification, fixed tie-break, sweep-table transparency — on real data. It does **not** validate sweep runtime (Decision 3's runtime budget) or the actual PL/PS system, which doesn't exist yet.

---

### 3.3.3.4 Risk Analysis and config generation

A validation pass on the winning parameters, not another optimization step. Three checks: (1) did this parameter set ever breach the hard risk limits during the backtest (notional, position size, order rate — the same limits the PS enforces at runtime, 3.2.3.3)? (2) is the worst peak-to-trough loss within bounds — flagged if it exceeds $25,000 CAD, half the FS3 notional ceiling; (3) is the result backed by enough trades to be statistically meaningful — a high Sharpe from only 2 trades isn't, so anything under 10 trades is flagged. None of these checks reject automatically: a failed check is written into the operator's report, and the operator decides.

### 3.3.3.5 JSON configuration schema (jointly owned with 3.2.3.4)

The fields of the config file the pipeline produces: which strategy and regime were selected, the parameter values, the risk limits, audit metadata on how the result was produced, and who approved it and when.

| Field | Type | Content |
|---|---|---|
| `strategy_id` | string | `momentum` / `mean_reversion` / `defensive` |
| `regime_label` | string | `trending` / `ranging` / `volatile` |
| `parameters` | object | Swept winner's values, integer-encoded to match the PS kernel. Keys per strategy — momentum: `lookback`, `entry_thresh`, `pos_scalar`; mean_reversion: `window`, `dev_thresh`, `pos_scalar`; defensive: `spread_floor`, `vol_cutoff`, `pos_scalar` (lockstep with 3.2.3.2 and the 3.3.3.3 grid axes) |
| `risk_limits` | object | `max_notional_cad`, `max_position_shares`, `max_order_rate`, each ≤ its FS3 ceiling |
| `provenance` | object | Data window, grid hash, backtest Sharpe, pipeline version — the FS12 record embedded for audit |
| `approval` | object | `operator_id`, `timestamp` — appended only by the approval action (3.3.3.7) |

### 3.3.3.6 FS12 status reporting

Each stage logs entry/exit + key numbers via a shared wrapper. A failed stage emits no config.

### 3.3.3.7 Operator Approval and configuration transmission (FS8)

The operator reviews the full FS12 report and approves interactively. Transmission cannot occur without that approval, not because of a check that could be skipped, but because the send call exists only inside the code path that runs after approval succeeds — there's no separate step where the code checks "was this approved?" before sending. Approving is the action that triggers sending. If nobody approves, the send call is never reached. That satisfies FS8's requirement directly, and is exactly what its verification checks for.

Transport is a push over the PS GbE via `scp` to a staging path on the SoC, from which the Config Loader ingests it at startup.

---

## 3.3.4 Specification Compliance Summary

| Spec | How the final design satisfies it | Evidence status |
|---|---|---|
| FS6 | Percentile-thresholded two-feature classifier; ≥ 3 non-empty regimes provable by construction (3.3.3.2) | Closed by arithmetic; pending 6-month reference-data run |
| FS7 | Exhaustive fixed-order grid + deterministic vectorized kernel + total-order tie-break; all nondeterminism sources enumerated and closed (3.3.3.3) | Analytical; pending double-run byte-compare |
| FS8 | Transmission call structurally unreachable without operator approval — the send has one caller, the approval prompt's success branch (3.3.3.7) | Pending no-approval injection test |
| FS12 (non-ess.) | `run_stage()` wrapper logs every transition; approval report aggregates regime/sweep/Sharpe/status | Pending full-cycle log inspection |
| NFS5 (non-ess.) | ≈ 1–2 min pessimistic total vs 30 min budget; ≥ 15× margin with growth allowance (Decision 3's runtime budget and grid-scale table) | Analytical; pending reference-dataset wall-clock |

---

# 3.4 Exchange Simulator Subsystem

> Internal component names: *Dataset Preprocessor (offline), Replayer, Order Receiver, FS13 Offline Checker*. Measured figures in this section come from design-time prototype runs on the development sandbox; a re-run on the target host is pending.

---

## 3.4.1 Overview and Specification Mapping

The Exchange Simulator plays the exchange that the project deliberately does not connect to (Section 1.2's paper-trading boundary). It runs on the host PC at the far end of the point-to-point Gigabit Ethernet link: it replays a real order-level trading day into the PL in the custom protocol of Table 3.1.3, and captures every order packet the SoC emits (Table 3.1.4) for offline validation.

Published FPGA trading systems validate at three access tiers: live capital in exchange co-location [8], [9]; a broker's test server [2]; or a laboratory setup where a host script injects packets and captures what comes back [6], [7]. AQTA sits at the laboratory tier — co-location and broker-member access are out of scope for a capstone — so this subsystem must supply by itself what the upper tiers get from their environment: the market data, the counterparty, and the measurement fixture. The tier also fixes the right engineering form, which is deliberately small: **one real dataset, three short host scripts, and Wireshark, with every correctness judgment made offline rather than in a runtime component.** The simulator is thus both the exchange and the project's principal verification instrument: FS1's reference packet sequence, FS2's measurement input, FS13's captured packets, NFS2's frame counts, and NFS4's 6.5-hour session all come from here.

| Spec | Simulator role |
|---|---|
| **FS1, FS2** | Instrument: reference packet sequences are fixed slices of the replay dataset; the Replayer's TX log provides transmit-side timestamps. |
| **FS13** | Oracle: the Offline Checker independently parses every captured order packet against the Table 3.1.4 layout. |
| **NFS2** | Peer: the other endpoint of the 10-minute zero-drop window; the expected frame count is a static property of the frame file. |
| **NFS4** | Provider: replays the full 6.5-hour real session. |
| **FS6/FS7 (bootstrap)** | Data source: the recorded replay session is the FS7 backtest bootstrap corpus (3.3.3.3); the regime path uses Yahoo daily OHLCV (3.3.1) instead. |
| **NFS3** | Pure host software — subsystem hardware cost is $0 (the host PC is excluded from the cap). |

Figure 3.5 shows the structure. *(Figure placeholder — two lanes: offline — LOBSTER files → Dataset Preprocessor → frame file + expected-book file; online — Replayer → UDP TX → PL; PL → UDP RX → Order Receiver → order log; post-session — FS13 Offline Checker, book diff against the expected-book file; Wireshark on the NIC.)*

---

## 3.4.2 Engineering Design Process

Two decisions define this subsystem; both were settled by external constraints and the published record.

### Decision 1 — Market-data source: replay a real captured L3 trading day

| Alternative | Outcome |
|---|---|
| Broker paper-trading counterparty | **Rejected.** Broker APIs are cloud REST/WebSocket sessions — they cannot terminate the point-to-point PL GbE link or speak the custom UDP protocol, so the PL path would be untestable. Live data is also unrepeatable, so FS1/FS2 reference sequences could not even be specified. And retail APIs top out at L2 (aggregated price levels, no order IDs [10]) while the protocol carries L3; the literature obtains order-level data only through member or institutional channels [2], [3]. |
| Synthetic order-flow generator | **Rejected.** Meets the protocol formats, but its realism (rates, event mix, burst structure) would itself need modeling and defense — effort no specification consumes. |
| **Replay of a real captured L3 day (selected)** | **Selected.** Realism is free (the stream *is* a real NASDAQ day), reproducibility is structural (a fixed file), and one full 6.5 h session is exactly what NFS4 needs. |

The data exists in exactly the required form: LOBSTER reconstructs order-level book data from NASDAQ TotalView-ITCH [11]; full access is a paid subscription [12], but the official free samples [13] include one complete trading day (AAPL, 2012-06-21) as a `message` file (the L3 event stream) plus an `orderbook` file (the book state after every message). The AAPL day at 10 book levels matches the PL book depth (Table 3.1.5), and published FPGA order-book work has validated against this same sample day [14]. The orderbook file is a ready-made per-message ground truth — it lets the PL book be verified without the simulator ever maintaining a book of its own (3.4.3.1). The dataset and the protocol were exercised together at design time by pushing the full day (400,391 messages) through a prototype of the translation layer: that run measured the day's rates (~17 msg/s average, ~2,400 msg/s worst 100 ms burst — the figures used throughout this section) and caught two protocol ambiguities early enough to fix the document rather than debug hardware — sub-penny prices (resolved by the integer-cent rounding of 3.1.3.2) and whether a Modify's `qty` is absolute or a delta (resolved in Table 3.1.3: absolute remaining quantity).

### Decision 2 — Execution model: validate-and-log, all judgment offline

| Alternative | Outcome |
|---|---|
| Full matching engine (received orders match against the replayed flow and produce fills) | **Rejected.** A large correct-by-construction artifact whose outputs no Section 2 spec consumes — and it would itself need a test bench. |
| **Paced replay + validate-and-log (selected)** | **Selected.** The replayed stream is never altered by received orders; every received packet is captured with a timestamp and checked offline against the FS13 layout. |

The published record splits on exactly this line: the one surveyed system with a full matching engine validates it against synthetically generated commands in an RTL testbench [18] — the matching engine substitutes for real data the authors did not have. Systems that *have* real data replay it and do not match against their own orders [3], [14], [8]. AQTA needs no fills from the simulator: fill timing is modeled on the PS side (fill delay **T**, 3.2.3.3), order disposition is tracked by the PS open-order table and Risk Guard (3.2.3.3, FS14), and with FS3 capping orders at 1,000 shares against a book quoting thousands per level, market impact would be second-order even if modeled.

Since nothing needs to be decided at runtime, all intelligence moves off the session path: a preprocessor materializes everything expensive once, the live path is a paced `sendto` loop plus a `recvfrom` logger, and parsing and comparison run afterwards against the logs. That a plain Python script suffices is settled by one chain of rates, each comfortably below the next:

```
real day, worst burst     ~2,400 msg/s    (measured, Decision 1)
replay script, max send   ~91,000 msg/s   (measured)
PS decision ceiling       ~200,000 /s     (analysis, 3.2 Decision 3)
PL wire ceiling           ~1.39 M pkt/s   (arithmetic, 3.1.2)
```

The sender is the bottleneck, and that is the right place for it: the script clears the worst real burst with a ~38× margin, no rate this subsystem can produce stresses the PL, and the PS can keep up with every tick at any replay speed.

---

## 3.4.3 Final Design Details

### 3.4.3.1 Components and artifacts

**Dataset Preprocessor (offline, once per slice).** Reads the LOBSTER message and orderbook files and slice bounds. Its translation layer tracks the order pool, rewrites Modify events to the order's new absolute remaining quantity (Table 3.1.3's `qty` semantics), rounds sub-penny prices to integer cents (per 3.1.3.2), and prepends a priming prefix of Add events reconstructing the book at slice start, so that the ~2% of messages referencing pre-session orders resolve. It runs at ~1 M msg/s — the full day translates in under a second. Two artifacts:

1. **Frame file** — the slice pre-encoded into Table 3.1.3 payloads, each frame keeping its original NASDAQ timestamp for pacing.
2. **Expected-book file** — per-message top-of-book, derived from LOBSTER's own orderbook file with the same cent rounding applied. Exported PS snapshots carry the PL `SEQ` they were decided against (3.2.3.5), which maps one-to-one onto frame index, so each snapshot is diffed against its expected-book row directly.

The preprocessor asserts three sanity checks on every run — every Modify/Delete references a known order, no book quantity goes negative, and every encoded frame decodes back to its source event — and all three passed with zero violations across the full real day. Its output is also deterministic: two passes over the same file and parameters produce byte-identical streams, which is what makes FS7's bootstrap corpus reproducible end-to-end.

**Replayer (online).** Reads the frame file and transmits each frame at `session_start + (t_msg − t_open)/rate_scale` (priming prefix sent back-to-back first), logging frame index + TX timestamp per frame. A timed `sendto` of pre-encoded bytes.

**Order Receiver (online).** Appends every received packet — raw bytes + RX timestamp — to the order log. Never parses, never replies.

**FS13 Offline Checker (post-session).** Parses every logged order packet against Table 3.1.4 and range-checks each field. As an independent second implementation of the protocol spec, any disagreement with the PL encoder indicts the *document* — the mechanism that already caught the Modify-semantics ambiguity during Decision 1's prototype run, before any hardware existed.

A full session's logs total tens of MB and average wire utilization is around 0.001% of the GbE link — data volume is a non-issue, so the NFS4 soak run keeps full logging on throughout.

### 3.4.3.2 Replay pacing

`rate_scale` is a command-line parameter: 1 reproduces the real day's timing; larger values compress it. Host timer resolution (~1 ms) is far below the day's mean message gap (~60 ms), so pacing is faithful at session scale. The ~38× send margin doubles as the **maximum faithful compression factor**: up to about `rate_scale = 38`, even the densest real burst stays within send capability and every frame lands on its scaled timestamp.

Usage rule: development and demo runs compress (`rate_scale = 20` replays the whole day in under 20 minutes with its burst structure intact) or replay a dense slice at real speed; verification runs anchored to wall-clock time — NFS4's soak, FS2's 1000-update measurement, NFS2's 10-minute window — use `rate_scale = 1`, because the PS's rate limit, fill delay **T**, and snapshot sampling are wall-clock-based.

### 3.4.3.3 Link and host configuration

Host NIC directly cabled to the PL RJ45 (no switch — NFS2's "no unexplained drops" argument depends on this), static IP/MAC matching the PL's compile-time constants (3.1.3.1), UDP checksum emitted as zero (the PL ignores the field; integrity is covered by the Ethernet FCS). The simulator may share a physical machine with the EOD server but runs as an independent process. Wireshark on this NIC is the primary instrument for FS2/NFS1/NFS2; the TX and RX logs share the host clock and serve as a second witness.

---

## 3.4.4 Specification Compliance Summary

| Spec | What the simulator provides | Evidence status |
|---|---|---|
| FS1/FS2 (instrument) | Reference sequences as preprocessed slices; TX log as second timing witness | Design complete; pending slice authoring |
| FS13 (oracle) | Offline parse of every captured order packet against Table 3.1.4 | Mechanism validated during Decision 1's prototype run; pending live cross-parse |
| NFS2 (peer) | Direct-cabled peer; expected frame count static in the frame file | Pending 10-min counted run |
| NFS4 (provider) | 6.5 h real-day replay at `rate_scale = 1` | Pending soak run |
| FS6/FS7 (bootstrap) | Recorded replay session as FS7 bootstrap corpus (3.3.3.3) | Translation validated at design time; recorded session pending |
| NFS3 | Host software only — $0 hardware | By construction |
| Own correctness | Sanity checks, determinism, and send-rate margin all measured (3.4.3.1, 3.4.2) | Sandbox-measured; target-host re-run pending |

---

# 4. Discussion and Project Timeline

## 4.1 Evaluation of Final Design

## 4.2 Use of Advanced Knowledge

## 4.3 Creativity, Novelty, Elegance

The most creative part of AQTA is the disciplined hardware/software partition: the design does not attempt to place an entire trading system in FPGA logic, and it does not accept a normal Linux network path for the latency-critical loop. Instead, it uses PL for deterministic field extraction and book maintenance, PS for bounded configurable decision logic, and an EOD server for slower optimization work.

The fixed-width packet format is also an elegant design point because it intentionally changes the simulator interface to match the strengths of hardware parsing. This simplifies PL logic, validation, and replay testing. RiskGuard adds a second elegant separation: strategies propose trades, but a strategy-independent safety layer decides whether an order is allowed to leave the system.

## 4.4 Student Hours

[INSERT A TABLE]

## 4.5 Potential Safety Hazards

The physical safety hazards are limited because the prototype uses a low-voltage development board, a host PC, and standard lab equipment. Standard ECE project-room handling still applies: power should be disconnected before rewiring, cables should be strain-relieved, and exposed conductors should not be probed while the board is powered unless normal lab electrical-safety practice is followed.

The more important hazards for AQTA are financial, social, and professional. A trading accelerator can encourage overconfidence if latency performance is mistaken for financial validity. The prototype therefore remains restricted to paper trading, requires operator approval before loading EOD-generated configurations, logs all decisions and rejections, and enforces RiskGuard limits regardless of active strategy. These safeguards are part of the engineering design rather than afterthoughts.

## 4.6 Project Timeline

[INSERT THE GANTT CHART]

# References

[1] C. Leber, B. Geib and H. Litz, "High Frequency Trading Acceleration Using FPGAs," *2011 21st International Conference on Field Programmable Logic and Applications*, Chania, Greece, 2011, pp. 317-322, doi: 10.1109/FPL.2011.64.

[2] Y.-C. Kao, H.-A. Chen and H.-P. Ma, "An FPGA-Based High-Frequency Trading System for 10 Gigabit Ethernet with a Latency of 433 ns," *2022 International Symposium on VLSI Design, Automation and Test (VLSI-DAT)*, Hsinchu, Taiwan, 2022, pp. 1-4, doi: 10.1109/VLSI-DAT54769.2022.9768065.

[3] C. He, H. Fu, W. Luk, W. Li and G. Yang, "Exploring the potential of reconfigurable platforms for order book update," *2017 27th International Conference on Field Programmable Logic and Applications (FPL)*, Ghent, Belgium, 2017, pp. 1-8, doi: 10.23919/FPL.2017.8056862.

[4] G. W. Morris, D. B. Thomas and W. Luk, "FPGA Accelerated Low-Latency Market Data Feed Processing," *2009 17th IEEE Symposium on High Performance Interconnects*, New York, NY, USA, 2009, pp. 83-89, doi: 10.1109/HOTI.2009.17.

[5] M. Mohamed Asan Basiri, "Hardware based Order Book Design in High Frequency Algo Trading," *2021 IEEE International Symposium on Smart Electronic Systems (iSES)*, Jaipur, India, 2021, pp. 285-288, doi: 10.1109/iSES52644.2021.00073.

[6] A. Boutros, B. Grady, M. Abbas and P. Chow, "Build fast, trade fast: FPGA-based high-frequency trading using high-level synthesis," *2017 International Conference on ReConFigurable Computing and FPGAs (ReConFig)*, Cancun, Mexico, 2017, pp. 1-6, doi: 10.1109/RECONFIG.2017.8279781.

[7] R. Osuna, B. Reponte, and L. G. Ramirez, "Low-latency Ethernet communications on FPGA SoC for high frequency trading," Kastner Research Group, University of California, San Diego, San Diego, CA, USA, Tech. Rep., Jun. 2025. [Online]. Available: https://kastner.ucsd.edu/wp-content/uploads/2025/06/admin/highfrequencytrading.pdf

[8] K. Tatsumura, R. Hidaka, J. Nakayama, T. Kashimata, and M. Yamasaki, "Real-time Trading System Based on Selections of Potentially Profitable, Uncorrelated, and Balanced Stocks by NP-Hard Combinatorial Optimization," *IEEE Access*, vol. 11, pp. 120023–120036, 2023, doi: 10.1109/ACCESS.2023.3326816.

[9] K. Tatsumura, R. Hidaka, J. Nakayama, T. Kashimata, and M. Yamasaki, "Pairs-Trading System Using Quantum-Inspired Combinatorial Optimization Accelerator for Optimal Path Search in Market Graphs," *IEEE Access*, vol. 11, pp. 104406–104416, 2023, doi: 10.1109/ACCESS.2023.3316727.

[10] Interactive Brokers, "Market Depth (Level II)," TWS API v9.72+ Documentation. [Online]. Available: https://interactivebrokers.github.io/tws-api/market_depth.html [Accessed: Jul. 9, 2026].

[11] R. Huang and T. Polak, "LOBSTER: Limit Order Book Reconstruction System," SSRN Working Paper 1977207, Humboldt-Universität zu Berlin, Dec. 2011, doi: 10.2139/ssrn.1977207.

[12] LOBSTER, "Price List — Academic Users," LOBSTER academic data. [Online]. Available: https://data.lobsterdata.com/info/docs/legal/LOBSTER_priceList.pdf [Accessed: Jul. 9, 2026].

[13] LOBSTER, "Sample Files" and "Data Structure," LOBSTER academic data, Humboldt-Universität zu Berlin. [Online]. Available: https://lobsterdata.com/info/DataSamples.php ; https://lobsterdata.com/info/DataStructure.php (dataset: AAPL 2012-06-21, levels 1–50; official NASDAQ Historical TotalView-ITCH sample day). [Accessed: Jul. 9, 2026].

[14] Y. Zheng, "FPGA-based Acceleration for High Frequency Trading," M.Phil. thesis, Dept. Electron. Comput. Eng., Hong Kong Univ. Sci. Technol., Hong Kong, Jan. 2023.

[15] J. D. Hamilton, "A New Approach to the Economic Analysis of Nonstationary Time Series and the Business Cycle," *Econometrica*, vol. 57, no. 2, pp. 357–384, Mar. 1989, doi: 10.2307/1912559.

[16] Xilinx, "Tri-Mode Ethernet MAC v9.0 LogiCORE IP Product Guide," PG051, Advanced Micro Devices, Inc. [Online]. Available: https://docs.amd.com/r/en-US/pg051-tri-mode-eth-mac [Accessed: Jul. 10, 2026].

[17] 正点原子 (ALIENTEK), "领航者 ZYNQ 之嵌入式开发指南 / Navigator ZYNQ-7020 Development Board User Manual (XC7Z020CLG400-2I)," Guangzhou Xingyi Electronic Technology Co., Ltd. [Online]. Available: http://www.openedv.com/docs/boards/fpga/zdyz_linhanzhe.html [Accessed: Jul. 10, 2026].

[18] S. Puranik, M. Barve, S. Rodi, and R. Patrikar, "Acceleration of Trading System Back End with FPGAs Using High-Level Synthesis Flow," *Electronics*, vol. 12, no. 3, art. 520, Jan. 2023, doi: 10.3390/electronics12030520.

[19] Xilinx, "Zynq-7000 SoC Data Sheet: Overview," DS190, v1.11.1, Advanced Micro Devices, Inc., Jul. 2018. [Online]. Available: https://docs.amd.com/v/u/en-US/ds190-Zynq-7000-Overview [Accessed: Jul. 11, 2026].

### Further reading (uncited in this document)

- D. H. Bailey, J. M. Borwein, M. López de Prado, and Q. J. Zhu, "The Probability of Backtest Overfitting," *Journal of Computational Finance*, vol. 20, no. 4, pp. 39–69, 2017, doi: 10.21314/JCF.2016.322.
- FIX Trading Community, "FIX Adapted for STreaming (FAST) Specification." [Online]. Available: https://www.fixtrading.org/standards/fast-online/ [Accessed: Jul. 9, 2026].
- J. Zang, "quant-engine: a C++ quantitative backtest and research engine," independent project documentation. [Online]. Available: https://qe.jiucheng-zang.ca [Accessed: Jul. 2026].

`[TEAM: bibliography housekeeping — (i) confirm the citation style guide for online resources; (ii) Hamilton 1989 is now in the list as [15]; Bailey et al. 2017 (backtest overfitting) moved to Further Reading since the grid-vs-Bayesian comparison it supported was cut; FinBERT/Araci and Loughran-McDonald were removed with the FS9/FS10 text-sentiment path (Section 2 footnote); Toshiba entries [8]/[9] venues confirmed (IEEE Access vol. 11, 2023, DOIs in place). TradingAgents 2024/2412.20138 remains a pending citation, to be appended if and when actually cited.]`
