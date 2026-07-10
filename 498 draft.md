# 1. Introduction

## 1.1 Motivation

Algorithmic trading systems are strongly constrained by end-to-end event latency: market data must be decoded, converted into a usable order book state, evaluated by a strategy, checked for risk, and converted into an order message before the opportunity disappears. A software-only implementation running on a general-purpose Linux host incurs kernel network stack and scheduler overhead before any strategy logic executes; published FPGA-based trading systems quantify this cost directly — a hardware datapath has been shown to achieve roughly a 4x latency reduction over a conventional software-based pipeline [1], and specialized hardware implementations report sub-microsecond response, with one 10 Gigabit Ethernet FPGA trading system achieving approximately 433 nanoseconds from market packet analysis to order trigger [2]. The current AQTA design therefore treats latency elimination as the central design problem rather than as a late-stage optimization.

AQTA addresses this by adopting a hardware-software co-designed architecture: the time-critical, deterministic portions of the pipeline — packet decoding and order-book maintenance — are implemented directly in programmable logic, while strategy evaluation, logging, and overnight reconfiguration remain in software for flexibility. This division follows the same rationale used throughout the FPGA trading literature cited above: push fixed, latency-critical operations into hardware, and keep the parts that need to change often in software.

## 1.2 Project Objective

The objective of this project is to design a hardware-software co-designed trading accelerator that processes simulated market data, maintains a real-time order book, selects and applies a validated trading decision, and emits a corresponding order within a bounded latency budget, while supporting operator-approved overnight strategy reconfiguration.

The essential prototype performs market-data ingestion, protocol decoding, and order-book maintenance in programmable logic (PL) to keep the time-critical path deterministic; passes the resulting order-book state to a configurable strategy running on the ARM processing system (PS), which selects among several pre-loaded strategies and applies a RiskGuard filter; and returns the validated decision to the PL, where it is encoded and transmitted back onto the exchange link.

The secondary objective is an End-of-Day (EOD) optimization pipeline that classifies the next trading day's market regime from historical data, searches a bounded parameter space to select a strategy configuration for that regime, and backtests the selected configuration before presenting it to a human operator for approval; only an approved configuration is loaded into the live system for the next trading session.

The prototype scope is intentionally bounded to one simulated exchange and one equity symbol, which keeps the project focused on the engineering problem of deterministic hardware/software partitioning while avoiding real-money financial risk and the complexity of multi-venue market-data normalization. Rather than implementing an industry-standard compressed protocol such as FAST, the prototype defines a fixed-width binary custom protocol for market data and order messages; this narrows the scope of the PL-side protocol decoder to a fixed, minimal field set and keeps decoding latency low, at the cost of interoperability with real exchange feeds. The prototype is restricted to paper trading and simulation: it does not place live orders and does not connect autonomous strategy decisions directly to a real-money account.

### 1.3 Block Diagram (Deprecated, only for reference)

---
config:
 layout: elk
---
flowchart TB
 subgraph PL["PL (FPGA)"]
 direction TB
 MAC["MAC Layer\n(Hardcoded ARP/MAC, P2P Link)"]
 IPUDP_RX["IP/UDP Header Parse"]
 DECODE["Protocol Decode"]
 BOOK["Build Order Book\n(L3 to L1/L2)"]
 ENCODE["Protocol Encode"]
 IPUDP_TX["IP/UDP Header Encode"]

 MAC --> IPUDP_RX --> DECODE --> BOOK
 ENCODE --> IPUDP_TX --> MAC
 end

 subgraph PS["PS (ARM OS Layer)"]
 direction TB
 DRV["Real-Time DMA Driver (deprecated)"]
 STRAT["Strategy Engine\n(3 Regimes / 3 Strategies)"]
 RISK["RiskGuard Filter"]
 HIST[("Local History Store\n(Shared DDR3 Buffer)")]

 DRV --> STRAT --> RISK --> HIST
 end

 subgraph SOC["SoC Board (Zynq-7000 / XC7Z020)"]
 PL
 PS
 end

 subgraph SERVER["EOD Server Pipeline"]
 direction TB
 CONSOLE["Console Monitor\n& Saved Logs"]

 subgraph PATH_MD["Market Data Path"]
 PE["Parameter Engineering"]
 REGIME["Regime Detection"]
 SELECT["Strategy Reoptimize"]
 PE --> REGIME --> SELECT
 end

 subgraph PATH_TXT["Text & Sentiment Path"]
 LLM["LLM Agent"]
 SENT["Sentiment Analysis"]
 LLM --> SENT
 end

 BACKTEST["Backtest & Parameter Sweep"]
 RANALYSIS["Risk Analysis"]
 CONFIG["Generate JSON Configs"]
 APPROVE{"Operator\nApproval"}

 PATH_MD --> BACKTEST
 PATH_TXT --> BACKTEST
 BACKTEST --> RANALYSIS --> CONFIG --> APPROVE
 end

 SIM["Exchange Simulator on Host\n(Live Order Book & Executor — 1 Exch / 1 Stock)"] -->|"1. PL GbE (RJ45): Custom L3 UDP"| MAC
 MAC -->|"4. PL GbE (RJ45): Custom UDP"| SIM

 BOOK -->|"2. AXI-Lite Register Bank (M_AXI_GP0): Top-of-Book"| DRV
 RISK -->|"3. AXI-Lite Register Bank (M_AXI_GP0): Validated Fields"| ENCODE

 HIST -->|"5. Debug UART: Console Log"| CONSOLE
 HIST -->|"6. PS GbE: Post-Trade EOD Log Export"| PE

 WEB["Web Sources: Fin News, Social Media,\n& Financial/Research Reports (Optional)"] -->|"7. HTTPS Ingestion"| LLM
 APPROVE -.->|"8. PS GbE: JSON Config Load"| DRV

## 2. System Specifications

### 2.1 Functional Specifications

| ID | Specification | Essential |
| --- | --- | --- |
| **FS1** | Upon receipt of a market data packet at the PL Gigabit Ethernet interface, the system must decode the packet and make an updated top-of-book snapshot **readable by the PS** within ≤ 1.1 μs of packet arrival. **Verifiable by:** ILA/logic analyzer measurement from MAC RX valid to **the PL snapshot-register write (`seq` increment)**, using a reference packet sequence. | **Y** |
| **FS2** | Upon a top-of-book update becoming visible to the PS, the system must produce a trading decision (BUY / SELL / HOLD) using one of three pre-loaded strategies, and transmit a corresponding order packet via the PL Gigabit Ethernet interface within ≤ 26 μs of the update becoming visible, evaluated at the 99th percentile. The selected design (busy-poll on an isolated core, 3.2 Decision 3) eliminates OS scheduling jitter on the hot path; NFS1's 300 μs worst-case ceiling applies only to the superseded interrupt-based design. **Verifiable by:** measuring elapsed time from PS observation of a new `seq` (PMU cycle counter) to MAC TX packet capture (Wireshark) across 1000 consecutive observed updates on the designated reference setup, verifying that the 99th percentile does not exceed 26 μs, and verifying order field encoding matches the protocol specification. | **Y** |
| **FS3** | The system must reject any order violating at least one of the following limits, each configurable via FS4, with the values below acting as hard ceilings that a loaded configuration may tighten but never exceed: (a) notional value > $50,000 CAD; (b) position size > 1,000 shares; (c) order submission rate > 1,000 orders/second; (d) in-flight (submitted but not yet terminal) orders > 100. **Verifiable by:** submitting one test order violating each of the four constraints individually and confirming a REJECT response with a logged reason code. | **Y** |
| **FS4** | At system startup, the system must load an externally-supplied strategy configuration — specifying the active strategy and its parameters — before processing any market data. **Verifiable by:** modifying the configuration source, restarting the system, and confirming via system log that the correct strategy and parameters are active. | **Y** |
| **FS5** | The system must continuously persist trading activity (strategy decisions, execution outcomes, order book snapshots) within a bounded memory budget, without triggering an out-of-memory condition during sustained high-frequency operation, and must be able to export this history for offline use. **Verifiable by:** stress-testing with > 10 million injected ticks and confirming static memory usage with no OOM exceptions; confirming a full session's history is successfully exported and contains one entry per decision. | **Y** |
| **FS6** | Given a history of daily market data, the system must classify the next trading day's market regime into one of at least three distinguishable states. **Verifiable by:** running the classifier on 6 months of historical OHLCV data for a single equity and confirming at least 3 distinct regimes are assigned across the period. | **Y** |
| **FS7** | Given a classified regime, the system must search a parameter space of at least 9 combinations for the corresponding strategy and select the combination that maximizes a defined performance metric (e.g., Sharpe ratio) over a recent trailing window. **Verifiable by:** running the optimizer twice on the same designated reference host with identical input data and confirming deterministic (bit-identical) output. | **Y** |
| **FS8** | A newly generated strategy configuration must not be loaded into the live trading system until it has been explicitly approved by a human operator. **Verifiable by:** confirming that the configuration is not transmitted to the SoC until a manual approval action is taken. | **Y** |
| **FS9** | The system should ingest unstructured text data (≥ 10 text assets/day, comprising financial news, social media streams, and optional financial/research reports) via HTTPS from designated web sources, and extract a structured event record (headline, entity/ticker mentioned, timestamp, source) from each asset for downstream sentiment scoring. **Verifiable by:** mocking a web server with standard news feeds and PDF financial reports, and verifying successful ingestion and correct structured-event extraction for each asset. | **N** |
| **FS10** | The system must compute a normalized sentiment score in [−1, +1] from each structured event record, and use this scored payload to adjust next-day position limits, where adjustment may only reduce limits below their configured baseline: negative sentiment tightens; neutral or positive sentiment leaves limits unchanged. **Verifiable by:** running the stage on a reference set of pre-labeled event records and confirming computed scores fall within [−1, +1] with correct polarity, confirming position-limit reduction occurs for negative-polarity records, and confirming no adjustment occurs for neutral or positive records. | **N** |
| **FS11** | During the trading session, the system should output a real-time report of current order book state and recent trading decisions via Debug UART; the server host software must print this to the console and save it to a local log file. **Verifiable by:** confirming output is received, displayed, and written to disk at the server console during an active simulated session. | **N** |
| **FS12** | During EOD pipeline execution, the system must display and log the current pipeline stage, the classified regime, the selected strategy and swept parameters, the backtest Sharpe ratio, and the operator approval status, updated as each stage completes. **Verifiable by:** running a full EOD pipeline cycle and confirming the console output and saved log contain one entry per pipeline stage transition, including the final approval status. | **N** |
| **FS13** | The order packet transmitted via the PL Gigabit Ethernet interface must conform to a fixed-length binary format specifying, at minimum: order ID, symbol identifier, side (BUY/SELL), quantity, price, and a checksum field. This format must be documented as a standalone protocol specification referenced by FS2's verification procedure. **Verifiable by:** parsing a captured order packet against the documented field layout and confirming byte-offset and length correctness for each field. | **Y** |
| **FS14** | The system must track the state of every in-flight (submitted but not yet terminal) order for the traded symbol, supporting up to 100 concurrent in-flight orders (configurable via FS4, with 100 as the default and hard ceiling per FS3(d)), without data corruption or dropped state. **Verifiable by:** injecting simulated order flow that drives the in-flight count to the configured limit and confirming, via post-run log inspection, that per-order state remains correct and no orders are lost or duplicated. | **Y** |

### 2.2 Non-Functional Specifications

| ID | Specification | Essential |
| --- | --- | --- |
| **NFS1** | Total system latency from market data packet arrival (PL MAC RX) to corresponding order packet transmission (PL MAC TX) must not exceed 50 μs typical, with a hard ceiling of 300 μs under the superseded interrupt-based design (the selected busy-poll design eliminates OS scheduling jitter on the hot path, making the 300 μs ceiling a historical bound, not an active requirement). **Verifiable by:** logic analyzer measurement of MAC RX to MAC TX interval on a reference loopback test packet. | **Y** |
| **NFS2** | The Ethernet link between the PL and the exchange simulator must sustain a 10-minute continuous test window with zero unexplained frame drops. **Verifiable by:** Wireshark capture over a 10-minute test window, confirming frame delivery matches expected count. | **Y** |
| **NFS3** | Physical hardware components (excluding the Zynq-7000 SoC development board, host PC, and monitors) must not exceed $1,000 CAD in total cost. **Verifiable by:** summing itemized purchase receipts for all acquired components. | **Y** |
| **NFS4** | The system must operate continuously through a full simulated trading session (6.5 hours, 09:30–16:00 ET) without a crash, hang, or unrecovered error requiring manual restart. **Verifiable by:** running the exchange simulator for a full session duration and inspecting system logs for fatal errors. | **Y** |
| **NFS5** | The full EOD pipeline (data ingestion → regime classification → parameter optimization → human approval prompt) must complete within 30 minutes of receiving end-of-day data. **Verifiable by:** timing the pipeline on a reference dataset of 1 year of daily OHLCV data for a single equity. | **N** |
| **NFS6** | The FPGA PL implementation must utilize fewer than 75% of available LUTs on the XC7Z020 device, and fewer than 85% of available Block RAMs, to ensure timing closure at 125 MHz. **Verifiable by:** Vivado post-implementation utilization and timing summary reports showing WNS > 0 ns at 125 MHz. | **Y** |
| **NFS8** | Upon detecting a recoverable fault — including but not limited to: a market data packet failing checksum validation, a receive FIFO overflow condition, or a strategy configuration failing validation at load time — the system must discard/reject the offending input, log a timestamped error record with a fault code, and continue normal operation without requiring a manual restart. **Verifiable by:** individually injecting each fault type (corrupted checksum packet, sustained burst exceeding FIFO depth, malformed config file) and confirming the system logs the corresponding fault code, discards the bad input, and resumes processing subsequent valid inputs within **≤ 96 ns (the Ethernet inter-packet gap)** for PL hardware faults, or immediately upon the next polling cycle for PS faults. | **Y** |
| **NFS9** | **Market Data Ingest Throughput** The FPGA PL data pipeline must sustain a peak market data ingestion and processing rate of ≥ 1.2 million messages per second (msg/s), matching or exceeding the theoretical maximum packet rate of the Gigabit Ethernet link (full wire-speed). The system must process micro-bursts at line rate without dropping packets or stalling the MAC RX buffer. **Verifiable by:** injecting a synthesized PCAP file containing FAST UDP packets at full 1 Gbps line rate using a packet generator, and confirming zero dropped packets via MAC/FPGA drop counters. *(Lit basis: FPGA book builders at 1.2–1.5M msg/s [3]; hardware feed processing reported at multi-M msg/s on faster links where line-rate is no longer the limiter [4].)* | **Y** |


# 3.1 PL (FPGA) Market Data Path Subsystem

> **Template conventions:**
> `[TEAM: …]` = requires a team decision or board-level confirmation.
> `OPEN: …` = a claim that is currently an analytical design target and must be replaced or confirmed by simulation/synthesis/measurement before the final report.
> `[REF-n]` = citation placeholder; map to the bibliography.
> All numeric analysis in 3.1.4 is derivable on paper today (line-rate arithmetic, cycle budgets, datasheet resource math) — no code required.

---

## 3.1.1 Overview and Specification Mapping

The PL subsystem implements the entire wire-to-snapshot market data path and the order egress path in programmable logic on the XC7Z020. On the receive side, it terminates the point-to-point Gigabit Ethernet link from the exchange simulator, validates and parses each custom UDP market data packet at fixed byte offsets, maintains a 10-level bid / 10-level ask limit order book (an L3-to-L1/L2 aggregation), and publishes the resulting top-of-book snapshot to the PS through an AXI-Lite register bank on M_AXI_GP0 (snapshot fields plus an incrementing `seq` register, committed atomically in one clock edge). On the transmit side, it receives risk-validated order fields written by the PS into the same register bank, begins encoding on the doorbell-register write strobe, encodes them into the fixed-length binary order format defined by FS13, and transmits them through the same PL GbE interface.

The subsystem exists because the software network path cannot meet the project's latency specifications: a conventional Linux socket path incurs interrupt handling, kernel protocol stack traversal, and kernel-to-user copies that together cost tens to hundreds of microseconds per packet, which is incompatible with the ≤ 1.1 μs decode budget of FS1. Placing the parse and book-build stages in the PL removes the operating system from the market-data critical path entirely.

This subsystem is directly responsible for the following specifications:

| Spec | Role of PL subsystem |
|---|---|
| **FS1** | Sole owner: packet arrival → decoded top-of-book snapshot available to PS in ≤ 1.1 μs. |
| **FS13** | Sole owner of the egress half: order packets must conform to the fixed-length binary format. |
| **NFS1** | Owns the two PL segments (RX decode, TX encode) of the ≤ 50 μs end-to-end budget (300 μs ceiling applies to the superseded interrupt design). |
| **NFS2** | Owns link integrity: zero unexplained frame drops over a 10-minute window. |
| **NFS6** | Owns the resource envelope: < 75% LUT, < 85% BRAM at 125 MHz with WNS > 0. |
| **NFS9** | Owns ingest throughput: ≥ 1.2 M msg/s sustained at line rate without MAC RX stall. |
| **NFS8 (partial)** | Owns the hardware fault path: checksum-fail discard and FIFO-overflow handling with fault counters. |

Figure 3.1 shows the PL block structure and the shared AXI-Lite register bank at the PS boundary. *(Figure placeholder — reuse the PL subgraph of the system block diagram; stage names below must match the block labels`[TEAM: unify naming — the latest diagram uses "Market Data Packet Parser / Market Feature Builder / Order Emitter"; this section currently uses "Protocol Decode / Build Order Book / Protocol Encode". Pick one vocabulary for both.]`.)*

---

## 3.1.2 Engineering Design Process

Four significant design decisions shaped this subsystem. Each is presented with the alternatives considered and the rationale for the selection; where the rationale is quantitative, the supporting calculation appears in Section 3.1.4.

### Decision 1 — Network path placement: PS socket, PS-DMA-then-parse, or full PL path

| Alternative | Description | Outcome |
|---|---|---|
| A. PS socket parsing | Receive UDP through the PS hardened GEM MAC and Linux sockets; parse in user space. | **Rejected.** Kernel networking and scheduler jitter are incompatible with FS1 (≤ 1.1 μs) and consume most of the NFS1 worst-case budget before any useful work occurs. |
| B. PS GEM + post-DMA parse | Let the PS GEM MAC receive frames, DMA raw frames to DDR3, then parse in PL or PS. | **Rejected.** The Zynq GEM controller is a PS hard block: even with EMIO pin routing, every frame still traverses PS memory before the PL can observe it, adding one full DDR3 round trip and defeating the purpose of hardware parsing. EMIO relocates pins, not the MAC. |
| C. Full PL path (selected) | Terminate the PHY on a PL I/O bank and implement MAC, parse, and book entirely in fabric. | **Selected.** The event is decoded before the PS ever observes it; latency is deterministic and clock-cycle countable. |

Alternative C is only feasible because the selected carrier board exposes a dedicated **PL-side Gigabit Ethernet (RJ45)** in addition to the PS-side Ethernet — this was a primary board-selection criterion (the sibling board “启明星” exposes only the PS-side PHY and cannot implement Alternative C at all, while “领航者” includes 1× PS GbE + 1× PL GbE). The target board for this report is the 正点原子领航者 ZYNQ7020 开发板 (XC7Z020CLG400-2I); the board reference manual is the authoritative source for the PL Ethernet PHY wiring (REF-3). This decision also constrained the device choice: the PL path plus PS-interface infrastructure must fit NFS6's resource envelope, which motivated the XC7Z020 (53,200 LUTs) over the XC7Z010 (17,600 LUTs) — see Table 3.1.7.

### Decision 2 — MAC layer implementation: vendor IP, open-source stack, or minimal custom MAC

| Criterion (weight) | Xilinx TEMAC IP | Open-source full stack (e.g., verilog-ethernet) | Minimal custom MAC (selected) |
|---|---|---|---|
| Latency determinism (35%) | Medium — general-purpose buffering | Medium-high | High — no unused feature logic in path |
| Resource cost (25%) | High (multi-thousand LUT + license terms) | Medium | Low — RX/TX framing + CRC only |
| Verification burden, given team capability (25%) | Low (pre-verified) | Medium (must verify integration) | Medium — small surface, fully testable with directed + constrained-random testbenches |
| Protocol generality (15%) | High | High | Low — sufficient (see below) |
| **Weighted result (1–5 scale)** | 3.55 | 3.65 | **4.05 — Selected** |

The generality that vendor and open-source MACs provide — address learning, ARP resolution, multi-node arbitration — is dead weight in this system, because the physical link is a two-node point-to-point segment with one fixed peer. Both endpoints' MAC and IP addresses are compile-time constants, so ARP is replaced by hardcoded address matching, and the MAC reduces to preamble/SFD detection, frame delimiting, and FCS (CRC-32) checking on RX, plus framing and FCS generation on TX. Removing dynamic address resolution eliminates an entire class of state machines from the timing-critical path and from the verification plan. (Scoring: each criterion rated 1–5 per row — cost-type criteria score higher when the cost is lower — then weighted; TEMAC = 0.35×3 + 0.25×2 + 0.25×5 + 0.15×5 = 3.55, open-source = 0.35×4 + 0.25×3 + 0.25×3 + 0.15×5 = 3.65, custom = 0.35×5 + 0.25×5 + 0.25×3 + 0.15×2 = 4.05. The weights encode our priorities — latency > resources ≈ verifiability > generality — and the custom MAC wins on the two heaviest criteria while losing only on generality, which the point-to-point link makes worthless.)

### Decision 3 — Parse architecture: store-and-forward vs. cut-through streaming parse

A store-and-forward design buffers the complete frame, verifies FCS, then parses. A cut-through design slices fields at their fixed byte offsets as bytes stream in from the MAC, so all fields are already latched when the final FCS byte arrives.

The quantitative case (full derivation in 3.1.4.2): at GMII rates the frame body alone occupies ~560 ns of the 1,100 ns FS1 budget. Store-and-forward would serialize an additional walk over the buffered frame after reception — a second traversal the budget cannot afford — whereas cut-through leaves the entire post-frame budget (~475 ns ≈ 59 cycles) for book update and snapshot commit. Cut-through is only safe because the packet format (Table 3.1.4) has fixed offsets: no length-dependent field positions exist, so slicing requires no lookahead. This is the same property that drove the format decision in Section 2: fixed-offset binary message layouts are an established market-data protocol class (NASDAQ ITCH-family feeds use fixed-length binary messages `[TEAM: confirm feed + cite the ITCH spec]`), and cut-through applies to that class; variable-length FAST-class encodings (presence maps, stop-bit fields) instead require stateful sequential decoding and framing/length handling that aggravates decoding complexity [1].

**Commit policy.** Cut-through creates one hazard: fields are latched before FCS validates the frame. The design therefore stages the parsed event in a holding register and commits it to the order book only on FCS pass; on FCS fail the event is discarded and a `parse_error` counter increments (NFS8 path). This costs one cycle of commit latency and zero throughput, versus the alternative of speculative book update with rollback, which was rejected because rollback of an aggregated price level requires storing pre-update state for every level touched — added area and a new failure mode for negligible latency gain.

### Decision 4 — Order book storage: BRAM-indexed structure vs. fixed register array

| Alternative | Description | Outcome |
|---|---|---|
| BRAM price-indexed table | Hash or direct-index price levels into Block RAM; scales to deep books and multiple symbols. | **Rejected for the prototype.** BRAM imposes synchronous 1-cycle read latency, making every book update a ≥ 2-cycle read-modify-write with pipeline hazard handling between back-to-back updates to the same level. Depth beyond 10 levels is not required by any specification for the single-equity scope. |
| Fixed register array (selected) | 10 bid + 10 ask levels as flip-flop registers; combinational best-price selection. | **Selected.** Single-cycle read of any level, single-cycle update, no read-after-write hazards, and a trivially verifiable datapath. Resource cost is bounded and small (3.1.4.3). |

Updates addressing a price level outside the 10-level working window are discarded and counted (`dropped_out_of_window`) rather than triggering structural growth in the critical path; the diagnostic counter makes the discard observable during verification without altering trading behaviour. This register-vs-BRAM trade aligns with published FPGA order book designs noting BRAM's synchronous access latency and the resulting read-after-write hazard handling on back-to-back updates [5]. `[TEAM: confirm discard vs. compress vs. resync policy — currently specified as discard-and-count.]`

FS14 (rev.) fixes the single-symbol scope, closing this forward dependency: the register-array choice is final for the prototype.

---

## 3.1.3 Final Design Details

### 3.1.3.1 Receive pipeline

The RX path is a five-stage streaming pipeline at 125 MHz (Figure 3.2 — *placeholder: per-stage pipeline diagram with cycle annotations*):

1. **MAC RX.** RGMII DDR capture from the PHY, preamble/SFD alignment, destination-MAC match against the hardcoded constant, FCS accumulation. Non-matching frames are dropped at this stage without downstream activity.
2. **IP/UDP header parse.** Fixed-offset validation of EtherType (0x0800), IP protocol (17), destination IP, and destination UDP port — all compile-time constants of the point-to-point link. IP header checksum is verified; the UDP checksum is not validated — the simulator emits UDP checksum = 0 (legal for IPv4 per RFC 768: zero means "no checksum") and the parser ignores the field, because payload integrity on this single-segment point-to-point link is already covered end-to-end by the Ethernet FCS (commit gate, stage 4).
3. **Protocol decode.** Field slicing of the custom payload (Table 3.1.4) into a staged event register as bytes arrive.
4. **Commit gate.** On FCS pass, the staged event commits; on fail, discard + `parse_error` increment (NFS8).
5. **Order book update.** Aggregation of the committed L3 event (Add/Modify/Delete keyed by `order_id`) into the affected side/level; for Modify, `qty` is the new absolute remaining quantity (not a delta), and for Delete `qty` is ignored (encoder sets it to 0). Combinational extraction of the new top-of-book; single-cycle atomic commit of the snapshot registers and `seq` increment in the register bank.

### 3.1.3.2 Packet formats (FS13 interface contract)

Table 3.1.4 — Custom market data payload (RX). *(Identical to the Section 2 contract table; repeat or cross-reference per report style.)*

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

**Scope note (validated translation layer).** The protocol deliberately carries book-affecting events only. Trading-halt and hidden-execution events present in some source feeds are consumed by the simulator and not forwarded to the PL.

**Price alternative (documented).** A higher-precision price unit (10⁻⁴ dollars) was considered to avoid any rounding, but is rejected for the prototype because it would change constants and worked examples across 3.1/3.2/3.3 for a small fraction of events; integer cents with encoder-side rounding is selected.

Table 3.1.5 — Order packet payload (TX, FS13): order_id, symbol, side, qty, price, checksum, at fixed offsets. `[TEAM: freeze exact layout; this table is the standalone protocol spec FS13 requires and is referenced by FS2's verification procedure.]`

### 3.1.3.3 Order book register layout

| Register group | Entries | Fields per entry | Purpose |
|---|---|---|---|
| Bid book | 10 | price_cents (32b), aggregate_qty (32b) | Highest active bid levels |
| Ask book | 10 | price_cents (32b), aggregate_qty (32b) | Lowest active ask levels |
| Top-of-book snapshot | 1 | best_bid_price, best_bid_qty, best_ask_price, best_ask_qty | Published to the PS-visible register bank (with `seq`) on each committed update |
| Diagnostic counters | 4+ | parse_error, fcs_fail, dropped_out_of_window, dma_backpressure | NFS2/NFS8 observability |

### 3.1.3.4 Clocking and PS interface

The PL runs a single 125 MHz clock domain: 125 MHz is simultaneously the GMII byte rate at 1 Gbps (one octet per cycle) and the NFS6 timing target, so the parse pipeline requires no clock-domain crossing between MAC and decode. On the selected board the PL reference clock is a 50 MHz active oscillator, so the 125 MHz PL fabric clock is generated by MMCM/PLL multiplication rather than sourced directly from the oscillator. The RGMII interface transfers 4 bits per edge at 125 MHz DDR; IDDR/ODDR primitives and the PHY-required clock skew are handled at the I/O ring `[TEAM: confirm RGMII delay scheme — PHY internal delay vs. IDELAY — from board schematic]`.

The PS boundary is a single AXI-Lite slave register bank on M_AXI_GP0 (full map in Section 3.2.3.1); the PL is never a bus master, and the HP ports are unused. Snapshot publication is a one-clock-edge atomic commit of all snapshot registers plus the `seq` increment — hardware-side tearing is impossible by construction; the multi-read consistency problem exists only on the PS side and is solved there by seqlock (3.2.3.1). FS1's measurable endpoint is the `seq`-increment write enable, observable with an ILA. On the egress side, the order-field registers are sampled only on the doorbell write strobe (PS writes payload first, doorbell last), which starts the Protocol Encode stage on the following cycle; a `tx_ready` flag provides flow control (structurally uncontended — see 3.2.4.2).

Datasheet references for all interface and resource claims: Zynq-7000 TRM, XC7Z020 datasheet, PHY datasheet/board reference manual `[TEAM: add once board + PHY part number are finalized]`.

---

## 3.1.4 Quantitative Technical Analysis

### 3.1.4.1 Line-rate throughput (NFS9)

The maximum packet rate of the link is fixed by arithmetic, and the design must not stall below it. With the 24-byte payload `[TEAM: confirm final size]`:

```
Frame on wire = preamble/SFD 8 + Eth header 14 + IPv4 20 + UDP 8
 + payload 24 + FCS 4 + inter-frame gap 12
 = 90 bytes = 720 bits
Line-rate ceiling = 10^9 b/s ÷ 720 b = 1.389 M packets/s
```

(For any payload ≤ 18 B the 64-byte Ethernet minimum applies and the ceiling rises to 1.488 Mpps — the classic 64-byte wire-speed figure; our payload is above the pad threshold, so 1.389 Mpps governs.)

The NFS9 target of ≥ 1.2 M msg/s therefore means: **the pipeline must sustain the true wire-speed ceiling of this link, 1.389 Mpps, with zero drops** — there is no headroom between 1.2 M and the ceiling worth engineering to; the design targets the ceiling. The pipeline sustains it structurally: every stage consumes one octet per cycle at 125 MHz with initiation interval 1, so a new frame can begin on the cycle after the previous frame's IFG — the pipeline is never the bottleneck; the wire is. This matches the range reported for comparable single-feed FPGA book builders (1.2–1.5 M msg/s) [3] and hardware feed processing studies that exceed gigabit wire-rate ceilings on faster links [4]. OPEN: confirm with a full-rate PCAP injection test and zero drop-counter delta (NFS9 verification procedure).

### 3.1.4.2 FS1 latency budget decomposition

FS1 allows 1,100 ns from MAC RX to the snapshot becoming readable by the PS (endpoint: `seq`-increment write enable). At 125 MHz (8 ns/cycle):

| Stage | Cycles | Time | Basis |
|---|---|---|---|
| Preamble/SFD detection (8 B) | 8 | 64 ns | GMII: 1 octet/cycle; MAC RX stage must detect SFD before frame body parsing begins |
| Frame body reception (70 B post-preamble, streaming) | 70 | 560 ns | GMII: 1 octet/cycle; parse overlaps reception (Decision 3), so this is reception time, not reception + parse |
| FCS check + commit gate | 2 | 16 ns | Registered compare + commit enable |
| Order book update + top-of-book extract | 4 | 32 ns | Register-array write + combinational best-price mux, registered (OPEN: confirm 4-cycle timing in RTL simulation) |
| Snapshot register commit + `seq` increment | 1 | 8 ns | Single-edge atomic write into the register bank |
| **Total** | **85** | **680 ns** | **38% margin against FS1 = 1,100 ns; every stage is design arithmetic** |

Two structural conclusions fall out of this table. First, 58% of the FS1 budget is consumed by physics (the preamble + frame must arrive), which is why Decision 3's cut-through overlap is not an optimization but a requirement: a store-and-forward second pass would consume most of the remaining budget for zero benefit. Second — and this is a direct consequence of the register-interface iteration described in 3.2.2 Decision 3 — the former governing unknown (AXI HP write latency into DDR3 under PS memory contention) has been eliminated from the FS1 path entirely: the endpoint is now a PL-internal register write whose latency is exactly one cycle by construction. FS1 compliance is therefore closed by arithmetic, pending only RTL simulation of the stated stage depths. Published HFT/market-data FPGA systems report sub-microsecond pipeline latencies on faster MACs (e.g., hundreds of nanoseconds) in similar parse→decision trigger chains, supporting the feasibility of microsecond-class PL budgets [2], [6]. *(Under the superseded DMA design, this row read "≤ 61 cycles, budget remainder, governing unknown" — retain that version as the documented iteration.)*

### 3.1.4.3 Resource envelope (NFS6)

XC7Z020 PL resources: 53,200 LUTs, 106,400 FFs, 140 × 36 Kb BRAM (4.9 Mb), 220 DSP. NFS6 caps usage at 75% LUT (39,900) and 85% BRAM (119 blocks).

| Component | FF estimate (arithmetic) | LUT estimate | BRAM |
|---|---|---|---|
| Order book registers | 20 levels × 64 b + snapshot 128 b + counters ≈ 1.5 K | Best-price compare tree over 10 levels ≈ small | 0 |
| Minimal MAC (RX+TX, CRC-32) | ≈ 0.5–1 K | ≈ 1–2 K (OPEN: confirm via synthesis) | 0–2 (elastic FIFO) |
| Header parse/encode + protocol decode/encode | ≈ 0.5 K | ≈ 1 K (constant-compare + slicing) | 0 |
| AXI-Lite register bank (GP0 slave) | ≈ 0.5 K | ≈ 0.5–1 K (wizard-generated slave + decode) (OPEN: confirm via Vivado utilization report) | 0 |
| **Preliminary total** | **≈ 3–4 K FF** | **≈ 5–8 K LUT ≈ 9–15% of device** | **≪ 10 blocks ≈ < 8%** |

The estimate sits a factor of ~5 below the NFS6 LUT ceiling, which is the deliberate margin motivating Decision 1's board choice: the same architecture on the XC7Z010 (17,600 LUTs) would already commit ~30–45% of the device before any capstone-scope growth (e.g., deeper book, added diagnostics). OPEN: replace all preliminary estimates with post-implementation Vivado utilization + timing summary; NFS6 pass gate is WNS > 0 at 125 MHz.

---

## 3.1.5 Specification Compliance Summary

| Spec | How the final design satisfies it | Evidence status |
|---|---|---|
| FS1 | Cut-through parse overlaps reception; 85-cycle path to snapshot-register commit (including preamble/SFD), 38% margin (3.1.4.2) | Closed by arithmetic; pending RTL sim + ILA measurement |
| FS13 | Fixed-offset TX encoder implements Table 3.1.5 byte-exactly | Design complete pending layout freeze |
| NFS1 (PL share) | RX segment ≤ 1.1 μs; TX encode segment is a fixed ~80-cycle (≈ 0.65 μs) path by the same octet-per-cycle arithmetic as 3.1.4.2 — doorbell latch + ~75 B order frame streamed at 1 octet/cycle | Analytical |
| NFS2 | Point-to-point link, no switch, elastic FIFO sized for IFG-less bursts; drop counters make every discard attributable | Pending 10-min Wireshark test |
| NFS6 | ~9–15% LUT estimate vs. 75% cap (3.1.4.3) | Pending synthesis |
| NFS9 | II=1 octet pipeline sustains the 1.389 Mpps wire ceiling (3.1.4.1) | Analytical; pending PCAP injection test |
| NFS8 | FCS-fail discard + fault counters; no manual restart path in PL | Pending fault-injection test |

---

# 3.2 PS (ARM OS Layer) Strategy & Risk Subsystem

> **Template conventions:** `[TEAM: …]` needs a team decision; `OPEN: …` is an analytical target pending simulation/measurement; `[REF-n]` maps to the bibliography.
> **Architecture baseline (v2):** hot-path interface is the **AXI-Lite register bank + doorbell on M_AXI_GP0** — no DMA, no interrupts, no HP ports on the intraday path. The earlier DMA/interrupt design is retained below only as documented iterations. All budgets are derived against **FS2 = 26 μs** (new wording: from a top-of-book update *becoming visible to the PS* to MAC TX).
> **Diagram naming:** subsection names follow the latest block diagram — *Config Loader, Strategy Engine (Plug-In Execution), Runtime Risk Guard, Execution Logger, HOLD Mode*. `[TEAM: keep 3.2.x headings and diagram labels in lockstep.]`

---

## 3.2.1 Overview and Specification Mapping

The PS subsystem is the software half of the intraday trading loop, executing on the dual-core ARM Cortex-A9 of the XC7Z020. Core 1 — isolated from the Linux scheduler — busy-polls the PL's snapshot registers, evaluates the currently active strategy on each newly observed top-of-book update, filters every proposed order through the Runtime Risk Guard, and issues risk-approved orders back to the PL by writing the order-field registers followed by the doorbell. Core 0 owns everything latency-tolerant: configuration loading at startup (FS4), the Execution Logger and end-of-session export (FS5), the Debug-UART console feed (FS11), recoverable-fault logging (NFS8), and HOLD-mode supervision.

The division of labour with the PL follows one rule established in 3.1: the PL owns everything that must be deterministic at wire speed; the PS owns everything that must be **changeable** — strategy formulas, parameters, and risk limits are all expected to be replaced nightly by the EOD pipeline (Section 3.3), and iterating on them must not require re-synthesis.

| Spec | Role of PS subsystem |
|---|---|
| **FS2** | Sole owner of the software segment: observed snapshot update → decision (BUY/SELL/HOLD) → order handed to PL, inside the ≤ 26 μs budget. |
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

### Decision 1 — Hardware/software boundary: why the strategy engine is not in the PL

| Alternative | Description | Outcome |
|---|---|---|
| Strategy in PL | Implement decision rules as fabric logic; sub-microsecond tick-to-order. | **Rejected.** Strategy formulas, thresholds, and the active strategy identity change nightly via the EOD JSON config (FS4/FS8). A PL implementation would either require re-synthesis per change (hours per iteration, incompatible with the EOD cycle) or a parameterized rule engine in fabric whose design and verification cost exceeds the entire remaining PL budget. Industry practice concurs: fixed protocol/risk primitives migrate to hardware, iterating alpha logic stays in software. |
| Strategy in PS (selected) | Evaluate rules on the Cortex-A9 against the observed snapshot. | **Selected.** A software strategy is reconfigured by rewriting a struct, tested with host-compiled unit tests, and debugged with standard tooling. The cost — microseconds instead of nanoseconds — is affordable: QTA 3.2.4.1 shows the FS2 budget closes with ~5× margin. |

This decision is the reason FS2's budget (26 μs) is three orders of magnitude looser than FS1's (1.1 μs): the specs deliberately price in the software boundary, and Decisions 2–3 carry the burden of proving the priced-in budget is achievable.

### Decision 2 — Operating environment: bare-metal, FreeRTOS, AMP, or Linux with core isolation

| Criterion (weight) | Bare-metal (both cores) | FreeRTOS | AMP (Linux + bare-metal core) | Linux + isolcpus (selected) |
|---|---|---|---|---|
| Hot-path determinism (30%) | Best | Good | Best on isolated core | Good — requires isolation measures (Decision 3) |
| TCP/IP, filesystem, UART tooling for FS4/FS5/FS11 (30%) | None — must port a network stack for the PS GbE paths | lwIP port; limited filesystem | Full on Linux core | Full, native |
| Team development & debug cost (25%) | High | Medium | High (OpenAMP, two-kernel shared-memory protocol) | Low — standard toolchain, matches team's embedded-Linux experience |
| NFS4 6.5-hour robustness path (15%) | All failure handling hand-rolled | Partial | Split-brain failure modes | Mature, observable (logs, watchdogs) |
| **Result** | Rejected | Rejected | **Documented fallback** | **Selected** |

The FS5 export and FS4/FS8 config paths both want a real TCP/IP stack and filesystem; bare-metal and FreeRTOS price those in as porting projects that add no marks. AMP delivers determinism plus Linux but introduces a two-kernel debugging burden — the classic capstone schedule-killer. Linux is selected **with the explicit obligation** to neutralize its scheduling jitter on the hot path, which is Decision 3's job. `[TEAM: confirm distro/kernel — PetaLinux vs. Ubuntu-based; PREEMPT_RT not required by the selected design.]`

### Decision 3 — Hot-path interface and event delivery: a three-iteration, spec-driven design history

This decision governs FS2 and went through three documented iterations; the reversals are driven by arithmetic, not preference, and each iteration is retained per the engineering-design-process requirement.

**Iteration 1 — AXI DMA + interrupt (superseded).** The initial design followed the dominant pattern in the literature: a PL DMA engine pushes each snapshot into a DDR3 ring via an HP port and raises an interrupt; a pinned SCHED_FIFO thread wakes and consumes,. This was designed against an early 200 μs stage budget and was internally consistent with it.

**Iteration 2 — FS2 tightened to 26 μs → interrupts infeasible.** Consolidating the spec table cut the software stage budget ~8×. Linux IRQ→userspace wakeup latency is typically 10–40 μs with worse tails `[TEAM: add a citable Linux IRQ→userspace latency measurement source]` — the *notification mechanism alone* can exceed the entire budget. The replacement is a **busy-poll on an isolated core**: core 1 is removed from the scheduler (`isolcpus`, IRQ affinity to core 0) and spins awaiting new data. The classic objection — polling wastes compute — is void here: the A9 has exactly two cores, core 0 absorbs all housekeeping, and core 1 has no other duty during the session; burning an otherwise-idle core to remove 10–40 μs of nondeterminism is the cheapest latency purchase in the system.

**Iteration 3 — busy-polling removes DMA's rationale → register bank + doorbell.** DMA earns its complexity (descriptor path, kernel driver, cache-coherency management — Zynq-7000 HP ports are not I/O-coherent) by moving bulk data without CPU involvement. With a core already dedicated to watching for a 16–24 B payload, that rationale is gone. The interface collapses to the simplest thing that works: the PL exposes the snapshot as **AXI-Lite registers plus an incrementing `seq`**; core 1 polls `seq` over M_AXI_GP0 and reads the fields on change. The egress direction is event-driven for free in hardware: the PS writes the order-field registers then a **doorbell register**, and the doorbell write strobe itself launches the PL encoder — payload-first/doorbell-last ordering makes torn sampling impossible without any lock.

**Reconciling with the literature (why our conclusion differs from the papers we cite).** Leber et al. and Morris et al. use DMA-to-ring architectures *because they are PCIe systems* [1], [4]: a CPU read of an FPGA register over PCIe is a non-posted MMIO transaction costing on the order of a microsecond and stalling the pipeline, so the only efficient pattern is hardware-push into host RAM and CPU polling of cache-resident memory,. On Zynq, the on-chip GP port inverts that cost structure: a PL register read costs ~0.15–0.3 μs and the payload is 16–24 B, so the same design principle — *minimize the CPU's cost of observing new data* — selects direct register polling instead. Kao et al. state the boundary explicitly: the DMA subsystem is appropriate for *non-timing-critical* transfers such as supervision and reporting [2] — which is precisely where DMA survives in AQTA (the PS GEM's internal DMA on the EOD export and config-load paths, interfaces 6/8). Osuna et al.'s PYNQ-Z2 study is the cautionary converse of our 3.1 Decision 1: with the PHY wired to the PS, they were forced into a socket-receive-then-DMA-to-PL topology [7] — the board-level constraint our carrier-board selection was made to avoid.

| Alternative (final trade study) | End-to-end estimate | Implementation cost | Outcome |
|---|---|---|---|
| Interrupt + DMA ring | 10–40 μs wakeup dominates | DMA IP + driver + coherency | Rejected — worst case exceeds FS2 |
| Busy-poll + DMA ring | ~1–1.5 μs | DMA IP + driver + coherency | Rejected — μs-class, but pays full DMA complexity for a 24 B payload |
| **Busy-poll + register bank + doorbell (selected)** | ~2 μs | Wizard-generated AXI-Lite slave + user-space mmap; zero driver, zero coherency | **Selected — μs-class latencies are indistinguishable against 26 μs; the decision criterion is implementation and verification cost, where the register bank wins decisively** |

Note the honest framing: the register path is *not* claimed to be faster than a well-built DMA push — both are single-digit μs. It is claimed to be **equally fast where it matters and drastically cheaper to build and verify**, which is the correct optimization target for this team and schedule.

### Decision 4 — Execution Logger architecture: the memory arithmetic forces the record policy

FS5 demands > 10 M ticks with bounded memory. The naive design — one full record per tick — fails by arithmetic before any code is written (QTA 3.2.4.3): 10 M × 128 B = 1.28 GB against roughly 512 MB of DDR3 realistically available, and at the 1.389 Mpps wire ceiling a full-rate log stream (~178 MB/s) exceeds any on-board sink's sustained write rate.

| Alternative | Description | Outcome |
|---|---|---|
| Full per-tick log in DRAM | One record per snapshot | **Rejected by capacity arithmetic.** |
| Full per-tick log streamed to eMMC/SD | Continuous spill | **Rejected**: worst-case bandwidth exceeds eMMC sustained write (OPEN: measure board eMMC sustained write bandwidth); a storage stall would back-pressure the hot path. |
| Decision-complete + snapshot-sampled ring (selected) | Log **every** decision/outcome record (rate structurally capped by FS3's 1,000 orders/s) plus book snapshots at a sampling interval and on order events; fixed pre-allocated ring in cached DDR3, written by core 1, drained asynchronously by core 0 | **Selected.** Decision records are what FS5's verification inspects ("one entry per decision"); FS3 caps their rate, so bandwidth is trivially bounded (3.2.4.3). Static allocation at startup — no malloc on the hot path, no OOM by construction. |

Note the logger is now **pure software**: core 1 writes an ordinary cached DDR3 ring; the PL is not involved and no cross-boundary protocol exists for logging. (PL-side diagnostic counters reach the log because core 0 periodically reads the `DIAG_*` registers through the same GP0 bank — a free by-product of the register interface.) **Snapshot sampling policy (selected):** periodic sampling at 100 Hz (every 10 ms) **plus** one snapshot on every order event; ring size 256 MB; flush sink: core 0 drains the ring to eMMC continuously during the session, with the full-session export over PS GbE (interface 6) at session end. These are the same working figures already carried by the arithmetic in 3.2.4.3 and 3.3.4.1. `[@cye: 100 Hz 采样率是经验值 — 回头在论文里找有依据的 snapshot 采样率数据再替换/背书]`

### Decision 5 — Runtime Risk Guard placement: PS software vs. PL hardware

Pre-trade risk in fabric is the industry pattern for exchange-facing gateways, and a PL Risk Guard was considered. It is rejected for this prototype on three grounds: (1) FS3's limits are EOD-configurable, so a PL implementation needs a writable-register interface plus its own verification — cost without marks; (2) QTA 3.2.4.4 shows the software cost is < 100 cycles ≈ 0.5% of the FS2 budget — there is no latency case for hardware; (3) placing the guard *after* the strategy in the same thread guarantees no order path can bypass it, which is simpler to argue for FS3's verification than a split HW/SW trust boundary. The PL retains a residual structural guard: the Order Emitter can only transmit packets assembled from fields the PS wrote through the register bank, in the FS13 fixed format — malformed egress is impossible by construction.

### Decision 6 — Order-terminal semantics for FS14: execution report vs. modeled fills (selected)

FS14/FS3(d) make “in-flight” a real, testable quantity; the design must define when an order stops being in-flight. The prototype selects a PS-only modeled fill delay **T**: on submission, an order enters the open-order table as in-flight and is treated as terminal after **T** elapses, at which point position and the execution-outcome log update. This is deterministic, requires no protocol changes, and makes the FS14 verification procedure feasible by arithmetic (e.g., at 1,000 orders/s, **T = 0.1 s** drives the in-flight count to 100).

---

## 3.2.3 Final Design Details

### 3.2.3.1 The PL/PS register bank and access protocol (interface contract)

The entire intraday PL/PS boundary is one AXI-Lite slave in the PL, mapped through M_AXI_GP0. This table is the interface contract, jointly owned with 3.1:

| Offset | Register | Dir (PS view) | Semantics |
|---|---|---|---|
| 0x00 | `SEQ` | R | Increments atomically with each snapshot commit; core 1 polls this |
| 0x04–0x10 | `BEST_BID_PRICE`, `BEST_BID_QTY`, `BEST_ASK_PRICE`, `BEST_ASK_QTY` | R | Feature Parameters (top-of-book snapshot) `[TEAM: extend if the Market Feature Builder emits more fields]` |
| 0x14–0x18 | `TIMESTAMP_LO/HI` | R | PL hardware timestamp of the committing packet |
| 0x20–0x2C | `DIAG_PARSE_ERR`, `DIAG_FCS_FAIL`, `DIAG_DROP_OOW`, … | R | NFS8/NFS2 counters, read periodically by core 0 |
| 0x40–0x4C | `ORD_SYMBOL_SIDE`, `ORD_QTY`, `ORD_PRICE`, `ORD_ID` | W | Order fields (FS13 source values) |
| 0x50 | `DOORBELL` | W | Write-1 launches the Order Emitter; **payload first, doorbell last** |
| 0x54 | `TX_READY` | R | Egress flow-control invariant (see 3.2.4.2) |

**Consistency protocol.** PL-side commits are single-clock-edge atomic (all snapshot registers + `SEQ` update together), so tearing exists only on the PS side, where reading 4–6 registers spans ~1 μs of separate AXI transactions. Core 1 uses a seqlock: read `SEQ`, read fields, re-read `SEQ`; on mismatch, retry. `[Documented alternative: a shadow-bank latch on `SEQ` read — rejected because read-side-effect registers complicate debug tooling for no measurable gain.]` On the egress side no lock exists or is needed: the PL samples order fields only on the doorbell strobe.

**Conflation semantics (deliberate).** The bank holds the *latest* snapshot; if ticks outrun the polling loop, intermediate snapshots are overwritten and the strategy always decides on the current book rather than a queue of stale ones. QTA 3.2.4.2 shows this is not a compromise: the CPU could not process every tick regardless, and latest-value conflation is the standard market-data semantics for top-of-book strategies. NFS9 is unaffected — the PL still ingests and books every packet at line rate; conflation applies only to what the PS samples.

### 3.2.3.2 Strategy Engine (Plug-In Execution)

The engine is a table dispatch: the active strategy ID (from the FS4 config) indexes a function table; each strategy is a pure function of (snapshot, rolling state, parameters) → {BUY, SELL, HOLD} + order fields. Rolling state is fixed-size (e.g., a lookback ring of midprices), so per-tick cost is O(1) and independent of session length.

| Regime | Strategy | Input signals | Decision rule |
|---|---|---|---|
| Trending | Momentum | Midprice sequence over configured lookback | `m = mid_t − mid_{t−L}`; BUY if `m ≥ +θ_entry`, SELL if `m ≤ −θ_entry`, else HOLD |
| Ranging | Mean Reversion | Midprice deviation from moving average | `d = mid_t − SMA_W(mid)`; BUY if `d ≤ −θ_dev`, SELL if `d ≥ +θ_dev`, else HOLD (trade toward the mean) |
| Volatile | Defensive | Spread, volatility flag, position state | If `spread ≥ spread_floor` or the vol flag is set: suppress new entries and emit only position-reducing orders toward flat; else HOLD |

`mid` is held in half-cent units (`best_bid + best_ask`) so the arithmetic stays integer; thresholds are configured in the same units. Every window, threshold, and position scalar loads from the FS4 JSON config — the parameter names are exactly the axes swept in 3.3.3a.3 (`lookback/entry_thresh/pos_scalar`, `window/dev_thresh/pos_scalar`, `spread_floor/vol_cutoff/pos_scalar`) — so tuning never requires recompilation. The formulas are deliberately simple: per-strategy sophistication lives in the EOD parameter sweep (3.3), not the intraday rule; the design's contribution is the deterministic, reconfigurable evaluation machinery, not the alpha.

All arithmetic is integer (prices already in cents from the PL), avoiding FPU state on the isolated core and making decisions bit-reproducible for backtest cross-validation against the EOD pipeline. The integer-only commitment is confirmed as a binding design commitment; it also extends FS7's determinism property to the SoC side.

### 3.2.3.3 Runtime Risk Guard (FS3)

Executed unconditionally after every non-HOLD decision, in-thread:

| Check | Rule | Mechanism |
|---|---|---|
| Notional | qty × price ≤ $50,000 CAD limit (configurable) | 32×32→64-bit multiply, one compare |
| Position | \|position ± qty\| ≤ 1,000 shares | Signed accumulate against local position state, one compare |
| Rate | ≤ 1,000 orders/s | Token bucket: capacity 1,000, refill from the global timer via fixed-point multiply-shift — no divides on the hot path (3.2.4.4) |
| In-flight | in-flight count ≤ 100 | Compare against open-order table occupancy counter (increment on doorbell; decrement on modeled terminal transition — Decision 6) |

Rejections write a reason-coded record to the Execution Logger (FS3's "logged reason code") and never reach the doorbell. A REJECT may also assert the Runtime Trigger into HOLD Mode (3.2.3.6). Limits load from the FS4 config and are immutable during a session.

### 3.2.3.3.1 Open-order table (FS14)

Core 1 maintains a fixed, pre-allocated open-order table of ≥ 128 entries `{order_id, side, qty, price, submit_timestamp, state}` for the traded symbol. The capacity is sized at startup from the FS4 config (bounded by FS3(d)'s ceiling), and overflow is impossible because the Risk Guard's in-flight check rejects before insertion. Orders transition to terminal by the modeled fill-delay policy (Decision 6); each terminal transition produces an execution-outcome record for FS5.

### 3.2.3.4 Config Loader (FS4) and fault handling (NFS8)

At startup, before core 1 begins polling, the loader ingests the JSON configuration (either from the board's SD/TF card slot or via a TCP push from the EOD server — interface 8), validates schema, ranges, and the operator-approval hash (FS8 chain of custody), and populates the strategy table and Risk Guard limits. Any validation failure is NFS8's "malformed config" case: log fault code, refuse to start the polling loop, remain up for re-push — never trade on a default. Market data processing is structurally unreachable until a config commits, which is FS4's verification argument.

### 3.2.3.5 Execution Logger and Console (FS5, FS11)

Core 0 owns everything off the hot path: draining the history ring to the flush sink, the end-of-session export over PS GbE to the EOD server (interface 6), periodic `DIAG_*` register sampling into the log, and the FS11 console feed — a rate-limited (`[TEAM: e.g., 1 Hz]`) rendering of current book top and recent decisions over Debug UART (interface 5). The UART feed reads the same ring; it adds zero work to core 1.

**Execution record schema (frozen — 128 B fixed).** One record per strategy decision, execution outcome, sampled snapshot, Risk Guard REJECT, or fault event, written by core 1 as a single fixed-size struct copy:

| Field | Offset (B) | Size (B) | Content |
|---|---|---|---|
| `record_type` | 0 | 1 | 0x01 DECISION, 0x02 OUTCOME, 0x03 SNAPSHOT, 0x04 REJECT, 0x05 FAULT |
| `decision` | 1 | 1 | 0x00 HOLD, 0x01 BUY, 0x02 SELL (0x00 for non-decision records) |
| `strategy_id` | 2 | 1 | Active strategy index (FS4 config) |
| `reason_code` | 3 | 1 | FS3 reject reason / NFS8 fault code; 0 otherwise |
| `seq` | 4 | 4 | PL snapshot `SEQ` this record was decided against |
| `pl_timestamp` | 8 | 8 | `TIMESTAMP_HI:LO` of the committing packet (3.2.3.1) |
| `cpu_timestamp` | 16 | 8 | Core-1 PMU cycle count (CCNT) — FS2 instrumentation for free |
| `best_bid_price`, `best_bid_qty`, `best_ask_price`, `best_ask_qty` | 24 | 16 | Top-of-book at decision time (4 × u32, integer cents / shares) |
| `order_id` | 40 | 4 | 0 if no order emitted |
| `order_qty`, `order_price` | 44 | 8 | 2 × u32; 0 if no order |
| `position_after` | 52 | 4 | Signed shares after this record's effect |
| `inflight_count` | 56 | 4 | Open-order table occupancy after this record |
| `realized_pnl` | 60 | 8 | Cumulative, signed integer cents |
| `reserved` | 68 | 60 | Zero-filled — pads to 128 B and absorbs schema growth without a size change |

### 3.2.3.6 HOLD Mode

HOLD is a state, not a message. On the per-decision level, HOLD simply means **no doorbell write** — nothing crosses to the PL, and a HOLD record enters the logger. On the session level, HOLD Mode is a latched supervisory state entered by (a) the Runtime Trigger from a Risk Guard REJECT pattern — trigger rule: **≥ 3 REJECTs within a rolling 10 s window** latches HOLD (both values load from the FS4 config; the working values are deliberately conservative so the prototype fails safe), or (b) the EOD path's "REJECT / No Approval" outcome; while latched, the strategy output is forced to HOLD until an operator action clears it. Because HOLD requires no PL cooperation, no cross-boundary protocol element exists for it — the diagram's "Hold Decision" arrow into the PL should be removed or re-annotated as "(no doorbell)". `[TEAM: confirm with diagram owner.]`

---

## 3.2.4 Quantitative Technical Analysis

### 3.2.4.1 FS2 latency budget decomposition (26 μs at 766 MHz)

26 μs ≈ 19,900 CPU cycles at 766 MHz (the Cortex-A9 max frequency on the target board). The budget also funds the PL egress tail (doorbell-to-MAC-TX ≈ ~1 μs by 3.1 arithmetic), leaving ~25 μs for software:

| Stage | Estimate | Basis |
|---|---|---|
| Detect new `SEQ` (one GP0 read) | ~0.15–0.3 μs | AXI-Lite read via GP (OPEN: PMU/ILA microbenchmark — the single number this table hangs on) |
| Snapshot read: 4–6 field reads + seqlock re-read | ~1–1.8 μs | 6–8 GP reads; retry probability bounded in 3.2.4.2 |
| Strategy evaluation | ≤ ~1 μs | Hundreds of integer ops on O(1) state — generous ceiling |
| Runtime Risk Guard | ≪ 0.1 μs | < 100 cycles (3.2.4.4) |
| Logger record write | ≤ ~0.5 μs | Fixed 128 B struct copy into cached ring |
| Order-field writes + doorbell (5 GP writes) | ~0.5–1 μs | AXI-Lite posted writes |
| **Software total** | **≤ ~5 μs** | **≥ 5× margin against the ~25 μs share; worst case is what FS2's 1,000-tick verification samples** |

Under the rejected interrupt design, the first row alone costs 10–40 μs (OPEN: add a citable Linux IRQ→userspace latency measurement source) — 40–160% of budget before any work. The selected design's entire path is bounded by countable bus transactions. OPEN: replace estimates with PMU (CCNT) per-stage instrumentation across 1,000 ticks, then the Wireshark end-to-end check.

### 3.2.4.2 Interface capacity, conflation, and the DMA comparison

Three rates bound the system (using the GP-read estimate above, worst case 0.3 μs):

```
Snapshot read cost (6 reads + seqlock): ~1.5–2 μs → PS observation ceiling ≈ 500–600 K snapshots/s
Full decision iteration (table 3.2.4.1): ~5 μs → PS decision ceiling ≈ 200–330 K decisions/s
Wire tick ceiling (3.1.4.1): 1.389 M ticks/s
```

The PS cannot observe every tick (600 K < 1.389 M) — but it cannot *process* every tick either (330 K < 1.389 M): **the bottleneck is the CPU, not the interface.** A DMA ring would not raise either ceiling; it would only queue ticks the CPU cannot consume, forcing the strategy to act on progressively staler books — for trading, a negative. A ring consumer would end by skipping to the newest entry, i.e., re-implementing conflation with more hardware. Conflation is therefore the *correct* semantics given CPU throughput < wire rate, not a limitation accepted for convenience. Seqlock retry probability: a retry occurs only if a commit lands inside the ~1.5 μs read window; even at full wire rate the expected retries per read ≈ 1.5 μs × 1.389 M/s ≈ 2 — bounded by capping retries at `[TEAM: e.g., 4]` and accepting the newest consistent snapshot. OPEN: record a retry-rate counter during full-rate injection.

**Sensitivity boundaries (when this interface stops being right):**

| Condition | Register path | Conclusion |
|---|---|---|
| Current spec: 1 symbol, top-of-book, conflation acceptable | ~1.5–2 μs/read, ≥ 5× FS2 margin | **Adequate — selected** |
| Payload > ~100 B/event (e.g., 10-level depth) | ~40 reads ≈ 10 μs — erodes margin | Migrate to a **GP-mapped dual-port BRAM window** (PL BRAM as AXI slave) — still no DMA IP, no driver |
| Per-tick consumption required (no conflation) | Observation ceiling < wire rate | DMA ring required — and a faster CPU with it; out of prototype scope |

**TX contention arithmetic:** FS3 caps orders at 1,000/s (≥ 1 ms spacing) vs. ~1 μs per packet transmit — a 1000× margin; `TX_READY` exists as a correctness invariant, not a performance mechanism.

### 3.2.4.3 FS5 memory budget arithmetic

Record size = 128 B (schema frozen in 3.2.3.5):

```
Full per-tick logging: 1.389 M/s × 128 B ≈ 178 MB/s bandwidth; 10 M ticks × 128 B = 1.28 GB capacity
Available DDR3 (approx): PS DDR3 is 1 GB total (2×512 MB). Assuming ≈ 512 MB remains available after OS + code is a reasonable working budget for FS5 planning.
Decision-record ceiling: 1,000/s (FS3) × 128 B = 128 KB/s
Snapshot sampling @100 Hz: 12.8 KB/s
```

Per-tick logging fails on both capacity and bandwidth — Decision 4 is forced, not chosen. The selected policy's sustained rate (~141 KB/s) is three orders of magnitude below the failure mode; the 256 MB ring holds ≈ 30 minutes at the absolute-worst decision rate while core 0 drains at ≥ (OPEN: board eMMC benchmark) MB/s, so occupancy stays bounded. The board's 8 GB eMMC capacity is ample for the ring + export; the remaining question is sustained write bandwidth, which must be measured. No allocation after startup — FS5's no-OOM clause holds by construction.

### 3.2.4.4 Runtime Risk Guard cost bound

Notional: one `umull` + compare ≈ 5–10 cycles. Position: add + two compares ≈ 5 cycles. Rate: timer-delta × fixed-point constant, multiply-shift-saturate ≈ 10 cycles; spend = decrement + compare. In-flight: one counter compare ≈ 1–2 cycles. Total ≪ 100 cycles ≈ 0.13 μs at 766 MHz ≈ 0.5% of the FS2 budget — quantitatively closing Decision 5's "no latency case for hardware risk checks" claim.

---

## 3.2.5 Specification Compliance Summary

| Spec | How the final design satisfies it | Evidence status |
|---|---|---|
| FS2 | Busy-poll isolated core + register reads; ≤ ~5 μs software path vs. ~25 μs share (3.2.4.1) | Analytical; pending PMU-instrumented 1,000-tick run + Wireshark |
| FS3 | Unbypassable in-thread Risk Guard; four checks + reason-coded log | Pending four-violation injection test |
| FS4 | Polling loop structurally unreachable until validated config commits | Pending config-swap restart test |
| FS5 | Static allocation, decision-complete + sampled-snapshot ring, async flush (3.2.4.3) | Analytical; pending 10 M-tick stress + export check |
| FS14 | Pre-allocated open-order table sized from config; Risk Guard rejects at limit; modeled terminal transitions (Decision 6) | Pending limit-saturation injection test |
| FS11 | Core-0 UART renderer off the shared ring | Pending live-session check |
| NFS1 (PS share) | FS2 path is the PS contribution; margin table 3.2.4.1 | Analytical |
| NFS4 | Linux + watchdog `[TEAM: define]` + no hot-path allocation; fault paths per NFS8; HOLD Mode as safe state | Pending 6.5 h soak |
| NFS8 | Config-reject path; fault-coded logging; session continues; PL `DIAG_*` counters surfaced via GP0 | Pending malformed-config injection |

# 3.3 EOD Server Pipeline Subsystem

> **Template conventions:** `[TEAM: …]` needs a team decision; `[EVIDENCE: …]` is an analytical target pending simulation/measurement; `[REF-n]` maps to the bibliography.
> **Scope note:** this subsystem contains two internal data paths that merge before the approval gate. For readability, Final Design Details are split into **3.3.3a (Market Data Path — essential)** and **3.3.3b (Text & Sentiment Path — non-essential)**; they remain one subsystem, matching the block diagram.
> **Diagram naming:** stage names follow the block diagram — *Parameter Engineering, Regime Detection, Strategy Reoptimize, LLM Agent, Sentiment Analysis, Backtest & Parameter Sweep, Risk Analysis, Generate JSON Configs, Operator Approval*. `[TEAM: keep 3.3.x headings and diagram labels in lockstep, same as 3.1/3.2.]`
> All numeric analysis in 3.3.4 is derivable on paper today (dataset-size arithmetic, iteration-count budgets, complexity bounds, inequality proofs) — no code required.

---

## 3.3.1 Overview and Specification Mapping

The EOD (End-of-Day) Server Pipeline is the adaptation layer of AQTA — the component that makes the system *Adaptive* rather than a fixed-strategy appliance. It runs on a host server, entirely off the intraday critical path, and closes the loop between one trading session and the next: it ingests the session history exported by the PS (interface 6) together with historical daily OHLCV data, classifies the next trading day's market regime (FS6), re-optimizes the parameters of the strategy assigned to that regime by exhaustively backtesting a bounded parameter grid (FS7), optionally adjusts the risk envelope using sentiment extracted from unstructured text sources (FS9/FS10), assembles the result into a candidate JSON configuration, and presents it to a human operator whose explicit approval is the only path by which any configuration can reach the live system (FS8, via interface 8 into the PS Config Loader of 3.2.3.4).

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
| **NFS8 (partial)** | Owner of server-side fault handling: malformed/missing input data or failed text ingestion must degrade safely (log fault code, emit no config or a neutral adjustment) rather than abort the nightly cycle uncleanly. `[TEAM: NFS7 and NFS8 are currently word-identical in Section 2 — resolve the duplicate before final submission.]` |

Upstream dependency: FS5's exported session history (interface 6) and a historical daily OHLCV dataset are the pipeline's inputs. The OHLCV source is pinned to the project's own 3.4 corpus: seed-reproducible simulator sessions aggregated to daily bars (regime-labeled, unlimited volume, zero license cost), anchored by the real LOBSTER AAPL sample day (3.4.4.6 — a freely published official sample), so no external market-data feed or license is required. Downstream contract: the JSON configuration schema of 3.3.3.5, consumed by the PS Config Loader — jointly owned with 3.2, exactly as the register bank table of 3.2.3.1 is jointly owned with 3.1.

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

**Why this doesn't contradict the "prefer existing libraries" principle.** The principle applies where the component is commodity infrastructure (data loading, HTTP, JSON, metric arithmetic — all off-the-shelf here). The backtest *kernel* is not commodity: its defining requirement is decision parity with our own PS code, a property no external library can supply by definition. The cost of the custom choice is speed — a pure-Python event loop is orders of magnitude slower than vectorized NumPy — and 3.3.4.1 shows that cost is affordable inside NFS5 with a ≥ 3× margin: **slow-but-identical beats fast-but-divergent when the budget makes slow free.** Cross-validation between the kernel and the PS engine (same recorded input, byte-compared decision sequences) is itself a planned verification artifact. `[EVIDENCE: kernel-vs-PS decision-sequence byte comparison on a recorded session.]`

**Backtest data source.** The kernel replays the **snapshot stream exported by the Execution Logger** (FS5, interface 6) — the sampled top-of-book records the live system actually observed — rather than synthetic bars. This closes the loop with zero format invention: the system generates its own backtest data in its own schema, and the parameter sweep evaluates strategies on exactly the data distribution the deployed strategy will see. Bootstrap case (no live sessions yet): replay sessions generated by the Exchange Simulator (3.4) `[TEAM: confirm bootstrap dataset — N simulator sessions recorded before first live run]`. The daily-OHLCV dataset is used only by the regime path (FS6 is explicitly specified on daily data), not by the sweep.

### Decision 5 — Text & Sentiment Path architecture (FS9/FS10): where the LLM belongs, and the determinism boundary

The non-essential path raises a design tension: an LLM is the strongest available tool for FS9's actual problem (extracting structured records from heterogeneous unstructured sources — HTML news, social posts, PDF reports), but LLM outputs are non-deterministic and externally hosted — properties that must not contaminate FS7's bit-identical guarantee or FS8's audit chain. The design resolves this by splitting the path at a **determinism boundary** and choosing a different tool on each side.

**Stage 1 — Extraction (FS9): LLM agent, selected for the messy side.** Alternatives: hand-written per-source parsers (rejected: one parser per source format, brittle against layout changes, and PDF report extraction alone is a project), classical NLP/NER pipelines (rejected: comparable integration cost to FinBERT below but solves only entity tagging, not headline/relevance extraction from arbitrary formats). The LLM agent ingests each asset over HTTPS and emits one structured event record (headline, ticker, timestamp, source — FS9's exact field list). Every emitted record is **logged verbatim**; everything downstream operates only on logged records. Non-determinism therefore stops at the boundary: re-running the pipeline *from the logged records* is fully deterministic, which is the precise sense in which FS7's re-run verification is defined. `[TEAM: LLM provider/API vs local model; FS9's verification uses a mocked web server, so the demo does not depend on live source availability.]`

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

**Coupling into the essential path — risk-tightening-only, by proof.** The sentiment output enters the **Risk Analysis** stage as a position-limit scalar, under a monotonicity constraint proven in 3.3.4.4: the adjusted limit satisfies `L(s) ≤ L_base` for every possible score `s`, with equality for all `s ≥ 0`. Sentiment can therefore only *shrink* the risk envelope below the FS3 ceilings, never expand it, and never touches the optimization objective or strategy selection. Consequently the non-essential path is **incapable of harming the essential system**: its total failure (no assets, API down, model missing) degrades to `s = 0` ⇒ no adjustment ⇒ the essential pipeline's output is byte-identical to a run with the path disabled. This is the same structural-safety argument style as 3.2's "malformed egress is impossible by construction." *(Diagram note: the block diagram's `PATH_TXT → BACKTEST` arrow should be re-annotated to target Risk Analysis — sentiment does not feed the backtest objective. `[TEAM: confirm with diagram owner, same as the HOLD-arrow fix in 3.2.3.6.]`)*

### Decision 6 — Approval gate and configuration chain of custody (FS8)

| Alternative | Description | Outcome |
|---|---|---|
| Procedural gate | Pipeline writes the config; operator manually copies it to the SoC when satisfied. | **Rejected.** FS8's verification must show the config *cannot* reach the SoC unapproved; a procedure is a promise, not a mechanism — nothing distinguishes an approved file from an unapproved one after the fact. |
| Approval flag in the config | Pipeline sets `approved: true` after a y/n prompt; transmission code checks the flag. | **Rejected.** The flag is data, forgeable by any bug or manual edit between generation and load; the PS cannot distinguish a genuinely approved config from one with the bit flipped. |
| **Hash-bound approval + gated transmission (selected)** | The pipeline computes SHA-256 over the **canonically serialized** config payload (canonicalization frozen: UTF-8; keys sorted lexicographically; compact separators with no insignificant whitespace; integers in plain decimal; float metrics pre-rounded to fixed 6-decimal strings before serialization — i.e., Python `json.dumps(payload, sort_keys=True, separators=(',',':'))` over an int/string-only payload. These rules are part of the interface contract; any revision bumps the provenance `pipeline_version` field). The operator is shown the FS12 report (regime, sweep table, selected parameters, Sharpe, sentiment adjustment) plus the hash, and approves interactively; approval appends an approval block (operator ID, timestamp, payload hash). Only then does control flow reach the transmission call — **the network send is inside the approval-gated branch**, so an unapproved config is unreachable code, the same structural argument as FS4's in 3.2.3.4. On the receiving end, the PS Config Loader independently recomputes the payload hash and refuses any config whose hash does not match its approval block (the "operator-approval hash" validation already specified in 3.2.3.4). | **Selected.** Two independent enforcement points (server-side structural gate + SoC-side hash verification) mean FS8 survives either a server-side bug or a tampered file in transit; a REJECT/no-approval outcome leaves the SoC's previous config in place and (per 3.2.3.6) latches the next session into HOLD Mode. |

Transport for the approved config is a push over the PS GbE (interface 8) via `scp` to a staging path on the SoC, from which the Config Loader ingests it at startup — selected over a minimal custom TCP receiver purely for implementation convenience; the FS8 argument rests on the hash chain, not the transport.

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

### 3.3.3.5 JSON configuration schema (interface 8 contract, jointly owned with 3.2.3.4)

| Field | Type | Content |
|---|---|---|
| `strategy_id` | string | `momentum` / `mean_reversion` / `defensive` |
| `regime_label` | string | `trending` / `ranging` / `volatile` |
| `parameters` | object | The swept winner's values, integer-encoded to match the PS kernel. Keys per strategy — momentum: `lookback`, `entry_thresh`, `pos_scalar`; mean_reversion: `window`, `dev_thresh`, `pos_scalar`; defensive: `spread_floor`, `vol_cutoff`, `pos_scalar` (lockstep with 3.2.3.2's formulas and the 3.3.3a.3 grid axes) |
| `risk_limits` | object | `max_notional_cad`, `max_position_shares`, `max_order_rate` — post-sentiment values, each ≤ its FS3 ceiling |
| `provenance` | object | Data window, grid hash, backtest Sharpe, sentiment score, pipeline version — the FS12 record embedded for audit |
| `approval` | object | `operator_id`, `timestamp`, `payload_sha256` — appended only by the approval action (Decision 6) |

### 3.3.3.6 FS12 status reporting and server-side fault handling (NFS8)

Every stage transition writes one structured log line — `(timestamp, stage, status, key metrics)` — to console and to the nightly log file; the approval prompt renders the accumulated report (regime, full sweep table, selected parameters, Sharpe, sentiment, risk-check annotations, payload hash). FS12's verification (one entry per stage transition, including final approval status) is satisfied by the `run_stage()` wrapper of Decision 1's orchestration corollary. Server-side recoverable faults follow one uniform policy: log a timestamped fault code; degrade to the stage's neutral/abort behavior (text path → neutral; market path → abort before config generation); never emit a config that any validation stage has not passed.

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
Report/serialize/hash:  negligible

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
| FS8 | Hash-bound approval; transmission call structurally unreachable without approval; PS-side hash re-verification (Decision 6) | Pending no-approval / tampered-hash injection tests |
| FS9 (non-ess.) | LLM agent → verbatim-logged structured records; per-asset fault isolation | Pending mocked-server ingestion test |
| FS10 (non-ess.) | FinBERT scoring in [−1,+1] by construction; risk-tightening-only coupling with proven bound (3.3.4.4) | Analytical; pending pre-labeled reference-set test |
| FS12 (non-ess.) | `run_stage()` wrapper logs every transition; approval report aggregates regime/sweep/Sharpe/status | Pending full-cycle log inspection |
| NFS5 (non-ess.) | ≈ 7–8 min pessimistic total vs 30 min budget; ≥ 3× margin with growth allowance (3.3.4.1, 3.3.4.5) | Analytical; pending reference-dataset wall-clock |
| NFS8 (partial) | Validate-before-compute; fault-coded logging; text path degrades to neutral; no config emitted past a failed validation | Pending malformed-input injection |

---

# 3.4 Exchange Simulator Subsystem

> **Template conventions:** `[TEAM: …]` needs a team decision; `[EVIDENCE: …]` is an analytical target pending measurement; `[REF-n]` maps to the bibliography at the end of this section.
> **Diagram naming:** the block diagram labels this subsystem *"Exchange Simulator on Host (Live Order Book & Executor — 1 Exch / 1 Stock)"*; internal component names below are *Order-Flow Generator (dual-driver), Book Mirror, Protocol Encoder, Order Executor (validate-and-log), Scenario Engine, Ground-Truth Logger*. `[TEAM: keep headings and diagram labels in lockstep.]`
> **Spec baseline:** assumes the amended Section 2 (single-symbol FS14, four-limit FS3, percentile FS2) and fill-semantics option C2 (PS-side simulated fill latency; C1 execution reports as documented extension).
> All measured figures in this section were produced on the development sandbox against the real LOBSTER AAPL sample dataset (3.4.4.6); re-run on the target host before final submission `[EVIDENCE]`.

---

## 3.4.1 Overview and Specification Mapping

The Exchange Simulator is the counterparty to everything built in 3.1–3.3: it plays the exchange that the project objective requires but deliberately does not connect to (Section 1.2's paper-trading boundary). It runs on the host PC, terminates the far end of the point-to-point Gigabit Ethernet link into the PL (interfaces 1 and 4), generates the market-data event stream in the custom protocol of Table 3.1.4, maintains its own mirror of the resulting order book, and receives, validates, and logs every order packet the SoC emits (Table 3.1.5).

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
| Validate-and-log executor, no-impact assumption (selected) | Every received order packet is parsed against the FS13 layout, checksum-verified, range-checked, timestamped, and logged; the generated market-data stream is **not** altered by received orders. | **Selected.** This is exactly the FS13 oracle role: an independent second implementation of the protocol parse is the strongest practical check of the spec document (any ambiguity in Table 3.1.5 surfaces as a disagreement between the PL encoder and the simulator parser — at which point the *document* gets fixed, which is FS13's actual point; 3.4.4.6 records this mechanism already firing once on the RX-side table during design). The no-impact assumption is stated openly as a modeling boundary: with FS3 capping orders at 1,000 shares against a book quoting thousands of shares per level, self-impact would be second-order even if modeled. `[TEAM: state the no-impact assumption in the report's limitations paragraph; it is a deliberate scope cut, not an oversight.]` |

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
6. **Order Executor (validate-and-log) + Ground-Truth Logger** — parses every received order packet against Table 3.1.5 (FS13 oracle), checksum-verifies, and appends to the ground-truth log; the logger also records every transmitted event with a host timestamp.

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

---

## Document Index (titles + line numbers)

Line numbers refer to this file as currently written (they will shift as edits are made).

- L1 1. Introduction
- L3 1.1 Motivation
- L9 1.2 Project Objective
- L19 1.3 Block Diagram (Deprecated, only for reference)
- L93 2. System Specifications
- L95 2.1 Functional Specifications
- L114 2.2 Non-Functional Specifications
- L128 3.1 PL (FPGA) Market Data Path Subsystem
- L138 3.1.1 Overview and Specification Mapping
- L160 3.1.2 Engineering Design Process
- L164 Decision 1 — Network path placement: PS socket, PS-DMA-then-parse, or full PL path
- L174 Decision 2 — MAC layer implementation: vendor IP, open-source stack, or minimal custom MAC
- L186 Decision 3 — Parse architecture: store-and-forward vs. cut-through streaming parse
- L194 Decision 4 — Order book storage: BRAM-indexed structure vs. fixed register array
- L207 3.1.3 Final Design Details
- L209 3.1.3.1 Receive pipeline
- L219 3.1.3.2 Packet formats (FS13 interface contract)
- L240 3.1.3.3 Order book register layout
- L249 3.1.3.4 Clocking and PS interface
- L259 3.1.4 Quantitative Technical Analysis
- L261 3.1.4.1 Line-rate throughput (NFS9)
- L276 3.1.4.2 FS1 latency budget decomposition
- L290 3.1.4.3 Resource envelope (NFS6)
- L306 3.1.5 Specification Compliance Summary
- L320 3.2 PS (ARM OS Layer) Strategy & Risk Subsystem
- L328 3.2.1 Overview and Specification Mapping
- L350 3.2.2 Engineering Design Process
- L352 Decision 1 — Hardware/software boundary: why the strategy engine is not in the PL
- L361 Decision 2 — Operating environment: bare-metal, FreeRTOS, AMP, or Linux with core isolation
- L373 Decision 3 — Hot-path interface and event delivery: a three-iteration, spec-driven design history
- L393 Decision 4 — Execution Logger architecture: the memory arithmetic forces the record policy
- L405 Decision 5 — Runtime Risk Guard placement: PS software vs. PL hardware
- L409 Decision 6 — Order-terminal semantics for FS14: execution report vs. modeled fills (selected)
- L415 3.2.3 Final Design Details
- L417 3.2.3.1 The PL/PS register bank and access protocol (interface contract)
- L435 3.2.3.2 Strategy Engine (Plug-In Execution)
- L447 3.2.3.3 Runtime Risk Guard (FS3)
- L460 3.2.3.3.1 Open-order table (FS14)
- L464 3.2.3.4 Config Loader (FS4) and fault handling (NFS8)
- L468 3.2.3.5 Execution Logger and Console (FS5, FS11)
- L472 3.2.3.6 HOLD Mode
- L478 3.2.4 Quantitative Technical Analysis
- L480 3.2.4.1 FS2 latency budget decomposition (26 μs at 766 MHz)
- L496 3.2.4.2 Interface capacity, conflation, and the DMA comparison
- L518 3.2.4.3 FS5 memory budget arithmetic
- L531 3.2.4.4 Runtime Risk Guard cost bound
- L537 3.2.5 Specification Compliance Summary
- L551 3.3 EOD Server Pipeline Subsystem
- L560 3.3.1 Overview and Specification Mapping
- L585 3.3.2 Engineering Design Process
- L589 Decision 1 — Execution environment: on-SoC overnight job, compiled host pipeline, or Python host pipeline
- L599 Decision 2 — Regime classifier (FS6): rule-based thresholds, k-means clustering, or Hidden Markov Model
- L615 Decision 3 — Parameter search (FS7): exhaustive grid, random search, or Bayesian optimization
- L625 Decision 4 — Backtest kernel: vectorized library, event-driven framework, or parity-ported custom loop
- L639 Decision 5 — Text & Sentiment Path architecture (FS9/FS10): where the LLM belongs, and the determinism boundary
- L659 Decision 6 — Approval gate and configuration chain of custody (FS8)
- L671 3.3.3 Final Design Details
- L675 3.3.3a Market Data Path (essential — FS6, FS7)
- L677 3.3.3a.1 Data import and Parameter Engineering
- L690 3.3.3a.2 Regime Detection (FS6)
- L705 3.3.3a.3 Strategy Reoptimize — Backtest & Parameter Sweep (FS7)
- L734 3.3.3a.3.1 Preliminary validation run (real data)
- L764 3.3.3a.4 Risk Analysis and config generation
- L768 3.3.3b Text & Sentiment Path (non-essential — FS9, FS10)
- L770 3.3.3b.1 LLM Agent — ingestion and extraction (FS9)
- L784 3.3.3b.2 Sentiment Analysis (FS10)
- L788 3.3.3b.3 Coupling into Risk Analysis
- L798 3.3.3.5 JSON configuration schema (interface 8 contract, jointly owned with 3.2.3.4)
- L809 3.3.3.6 FS12 status reporting and server-side fault handling (NFS8)
- L815 3.3.4 Quantitative Technical Analysis
- L817 3.3.4.1 NFS5 runtime budget decomposition
- L843 3.3.4.2 FS7 determinism argument — enumeration of nondeterminism sources
- L859 3.3.4.3 Regime classifier non-degeneracy (FS6 verifiability by construction)
- L879 3.3.4.4 Sentiment risk-coupling safety bound (FS10 cannot violate FS3)
- L893 3.3.4.5 Grid scale sensitivity (why exhaustive search is the right size, and when it stops being)
- L906 3.3.5 Specification Compliance Summary
- L921 3.4 Exchange Simulator Subsystem
- L930 3.4.1 Overview and Specification Mapping
- L955 3.4.2 Engineering Design Process
- L957 Decision 1 — Market-data source: a four-iteration design history
- L976 Decision 2 — Execution model: full matching engine vs. validate-and-log executor under a no-impact assumption
- L985 Decision 3 — Rate architecture: one online generator for everything, or an offline-generate / online-replay split
- L999 Decision 4 — Test controllability: hardcoded test modes, interactive control, or declarative scenario files
- L1009 3.4.3 Final Design Details
- L1011 3.4.3.1 Component structure and data flow
- L1022 3.4.3.2 Order-flow model (synthetic driver)
- L1033 3.4.3.3 Session configuration and ground-truth log
- L1039 3.4.3.4 Link and host configuration
- L1045 3.4.4 Quantitative Technical Analysis
- L1047 3.4.4.1 Session-mode rate capability — measured
- L1059 3.4.4.2 Stress-mode PCAP sizing (NFS9)
- L1071 3.4.4.3 Determinism — measured
- L1075 3.4.4.4 Generator correctness invariants (the simulator's own test plan)
- L1085 3.4.4.5 Session data-volume arithmetic (NFS4 soak, log sizing)
- L1097 3.4.4.6 Real-data validation: LOBSTER replay through the protocol layer — measured
- L1117 3.4.5 Specification Compliance / Instrumentation Summary
- L1132 References
- L1162 Further reading (uncited in this document)
