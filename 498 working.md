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

*(NFS8 and NFS9 — fault-recovery and line-rate ingest-throughput acceptance specs — were dropped from scope: their verification procedures (scripted fault injection, line-rate PCAP stress) require a test-injection apparatus whose build-and-verify cost is disproportionate to the project's core objective, and the exchange simulator that would have supplied it is deliberately a replay-based instrument (3.4.2 Decision 1). The underlying engineering survives as design features without acceptance criteria: the PL fault-handling path and line-rate throughput analysis (3.1.3.1, 3.1.4.1), PS-side config validation (3.2.3.4), and EOD input validation (3.3.3.6). IDs are left unrenumbered, as with FS9/FS10.)*


# 3. Detailed Design

## 3.1 PL (FPGA) Market Data Path Subsystem

All numeric analysis in 3.1.4 is derivable on paper today (line-rate arithmetic, cycle budgets, datasheet resource math) — no code required.

---

### 3.1.1 Overview and Specification Mapping

The PL subsystem implements the entire wire-to-snapshot market data path and the order egress path in programmable logic on the XC7Z020[cite: 11]. On the receive side, it terminates the point-to-point Gigabit Ethernet link from the exchange simulator, validates and parses each custom UDP market data packet at fixed byte offsets, maintains a 10-level bid / 10-level ask limit order book (an L3-to-L1/L2 aggregation), and publishes the resulting top-of-book snapshot to the PS through an AXI-Lite register bank on M_AXI_GP0 (snapshot fields plus an incrementing `seq` register, committed atomically in one clock edge)[cite: 11]. On the transmit side, it receives risk-validated order fields written by the PS into the same register bank, begins encoding on the doorbell-register write strobe, encodes them into the fixed-length binary order format defined by FS13, and transmits them through the same PL GbE interface[cite: 11].

The subsystem exists because the software network path cannot meet the project's latency specifications: a conventional Linux socket path incurs interrupt handling, kernel protocol stack traversal, and kernel-to-user copies that together cost tens to hundreds of microseconds per packet, which is incompatible with the ≤ 1.5 μs decode budget of FS1[cite: 11]. By hardware/software partitioning, implementing the critical data path in the PL is structurally superior to the PS because programmable logic processes incoming packets with deterministic, microsecond-class, clock-cycle-exact latency, achieving nearly an order of magnitude faster tick-to-order response than a comparable software-only pipeline running on the PS[cite: 11]. Placing the parse and book-build stages in the PL removes the operating system from the market-data critical path entirely[cite: 11].

This subsystem is directly responsible for the following specifications:

| Spec | Role of PL subsystem |
| :--- | :--- |
| **FS1** | Sole owner: packet arrival → decoded top-of-book snapshot available to PS in ≤ 1.5 μs[cite: 11]. |
| **FS13** | Sole owner of the egress half: order packets must conform to the fixed-length binary format[cite: 11]. |
| **NFS1** | Owns the two PL segments (RX decode, TX encode) of the ≤ 50 μs end-to-end budget (300 μs ceiling applies to the superseded interrupt design)[cite: 11]. |
| **NFS2** | Owns link integrity: zero unexplained frame drops over a 10-minute window[cite: 11]. |
| **NFS6** | Owns the resource envelope: < 75% LUT, < 85% BRAM at 125 MHz with WNS > 0[cite: 11]. |
| **Fault handling (partial)** | Owns the hardware fault path: checksum-fail discard and FIFO-overflow handling with fault counters[cite: 11]. |
| **NFS4 (partial)** | Hardware fault paths (FCS discard, FIFO-overflow handling, drop counters) keep line-rate faults from escalating into a session-ending hang; primary ownership of the 6.5-hour stability requirement remains with the PS (3.2.1)[cite: 11]. |

Figure 3.1 shows the PL block structure and the shared AXI-Lite register bank at the PS boundary, using the stage names adopted throughout this section (Protocol Decode / Build Order Book / Protocol Encode)[cite: 11].

---

### 3.1.2 Engineering Design Process

Four significant design decisions shaped this subsystem[cite: 11]. Quantitative justifications regarding line-rate throughput, cycle budgets, and resource envelopes are integrated directly into each decision to confirm design feasibility[cite: 11].

#### Decision 1 — MAC layer implementation: vendor IP vs. minimal custom MAC

| Criterion (weight) | Xilinx TEMAC IP (selected) | Minimal custom MAC |
| :--- | :--- | :--- |
| Development & verification effort (40%) | 5 (Low — pre-verified vendor IP, wizard-generated) | 2 (High — custom preamble/FCS designed from scratch) |
| Resource cost (20%) | 2 (Medium-high — multi-thousand LUT baseline footprint) | 5 (Low — minimal RX/TX framing and CRC only) |
| Latency determinism (20%) | 3 (Medium — bounded, datasheet-specified pipeline delay) | 5 (High — zero unused feature logic overhead) |
| Protocol generality (20%) | 5 (High — robust standard interface ecosystem) | 2 (Low — limited point-to-point link only) |
| **Weighted result (1.0–5.0 scale)** | **4.0 — Selected**[cite: 11] | 3.2 |

*   **Rationale:** Development and verification speed represent the binding constraints because the pipeline cycle budget closes comfortably[cite: 11]. Standard engineering literature (Boutros et al.) supports instantiating off-the-shelf cores over custom layout verification[cite: 11].
*   **Integrated MAC Resource Envelope Analysis (NFS6):** Per Xilinx product guide specifications (PG051), the Tri-Mode Ethernet MAC core utilizes ≈1,500 registers and ≈3,000 LUTs along with 3 Block RAM blocks for internal streaming FIFOs[cite: 11]. While a custom MAC would minimize this footprint, the XC7Z020's spacious resource profile allows us to absorb this overhead safely[cite: 11].
*   **Integrated MAC Latency Impact:** The core introduces a deterministic internal pipeline delay of ≈20 clock cycles during RGMII DDR capture, which scales to roughly 160 ns at 125 MHz[cite: 11]. This delay is thoroughly accounted for in the available safety margins calculated under Decision 2[cite: 11].

#### Decision 2 — Parse architecture: store-and-forward vs. cut-through streaming parse

*   **Alternatives:** Store-and-forward buffers the complete frame before decoding; cut-through streams and slices fields in real time at fixed byte offsets[cite: 11].
*   **Integrated Line-Rate Throughput Analysis :** The maximum theoretical packet rate of a 1 Gbps link for our 24-byte payload configuration is derived below[cite: 11]:
    $$\text{Frame Over Wire} = 8\ \text{Preamble} + 14\ \text{Ethernet} + 20\ \text{IPv4} + 8\ \text{UDP} + 24\ \text{Payload} + 4\ \text{FCS} + 12\ \text{IFG} = 90\ \text{bytes} = 720\ \text{bits}$$[cite: 11]
    $$\text{Line Rate Saturation Limit} = 10^9\ \text{bits/sec} \div 720\ \text{bits} = 1,388,888\ \text{packets/second}$$[cite: 11]
    Serializing frame buffering under a store-and-forward design adds a 560 ns transmission serialization penalty (70 bytes post-preamble streaming at 1 octet/cycle), consuming over a third of the remaining budget[cite: 11].
*   **Integrated Latency Path Decomposition (FS1):** Cut-through parsing is selected because fixed offsets permit deterministic bit slicing concurrently with line arrival, removing Look-Ahead serialization[cite: 11]. The absolute step-by-step custom hardware logic latency totals exactly 77 clock cycles (616 ns): (1) Frame reception streaming: 560 ns (70 bytes), (2) FCS validation latch: 16 ns, (3) Tournament compare network reduction: 32 ns, and (4) Register bank synchronization: 8 ns[cite: 11]. Accounting for the vendor-spec MAC core ingestion delay, sensitivity analysis establishes the following final path budgets against the 1.5 μs functional specification ceiling[cite: 11]:
    *   *Optimistic Ingest Assumption (100 ns):* $616\ \text{ns} + 100\ \text{ns} = 716\ \text{ns}$ (**52% Safety Margin**)[cite: 11].
    *   *Pessimistic Ingest Assumption (400 ns):* $616\ \text{ns} + 400\ \text{ns} = 1,016\ \text{ns}$ (**32% Safety Margin**)[cite: 11].
*   **Commit Policy:** To ensure data integrity, fields are held in speculative staging registers and committed to the order book only upon an Ethernet Frame Check Sequence (FCS) pass signal[cite: 11]. On FCS fail, the frame is safely discarded, and a `parse_error` counter increments, fulfilling the fault-tolerant criteria of the fault-handling path[cite: 11].

#### Decision 3 — Order book storage: BRAM-indexed structure vs. fixed register array

*   **Alternatives:** Hashing price levels into distributed Block RAM (BRAM), or instantiating a dedicated flip-flop register array[cite: 11].
*   **Integrated Resource Footprint Projections (NFS6):** BRAM structures incur significant memory block fragmentation and address-lookup pipeline stalls at small depths[cite: 11]. Because our prototype scope is bounded to a single symbol with a 10-level bid and 10-level ask depth, a fixed flip-flop register array is selected[cite: 11]. This requires ≈1,500 registers (20 levels × 64 bits + snapshot 128 bits + counters) and ≈1,000 LUTs (to implement 20 parallel comparators and a 9-compare tournament reduction tree)[cite: 11]. This allows parallel combinational best-price extraction within a single 8 ns clock edge (125 MHz), ensuring clean timing closure (WNS > 0 ns) while utilizing 0 Block RAM blocks[cite: 11]. Updates addressing a price level outside the 10-level working window are discarded and tracked via internal diagnostic counters (`dropped_out_of_window`)[cite: 11].

---

### 📝 Final Resource Envelope Summary

To provide a high-level view of our overall hardware constraints across all combined decisions, Table 3.1.6 summarizes the estimated gate-level allocations on the XC7Z020 fabric[cite: 11].

Table 3.1.6: Gate-Level Hardware Resource Footprint Projections (XC7Z020 / NFS6)
| Component | Flip-Flop (FF) Estimate | Look-Up Table (LUT) Estimate | Block RAM (BRAM) |
| :--- | :--- | :--- | :--- |
| **Order Book Register Logic** | ≈1,500 registers | ≈1,000 LUTs (20 comparators) | 0 blocks[cite: 11] |
| **Xilinx TEMAC Core** | ≈1,500 registers | ≈3,000 LUTs (datasheet base) | 3 blocks (internal buffers)[cite: 11] |
| **Slicing & Header Decoders** | ≈500 registers | ≈1,000 LUTs (combinational masks) | 0 blocks[cite: 11] |
| **AXI-Lite GP0 Slave Bus Interface** | ≈500 registers | ≈800 LUTs (address decoding) | 0 blocks[cite: 11] |
| **Projected Footprint Totals** | **≈4,000 FFs (< 4%)** | **≈5,800 LUTs (≈11% of device)** | **3 Blocks (< 3%)**[cite: 11] |

> **Strategic Disclaimer regarding Page Constraints:** Detailed analytical modeling regarding long-term history ring buffer allocation bounds, EOD walks, and server hyper-parameter search spaces are omitted in this subsection due to report page constraints; full quantitative technical analysis for those software-side blocks is handled in Section 3.9[cite: 11].

---

### 3.1.3 Final Design Details

#### 3.1.3.1 Receive pipeline

The receive path is structured as a five-stage streaming pipeline running at a clock frequency of 125 MHz[cite: 11]:

1. **MAC RX (Xilinx TEMAC):** Handles RGMII DDR capture from the external PHY, preamble alignment, and FCS tracking, streaming data out over its AXI4-Stream RX interface[cite: 11]. Non-matching destination MAC addresses are filtered out immediately[cite: 11].
2. **IP/UDP Header Parse:** Fixed-offset validation of EtherType (0x0800), IP protocol (17), destination IP, and destination UDP port against compile-time constants[cite: 11]. The UDP checksum is bypassed because payload integrity on this single-segment point-to-point link is covered by the Ethernet FCS[cite: 11].
3. **Protocol Decode:** Executes real-time bit-slicing of the incoming custom payload directly into staging registers as bytes arrive[cite: 11].
4. **Commit gate:** On TEMAC's `tuser` frame-good signal at `tlast`, the staged event commits; on frame-bad, discard + `parse_error` increment (fault-handling path)[cite: 11].
5. **Order book update:** Aggregates the committed L3 event (keyed by `order_id`) into the affected side/level[cite: 11]. Extracting the new top-of-book occurs via combinational reduction, driving an atomic commit to the register bank and a single-cycle increment of the `seq` register[cite: 11].

#### 3.1.3.2 Packet formats (FS13 interface contract)

All market data and order messages within the intraday critical path are bound to a strict fixed-width protocol specification[cite: 11]. To minimize hardware design complexity and latency within the custom PL arithmetic blocks, the system enforces a strict integer cent assumption (`price_cents`) rather than utilizing sub-cent or floating-point precision units[cite: 11]. Integer field encoding avoids multi-cycle floating-point conversion logic, keeping parsing and book aggregation fully deterministic[cite: 11]. While standard equity price values map natively to integer cents, any incoming sub-cent prices from external feed simulations are systematically rounded half-to-even at the system ingress boundary and logged using localized diagnostic counters (`price_rounded`) to guarantee full data observability without degrading hardware cycle-time[cite: 11].

Table 3.1.3 serves as the protocol interface contract for incoming market updates, and Table 3.1.4 establishes the exact byte-level layout required for outbound order packet verification under FS13[cite: 11].

Table 3.1.3: Custom Market Data Payload Layout (RX Ingress Contract)
| Field | Bit offset | Width (bits) | Protocol Encoding & Meaning |
| :--- | :--- | :--- | :--- |
| **msg_type** | 0 | 8 | 0x01 = Add, 0x02 = Modify, 0x03 = Delete[cite: 11] |
| **symbol** | 8 | 16 | Numeric symbol identifier for single equity (constant = 1)[cite: 11] |
| **price** | 24 | 32 | Unsigned fixed-point integer representing cents[cite: 11] |
| **qty** | 56 | 32 | Unsigned share quantity; absolute volume for Modify commands[cite: 11] |
| **side** | 88 | 8 | 0x01 = Bid, 0x02 = Ask[cite: 11] |
| **order_id** | 96 | 32 | Unique transaction identifier within the simulator session[cite: 11] |
| **seq_num** | 128 | 32 | Monotonic sequence tracker for drop accounting (NFS2)[cite: 11] |
| **pad** | 160 | 32 | Reserved padding fields (hardcoded to 0x00)[cite: 11] |

Table 3.1.4: Custom Order Packet Payload Layout (TX Egress Spec / FS13 Contract)
| Field | Bit offset | Width (bits) | Protocol Encoding & Meaning |
| :--- | :--- | :--- | :--- |
| **order_id** | 0 | 32 | Client-assigned order identifier, echoed from the originating decision (FS14 tracking key)[cite: 11] |
| **symbol** | 32 | 16 | Numeric equity asset identifier (constant = 1, matches Table 3.1.3)[cite: 11] |
| **side** | 48 | 8 | 0x01 = Buy, 0x02 = Sell[cite: 11] |
| **qty** | 56 | 32 | RiskGuard-validated outbound order size[cite: 11] |
| **price** | 88 | 32 | Executable order price mapped to integer cents[cite: 11] |
| **pad** | 120 | 8 | Formatting padding field (hardcoded to 0x00)[cite: 11] |

#### 3.1.3.3 Order book register layout

Table 3.1.5: Order Book Register Sizing & Diagnostic Layout
| Register group | Entries | Fields per entry | Structural Purpose |
| :--- | :--- | :--- | :--- |
| **Bid book** | 10 | price_cents (32b), aggregate_qty (32b) | Tracks highest active bid levels[cite: 11] |
| **Ask book** | 10 | price_cents (32b), aggregate_qty (32b) | Tracks lowest active ask levels[cite: 11] |
| **Top-of-book snapshot** | 1 | best_bid_price, best_bid_qty, best_ask_price, best_ask_qty | Committed atomically to AXI-Lite register bank on every tick[cite: 11] |
| **Diagnostic counters** | 4+ | parse_error, fcs_fail, dropped_out_of_window, tx_backpressure | NFS2 / fault-path observability[cite: 11] |

#### 3.1.3.4 PS interface and transmission pipeline

The PS boundary is structured as a single AXI-Lite slave register bank on M_AXI_GP0[cite: 11]. Snapshot publication is executed via a one-clock-edge atomic commit of all snapshot registers plus the `seq` increment, removing the possibility of hardware-side tearing[cite: 11]. The multi-read consistency problem is handled on the PS side via a seqlock design pattern[cite: 11]. FS1's measurable endpoint is the `seq`-increment write enable, observable with an ILA[cite: 11].

The TX egress path operates as a four-stage pipeline[cite: 11]:
1. **Order-field write:** The PS writes the risk-approved order fields into the AXI-Lite register bank, payload first[cite: 11].
2. **Doorbell strobe:** The PS writes to the doorbell register last; the strobe itself launches the encode stage on the following cycle[cite: 11]. A `tx_ready` flag provides flow control[cite: 11].
3. **Protocol Encode:** Packs the sampled data fields into the Table 3.1.4 fixed-offset format[cite: 11].
4. **MAC TX (Xilinx TEMAC):** The vendor core frames the payload and transmits it over RGMII to the external PHY[cite: 11].

---

### 3.1.4 Specification Compliance Summary

Table 3.1.7: Subsystem Traceability and Core Specification Compliance
| Spec | How the final design satisfies it | Verification Metric | Status |
| :--- | :--- | :--- | :--- |
| **FS1** | Cut-through stream parsing completes custom book updates in 77 cycles, leaving a 32% margin under worst-case pipeline conditions[cite: 11]. | Logic-analyzer trace from MAC valid to register latch[cite: 11]. | **Y**[cite: 11] |
| **FS13** | Egress formatting matching Table 3.1.4 byte-offsets is hardcoded into sequential register arrays[cite: 11]. | Wireshark inspection of simulated order frame[cite: 11]. | **Y**[cite: 11] |
| **NFS1** | Hardware RX (0.61 μs) and TX (0.65 μs) path budgets consume less than 3% of the absolute system latency budget[cite: 11]. | Synchronized hardware timestamp capture loop[cite: 11]. | **Y**[cite: 11] |
| **NFS6** | Gate-level resource footprints map to approximately 11% of available fabric resources on the target device[cite: 11]. | Vivado post-implementation utilization summary report[cite: 11]. | **Y**[cite: 11] |
# 3.2 PS (ARM OS Layer) Strategy & Risk Subsystem

## 3.2.1 Overview and Specification Mapping

The PS subsystem is the software half of the intraday trading loop, on the dual-core ARM Cortex-A9 of the XC7Z020. Core 1, isolated from the Linux scheduler, busy-polls the PL's snapshot registers, evaluates the active strategy, filters proposed orders through the Runtime Risk Guard, and writes risk-approved orders back via the register bank and doorbell. Core 0 owns everything latency-tolerant: config loading (FS4), the Execution Logger and export (FS5), the Debug-UART feed (FS11), and HOLD-mode supervision.

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

**Interrupts are out.** Linux IRQ→userspace wakeup is taken as 10–40 μs — a working figure whose exact value the argument does not hang on: even the optimistic end consumes a third of the FS2 budget before any work happens, and the design case needs only that order of magnitude. This isn't just this project's estimate: Leber et al. trace interrupts' high latency to the context switch itself [1], Morris et al. poll a memory queue for the same reason [4], and Toshiba's production system polls FIFOs in hardware rather than using interrupts [8]. The replacement is busy-poll: core 1 is pulled out of the scheduler (`isolcpus`) and spins on new data instead.

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
| 0x20–0x2C | `DIAG_PARSE_ERR`, `DIAG_FCS_FAIL`, `DIAG_DROP_OOW`, `DIAG_TX_BACKPRESSURE` | R | Diagnostic counters (NFS2), read periodically by core 0 |
| 0x40–0x4C | `ORD_SYMBOL_SIDE`, `ORD_QTY`, `ORD_PRICE`, `ORD_ID` | W | Order fields (FS13 source values) — the block diagram's "Trade Decision" arrow. `ORD_SYMBOL_SIDE` packs `symbol` in bits [15:0] and `side` in bits [23:16] (bits [31:24] reserved = 0), matching their widths in Table 3.1.5. |
| 0x50 | `DOORBELL` | W | Write-1 launches the Order Emitter; **payload first, doorbell last** |
| 0x54 | `TX_READY` | R | Egress flow-control invariant (see 3.2.4.1) |

**Consistency and conflation.** PL commits are single-clock-edge atomic, so tearing can only happen on the PS side, where reading 4–6 registers spans ~1 μs across several AXI transactions; core 1 guards against it with a seqlock (read `SEQ`, read fields, re-read `SEQ`, retry on mismatch). Egress needs no lock — the PL samples order fields only on the doorbell strobe. The bank also holds only the latest snapshot: if ticks outrun the polling loop, intermediate snapshots are overwritten rather than queued, so the strategy always decides on the current book. This doesn't affect PL-side ingest — the PL still books every packet at line rate (3.1.4.1); conflation applies only to what the PS samples, and it is a consequence of keeping the strategy in PS software (Decision 1), not a general HFT norm — see the trade-off discussion in 3.2.4.1.

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

### 3.2.3.4 Config Loader (FS4)

At startup, before core 1 begins polling, the loader ingests the JSON configuration (either from the board's SD/TF card slot or via an `scp`/SSH push from the EOD server to a staging path, per 3.3.3.7), validates schema and ranges, and populates the strategy table and Risk Guard limits. Any validation failure is logged, and the polling loop is refused to start — never trade on a default. Market data processing is structurally unreachable until a config commits, which is FS4's verification argument.

### 3.2.3.5 Execution Logger and Console (FS5, FS11)

The logger is pure software: core 1 writes into a fixed, pre-allocated 256 MB ring in cached DDR3 (no malloc on the hot path, no OOM by construction); the PL isn't involved. A full per-tick log doesn't fit the budget (3.2.4.2), so the ring logs every decision/outcome record (rate capped by FS3's 1,000 orders/s) plus book snapshots sampled at 100 Hz and on every order event (working figures, pending a cited source). Core 0 handles everything off the hot path: draining the ring to eMMC continuously, the end-of-session export over PS GbE, periodic `DIAG_*` sampling into the log, and the FS11 console feed — a 1 Hz rendering of book top and recent decisions over Debug UART, reading the same ring at zero cost to core 1.

**Execution record schema (frozen — 128 B fixed).** One record per strategy decision, execution outcome, sampled snapshot, Risk Guard REJECT, or fault event, written by core 1 as a single fixed-size struct copy:

| Field | Offset (B) | Size (B) | Content |
|---|---|---|---|
| `record_type` | 0 | 1 | 0x01 DECISION, 0x02 OUTCOME, 0x03 SNAPSHOT, 0x04 REJECT, 0x05 FAULT |
| `decision` | 1 | 1 | 0x00 HOLD, 0x01 BUY, 0x02 SELL (0x00 for non-decision records) |
| `strategy_id` | 2 | 1 | Active strategy index (FS4 config) |
| `reason_code` | 3 | 1 | FS3 reject reason / fault code; 0 otherwise |
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
| NFS4 | Linux + isolated core, no hot-path allocation; HOLD Mode as safe state | Pending 6.5 h soak |

# 3.3 EOD Server Pipeline Subsystem

> **Scope note:** an earlier draft of this subsystem also carried a non-essential text/LLM-sentiment path (FS9/FS10), which has been dropped from scope (rationale in the Section 2 footnote). Stage names are *Parameter Engineering, Regime Detection, Strategy Reoptimize, Backtest & Parameter Sweep, Risk Analysis, Generate JSON Config, Operator Approval*.
> All numeric analysis in this section is derivable on paper today (dataset-size arithmetic, iteration-count budgets, complexity bounds, inequality proofs) — no code required. Quantitative analysis appears inline where each decision or design element needs it, not as a separate section.

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
| **NFS5 (non-ess.)** | Sole owner: full pipeline (ingestion → classification → optimization → approval prompt) within 30 minutes; input validation per 3.3.3.6. |

Upstream dependency: FS5's exported session history and a historical daily OHLCV dataset are the pipeline's inputs. The session history comes from sessions traded against 3.4's replay-based simulator, which carries tick-level (L3) event streams; it does not aggregate those streams into daily bars, so it is not the daily-OHLCV source. The daily OHLCV source is **Yahoo Finance** (free, no license required) — the same source already exercised in the preliminary validation run (3.3.3.3.1). Downstream contract: the JSON configuration schema of 3.3.3.5, consumed by the PS Config Loader — jointly owned with 3.2, exactly as the register bank table of 3.2.3.1 is jointly owned with 3.1.

Figure 3.4 shows the pipeline structure. *(Figure placeholder — reuse the SERVER subgraph of the system block diagram, minus the Console Monitor, which belongs to the PS peripheral group per the final subsystem split, and minus the External Resources / Web-News-Social block and its NLP/LLM Pipeline and sentiment arrows, dropped along with FS9/FS10 — see Section 2 footnote. The EOD→PS arrow should be annotated as the HOLD-latch/config-push path of 3.2.3.6 and 3.3.3.7, not as a generic link.)*

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

The pipeline is a sequential staged program; Figure 3.5 shows the stage graph with FS12 log points at every transition. *(Figure placeholder — stage flowchart: [Data Import & Validation] → [Parameter Engineering] → [Regime Detection] → [Strategy Reoptimize / Backtest & Parameter Sweep] → [Risk Analysis] → [Generate JSON Config] → [Operator Approval] → [Transmit / or REJECT→HOLD].)*

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

The procedures above were run end-to-end against real AAPL daily OHLCV (1984-09-07 to 2008-10-14, BSD-licensed public archive, fetched via raw.githubusercontent.com) as a preliminary check ahead of full implementation. This is a stand-in for the production source (Yahoo Finance, per 3.3.1) rather than a pull from Yahoo Finance itself; both are free daily-OHLCV sources with no license required, so the substitution does not change the data-access argument. This window predates and is unrelated to the LOBSTER anchor day (3.4.4.6); the two real-data checks in this report are independent by design — this one exercises the regime/sweep procedure on a full percentile-scheme-sized history, the other (3.4.4.6) exercises the tick-level protocol translation — and are not required to share a period.

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

> The block diagram labels this subsystem *"Exchange Simulator on Host (Live Order Book & Executor — 1 Exch / 1 Stock)"*; internal component names below are *LOBSTER Replay Driver, Book Mirror, Protocol Encoder, Order Executor (validate-and-log), Ground-Truth Logger*.
> **Spec baseline:** Section 2's FS14 (single-symbol), FS3 (four-limit), and FS2 (99th-percentile) already reflect the design below; fill semantics use option C2 (PS-side simulated fill latency), with C1 execution reports documented as a future extension.
> All measured figures in this section were produced on the development sandbox against the real LOBSTER AAPL sample dataset (3.4.4.5); pending a re-run on the target host before final submission.

---

## 3.4.1 Overview and Specification Mapping

The Exchange Simulator is the counterparty to everything built in 3.1–3.3: it plays the exchange that the project objective requires but deliberately does not connect to (Section 1.2's paper-trading boundary). It runs on the host PC, terminates the far end of the point-to-point Gigabit Ethernet link into the PL (both the outbound market-data feed and the inbound order-receive path), produces the market-data event stream by replaying a real order-level trading day in the custom protocol of Table 3.1.4, maintains its own mirror of the resulting order book, and receives, validates, and logs every order packet the SoC emits (Table 3.1.5).

**Positioning within the field.** Published end-to-end FPGA trading systems fall into a clear feasibility hierarchy defined by exchange access. At the top, Toshiba's two production systems ran live capital in the Tokyo Stock Exchange's JPX co-location facility [8], [9]; below them, Kao et al. connected to a real futures-broker test server for the Taiwan Futures Exchange, exercising genuine protocol handshakes without live capital [2]; at the laboratory tier, Boutros et al. validated their HLS pipeline by injecting UDP packets and capturing returned order packets in loopback [6], and Osuna et al.'s PYNQ-Z2 educational system replays market data from a host Python script [7]. AQTA belongs, by construction, to this laboratory tier: the co-location and broker-member access that define the upper tiers is unavailable to (and out of scope for) a capstone project. The design consequence is that this subsystem must supply, *by itself*, everything the upper tiers get from their environment — the market data, the counterparty, and the measurement fixture — which is why it is engineered as a first-class subsystem rather than a test script.

**Dual identity.** Functionally, the simulator is the *exchange*: without it, no market data exists and the system under design has nothing to trade against. Its more demanding identity, however, is as the project's principal *verification instrument*: nearly every remaining verification procedure in Section 2 — FS1's reference packet sequence, FS2's 1000-update measurement, FS13's captured-packet parse, NFS2's 10-minute frame count, NFS4's 6.5-hour session — names an input that only this subsystem can supply. A simulator that merely "produces plausible ticks" would satisfy the first identity and fail the second; the design therefore treats **reproducibility and ground-truth observability** as first-class requirements — and then gets market realism for free, because the stream it emits is a real trading day (Decision 1).

**Scope statement.** Two instrument roles carried by earlier drafts — scripted fault injection and line-rate stress generation — were dropped together with the NFS8/NFS9 acceptance specs they served (Section 2 note), and with them the synthetic order-flow generator and scenario engine that existed to provide them. What remains is deliberately minimal: a replay data path, a validate-and-log executor, and ground-truth logging — and every remaining Section 2 procedure is served by exactly these.

Unlike 3.1–3.3, this subsystem is the *sole owner* of few specifications — its ownership is instrumental:

| Spec | Simulator role |
|---|---|
| **FS1, FS2** | Instrument: emits the reference packet sequences these measurements are defined against — fixed, hash-named slices of the replay dataset; ground-truth log provides transmit-side timestamps. |
| **FS13** | Oracle: independently parses and validates every received order packet against the documented layout — a second implementation of the protocol spec, which is the strongest practical test of the spec document's completeness (a mechanism already vindicated during design — on the TX-side Table 3.1.4 rather than on Table 3.1.5 itself: see the Modify-semantics finding in 3.4.4.5; the live RX-side cross-parse remains pending). |
| **NFS2** | Peer: the other endpoint of the 10-minute zero-drop window; its TX count is the expected-frame denominator. |
| **NFS4** | Provider: replays the full 6.5-hour session the SoC must survive. |
| **FS6/FS7 (bootstrap)** | Data source: before any live sessions exist, the recorded replay session is the FS7 backtest bootstrap corpus (3.3.3.3's bootstrap case); regime classification draws on the daily-OHLCV source (Yahoo Finance, 3.3.1), not on simulator output. |
| **NFS3** | The simulator is pure software on the host PC, which NFS3 explicitly excludes from the cost cap — subsystem hardware cost is $0. |

Figure 3.6 shows the simulator's internal structure and its two link-level interfaces. *(Figure placeholder — component diagram: LOBSTER Replay Driver [translation layer + pacing clock] → [Book Mirror, Protocol Encoder → EventSink: UDP TX]; UDP RX → Order Executor → Ground-Truth Logger; all components writing to the Ground-Truth Logger.)*

---

## 3.4.2 Engineering Design Process

### Decision 1 — Market-data source: a four-iteration design history

This decision went through four documented iterations driven by successively discovered external constraints; each reversal is retained because the constraints, not preferences, did the deciding.

**Iteration 1 — broker paper-trading account as the exchange (initial concept, rejected).** The most "real" option available to the team: use a retail broker's simulated-trading environment (Interactive Brokers, Webull, Futu-class APIs) as the live counterparty, so the SoC trades real market data with fake money. Two structural mismatches killed it. (1) *Interface*: broker APIs are REST/WebSocket sessions to the broker's cloud, with latencies in the tens-of-milliseconds-to-seconds class — they cannot terminate our point-to-point PL GbE link or speak the FS13/Table-3.1.4 custom UDP protocol, so the entire PL path (the project's core) would be untestable against them. (2) *Reproducibility*: live market data is unrepeatable by definition; a failed FS2 run could never be re-run on identical input, and no measurement defined against a reference packet sequence (FS1/FS2) can even be specified.

**Iteration 2 — the granularity ceiling (real-data ambitions narrowed by evidence).** Rejecting the broker *interface* did not settle whether real market *data* could still drive the simulator. Investigating this surfaced a harder constraint: the custom protocol carries **L3 order-level events** (Add/Modify/Delete keyed by `order_id`, Table 3.1.4), but retail-tier APIs top out at **L2**. Interactive Brokers' own documentation defines its market-depth product as "level II," delivered as *aggregated price-level rows* (position/operation/price/size callbacks) with no order identifiers [10] — and depth subscriptions are per-venue paid market-data lines whose availability on paper accounts is itself conditional. The published record confirms this is a structural boundary, not a shopping failure: the one cited system that operated against genuine order-level exchange messaging below the co-location tier did so through a *futures-broker member test server* [2], and He et al.'s order-book-update work drew CFFEX message streams from the exchange's internal unified data bus — access mediated by an institutional research relationship, not a public endpoint [3]. No tier of the literature obtains L3 through a retail channel, because no retail channel carries it.

**Iteration 3 — real L3 exists after all, behind a price wall with a free crack (the LOBSTER discovery).** The academic market-microstructure community solved exactly this access problem a decade ago: LOBSTER reconstructs order-level limit-order-book data — every submission, cancellation, deletion, and execution, keyed by order ID — for the entire NASDAQ universe from Historical TotalView-ITCH files [11], and has served as the community's standard source since 2013. Full access is a paid academic subscription (published price list: £6,897/year [12]) — out of the question for a capstone. But LOBSTER publishes **free official sample files** [13]: one full trading day (2012-06-21) for AAPL, AMZN, GOOG, INTC, and MSFT at 1/5/10/30/50 book levels, each comprising a `message` file (time, type, order ID, size, price, direction — the L3 event stream itself) and a level-by-level `orderbook` snapshot file. One day of five symbols is a bounded corpus — but the prototype's needs are bounded to match (one exchange, one symbol, FS14), and the day is exactly sufficient for what the instrument identity needs from real data: a ground-truth check that the protocol and the translation semantics survive contact with a real order flow, and a full-length real session to replay. (The team notes, without needing it as evidence, that published FPGA order-book work has used this same sample day and ticker set — e.g., the MSFT 2012-06-21 dataset in [14].)

**Iteration 4 — final architecture: replay only, one driver.** The end state is a single **LOBSTER-replay driver**: the real AAPL sample day streams through a translation layer (3.4.4.5), the Protocol Encoder, and the UDP EventSink onto the link. Earlier drafts paired it with a seeded synthetic order-flow generator plus a scenario engine for scripted faults and bursts; those components existed to serve the NFS8/NFS9 injector roles and left the design when those specs were dropped (Section 2 note). Everything verification still needs from the data source, replay provides more cheaply:

| Property | How the replay driver provides it |
|---|---|
| Reproducibility | The dataset file's hash names the session: same file + same config ⇒ bit-identical byte stream (measured, 3.4.4.2). FS1/FS2 reference sequences are fixed slices of the day, cited by hash + slice bounds. |
| Realism | The stream *is* a real NASDAQ trading day — no statistical model to defend, no calibration to maintain. |
| Volume and shape | 400,391 messages over one complete 6.5 h session — exactly the session NFS4 requires and NFS2's 10-minute window slices from. |
| Rate control | A replay-clock scale factor (Decision 3), not a generator. |

This iteration history is also the origin of two protocol-level findings (sub-penny prices; Modify-semantics ambiguity) reported in 3.4.4.5 — discoveries that would not have occurred under Iteration 1's architecture and that alone justify the investigation's cost.

### Decision 2 — Execution model: full matching engine vs. validate-and-log executor under a no-impact assumption

| Alternative | Description | Outcome |
|---|---|---|
| Full price-time-priority matching engine | Received orders rest in the simulator's book, match against the replayed flow, and produce fills; our orders alter the market-data stream. | **Rejected for the prototype.** A matching engine is a substantial correct-by-construction artifact (price-time priority, partial fills, self-match handling) whose output — realistic fills and market impact — no Section 2 specification consumes. Under the C2 fill-semantics decision, fill timing is modeled PS-side; the simulator does not need to adjudicate fills at all. The cost would be large, the verification burden larger (the matching engine would itself need a test bench), and the marks zero. |
| Validate-and-log executor, no-impact assumption (selected) | Every received order packet is parsed against the FS13 layout, range-checked, timestamped, and logged; the replayed market-data stream is **not** altered by received orders. | **Selected.** This is exactly the FS13 oracle role: an independent second implementation of the protocol parse is the strongest practical check of the spec document (any ambiguity in Table 3.1.5 surfaces as a disagreement between the PL encoder and the simulator parser — at which point the *document* gets fixed, which is FS13's actual point; 3.4.4.5 records this second-implementation mechanism already firing once during design — on the TX-side Table 3.1.4 (Finding 2), with the Table 3.1.5 cross-parse itself pending live integration). The no-impact assumption is stated openly as a modeling boundary: with FS3 capping orders at 1,000 shares against a book quoting thousands of shares per level, self-impact would be second-order even if modeled.  |

**The closed-loop caution from the literature.** The survey of deployed systems is blunt about open-loop order emission: only the Toshiba production systems close the post-trade loop, pairing the FPGA's inline order path with CPU-side order confirmation and position-state management [8], [9] — because an exchange-facing device that fires orders without tracking their disposition carries unbounded exposure. AQTA's architecture already embodies this division: the PS-side Runtime Risk Guard and open-order table (3.2.3.3, amended FS3/FS14) are the CPU-side state machine, and the C2 fill model closes the loop in simulation. If fill semantics are later upgraded to C1, the executor gains exactly one behavior — emit a `msg_type 0x04` execution report over the same link after a configurable delay — without touching the replay driver or book mirror; the decision structure deliberately leaves that seam open.

### Decision 3 — Replay pacing: dataset-clock pacing vs. free-running emission

| Alternative | Description | Outcome |
|---|---|---|
| Free-running emission | Emit events as fast as the Python loop can push them. | **Rejected as the session mode.** It destroys the session's temporal shape — NFS4's 6.5-hour session collapses to seconds, open/close activity concentration disappears, and TX timestamps become meaningless for the FS2/NFS1 cross-checks. Retained as a smoke-test utility only. |
| **Dataset-clock pacing with a scale factor (selected)** | Each LOBSTER message carries its original NASDAQ timestamp; the replay scheduler emits at `session_start + (t_msg − t_open)/rate_scale`. | **Selected.** `rate_scale = 1` reproduces the real day for the NFS4/NFS2 runs; `rate_scale > 1` compresses idle stretches for development iterations. Pacing granularity is bounded by host timer resolution (~1 ms) — three orders of magnitude below the day's mean inter-arrival gap (~58 ms at 17.1 msg/s), so session-scale timing is faithful; inside the densest 100 ms bursts (sub-millisecond gaps) individual spacings are smeared by timer granularity while burst mass at the 100 ms scale is preserved. Acceptable because no remaining specification measures sub-millisecond inter-arrival fidelity. |

A pacing knob is all that remains of what earlier drafts spent two further decisions on (an offline/online rate split for line-rate stress generation, and a declarative scenario-file mechanism for scripted fault directives — both serving the dropped NFS8/NFS9 roles); the replay-only architecture reduces the simulator's control surface to one number and one dataset.

---

## 3.4.3 Final Design Details

### 3.4.3.1 Component structure and data flow

One Python process, five components, one thread on the hot path:

1. **LOBSTER Replay Driver** — loads the session config and owns the master event clock (Decision 3); streams the real message file through the translation layer of 3.4.4.5, after a book-priming step for pre-session orders; emits abstract L3 events that are always consistent with the Book Mirror's state (invariant I1, 3.4.4.3).
2. **Book Mirror** — applies each emitted event to the simulator's own copy of the book; this is the ground-truth book against which the PL's order-book construction (3.1) is verified.
3. **Protocol Encoder** — packs events into the Table 3.1.4 layout.
4. **EventSink (UDP TX)** — transmits the encoded stream over the point-to-point link.
5. **Order Executor (validate-and-log) + Ground-Truth Logger** — parses every received order packet against Table 3.1.5 (FS13 oracle) and appends it to the ground-truth log; the logger also records every transmitted event with a host timestamp.

### 3.4.3.2 Session configuration and ground-truth log

**Session config (JSON):** `{dataset_path, dataset_sha256, slice: [first_msg, last_msg] | full, rate_scale, symbol_id}`. The dataset hash *is* the session: same file + same config + same replayer version ⇒ bit-identical byte stream (measured, 3.4.4.2), so a session is *named* by its config file, and every verification run cites one — FS1/FS2 reference sequences are simply configs with fixed `slice` bounds.

**Ground-truth log (append-only, one line per event):** `{host_ts_ns, dir: TX, raw_bytes_hex, decoded_fields, book_top_after}` for TX; `{host_ts_ns, dir: RX, raw_bytes_hex, parse_result, fault_code?}` for RX. This log is the **golden reference** the other subsystems' logs are diffed against: the PL's book (via PS snapshots in the FS5 export) against `book_top_after`; PS decision timestamps against TX/RX host timestamps for the FS2/NFS1 cross-checks (single host clock covers both directions; Wireshark on the same NIC remains the primary instrument, the ground-truth log the redundant second witness). The full `raw_bytes_hex` output can be disabled for long runs, retaining only the parsed fields; at the real day's rates even full-mode logging is ≈ 48 MB per session (3.4.4.4), so this is a tidiness option rather than a storage necessity.

### 3.4.3.3 Link and host configuration

Host NIC directly cabled to the PL RJ45 (no switch — NFS2's "no unexplained drops" argument depends on this), static IP/MAC matching the PL's compile-time constants (3.1.3.1), UDP checksum emitted as zero (per 3.1.3.1's accept-zero decision — the PL parser ignores the field). The simulator host may be the same physical machine as the EOD server; however, they execute as strictly independent processes with zero intraday coupling. Wireshark/tcpdump capture on this NIC is the shared instrument for FS2/NFS1/NFS2 procedures.

---

## 3.4.4 Quantitative Technical Analysis

### 3.4.4.1 Session-mode rate capability — measured

Microbenchmarks on the development sandbox (Python 3, loopback socket, 20–24 B payloads; caveat: loopback ≠ real NIC path — order-of-magnitude evidence; confirmed via re-run on the final target host NIC) measured the full online emit path — event preparation + book-mirror update + `struct.pack` encode + UDP `sendto` — at **≈ 91 K events/s** sustained, single-threaded. Set against the *measured* profile of the real day (3.4.4.5: 17.1 msg/s session average, 584 msg/s peak second, 2,390 msg/s peak 100 ms burst equivalent), that is a **~38× margin over the worst real burst and ~5,000× over the session average**. Session-mode feasibility in plain Python is settled by arithmetic: no faster language, batching, or raw-socket work is needed at any rate this data source can produce.

### 3.4.4.2 Reproducibility — measured

Same-input reproducibility was checked directly rather than asserted: two full replay passes over the same dataset and config produce **byte-identical** output streams (verified during the 3.4.4.5 validation runs, 380,678 encoded events). The design conditions this rests on: single-threaded replay, integer arithmetic in the translation layer, and no wall-clock dependence in event *content* (host timestamps appear only in the ground-truth log, never in the byte stream); the input itself is pinned by the `dataset_sha256` field of the session config. Consequence chain: deterministic byte stream ⇒ deterministic PL book states ⇒ deterministic PS snapshot sequence ⇒ FS7's backtest bootstrap corpus is reproducible end-to-end from the dataset hash.

### 3.4.4.3 Replay correctness invariants (the simulator's own test plan)

The simulator is a verification instrument, so its own correctness needs an argument that does not circularly depend on the system under test. Three machine-checkable invariants, enforced in the replay driver and executor and asserted in tests (validated via full-dataset replays):

| Invariant | Statement | Why it matters downstream | Real-data status (3.4.4.5) |
|---|---|---|---|
| I1 — referential integrity | Every Modify/Delete references an `order_id` currently live in the Book Mirror | The PL book builder (3.1.3.1 stage 5) is entitled to assume well-formed L3 flow | Enforced by the translation layer; 2.09% of raw LOBSTER messages reference pre-session orders and are handled by book-priming (pre-loading the initial limit order book state before the session begins). |
| I2 — book non-negativity | No aggregate level quantity ever goes negative; no order's remaining quantity goes negative | Ground-truth `book_top_after` must be a valid book or the golden reference is worthless | **0 violations** across 400,391 real messages |
| I3 — encode/decode round-trip | `decode(encode(event)) == event` for the simulator's own encoder against its own Table-3.1.4 parser | The oracle property of Decision 2: self-round-trip is its base case | **0 failures** across 380,678 real encoded events |

### 3.4.4.4 Session data-volume arithmetic (NFS4 soak, log sizing)

```
6.5 h replayed session (the real day: 400,391 messages ≈ 17 msg/s average):
Ground-truth log, full mode (~120 B/line with hex):   400,391 × 120 B ≈ 48 MB/session
Ground-truth log, parsed-fields mode (~40 B/line):    400,391 × 40 B  ≈ 16 MB/session
Wire traffic: 400,391 × 90 B ≈ 36 MB over 6.5 h ≈ 0.012 Mbps average — link utilization ~0.001%;
NFS2/NFS4 stress the SoC's endurance, not the wire
```

Every figure is trivial on host disk — the NFS4 soak run can keep full-hex logging enabled throughout.

### 3.4.4.5 Real-data validation: LOBSTER replay through the protocol layer — measured

The full free-sample dataset — 400,391 real order-level messages, AAPL, one complete NASDAQ trading day (2012-06-21), top-10 book levels [13] — was run through a prototype of the replay driver's translation layer and the Table 3.1.4 encoder. This is a validation of the *protocol and translation semantics against real order flow*, executed at design time precisely so its findings could shape the design rather than audit it. Four results and two findings:

**Result 1 — real rate profile (supersedes all earlier estimates).** Session average **17.1 msg/s**; peak one-second rate **584 msg/s**; peak 100 ms burst **2,390 msg/s equivalent**. These figures replace the guessed rate estimates carried by earlier drafts and anchor the margins in 3.4.4.1. They also put the wire in perspective: the link's physical ceiling of 1.389 M pps (3.1.4.1) exceeds this real symbol's *peak burst* by ~580× — the PL's line-rate capability is engineering margin far beyond anything real single-symbol flow produces, context worth stating now that no stress specification exercises it.

**Result 2 — event-mix characterization.** Real composition: submissions 47.7%, full deletions 42.7%, visible executions 5.9%, hidden executions 2.8%, partial cancels 0.8%. This stands as the reference characterization of the replayed flow — and it corrects the working figures carried by earlier drafts (55/25/20), which were materially wrong about modify frequency: real flow is add/delete-dominated, and modifies are rare.

**Result 3 — field-width confirmation.** Max real `order_id` = 287,150,931 (u32: fits, 15× headroom); max size 15,000 shares (u32: trivial). Table 3.1.4's field widths survive contact with real data.

**Result 4 — translation throughput and invariants.** The Python translation layer (order-pool tracking + encode) processed the full day at **1.10 M msg/s** — the entire real session translates offline in 0.37 s, so replay preparation is never a cost. I2 and I3 passed with zero violations across the full dataset (table in 3.4.4.3).

**Finding 1 — sub-penny prices break the integer-cents assumption (protocol change required or policy needed).** 372 of 400,391 real events (0.09%) carry prices that are *not* whole cents (LOBSTER prices are dollars ×10⁴; these events have a nonzero residue mod 100 — sub-penny executions/price-improvement prints). The Table 3.1.4 `price` field is specified in integer cents, so these events cannot be represented exactly. **Design decision:** the integer-cents commitment is retained (zero protocol change), preserving the deterministic parity chain across the PL and PS. Sub-penny prices are rounded half-to-even to the nearest cent — 0.09% of events carry ≤ $0.005 error — and a `price_rounded` diagnostic counter records every occurrence so the approximation stays observable.

**Finding 2 — the Modify-semantics ambiguity (the FS13 oracle mechanism fired at design time).** Writing the translation forced a question Table 3.1.4 does not answer: does a Modify's `qty` field carry the *new absolute* quantity or a *delta*? LOBSTER's partial-cancel and execution events carry deltas; the translation had to pick a convention (absolute remaining quantity was chosen) and the PL book-update stage must agree or the books diverge silently. This is precisely Decision 2's claim — that an independent second implementation is the strongest test of the protocol document — vindicated before any hardware exists: the ambiguity is now a required amendment to Table 3.1.4's field description rather than a future integration bug. **Design decision:** Table 3.1.4's field description is amended to define `qty` as the order's new absolute remaining quantity, allowing the PL book-update stage to remain stateless with respect to order deltas.

**Honest scope statement.** This validation exercises the translation layer and encoder on the development sandbox; it does not exercise the physical link, the PL parser, or timing (those are the Section 2 procedures, which remain pending). One symbol-day is a semantic ground-truth check, not a statistical study; the mix and rate figures above are one liquid large-cap's behavior on one 2012 day and are used as *characterization anchors*, not as claims about markets in general. That single day is also the prototype's entire market-data corpus — a deliberate scope bound stated in 3.4.1, not a hidden limitation.

---

## 3.4.5 Specification Compliance / Instrumentation Summary

| Spec | What the simulator provides | Evidence status |
|---|---|---|
| FS1/FS2 (instrument) | Fixed replay slices as reference sequences (cited by dataset hash + slice bounds, 3.4.3.2); TX-side ground-truth timestamps | Design complete; pending slice-config authoring |
| FS13 (oracle) | Independent parse of every order packet; disagreements surface spec ambiguities | Mechanism validated at design time (Finding 2 — TX-side analog on Table 3.1.4); pending live RX-side cross-parse |
| NFS2 (peer) | Direct-cabled link peer; TX frame counts as expected-delivery denominator | Pending 10-min counted run |
| NFS4 (provider) | 6.5 h real-day replay at `rate_scale = 1`; full-mode logging ≈ 48 MB (3.4.4.4) | Pending soak run |
| FS6/FS7 (bootstrap) | The recorded replay session as the FS7 bootstrap corpus (3.3.3.3); regime path draws on Yahoo daily OHLCV (3.3.1), not simulator output | Real-data translation validated (3.4.4.5); recorded session pending |
| Own correctness | Invariants I1–I3; reproducibility (measured); rate margin (measured); real-data validation (measured, full dataset) | Sandbox-measured; target-host re-runs pending |

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

[16] Xilinx, "Tri-Mode Ethernet MAC v9.0 LogiCORE IP Product Guide," PG051, Advanced Micro Devices, Inc. [Online]. Available: https://docs.amd.com/r/en-US/pg051-tri-mode-eth-mac [Accessed: Jul. 10, 2026].

[17] 正点原子 (ALIENTEK), "领航者 ZYNQ 之嵌入式开发指南 / Navigator ZYNQ-7020 Development Board User Manual (XC7Z020CLG400-2I)," Guangzhou Xingyi Electronic Technology Co., Ltd. [Online]. Available: http://www.openedv.com/docs/boards/fpga/zdyz_linhanzhe.html [Accessed: Jul. 10, 2026].

### Further reading (uncited in this document)

- D. H. Bailey, J. M. Borwein, M. López de Prado, and Q. J. Zhu, "The Probability of Backtest Overfitting," *Journal of Computational Finance*, vol. 20, no. 4, pp. 39–69, 2017, doi: 10.21314/JCF.2016.322.
- FIX Trading Community, "FIX Adapted for STreaming (FAST) Specification." [Online]. Available: https://www.fixtrading.org/standards/fast-online/ [Accessed: Jul. 9, 2026].
- J. Zang, "quant-engine: a C++ quantitative backtest and research engine," independent project documentation. [Online]. Available: https://qe.jiucheng-zang.ca [Accessed: Jul. 2026].

`[TEAM: bibliography housekeeping — (i) confirm the Toshiba entries' actual venues (both appear to be published papers; locate DOI/venue before submission); (ii) confirm the citation style guide for online resources; (iii) Hamilton 1989 is now in the list as [15]; Bailey et al. 2017 (backtest overfitting) moved to Further Reading since the grid-vs-Bayesian comparison it supported was cut; FinBERT/Araci and Loughran-McDonald were removed with the FS9/FS10 text-sentiment path (Section 2 footnote). TradingAgents 2024/2412.20138 remains a pending citation, to be appended if and when actually cited.]`
