**University of Waterloo**\
**Faculty of Engineering**\
**Department of Electrical and Computer Engineering**

**Detailed Design and Project Timeline**

**Adaptive Quantitative Trading Accelerator**

**Group 2026.36**

**Team Members**:

Hanyu Yao (20937336),
[*h39yao@uwaterloo.ca*](mailto:h39yao@uwaterloo.ca)\
Catherine Ye (20873615),
[*z222ye@uwaterloo.ca*](mailto:z222ye@uwaterloo.ca)\
Ashley Wu (20901849),
[*y845wu@uwaterloo.ca*](mailto:y845wu@uwaterloo.ca)\
Panzy Pan (20992671), [*y7pan@uwaterloo.ca*](mailto:y7pan@uwaterloo.ca)\
Lucy Sun (20958282), [*g33sun@uwaterloo.ca*](mailto:g33sun@uwaterloo.ca)

**Consultant**: Bill Bishop

**Date**: July 12, 2026

**Table of Contents**

[1. Introduction [2](#introduction)](#introduction)

[1.1 Motivation [2](#motivation)](#motivation)

[1.2 Project Objective [2](#project-objective)](#project-objective)

[1.3 Block Diagram [3](#block-diagram)](#block-diagram)

[2. System Specifications
[4](#system-specifications)](#system-specifications)

[2.1 Functional Specifications
[4](#functional-specifications)](#functional-specifications)

[2.2 Non-Functional Specifications
[5](#non-functional-specifications)](#non-functional-specifications)

[3. Detailed Design [5](#detailed-design)](#detailed-design)

[3.1 PL (FPGA) RX Market-Data and TX Order-Egress Subsystems
[5](#pl-fpga-rx-market-data-and-tx-order-egress-subsystems)](#pl-fpga-rx-market-data-and-tx-order-egress-subsystems)

[3.1.1 Overview and Specification Mapping
[5](#overview-and-specification-mapping)](#overview-and-specification-mapping)

[3.1.2 Engineering Design Process
[6](#engineering-design-process)](#engineering-design-process)

[3.1.3 Final Design Details
[8](#final-design-details)](#final-design-details)

[3.1.4 Specification Compliance Summary
[10](#specification-compliance-summary)](#specification-compliance-summary)

[3.2 PS (ARM OS Layer) Strategy & Risk Subsystem
[10](#ps-arm-os-layer-strategy-risk-subsystem)](#ps-arm-os-layer-strategy-risk-subsystem)

[3.2.1 Overview and Specification Mapping
[10](#overview-and-specification-mapping-1)](#overview-and-specification-mapping-1)

[3.2.2 Engineering Design Process
[11](#engineering-design-process-1)](#engineering-design-process-1)

[3.2.3 Final Design Details
[13](#final-design-details-1)](#final-design-details-1)

[3.2.4 Specification Compliance Summary
[16](#specification-compliance-summary-1)](#specification-compliance-summary-1)

[3.3 EOD Server Pipeline Subsystem
[16](#eod-server-pipeline-subsystem)](#eod-server-pipeline-subsystem)

[3.3.1 Overview and Specification Mapping
[16](#overview-and-specification-mapping-2)](#overview-and-specification-mapping-2)

[3.3.2 Engineering Design Process
[17](#engineering-design-process-2)](#engineering-design-process-2)

[3.3.3 Final Design Details
[19](#final-design-details-2)](#final-design-details-2)

[3.3.4 Specification Compliance Summary
[21](#specification-compliance-summary-2)](#specification-compliance-summary-2)

[3.4 Exchange Simulator Subsystem
[22](#exchange-simulator-subsystem)](#exchange-simulator-subsystem)

[3.4.1 Overview and Specification Mapping
[22](#overview-and-specification-mapping-3)](#overview-and-specification-mapping-3)

[3.4.2 Engineering Design Process
[23](#engineering-design-process-3)](#engineering-design-process-3)

[3.4.3 Final Design Details
[24](#final-design-details-3)](#final-design-details-3)

[3.4.4 Specification Compliance Summary
[25](#specification-compliance-summary-3)](#specification-compliance-summary-3)

[4. Discussion and Project Timeline
[26](#discussion-and-project-timeline)](#discussion-and-project-timeline)

[4.1 Evaluation of Final Design Against Objective and Specifications
[26](#evaluation-of-final-design-against-objective-and-specifications)](#evaluation-of-final-design-against-objective-and-specifications)

[4.2 Use of Advanced ECE Knowledge
[26](#use-of-advanced-ece-knowledge)](#use-of-advanced-ece-knowledge)

[4.3 Creativity, Novelty, and Elegance of the AQTA Design
[27](#creativity-novelty-and-elegance-of-the-aqta-design)](#creativity-novelty-and-elegance-of-the-aqta-design)

[4.4 Student Hours [27](#student-hours)](#student-hours)

[4.5 Potential Safety Hazards
[27](#potential-safety-hazards)](#potential-safety-hazards)

[4.6 Project Timeline [28](#project-timeline)](#project-timeline)

[References [29](#references)](#references)

# 1. Introduction

## 1.1 Motivation

Algorithmic trading systems are limited by end-to-end event latency:
market data must be decoded, converted into an order-book state (a
structured record of pending buy and sell orders), evaluated by a
strategy, checked for risk, and converted into an order message before
the opportunity disappears. A software-only implementation on a Linux
host adds kernel network-stack and scheduler overhead before any
strategy logic runs. Published FPGA-based systems quantify this cost: a
hardware datapath achieves roughly 4× lower latency than a software
pipeline \[1\], and a 10 Gigabit Ethernet FPGA system reaches 433 ns
from packet analysis to order trigger \[2\]. AQTA treats latency
elimination as the central design problem rather than a late-stage
optimization, using a hardware-software co-designed architecture in
which the deterministic, time-critical stages --- packet decoding and
order-book maintenance --- run in programmable logic (PL), while
strategy evaluation, logging, and overnight reconfiguration remain in
software. This follows the established rationale in the FPGA trading
literature: fixed, latency-critical operations belong in hardware, while
operations that change frequently belong in software.

## 1.2 Project Objective

The primary objective is to design and implement an ultra-low-latency,
hardware-accelerated algorithmic trading platform. By partitioning the
pipeline across programmable logic and an embedded processor, the system
targets deterministic microsecond-class tick-to-order latency ---
roughly 10 times faster than a software-only pipeline --- while
supporting operator-approved overnight strategy reconfiguration.

In the essential prototype, the PL performs market-data ingestion,
protocol decoding, and order-book maintenance to keep the time-critical
path deterministic, then passes the resulting order-book state to a
configurable strategy running on the ARM processing system (PS). The PS
selects among pre-loaded strategies and applies a RiskGuard filter (a
risk-management check on proposed orders); the validated decision then
returns to the PL, where it is encoded and transmitted back onto the
exchange link.

The secondary objective is an End-of-Day (EOD) optimization pipeline: it
classifies the next trading day\'s market regime from historical data,
searches a bounded parameter space for that regime\'s optimal strategy
configuration, and backtests the selected configuration before
presenting it to a human operator for approval. Only an approved
configuration is loaded for the next trading session.

**Prototype Scope and Constraints** The prototype is bounded to one
simulated exchange and one equity symbol, and defines a fixed-width
binary custom protocol for market data and order messages to keep the
PL-side decoder minimal and deterministic. It targets paper trading and
simulation only, not a live brokerage account. Together, these
constraints remove financial risk, multi-venue complexity, and
live-protocol dependencies, keeping the project focused on deterministic
hardware/software partitioning.

## 1.3 Block Diagram

![](media/image1.png){width="5.795833333333333in"
height="8.130555555555556in"}*Figure 1* shows the AQTA architecture and
distinguishes essential designed subsystems, optional designed
subsystems, and external dependencies. The central intraday path is the
FPGA PL and ARM PS loop; the overnight path is the server-side EOD
optimization pipeline.

*Figure 1: AQTA system block diagram showing designed subsystems and
external dependencies. **Note** the certain blocks (LLM part) were
temporarily deducted due to External Resources limitations.*

# 2. System Specifications

## 2.1 Functional Specifications

*Table 1* listed functional specifications, which describe required
system behaviors.

*Table 1: Functional Specifications and Verification Method*

  -----------------------------------------------------------------------------------------
  ID     Specification        Description                   Verification Method Essential
  ------ -------------------- ----------------------------- ------------------- -----------
  FS1    Packet-to-snapshot   Top-of-book snapshot readable Logic-analyzer      **Y**
         latency              by the PS within ≤ 1.5 μs of  timing from MAC RX  
                              packet arrival at the PL MAC. to                  
                                                            snapshot-register   
                                                            write, reference    
                                                            packet sequence.    

  FS2    Decision-to-order    Trading decision              PMU timing vs.      **Y**
         latency              (BUY/SELL/HOLD) produced and  Wireshark capture   
                              order packet transmitted      over 1000 updates.  
                              within                                            
                              $\leq \$`<!-- -->`{=html}30                       
                              μs of a top-of-book update,                       
                              99th percentile.                                  

  FS3    Order risk limits    Reject orders exceeding       One violating test  **Y**
                              configurable limits, with     order per limit,    
                              hard ceilings of: notional \> confirm REJECT +    
                              \$50,000 CAD; position \>     logged reason.      
                              1,000 shares; rate \> 1,000                       
                              orders/s; in-flight \> 100                        
                              --- a loaded configuration                        
                              may tighten these but never                       
                              exceed them.                                      

  FS4    Configurable startup Load an externally-supplied   Change config,      **Y**
                              strategy configuration before restart, confirm    
                              processing any market data.   active strategy via 
                                                            log.                

  FS5    Bounded activity     Persist trading activity      Stress test with    **Y**
         logging              within a bounded memory       \>10M ticks, no     
                              budget, no OOM under          OOM; export         
                              sustained operation,          contains one entry  
                              exportable for offline use.   per decision.       

  FS6    Regime               Classify next trading day\'s  Run on 6 months of  **Y**
         classification       regime into                   OHLCV data, confirm 
                              $\geq \$`<!-- -->`{=html}3    ≥ 3 regimes         
                              distinguishable states.       assigned.           

  FS7    Parameter search     Search                        Run twice on        **Y**
                              $\geq \$`<!-- -->`{=html}9    identical input,    
                              parameter combinations per    confirm             
                              regime, select the one        bit-identical       
                              maximizing a defined metric   output.             
                              (e.g. Sharpe).                                    

  FS8    Human-approved       A new strategy configuration  Confirm no          **Y**
         deployment           is not loaded into the live   transmission to SoC 
                              system without explicit       before manual       
                              operator approval.            approval.           

  FS9    Live status output   Real-time order-book/decision Confirm console +   **N**
                              report via Debug UART,        log output during   
                              printed to console and logged an active session.  
                              to file.                                          

  FS10   EOD pipeline logging Log pipeline stage,           Run full cycle,     **N**
                              classified regime, selected   confirm one log     
                              strategy/parameters, backtest entry per stage     
                              Sharpe, and approval status   transition.         
                              as each stage completes.                          

  FS11   Order packet format  Fixed-length binary format    Parse a captured    **Y**
                              with order ID, symbol, side,  packet against the  
                              quantity, and price,          documented layout.  
                              documented as a standalone                        
                              protocol spec.                                    

  FS12   In-flight order      Track state of every          Drive in-flight     **Y**
         tracking             in-flight order, up to 100    count to the limit, 
                              concurrent, without           confirm correct     
                              corruption or loss.           state via log       
                                                            inspection.         
  -----------------------------------------------------------------------------------------

## 2.2 Non-Functional Specifications

*Table 2* listed non-functional specifications on performance, cost, and
implementation constraints.

*Table 2: Non-Functional Specifications and Verification Method*

  ----------------------------------------------------------------------------------------
  ID     Specification   Description                   Verification Method     Essential
  ------ --------------- ----------------------------- ----------------------- -----------
  NFS1   End-to-end      Total latency from MAC RX to  Logic-analyzer          **Y**
         latency         MAC TX                        measurement on a        
                         $\leq \$`<!-- -->`{=html}50   reference loopback      
                         μs typical.                   packet.                 

  NFS2   Link            Zero unexplained frame drops  Wireshark capture,      **Y**
         reliability     over a 10-minute continuous   confirm frame count.    
                         test window.                                          

  NFS3   Hardware cost   Physical components (excl.    Sum itemized purchase   **Y**
                         SoC board, host PC, monitors) receipts.               
                         $\leq \$\$1,000 CAD total.                            

  NFS4   Session         Runs a full 6.5-hour          Full-session run,       **Y**
         stability       simulated session without     inspect logs for fatal  
                         crash, hang, or unrecovered   errors.                 
                         error.                                                

  NFS5   EOD pipeline    Full EOD pipeline (ingestion  Timed run on 1 year of  **N**
         runtime         → classification →            reference OHLCV data.   
                         optimization → approval                               
                         prompt) completes within 30                           
                         minutes.                                              

  NFS6   Resource        \< 75% LUTs and \< 85% Block  Vivado                  **Y**
         utilization     RAMs on XC7Z020, timing       utilization/timing      
                         closure at 125 MHz.           reports, WNS \> 0 ns    
  ----------------------------------------------------------------------------------------

# 3. Detailed Design

This design comprises five open-ended subsystems: PL RX for market-data
ingest, parsing, book maintenance, and snapshot publication; PL TX for
PS handoff and order-packet transmission; PS Strategy & Risk for
isolated-core decisions, Risk Guard, and in-flight state; EOD Server
Pipeline for offline adaptation and approved configuration generation;
and Exchange Simulator for deterministic replay, capture, and
validation.

## 3.1 PL (FPGA) RX Market-Data and TX Order-Egress Subsystems 

### 3.1.1 Overview and Specification Mapping

This section contains two tightly coupled PL subsystems inside the
single FPGA market-data path: the RX Ingress and Book-Builder Subsystem,
and the TX Order-Egress and PS Interface Subsystem. Both are implemented
on the AMD Xilinx Zynq-7000 (XC7Z020CLG400-21) fabric, but they have
separate ownership boundaries: RX owns wire-to-snapshot market-data
processing, while TX owns order egress and FS11 packet encoding.

The RX subsystem terminates the point-to-point Gigabit Ethernet feed,
validates and parses custom UDP market-data packets, maintains the
10-level bid/ask book, and publishes top-of-book snapshots plus SEQ
atomically to the PS. The TX subsystem samples risk-validated order
fields from the PS only after the DOORBELL write, encodes the
fixed-width order payload, and transmits it through TEMAC TX. The two
subsystems share the TEMAC, AXI-Lite register bank on M_AXI_GP0,
diagnostic counters, and NFS6 resource envelope, but the RX read-side
contract and TX write-side contract remain distinct. Specifications are
listed below in *Table 3*.

*Table 3: PL Subsystem Specification Ownership and Mapping*

  ---------------------------------------------------------------------
  Spec          Role of PL subsystem
  ------------- -------------------------------------------------------
  FS1           RX subsystem owner: packet arrival → decoded
                top-of-book snapshot available to PS in ≤ 1.5 μs.

  FS11          TX subsystem owner: risk-approved PS order fields are
                encoded into the fixed-length binary order packet.

  NFS1          Combined hardware latency: RX decode plus TX encode are
                the bounded PL contributions to the ≤ 50 μs end-to-end
                budget.

  NFS2          RX owns frame-count/drop observability; shared
                diagnostics expose parse, FCS, out-of-window, and
                TX-backpressure counters.

  NFS6          Shared resource envelope: RX book-builder, TX encoder,
                TEMAC, and AXI-Lite logic remain within LUT/BRAM
                limits.

  Fault Path    RX drops FCS-failed frames; TX exposes
                ready/backpressure state; both surface localized
                diagnostic counters.
  ---------------------------------------------------------------------

![图形用户界面, 应用程序, 表格 AI
生成的内容可能不正确。](media/image2.png){width="7.456692913385827in"
height="1.9921259842519685in"}*Figure 2* shows the PL block structure,
Tx path, Rx path and the shared AXI-Lite register at the PS boundary.

*Figure 2: FPGA PL packet processing pipeline and target cycle budget.*

### 3.1.2 Engineering Design Process

#### Decision 1 --- MAC Layer Implementation: Vendor IP vs. Minimal Custom MAC

Development speed is the binding constraint because the pipeline cycle
budget closes comfortably. Pre-verified vendor IP minimizes verification
loop iterations, as evaluated in the decision matrix shown in *Table 4*.

*Table 4: Weighted Design Decision Matrix for MAC Layer Selection*

+------------------+--------------------------+------------------------+
| Criterion        | Xilinx TEMAC IP          | Minimal custom MAC     |
| (weight)         | (selected)               |                        |
+==================+:=========================+:=======================+
| Development &    | **5** (Low               | **2** (High --- custom |
| verification     | ---pre-verified vendor   | preamble/FCS designed  |
| effort (40%)     | IP, wizard-generated)    | from scratch)          |
+------------------+--------------------------+------------------------+
| Resource cost    | **2** (Medium-high ---   | **5** (Low --- minimal |
| (20%)            | multi-thousand LUT       | RX/TX framing and CRC  |
|                  | baseline footprint)      | only)                  |
+------------------+--------------------------+------------------------+
| Latency          | **3** (Medium ---        | **5** (High --- zero   |
| determinism      | bounded,                 | unused feature logic   |
| (20%)            | datasheet-specified      | overhead)              |
|                  | pipeline delay)          |                        |
+------------------+--------------------------+------------------------+
| Protocol         | **5** (High --- robust   | **2** (Low --- limited |
| generality (20%) | standard interface       | point-to-point link    |
|                  | ecosystem)               | only)                  |
+------------------+--------------------------+------------------------+
| Weighted result  | **4.0 --- Selected**     | 3.2                    |
|                  |                          |                        |
| (1.0--5.0 scale) |                          |                        |
+------------------+--------------------------+------------------------+

- **Resource Envelope Analysis (NFS6):** Per Xilinx PG051, the Tri-Mode
  Ethernet MAC utilizes ≈1,500 registers, ≈3,000 LUTs, and 3 BRAM blocks
  for streaming FIFOs. The XC7Z020 resource profile safely absorbs this
  footprint.

- **Latency Impact:** The core introduces a deterministic pipeline delay
  of $\approx 20$ clock cycles during RGMII DDR capture ($\approx 160$
  ns at 125 MHz), accounted for in Decision 2.

#### Decision 2 --- Parse Architecture: Store-and-Forward vs. Cut-Through Streaming Parse

- **Line-Rate Throughput Analysis:** For a 24-byte payload, the maximum
  theoretical packet rate over a 1 Gbps link is derived as:

> $$\text{Frame} = 8\ \left( \text{Preamble} \right) + 14\ \left( \text{Ethernet} \right) + 20\ \left( \text{IPv4} \right) + 8\ \left( \text{UDP} \right) + 24\ \left( \text{Payload} \right) + 4\ \left( \text{FCS} \right) + 12\ \left( \text{IFG} \right) = 90\ \text{bytes} = 720\ \text{bits}$$
>
> $$\text{Line~Rate~Saturation~Limit} = 10^{9}\ \text{bits/sec} \div 720\ \text{bits} = 1,388,888\ \text{packets/second}$$
>
> Store-and-forward buffering adds a 560 ns serialization penalty (70
> bytes post-preamble streaming at 1 octet/cycle), consuming over a
> third of the latency budget.

- **Latency Path Decomposition (FS1):** Cut-through parsing permits
  deterministic bit-slicing concurrently with line arrival. The
  step-by-step logic latency totals 77 clock cycles (616 ns) at 125
  MHz: (1) Frame reception streaming: 560 ns (70 bytes), (2) FCS
  validation latch: 16 ns, (3) Tournament compare network reduction: 32
  ns, and (4) Register bank synchronization: 8 ns.

Sensitivity Analysis against FS1 (1.5 µs / 1500 ns ceiling):

> Optimistic Ingest ($100\ \text{ns }$MAC delay):
> $616\ \text{ns} + 100\ \text{ns} = 716\ \text{ns}$ (**52% Safety
> Margin**).
>
> Pessimistic Ingest ($400\ \text{ns }$MAC delay):
> $616\ \text{ns} + 400\ \text{ns} = 1,016\ \text{ns}$ (**32% Safety
> Margin**).

- **Commit Policy:** Fields are held in staging registers and commit to
  the book only upon an Ethernet Frame Check Sequence (FCS) pass signal.
  If the FCS fails, the frame is discarded and parse_error increments.

#### Decision 3 --- Order Book Storage: BRAM-Indexed Structure vs. Fixed Register Array

**Resource Footprint Projections (NFS6):** Hashing prices into Block RAM
(BRAM) incurs fragmentation and address-lookup pipeline stalls at small
depths. Because the prototype scope is bounded to a single symbol with a
10-level depth, a fixed flip-flop register array is selected.

This requires ≈ 1,500 registers (20 levels × 64 bits + snapshot 128
bits + counters) and ≈ 1,000 LUTs (implementing 20 parallel comparators
and a 9-compare tournament reduction tree). This design achieves
parallel combinational best-price extraction within a single 8 ns clock
edge (125 MHz), ensuring timing closure ($WNS > 0ns$) while utilizing 0
BRAM blocks. The complete gate-level resource utilization predictions
are tabulated in *Table 5*. Updates outside the 10-level window are
tracked via the dropped_out_of_window diagnostic counter.

*Table 5: Gate-Level Hardware Resource Footprint Projections (XC7Z020 /
NFS6)*

  ----------------------------------------------------------------------------------------------------------------
  Component          Flip-Flop (FF) Estimate  Look-Up Table (LUT) Estimate                Block RAM (BRAM)
  ------------------ ------------------------ ------------------------------------------- ------------------------
  Order Book         $1,500$ registers        $1,000$ LUTs (20 comparators)               0 blocks
  Register Logic                                                                          

  Xilinx TEMAC Core  $1,500$ registers        $3,000$ LUTs (datasheet base)               3 blocks (internal
                                                                                          buffers)

  Slicing & Header   $500$ registers          $1,000$ LUTs (combinational masks)          0 blocks
  Decoders                                                                                

  AXI-Lite Slave     $500$ registers          $800$ LUTs (address decoding)               0 blocks
  Interface                                                                               

  Projected          $\mathbf{4,000}$ **FFs   $\mathbf{5,800}$ **LUTs                     $\mathbf{3}$ **Blocks
  Footprint Totals   (**$\mathbf{4\%}$**)**   (**$\mathbf{11\%\ }\text{of~device}$**)**   (**$\mathbf{3\%}$**)**
  ----------------------------------------------------------------------------------------------------------------

### 3.1.3 Final Design Details

#### 3.1.3.1 RX Ingress and Book-Builder Subsystem

The RX subsystem is the left-to-right market data ingest lane in *Figure
2*. It runs at 125 MHz and converts an accepted Ethernet frame into a
coherent top-of-book snapshot for the PS. Its FS1 evidence is the
77-cycle (616 ns) cut-through logic path; its NFS2/fault evidence is the
FCS-gated commit and localized drop counters. Here are 5 main stages:

1.  **MAC RX (Xilinx TEMAC)**: Captures RGMII DDR data, aligns
    preambles, tracks FCS, and filters non-matching destination MAC
    addresses out of the AXI4-Stream interface.

2.  **IP/UDP Header Parse**: Validates EtherType (0x0800), IP protocol
    (17), destination IP, and UDP port at fixed byte offsets. UDP
    checksums are bypassed because this point-to-point link relies on
    Ethernet FCS for payload integrity.

3.  **Protocol Decode**: Slices the custom incoming payload into staging
    registers in real time.

4.  **Commit Gate**: Commits the staged event on a TEMAC tuser
    frame-good signal at tlast. If frame-bad asserts, the frame is
    dropped and parse_error increments.

5.  **Order Book Update**: Maps the committed event into the target
    price level. Combinational reduction extracts the new top-of-book,
    then commits snapshot fields and increments SEQ in one PL clock
    edge.

#### 3.1.3.2 TX Order-Egress and PS Interface Subsystem

The TX subsystem is the right-to-left PL order-egress lane in *Figure
2*. It starts after the PS Strategy/Risk subsystem writes a
risk-approved order through the AXI-Lite register bank, keeping strategy
and risk decisions in software while packet construction and
transmission remain deterministic hardware operations. The TX path has
five stages:

1.  **Order Register Write:** PS writes the approved order fields
    through AXI-Lite, checks TX_READY, and writes DOORBELL last.

2.  **Order Field Latch:** PL samples the order fields triggered by
    DOOLBELL, creating stable order commands.

3.  **Custom Payload Build:** The latched fields are packed into the
    fixed-format FS11 order payload defined in *Table 7* below.

4.  **TX Frame Build:** The payload is combined with
    Ethernet/IP/UDP-like header fields to form the complete TX frame.

5.  **Ethernet Transmit:** Xilinx TEMAC sends the frame through the
    RGMII TX interface as an order packet to the Exchange Simulator.

The estimated TX lane latency is about **0.65 μs**, making it a bounded
hardware tail of the NFS1 path rather than the dominant latency source.

#### 3.1.3.3 Shared PL/PS Boundary and Cross-Lane Contracts

The shared boundary is one AXI-Lite slave register bank on M_AXI_GP0,
but the two contained subsystems use disjoint roles within it. RX owns
the read-side snapshot registers and SEQ publications; TX owns the
write-side order registers, DOORBELL launch strobe, and TX_READY
control. This keeps the physical interface compact without blurring
subsystem ownership.

The RX contract is "snapshot plus SEQ is coherent after a single-clock
commit." The TX contract is "order fields are sampled only on DOORBELL
after payload writes." Diagnostic counters are shared observability:
parse_error, fcs_fail, dropped_out_of_window, and tx_backpressure let
the PS distinguish RX data-quality faults from TX egress backpressure.

#### 3.1.3.4 Packet and Register Contracts

The RX and TX paths use fixed-width binary contracts so the PL logic and
host-side validation tools can parse every field deterministically. Both
directions use the same integer-cent price convention, avoiding
floating-point conversion inside the PL datapath.

*Table 6* defines the fixed RX market-data payload for the parser and
book-builder. *Table 7* defines the TX order-egress payload for FS11,
where RiskGuard-approved AXI-Lite fields are latched and encoded by the
PL. *Table 8* summarizes the bid/ask book registers, top-of-book
snapshot, and diagnostic counters.

*Table 6: RX Ingress and Book-Builder Subsystem Input Payload Contract*

  --------------------------------------------------------------------------
  Field      Bit       Width       Protocol Encoding & Meaning
             offset    (bits)      
  ---------- --------- ----------- -----------------------------------------
  msg_type   0         8           0x01 = Add, 0x02 = Modify, 0x03 = Delete

  symbol     8         16          Numeric symbol identifier for single
                                   equity (constant = 1)

  price      24        32          Unsigned fixed-point integer representing
                                   cents

  qty        56        32          Unsigned share quantity; absolute volume
                                   for Modify commands

  side       88        8           0x01 = Bid, 0x02 = Ask

  order_id   96        32          Unique transaction identifier within the
                                   simulator session

  seq_num    128       32          Monotonic sequence tracker for drop
                                   accounting (NFS2)

  pad        160       32          Reserved padding fields (hardcoded to
                                   0x00)
  --------------------------------------------------------------------------

*Table 7: TX Order-Egress and PS Interface Subsystem Output Packet
Contract (FS11)*

  --------------------------------------------------------------------------
  Field      Bit       Width       Protocol Encoding & Meaning
             offset    (bits)      
  ---------- --------- ----------- -----------------------------------------
  order_id   0         32          Client-assigned tracking identifier
                                   forwarded to the exchange

  symbol     32        16          Numeric equity asset identifier (constant
                                   = 1)

  side       48        8           0x01 = Buy, 0x02 = Sell

  qty        56        32          RiskGuard-validated outbound order size

  price      88        32          Executable order price mapped to integer
                                   cents

  pad        120       8           Formatting padding field (hardcoded to
                                   0x00)
  --------------------------------------------------------------------------

*Table 8: Order Book Register Sizing & Diagnostic Layout*

  -----------------------------------------------------------------------------
  Register      Entries   Fields per entry             Structural Purpose
  group                                                
  ------------- --------- ---------------------------- ------------------------
  Bid book      10        price_cents (32b),           Tracks highest active
                          aggregate_qty (32b)          bid levels

  Ask book      10        price_cents (32b),           Tracks lowest active ask
                          aggregate_qty (32b)          levels

  Top-of-book   1         best_bid_price,              Committed atomically to
  snapshot                best_bid_qty,                AXI-Lite register bank
                          best_ask_price, best_ask_qty on every tick

  Diagnostic    4+        parse_error, fcs_fail,       NFS2/ fault-handling
  counters                dropped_out_of_window,       path system
                          tx_backpressure              observability
  -----------------------------------------------------------------------------

### 3.1.4 Specification Compliance Summary

The final verification metrics and traceability status for each owned PL
specification are summarized in *Table 9*.

*Table 9: Subsystem Traceability and Core Specification Compliance*

  ---------------------------------------------------------------------------
  Spec   How the final design satisfies  Verification Metric       Status
         it                                                    
  ------ ------------------------------- --------------------- --------------
  FS1    Cut-through stream parsing      Logic-analyzer trace      **Y**
         completes updates in 77 cycles, from MAC valid to     
         leaving a 32% worst-case timing register latch.       
         margin.                                               

  FS11   Egress formatting matches       Wireshark inspection      **Y**
         *Table 7* byte-offsets          of simulated order    
         hardcoded into sequential       frame.                
         register arrays.                                      

  NFS1   Hardware RX (0.61 µs) and TX    Synchronized hardware     **Y**
         (0.65 µs) paths consume less    timestamp capture     
         than 3% of total system budget. loop.                 

  NFS6   Gate-level footprints map to    Vivado                    **Y**
         approximately 11% of LUTs and   post-implementation   
         3% of BRAM on the XC7Z020.      utilization report.   
  ---------------------------------------------------------------------------

## 3.2 PS (ARM OS Layer) Strategy & Risk Subsystem

### 3.2.1 Overview and Specification Mapping

The PS subsystem is the software half of the intraday trading loop on
the selected XC7Z020 Zynq-7000 device, whose family provides a dual-core
ARM Cortex-A9 processing system \[3\]. It follows the 3.1 partition: PL
owns wire-speed determinism; PS owns session-to-session changeability.
Core 1 is isolated for the hot path (poll snapshot registers, evaluate
strategy, apply Runtime Risk Guard, write order fields/doorbell); core 0
handles configuration, log drain/export, Debug-UART reporting, and
supervision. The complete specification ownership breakdown is displayed
in *Table 10*.

*Table 10: PS Subsystem Specification Ownership and Mapping*

  ----------------------------------------------------------------------------
  Spec         Role of PS subsystem
  ------------ ---------------------------------------------------------------
  FS2          Sole owner of the software segment: observed snapshot update →
               decision (BUY/SELL/HOLD) → order handed to PL, inside the ≤ 30
               μs budget.

  FS3          Sole owner: reject orders violating notional (\> \$50,000 CAD),
               position (\> 1,000 shares), rate (\> 1,000 orders/s), or
               in-flight (\> 100) limits, with logged reason codes.

  FS12         Sole owner: track every in-flight order\'s state for the traded
               symbol, up to the configured capacity, and expose terminal
               outcomes to the logger.

  FS4          Sole owner: load and validate the externally supplied strategy
               configuration before any market data is processed.

  FS5          Sole owner: bounded-memory persistence of
               decisions/outcomes/snapshots over \> 10 M injected ticks, plus
               full-session export.

  FS9          Owner of the SoC side: real-time book/decision report over
  (non-ess.)   Debug UART.

  NFS1         Owns the dominant software segment of the ≤ 50 μs typical
               budget.

  NFS4         Primary owner: 6.5-hour session with no crash/hang/unrecovered
               error.
  ----------------------------------------------------------------------------

![](media/image3.png){width="6.425694444444445in"
height="2.9298611111111112in"}*Figure 3* shows the overall PS runtime
structure. Important detailed design will be introduced in 3.2.3.

*Figure 3: ARM PS Strategy processing within two cores*

### 3.2.2 Engineering Design Process

Three significant design decisions shaped this subsystem.

#### Decision 1 --- Hardware/software boundary: strategy in PL vs. strategy in PS

The selected design places the strategy logic in the PS. Strategy
formulas, thresholds, and the active strategy identity change nightly
via the EOD JSON config, so a PL implementation would require hours of
re-synthesis per change and would be incompatible with the EOD cycle.
FPGA trading literature supports moving fixed protocol-processing
primitives into hardware \[1\], \[4\], while this prototype keeps the
changeable alpha logic in software. The FS2 latency budget still closes
under this choice: FS2 caps the software path at 30 μs, and at the
selected \`-2\` speed-grade Cortex-A9 frequency of 766 MHz \[3\], the
selected path is budgeted at no more than about 5 μs. The Runtime Risk
Guard contributes only about 25--30 cycles, far below 0.1 μs, leaving no
latency-driven case for moving risk checks or strategy logic into PL.

#### Decision 2 --- Operating environment: bare-metal vs. Linux vs. Linux with core isolation

The trade-off matrix supporting this operating environment selection is
compiled in *Table 11*.

*Table 11: Operating Environment Trade-Off Analysis.*

  ------------------------------------------------------------------------
  Criterion (weight)        Bare-metal (both      Linux (selected)
                            cores)                
  ------------------------- --------------------- ------------------------
  Hot-path determinism      Best                  Poor: scheduler jitter
  (30%)                                           on the hot path

  TCP/IP, filesystem, UART  None --- must port a  Full, native
  tooling for FS4/FS5/FS9   network stack for the 
  (30%)                     PS GbE paths          

  Team development & debug  High                  Low: standard toolchain,
  cost (25%)                                      matches team\'s
                                                  embedded-Linux
                                                  experience

  NFS4 6.5-hour robustness  All failure handling  Mature, observable
  path (15%)                hand-rolled           (logs, watchdogs)

  Weighted result (1--5     2.6                   **4.1 (Selected)**
  scale)                                          
  ------------------------------------------------------------------------

Linux is selected only with the explicit constraint that the hot path
does not run as ordinary scheduled userspace. Core 1 is removed from
normal scheduling with isolcpus, which Decision 3 relies on; core 0
keeps Linux\'s filesystem, network, logging, and UART advantages for
FS4/FS5/FS9/NFS4. The target image is PetaLinux because the
implementation is board-specific; the design depends on Linux services
and CPU isolation, not on PREEMPT_RT, because the isolated core is
designed not to re-enter the scheduler during the hot path.

#### Decision 3 --- Hot-path interface and event delivery: interrupt + DMA ring vs. busy-poll register bank

FS2 caps the software path at 30 μs. The selected design must therefore
avoid any wakeup path whose latency is comparable to the whole budget,
leading to the trade-offs detailed in *Table 12*.

*Table 12: Hot-Path Interface and Event Delivery Alternatives.*

  -----------------------------------------------------------------------
  Alternative       Implementation cost        Outcome
  ----------------- -------------------------- --------------------------
  Interrupt + DMA   DMA IP + driver +          Rejected: interrupt wakeup
  ring              coherency                  alone risks consuming most
                                               of the budget

  Busy-poll +       Wizard-generated AXI-Lite  Selected
  register bank +   slave; zero driver, zero   
  doorbell          coherency                  
  -----------------------------------------------------------------------

Linux IRQ-to-userspace wakeup is treated as 10-40 μs: even the
optimistic end consumes one third of FS2 before strategy logic begins.
This is consistent with the broader low-latency pattern: Leber et al.
identify context switching as a central software-latency cost \[1\], and
Morris et al. use polling for host-side market data \[4\]. Core 1
therefore busy-polls SEQ over M_AXI_GP0 instead of sleeping.

DMA also loses its main benefit once a core is already dedicated to
waiting: the snapshot is only 16-24 B, so bulk transfer hardware adds
driver/coherency work without raising the strategy\'s processing
ceiling. The PL exposes a register snapshot plus SEQ; egress is
symmetric, with payload fields written first and DOORBELL last.

30 μs is about 23,000 cycles at the board\'s 766 MHz Cortex-A9 frequency
\[5\]. Allowing about 1 μs for the PL egress tail leaves about 29 μs for
software, resulting in the tight software timing margins estimated in
*Table 13*.

*Table 13: Estimated Core 1 Software Latency Budget.*

  ----------------------------------------------------------------------------
  Stage                 Estimate        Basis
  --------------------- --------------- --------------------------------------
  Detect new SEQ        \~0.15 to 0.3   AXI-Lite read via GP0
                        μs              

  Snapshot read         \~1 to 1.8 μs   4 to 6 field reads + seqlock re-read

  Strategy evaluation   $\leq \$\~1 μs  Hundreds of integer ops on O(1) state

  Runtime Risk Guard    ≪ 0.1 μs        \~25 to 30 cycles
                                        (multiply-shift-saturate)

  Logger record write   $\leq \$\~0.5   Fixed 128 B struct copy into cached
                        μs              ring

  Order-field writes +  \~0.5 to 1 μs   AXI-Lite posted writes (5 GP writes)
  doorbell                              

  Software Total        $\leq \$**\~5   **≥ 5.5× margin against the \~29 μs
                        μs**            software share**
  ----------------------------------------------------------------------------

The same arithmetic explains why conflation is acceptable for the
current prototype. Snapshot reads observe at roughly 500-670 K
snapshots/s and full decision iterations run at over 200 K decisions/s,
while the wire ceiling from 3.1 Decision 2 is 1.389 M ticks/s. The CPU,
not the register interface, is the bottleneck; a DMA ring would mostly
queue stale ticks. The selected register path therefore keeps only the
latest snapshot. The boundary scalability thresholds and expected
operational paths under different workloads are detailed in *Table 14.*

*Table 14: Register-Based Interface Scalability Limits.*

  -----------------------------------------------------------------------
  Condition                   Register path conclusion
  --------------------------- -------------------------------------------
  Current spec: 1 symbol,     Adequate; \~1.5 to 2 μs/read with
  top-of-book, conflation     $\geq \$`<!-- -->`{=html}5x FS2 margin.
  acceptable                  

  Payload \> \~100 B/event,   Migrate to a GP-mapped dual-port BRAM
  e.g., 10-level depth        window.

  Per-tick consumption        DMA ring plus faster software consumer
  required, no conflation     required; out of prototype scope.
  -----------------------------------------------------------------------

TX contention is non-binding: FS3 caps orders at 1,000/s, while a packet
transmit is about 1 μs, giving roughly 1000x spacing margin. TX_READY is
retained as a correctness invariant rather than a performance mechanism.

### 3.2.3 Final Design Details

The final design follows one tick through the software path: the
register bank delivers the snapshot, the Strategy Engine decides, the
Runtime Risk Guard filters and tracks orders, the Config Loader supplies
all session parameters, and the Execution Logger records the result.

#### 3.2.3.1 The PL/PS register bank and access protocol (interface contract)

The entire intraday PL/PS boundary is one AXI-Lite slave in the PL,
mapped through a 32-bit PS-to-PL AXI master port (M_AXI_GP0 in the
Vivado design) on the Zynq interconnect \[6\]. This memory map, outlined
in *Table 15*, serves as the hard hardware-software interface contract.

*Table 15: PL/PS AXI-Lite Register Map and Access Contract.*

  -------------------------------------------------------------------------------
  Offset       Register               Dir (PS Semantics
                                      view)   
  ------------ ---------------------- ------- -----------------------------------
  0x00         SEQ                    R       Increments atomically with each
                                              snapshot commit; core 1 polls this

  0x04--0x10   BEST_BID_PRICE,        R       Feature Parameters (top-of-book
               BEST_BID_QTY,                  snapshot); extend if the Market
               BEST_ASK_PRICE,                Feature Builder emits more fields
               BEST_ASK_QTY                   

  0x14--0x18   TIMESTAMP_LO/HI        R       PL hardware timestamp of the
                                              committing packet

  0x20--0x2C   DIAG_PARSE_ERR,        R       NFS2 counters, read periodically by
               DIAG_FCS_FAIL,                 core 0
               DIAG_DROP_OOW,                 
               DIAG_TX_BACKPRESSURE           

  0x40--0x4C   ORD_SYMBOL_SIDE,       W       Order fields (FS11 source values)
               ORD_QTY, ORD_PRICE,            --- the block diagram\'s \"Trade
               ORD_ID                         Decision\" arrow. ORD_SYMBOL_SIDE
                                              packs symbol in bits \[15:0\] and
                                              side in bits \[23:16\] (bits
                                              \[31:24\] reserved = 0), matching
                                              their widths in Table 7.

  0x50         DOORBELL               W       Write-1 launches the Order Emitter;
                                              **payload first, doorbell last**

  0x54         TX_READY               R       Egress flow-control invariant (see
                                              3.2.2)
  -------------------------------------------------------------------------------

PL commits are single-clock-edge atomic. PS-side multi-read consistency
is protected by a seqlock: read SEQ, read fields, re-read SEQ, and retry
if the value changed. Egress needs no lock because the PL samples order
fields only on the doorbell strobe.

#### 3.2.3.2 Strategy Engine (Plug-In Execution)

The engine is a table dispatch: the active strategy ID (from the FS4
config) indexes a function table; each strategy is a pure function of
(snapshot, rolling state, parameters) → {BUY, SELL, HOLD} + order
fields. Rolling state is fixed-size (e.g., a lookback ring of
midprices), so per-tick cost is O(1) and independent of session length.
The core operating rules mapped to each identified market regime are
summarized in *Table 16*.

*Table 16: Runtime Strategy Mapping by Market Regime.*

  ------------------------------------------------------------------------
  Regime     Strategy     Core rule
  ---------- ------------ ------------------------------------------------
  Trending   Momentum     BUY/SELL from configured midprice lookback
                          delta.

  Ranging    Mean         Trade toward the configured moving-average
             Reversion    deviation band.

  Volatile   Defensive    Suppress entries, allow only position-reducing
                          orders toward flat.
  ------------------------------------------------------------------------

mid is held in half-cent units (best_bid + best_ask) so arithmetic
remains integer and bit-reproducible on the isolated core. Every window,
threshold, and position scalar loads from the FS4 JSON config using the
same parameter names swept in 3.3.3.3, so tuning never requires
recompilation. The design contribution is deterministic, reconfigurable
evaluation machinery; alpha selection belongs to the EOD sweep.

#### 3.2.3.3 Runtime Risk Guard (FS3)

The guard executes unconditionally after every non-HOLD decision in the
same thread as the strategy, so no order path can bypass it. Keeping the
guard in PS software also keeps FS3 limits EOD-configurable; a PL guard
would need its own writable-register interface. The software cost is
bounded at about 23-29 cycles: multiply/compare for notional,
add/compare for position, fixed-point token-bucket update for rate, and
one occupancy compare for in-flight count. At 766 MHz this is about
0.03-0.04 μs, under 0.1% of the FS2 budget, leaving no latency case for
hardware risk checks. *Table 17* itemizes the specific checks and
low-overhead mathematical mechanisms evaluated by the Risk Guard.

*Table 17: Runtime Risk Guard Checks and Mechanisms.*

  -------------------------------------------------------------------------------------
  Check       Rule                             Mechanism
  ----------- -------------------------------- ----------------------------------------
  Notional    qty × price $\leq$ \$50,000 CAD  32×32 → 64-bit multiply, one compare
              limit (configurable)             

  Position    abs(position ± qty) $\leq$ 1,000 Signed accumulate against local position
              shares                           state, range-checked against
                                               $\pm$`<!-- -->`{=html}1,000 (two
                                               compares)

  Rate        $\leq \$`<!-- -->`{=html}1,000   Token bucket with fixed-point refill; no
              orders/s                         divide on the hot path

  In-flight   in-flight count                  Compare against open-order table
              $\leq \$`<!-- -->`{=html}100     occupancy
  -------------------------------------------------------------------------------------

Core 1 maintains a fixed, pre-allocated open-order table of 100 entries
{order_id, side, qty, price, submit_timestamp, state} for the traded
symbol. The table is sized to FS12\'s 100-order tracking ceiling, while
the FS3 in-flight risk check rejects any order that would make the
in-flight count exceed 100 before insertion.

FS3 and FS12 both require the in-flight condition to be testable, so the
design fixes terminal timing with a PS-only modeled fill delay T. On
submission, an order enters the table as in-flight; after T, position
and the outcome log update, producing the FS5 execution-outcome record.
At 1,000 orders/s, T = 0.1 s drives the in-flight count to the 100-order
ceiling for verification. Rejections write reason-coded records and
never reach the doorbell. A configured rejection pattern, by default ≥ 3
REJECTs within 10 s, latches HOLD Mode until operator clearance; an EOD
"REJECT/No Approval" outcome uses the same latch. HOLD needs no PL
cooperation because it is simply the absence of a doorbell write.

#### 3.2.3.4 Config Loader (FS4)

Before core 1 polls, the loader validates the JSON schema, ranges,
strategy parameters, and risk limits, then populates the strategy table
and Risk Guard. Any failure is logged and prevents startup, so market
data processing is unreachable until a config commits.

#### 3.2.3.5 Execution Logger and Console (FS5, FS9)

Core 1 writes fixed 128 B decision/outcome/snapshot/reject/fault records
into a pre-allocated 256 MB cached-DDR ring, with no hot-path
allocation. Full per-tick logging fails: 1.389 M/s × 128 B ≈ 178 MB/s,
and 10 M ticks × 128 B = 1.28 GB. The selected policy logs all
decision/outcome/reject/fault records, rate-capped at 1,000/s by FS3,
plus 100 Hz snapshots and order-event snapshots. This contributes about
128 KB/s + 12.8 KB/s = 141 KB/s, so the 256 MB ring holds about 30
minutes at the worst-case decision rate while core 0 drains to eMMC,
exports over PS GbE, samples DIAG\_\*, and renders the FS9 1 Hz
Debug-UART feed.

### 3.2.4 Specification Compliance Summary

A structural trace of how the final software configuration fulfills the
targeted specifications is documented in *Table 18*.

*Table 18: PS Subsystem Specification Compliance Summary.*

  -------------------------------------------------------------------------
   Spec  How the final design satisfies it         Evidence status
  ------ ----------------------------------------- ------------------------
   FS2   Busy-poll isolated core + register reads; Analytical; pending
         $\leq \$\~5 μs software path vs. \~29 μs  PMU-instrumented
         share (3.2.2)                             1,000-tick run +
                                                   Wireshark

   FS3   Unbypassable in-thread Risk Guard; four   Pending four-violation
         checks + reason-coded log                 injection test

   FS4   Polling loop structurally unreachable     Pending config-swap
         until validated config commits            restart test

   FS5   Static allocation, decision-complete +    Analytical; pending 10
         sampled-snapshot ring, async flush        M-tick stress + export
         (3.2.3.5)                                 check

   FS12  Pre-allocated open-order table sized      Pending limit-saturation
         exactly to the FS3's in-flight ceiling;   injection test
         Risk Guard rejects at limit; modeled      
         terminal transitions (3.2.3.3)            

   FS9   Core-0 UART renderer off the shared ring  Pending live-session
                                                   check

   NFS1  FS2 path is the PS contribution; margin   Analytical
         *Table 3*                                 

   NFS4  Linux + isolated core, no hot-path        Pending 6.5 h soak
         allocation; HOLD Mode as safe state       
  -------------------------------------------------------------------------

## 3.3 EOD Server Pipeline Subsystem

### 3.3.1 Overview and Specification Mapping

The EOD (End-of-Day) Server Pipeline is AQTA\'s adaptation layer --- the
component that makes the system adaptive rather than a fixed-strategy
appliance. Running on a host server, off the intraday critical path, it
closes the loop between trading sessions: it ingests session history
from the PS along with historical daily OHLCV data
(Open-High-Low-Close-Volume, the standard daily price/volume summary),
classifies the next day\'s market regime (FS6), and re-optimizes that
regime\'s strategy parameters via exhaustive backtesting over a bounded
parameter grid (FS7). The result is assembled into a candidate JSON
configuration for operator approval; only an explicit approval reaches
the live system (FS8, sent to the PS Config Loader of 3.2.3.4), while
rejection or no response engages the PS HOLD latch of 3.2.3.3 until
cleared. Given the 30-minute budget in NFS5, the binding constraints
here are correctness, reproducibility, and auditability --- realized
through FS7\'s bit-identical re-runs and FS8\'s human veto --- which
drive every design decision below. This subsystem is directly
responsible for the specific functional targets listed in *Table 19*.

*Table 19: EOD Subsystem Specification Mapping.*

  ----------------------------------------------------------------------------
  Spec         Role of EOD subsystem
  ------------ ---------------------------------------------------------------
  FS6          Sole owner: classify the next trading day\'s regime into $\geq$
               3 distinguishable states from daily market data.

  FS7          Sole owner: search $\geq$ 9 parameter combinations for the
               regime\'s strategy and select the metric-maximizing one, with
               deterministic (bit-identical) output.

  FS8          Sole owner of the gate: no configuration reaches the live
               system without explicit operator approval. (The PS Config
               Loader in 3.2.3.4 owns the receiving end of the chain of
               custody.)

  FS10         Sole owner: display and log pipeline stage, regime, selected
  (non-ess.)   parameters, backtest Sharpe, and approval status as each stage
               completes.

  NFS5         Sole owner: full pipeline (ingestion → classification →
  (non-ess.)   optimization → approval prompt) within 30 minutes; input
               validation per 3.3.3.1.
  ----------------------------------------------------------------------------

Upstream dependency: FS5\'s exported session history and a historical
daily OHLCV dataset are the pipeline\'s inputs. The session history
comes from 3.4\'s replay-based simulator, which carries tick-level (L3)
events rather than daily bars, so it cannot be the OHLCV source; that
source is Yahoo Finance (free, no license required). Downstream
contract: the JSON configuration schema of 3.3.3.5, consumed by the PS
Config Loader --- jointly owned with 3.2.

![](media/image4.png){width="6.2952755905511815in"
height="0.8740157480314961in"}*Figure 4* below shows the pipeline
structure. Detailed design is introduced in 3.3.3.

*Figure 4: EOD Sequential Pipeline.*

### 3.3.2 Engineering Design Process

Three design decisions shaped this subsystem.

#### Decision 1 --- Execution environment: Python host pipeline

A scan of the open-source tooling landscape converged quickly: a Python
3 host pipeline --- pandas/NumPy for data handling, the standard library
for orchestration, the strategy kernel handled separately in 3.3.3.3.
Python has the deepest library ecosystem for this workload and the
lowest development cost of any realistic option, and NFS5\'s 30-minute
budget is generous enough that Python\'s performance profile is not
worth trading away for a faster language.

#### Decision 2 --- Regime classifier (FS6): rule-based thresholds vs. Hidden Markov Model

The classifier only routes tomorrow to one of three pre-built strategies
(3.2.3.2), not alpha generation, so the Hidden Markov Model (HMM)
favored by the regime-detection literature for its regime-persistence
accuracy \[7\] is rejected: FS6\'s verification only checks that
$\geq$`<!-- -->`{=html}3 regimes appear, never accuracy, so that
advantage is untested here; an HMM must also be iteratively fit rather
than computed by a fixed formula, is not guaranteed to converge
identically run-to-run, and adds an unfamiliar dependency (hmmlearn);
and its state posteriors require post-hoc labeling, undermining the FS8
operator-auditability requirement that a threshold rule such as \"vol \>
75% ⇒ Volatile\" satisfies by inspection in seconds. The two-feature
rule-based threshold classifier is therefore selected: unit-testable in
a day, deterministic, and directly auditable --- decisive given the
team\'s bandwidth already committed to 3.1/3.2.

A second iteration followed within the rule-based approach itself. The
first formulation used fixed cutoffs (e.g. \"vol \> 25% ⇒ Volatile\"):
simple, but capable of collapsing every day to one label on a calm
stretch that never crosses the constant --- violating FS6\'s
$\geq$`<!-- -->`{=html}3-regime requirement outright. Replacing the
fixed cutoffs with percentile thresholds closes this failure mode
structurally rather than by luck: the top 25% of days by volatility are
VOLATILE by definition, and TRENDING/RANGING split the rest, so a
single-label output becomes impossible, not just unlikely. This
percentile scheme is the design carried into 3.3.3.2.

#### Decision 3 --- Parameter search (FS7): exhaustive grid

The 27-point grid is enumerated exhaustively rather than searched with a
smarter method (e.g. Bayesian optimization): it is cheap enough to fully
evaluate (arithmetic below), a full sweep is deterministic by
construction --- which \"smart\" search isn\'t --- directly satisfying
FS7\'s bit-identical requirement, and it gives the operator the complete
result table for FS8 review rather than just the points a search
algorithm happened to sample.

**Runtime budget (NFS5).** NFS5 allows 30 minutes on the reference
workload (1 year of daily OHLCV). Every stage but the sweep is bounded
by trivial arithmetic:

> Regime path: 252 daily bars, O(n) feature computation → milliseconds\
> Classification: two percentile lookups + three comparisons, O(1) →
> microseconds\
> Sweep: 100 Hz × 6.5 h session = 2.34 M snapshot records; grid = 27
> points.\
> Each point is one vectorized NumPy/pandas pass over the 2.34 M-row
> array\
> (signal computation, position derivation, cumulative P&L) --- expected
> well\
> under 1 s/point on commodity hardware. Pessimistic allowance ≈ 1 min
> for\
> I/O and pandas overhead --- a \~50× cushion over that expectation, so
> the\
> NFS5 argument survives a large miss in the per-point estimate
> (wall-clock\
> confirmation is pending, 3.3.4).\
> Pipeline total (pessimistic): ≈ 1--2 min → ≥ 15× margin against
> NFS5\'s 30 min

This margin also licenses Decision 1 --- Python is fast enough, and
exhaustive search over the prototype\'s 27-point grid is affordable with
room to spare.

### 3.3.3 Final Design Details

The final design is a sequential staged pipeline program shown in
*Figure 4* above.

#### 3.3.3.1 Data import and Parameter Engineering

Inputs are validated before any computation: schema check,
monotonic-timestamp check, minimum-history check. The history floor is
calibration window + 126 trading days rather than a fixed number --- the
calibration window (config-adjustable) must sit entirely before the
earliest day classified, and FS6\'s own verification classifies a
6-month (126-day) span, so the floor can never be tighter than that.
Validation failure aborts --- no config from bad data.

Two features are computed from daily OHLCV closes, with their precise
operational definitions provided in *Table 20*.

*Table 20: EOD Regime Feature Definitions.*

  ------------------------------------------------------------------------------------------------------------------------------------------
  Feature        Definition                                                                             Window
  -------------- -------------------------------------------------------------------------------------- ------------------------------------
  Realized       $$\sigma = {std}\left( \ln\left( C_{t}/C_{t - 1} \right) \right) \times \sqrt{252}$$   20 trading days (matches the SMA₂₀
  volatility σ                                                                                          trend leg)

  Trend strength $$T = \frac{{SMA}_{5} - {SMA}_{20}}{{SMA}_{20}}$$                                      5- and 20-day SMAs
  T                                                                                                     
  ------------------------------------------------------------------------------------------------------------------------------------------

Both are standard constructions; the calibration scheme below (3.3.3.2)
is the real design contribution, with its non-degeneracy guarantee
proven in 3.3.2 Decision 2.

#### 3.3.3.2 Regime Detection (FS6)

> θ_vol = percentile(σ over calibration window, 75) \#
> config-adjustable\
> θ_trend = percentile(\|T\| over calibration window, 60) \#
> config-adjustable\
> if σ_today ≥ θ_vol: regime = VOLATILE → Defensive\
> elif \|T_today\| ≥ θ_trend: regime = TRENDING → Momentum\
> else: regime = RANGING → Mean Reversion

Pure function of the input window --- no state, no seed, no fit. Unit
tests cover all three branches plus both boundary equalities ("$\geq$"
resolves ties toward the safer, Defensive branch). Non-degeneracy over
FS6\'s $\geq$`<!-- -->`{=html}3-regime requirement follows structurally
from the percentile scheme --- see the threshold-iteration rationale in
3.3.2 Decision 2.

The classifier calibrates on a trailing window and applies the threshold
to the next, out-of-sample window, since a live system cannot compute a
threshold from data it hasn\'t seen yet.

#### 3.3.3.3 Strategy Reoptimize --- Backtest & Parameter Sweep (FS7)

Grid width follows each strategy\'s actual tunable levers rather than a
forced 3×3×3 shape: Momentum and Mean Reversion each expose three
independent parameters per their 3.2.3.2 core rule, but Defensive\'s
rule (\"suppress entries, allow only position-reducing orders toward
flat\") only has two --- a spread floor gating when reducing orders are
allowed to fire, and a position scalar setting how much to reduce by. A
third axis would not correspond to any real degree of freedom in that
strategy, so its grid is 3×3 = 9, still meeting FS7\'s
$\geq \$`<!-- -->`{=html}9-combination floor exactly rather than by
padding. The target sweep intervals for each feature parameters array
are configured according to *Table 21*. Grid values are specified in
decimal units below; the live intraday config carries their integer
half-cent equivalents per 3.2.3.2:

*Table 21: Strategy Parameter Sweep Grid.*

  -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
   Strategy                              Parameter 1                                                        Parameter 2                                                       Parameter 3                          Grid
                                                                                                                                                                                                                   size
  ----------- ----------------------------------------------------------------- -------------------------------------------------------------------- ------------------------------------------------------------- ------
   Momentum           $$\text{lookback} \in \left\{ 5,10,20 \right\}$$            $$\text{entry~threshold} \in \left\{ 0.005,0.01,0.02 \right\}$$     $$\text{position~scalar} \in \left\{ 0.5,1.0,1.5 \right\}$$  27

     Mean            $$\text{MA~window} \in \left\{ 10,20,50 \right\}$$          $$\text{deviation~threshold} \in \left\{ 0.01,0.02,0.05 \right\}$$   $$\text{position~scalar} \in \left\{ 0.5,1.0,1.5 \right\}$$  27
   Reversion                                                                                                                                                                                                       

   Defensive   $$\text{spread~floor} \in \left\{ 1,2,4 \right\}\text{~cents}$$      $$\text{position~scalar} \in \left\{ 0.25,0.5,1.0 \right\}$$                                  ---                              9
  -----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

The kernel replays the snapshot stream exported by the Execution Logger
(FS5) rather than synthetic bars, so the sweep evaluates strategies on
the data distribution the deployed strategy will see. Bootstrap case (no
live sessions yet): the recorded LOBSTER replay session from 3.4 serves
as the initial corpus --- a single session, thin by construction,
growing as live sessions accumulate. The daily-OHLCV dataset feeds only
the regime path, not the sweep.

> for params in grid (fixed lexicographic order): \# determinism: fixed
> order\
> signals = compute_signal_array(snapshot_df, params) \# vectorized
> NumPy/pandas ops\
> positions = signals_to_positions(signals, params)\
> pnl_series = positions_to_pnl(positions, price_series)\
> metrics\[params\] = sharpe(pnl_series), max_drawdown(pnl_series),
> n_trades\
> select params\* = argmax over sharpe,\
> ties broken by lexicographic parameter order \# total order ⇒ unique
> winner

Fills are priced at the touch, with no queue or market-impact modeling.
Grid points are ranked by
$Annualized\ Sharpe\ ratio\ (assuming\ the\ riskfree\ rate\ is\ 0)\  = \frac{{mean}\left( \text{daily~P\&L} \right)}{{std}\left( \text{daily~P\&L} \right)} \times \sqrt{252}$
--- steady profit scores higher than the same profit earned
inconsistently.

**FS7 determinism.** FS7 requires bit-identical re-runs, not just
correct output. Every nondeterminism source is closed by construction:
no RNG (no fitted model or sampling, per Decisions 2--3), strictly
sequential evaluation over ordered-list grids with canonical
serialization (3.3.3.5), a single designated verification host (no
cross-machine float drift), and a lexicographic tie-break on equal
Sharpe. Verified by running the pipeline twice on the same input and
byte-comparing the output.

#### 3.3.3.4 Risk Analysis and config generation

A validation pass on the winning parameters, not another optimization
step. Three checks: (1) did this parameter set ever breach the hard risk
limits during the backtest (notional, position size, order rate --- the
same limits the PS enforces at runtime, 3.2.3.3)? (2) is the worst
peak-to-trough loss within bounds --- flagged if it exceeds \$25,000
CAD, half the FS3 notional ceiling? (3) is the result backed by enough
trades to be statistically meaningful --- a high Sharpe from only 2
trades isn\'t, so anything under 10 trades is flagged? None of these
checks are rejected automatically: a failed check is written into the
operator\'s report, and the operator decides.

#### 3.3.3.5 JSON configuration schema (jointly owned with 3.2.3.4)

The config file the pipeline produces records of which strategy and
regime were selected, the parameter values, the risk limits, audit
metadata on how the result was produced, and who approved it and when.
The target formatting of this export is constrained to the JSON schema
layout listed in *Table 22*.

*Table 22:* *Approved JSON Configuration Schema.*

  -------------------------------------------------------------------------------
  Field          Type     Content
  -------------- -------- -------------------------------------------------------
  strategy_id    string   momentum / mean_reversion / defensive

  regime_label   string   trending / ranging / volatile

  parameters     object   Swept winner\'s values, integer-encoded to match the PS
                          kernel. Keys per strategy --- momentum: lookback,
                          entry_thresh, pos_scalar; mean_reversion: window,
                          dev_thresh, pos_scalar; defensive: spread_floor,
                          pos_scalar (lockstep with 3.2.3.2 and the 3.3.3.3 grid
                          axes)

  risk_limits    object   max_notional_cad, max_position_shares, max_order_rate,
                          each ≤ its FS3 ceiling

  provenance     object   Data window, grid hash, backtest Sharpe, pipeline
                          version --- the FS10 record embedded for audit

  approval       object   operator_id, timestamp --- appended only by the
                          approval action (3.3.3.7)
  -------------------------------------------------------------------------------

#### 3.3.3.6 FS10 status reporting

Each stage logs entry/exit + key numbers via a shared wrapper. A failed
stage emits no config.

#### 3.3.3.7 Operator Approval and configuration transmission (FS8)

The operator reviews the full FS10 report and approves interactively.
Transmission cannot occur without that approval --- not because of a
skippable check, but because the send call exists only inside the code
path that runs after approval succeeds. Approving is the action that
triggers sending; if nobody approves, the send call is never reached.
That satisfies FS8 directly and is exactly what its verification checks
for.

Transport is a push over the PS GbE via scp to a staging path on the
SoC, from which the Config Loader ingests it at startup.

### 3.3.4 Specification Compliance Summary

*Table 23* provides a complete review of the EOD layer\'s target
validation metrics and procedural evidence status.

*Table 23:* *EOD Subsystem Specification Compliance Summary.*

  ------------------------------------------------------------------------------
  Spec         How the final design satisfies it             Evidence status
  ------------ --------------------------------------------- -------------------
  FS6          Percentile-thresholded two-feature            Closed by
               classifier; $\geq \$`<!-- -->`{=html}3        arithmetic; pending
               non-empty regimes provable by construction    6-month
               (3.3.3.2)                                     reference-data run

  FS7          Exhaustive fixed-order grid + deterministic   Analytical; pending
               vectorized kernel + total-order tie-break;    double-run
               all nondeterminism sources enumerated and     byte-compare
               closed (3.3.3.3)                              

  FS8          Transmission call structurally unreachable    Pending no-approval
               without operator approval --- the send has    injection test
               one caller, the approval prompt\'s success    
               branch (3.3.3.7)                              

  FS10         run_stage() wrapper logs every transition;    Pending full-cycle
  (non-ess.)   approval report aggregates                    log inspection
               regime/sweep/Sharpe/status                    

  NFS5         $\approx$ 1 to 2 min pessimistic total vs 30  Analytical; pending
  (non-ess.)   min budget; $\geq 15 \times$ margin (Decision reference-dataset
               3\'s runtime budget)                          wall-clock
  ------------------------------------------------------------------------------

## 3.4 Exchange Simulator Subsystem

### 3.4.1 Overview and Specification Mapping

The Exchange Simulator plays the exchange that the project deliberately
does not connect to (Section 1.2\'s paper-trading boundary). It runs on
the host PC at the far end of the point-to-point Gigabit Ethernet link:
it replays a real order-level trading day into the PL in the custom
protocol of *Table 6* and captures every order packet the SoC emits
(*Table 7*) for offline validation. While published FPGA systems
validate across three access tiers---exchange co-location \[8\], \[9\],
broker test servers \[2\], or laboratory injection setups \[10\],
\[11\]---AQTA structurally targets the laboratory tier to respect the
capstone\'s paper-trading boundary. Consequently, this subsystem must
self-supply the market data, counterparty, and measurement fixtures
provided by higher-tier environments. The resulting architecture is
deliberately lean: one real dataset, three short host scripts, and
Wireshark, with all correctness judgments executed offline. This makes
the simulator the project\'s principal verification instrument, sourcing
inputs for FS1, FS2, FS11, NFS2, and NFS4.

The complete matrix of architectural roles fulfilled by this testing
tool is mapped out in *Table 24.*

*Table 24:* *Exchange Simulator Specification Mapping.*

  --------------------------------------------------------------------------
  Spec          Simulator role
  ------------- ------------------------------------------------------------
  FS1, FS2      Instrument: reference packet sequences are fixed slices of
                the replay dataset; the Replayer\'s TX log provides
                transmit-side timestamps.

  FS11          Oracle: the Offline Checker independently parses every
                captured order packet against the *Table 7* layout.

  NFS2          Peer: the other endpoint of the 10-minute zero-drop window;
                the expected frame count is a static property of the frame
                file.

  NFS4          Provider: replays the full 6.5-hour real session.

  FS6/FS7       Data source: the recorded replay session is the FS7 backtest
  (bootstrap)   bootstrap corpus (3.3.3.3); the regime path uses Yahoo daily
                OHLCV (3.3.1) instead.

  NFS3          Pure host software --- subsystem hardware cost is \$0 (the
                host PC is excluded from the cap).
  --------------------------------------------------------------------------

![](media/image5.png){width="4.863194444444445in"
height="3.8270833333333334in"}*Figure 5* shows the design structure of
this subsystem.

*Figure 5: Exchange Simulator Process, the Book Diff Result can be
output to console.*

### 3.4.2 Engineering Design Process

#### Decision 1 --- Market-data source: replay a real captured L3 trading day

The design trade-offs and selection outcomes regarding alternative
historical market data sources are evaluated in *Table 25*.

*Table 25:* *Market-Data Source Alternatives.*

  -----------------------------------------------------------------------
  Alternative        Outcome
  ------------------ ----------------------------------------------------
  Broker             **Rejected.** Broker APIs are cloud REST/WebSocket
  paper-trading      sessions --- they cannot terminate the
  counterparty       point-to-point PL GbE link or speak the custom UDP
                     protocol, so the PL path would be untestable. Live
                     data is also unrepeatable, so FS1/FS2 reference
                     sequences could not even be specified. And retail
                     APIs top out at L2 (aggregated price levels, no
                     order IDs \[12\]) while the protocol carries L3; the
                     literature obtains order-level data only through
                     member or institutional channels \[2\], \[13\].

  Synthetic          **Rejected.** Meets the protocol formats, but its
  order-flow         realism (rates, event mix, burst structure) would
  generator          itself need modeling and defense --- effort no
                     specification consumes.

  Replay of a real   **Selected.** Realism is free (the stream *is* a
  captured L3 day    real NASDAQ day), reproducibility is structural (a
  (selected)         fixed file), and one full 6.5 h session is exactly
                     what NFS4 needs.
  -----------------------------------------------------------------------

The academic LOBSTER dataset \[14\] provides the exact L3 order-level
NASDAQ data required. The AAPL day at 10 book levels matches the PL book
depth, and published FPGA order-book work has validated against this
same sample day \[15\]. Using the official AAPL sample day \[16\] offers
a free, deterministic, and highly realistic testing ground. Pushing the
full day (400,391 messages) through a design-time prototype successfully
validated the translation layer, measured real market rates (\~17 msg/s
average, \~2,400 msg/s peak burst), and resolved two protocol
ambiguities early (sub-penny rounding and Modify-semantics) prior to
hardware synthesis.

#### Decision 2 --- Execution model: validate-and-log, all judgment offline

The trade-offs among architectural execution models considered for the
verification pipeline are outlined in *Table 26*.

*Table 26:* *Simulator Execution Model Alternatives.*

  ----------------------------------------------------------------------
  Alternative                  Outcome
  ---------------------------- -----------------------------------------
  Full matching engine         **Rejected.** A large
  (received orders match       correct-by-construction artifact whose
  against the replayed flow    outputs no Section 2 spec consumes ---
  and produce fills)           and it would itself need a test bench.

  Paced replay +               **Selected.** The replayed stream is
  validate-and-log (selected)  never altered by received orders; every
                               received packet is captured with a
                               timestamp and checked offline against the
                               FS11 layout.
  ----------------------------------------------------------------------

A full matching engine is redundant because fill timing (delay T) and
order disposition are already modeled on the PS side by the Risk Guard
and open-order table (3.2.3.3, FS12). Furthermore, with FS3 capping
orders at 1,000 shares against a highly liquid book, market impact is
negligible. Therefore, the replayed stream remains unaltered, and
received orders are strictly captured for offline validation. Because
all intelligence is pushed to the preprocessor and offline checkers, the
live path is reduced to a paced sendto loop and a recvfrom logger. Rate
arithmetic confirms a Python script easily suffices:

> real day, worst burst \~2,400 msg/s (measured, Decision 1)\
> replay script, max send \~91,000 msg/s (measured)\
> PS decision ceiling \~200,000 /s (analysis, 3.2 Decision 3)\
> PL wire ceiling \~1.39 M pkt/s (arithmetic, 3.1.2)

The sender is the bottleneck, and that is the right place for it: the
script clears the worst real burst with a \~38× margin, no rate this
subsystem can produce stresses the PL, and the PS can keep up with every
tick at any replay speed.

### 3.4.3 Final Design Details

#### 3.4.3.1 Components and artifacts

- **Dataset Preprocessor (offline, once per slice).** Translates LOBSTER
  records into protocol-compliant bytes at \~1 M msg/s. It applies the
  agreed semantics (integer-cent rounding, absolute remaining quantity),
  primes the initial book state, and enforces structural invariants
  (e.g., preventing negative quantities). It yields two deterministic
  artifacts:

- **Frame file** --- the slice pre-encoded into *Table 6* payloads, each
  frame keeping its original NASDAQ timestamp for pacing.

- **Expected-book file** --- per-message top-of-book, derived from
  LOBSTER\'s own orderbook file with the same cent rounding applied.
  Exported PS snapshots carry the PL SEQ they were decided against
  (3.2.3.5), which maps one-to-one onto frame index, so each snapshot is
  diffed against its expected-book row directly.

> The preprocessor asserts three sanity checks on every run --- every
> Modify/Delete references a known order, no book quantity goes
> negative, and every encoded frame decodes back to its source event ---
> and all three passed with zero violations across the full real day.
> Its output is also deterministic: two passes over the same file and
> parameters produce byte-identical streams, which is what makes FS7\'s
> bootstrap corpus reproducible end-to-end.

- **Replayer & Order Receiver (online).** The Replayer is a paced sendto
  loop that streams the frame file and logs TX timestamps.
  Symmetrically, the Order Receiver blindly captures incoming raw
  packets and RX timestamps to an offline log. Neither component parses
  or processes data at runtime.

- **FS11 Offline Checker (post-session).** Parses the receiver\'s log
  against *Table 7*, functioning as the spec-validation oracle and
  isolating parsing overhead from session execution. A full session\'s
  logs total tens of MB and average wire utilization is around 0.001% of
  the GbE link --- data volume is a non-issue, so the NFS4 soak run
  keeps full logging on throughout.

#### 3.4.3.2 Pacing and Link Configuration

The rate_scale parameter controls pacing. A rate_scale of 1 faithfully
reproduces real-world microsecond timing for formal verification (e.g.,
NFS4 soak, FS2 measurement). For rapid development, the \~38× send
margin permits lossless session compression (e.g., rate_scale = 20
replays the 6.5-hour day in \< 20 minutes with its burst structure
intact). Physically, the host NIC is directly cabled to the PL (no
switch) using static IP/MAC configurations to eliminate external
networking variables. The simulator runs as an independent host process,
relying on Wireshark and host-clocked TX/RX logs as the primary
measurement instruments for drop-free assertions (NFS2).

### 3.4.4 Specification Compliance Summary

A summary of the target validation metrics and compliance status for the
owned simulator specifications is presented in *Table 27*.

*Table 27:* *Exchange Simulator Specification Compliance Summary.*

  ---------------------------------------------------------------------------
  Spec           What the simulator provides  Evidence status
  -------------- ---------------------------- -------------------------------
  FS1/FS2        Reference sequences as       Design complete; pending slice
  (instrument)   preprocessed slices; TX log  authoring
                 as second timing witness     

  FS11 (oracle)  Offline parse of every       Mechanism validated during
                 captured order packet        Decision 1\'s prototype run;
                 against *Table 7*            pending live cross-parse

  NFS2 (peer)    Direct-cabled peer; expected Pending 10-min counted run
                 frame count static in the    
                 frame file                   

  NFS4           6.5 h real-day replay at     Pending soak run
  (provider)     rate_scale = 1               

  FS6/FS7        Recorded replay session as   Translation validated at design
  (bootstrap)    FS7 bootstrap corpus         time; recorded session pending
                 (3.3.3.3)                    

  NFS3           Host software only --- \$0   By construction
                 hardware                     

  Own            Sanity checks, determinism,  Sandbox-measured; target-host
  correctness    and send-rate margin all     re-run pending
                 measured (3.4.3.1, 3.4.2)    
  ---------------------------------------------------------------------------

# 4. Discussion and Project Timeline

## 4.1 Evaluation of Final Design Against Objective and Specifications

The final design meets the project objective by keeping the intraday
critical path deterministic in hardware and pushing all changeable
decision logic into software. On the PL side, cut-through parsing closes
FS1\'s $\leq$ 1.5 μs snapshot budget in 77 clock cycles (616 ns) --- a
32% worst-case margin (3.1.2 Decision 2) --- while the fixed
register-array order book and TEMAC MAC keep NFS6 resource use to about
11% of LUTs and 3% of BRAM (3.1.2 Decision 3). On the PS side, the
busy-poll register interface closes FS2\'s $\leq$ 30 μs decision budget
with roughly 5.5× margin (3.2.2 Decision 3, *Table 13*), and the Runtime
Risk Guard adds under 0.1% of that budget while unconditionally
enforcing FS3\'s notional, position, rate, and in-flight limits
(3.2.3.3). The EOD pipeline satisfies FS6 by construction --- the
percentile-threshold classifier cannot collapse to a single regime label
(3.3.2 Decision 2) --- and satisfies FS7\'s bit-identical requirement by
closing every enumerated source of nondeterminism (3.3.3.3), completing
its 30-minute NFS5 budget with roughly 15× margin. The Exchange
Simulator closes the loop by supplying the only real, repeatable L3 data
source the PL path can be measured against (3.4.2 Decision 1).

Compliance is summarized per subsystem in *Tables 9, 18, 23,* and *27*.
Every essential spec closes analytically with margin to spare; what
remains is empirical confirmation on real hardware --- timing on the
synthesized board, a full 6.5-hour soak for NFS4, and the injection and
stress tests listed in each compliance table. No essential spec
currently identifies a design gap.

## 4.2 Use of Advanced ECE Knowledge

Digital hardware design and timing analysis (*ECE 327*) are used in the
PL parser, order book update path, and cycle-level latency budget.
Computer architecture and embedded systems knowledge (*ECE 320, ECE
455*) are used in the AXI-Lite memory-mapped register interface, the
seqlock-protected snapshot read, the cached-DDR logging ring, and the
PS/PL partitioning. Real-time operating systems knowledge (*ECE 350*) is
used in CPU isolation via isolcpus, the choice of busy-poll over
interrupt-driven wakeup to avoid scheduler jitter, and the bounded
poll-to-decision software timing budget. Computer networks knowledge
(*ECE 358*) is used in UDP payload design, fixed-width binary encoding,
packet capture verification, and simulator bridge contracts.
Quantitative finance and optimization knowledge are used in realized
volatility, moving-average crossover features, Sharpe-ratio parameter
selection, and risk-limited configuration generation.

## 4.3 Creativity, Novelty, and Elegance of the AQTA Design

AQTA\'s elegance shows in four separations. The PL market-data path
splits into RX and TX lanes sharing one TEMAC and AXI-Lite bank but
disjoint read/write contracts, synchronized only by the DOORBELL strobe
(3.1.3.3). The PS interface rejects interrupt-plus-DMA (3.2.2 Decision
3) for busy-poll register access, since the register path\'s throughput
already exceeds one strategy core\'s consumption --- fewer
driver/coherency bugs, not more hardware. The EOD classifier is
structurally robust: percentile thresholds make FS6\'s $\geq$ 3-regime
requirement impossible to violate by construction (3.3.2 Decision 2),
and the parameter grid follows suit, giving Defensive a 3×3 grid instead
of a forced 3×3×3 since it has only two real degrees of freedom
(3.3.3.3). RiskGuard is a strategy-independent layer no order can bypass
(3.2.3.3), with HOLD Mode --- the absence of a doorbell write --- as its
fail-safe state.

## 4.4 Student Hours

The breakdown of engineering development hours contributed by each
student is tracked in *Table 28.*

*Table 28: Student Hours Completed to Date.*

  -------------------------------
  Team Member    Hours Completed
  -------------- ----------------
  Hanyu Yao      72

  Catherine Ye   74

  Ashley Wu      72

  Panzy Pan      71

  Lucy Sun       73
  -------------------------------

## 4.5 Potential Safety Hazards

Physical safety risk is low: the prototype\'s only hardware is a
low-voltage Xilinx development board and a personal PC, with no motors,
high voltage, or moving parts. Standard lab precautions still apply ---
power is disconnected before rewiring, cables are secured, and exposed
conductors are not probed while the board is powered.

The real potential risk is financial and professional, not physical:
fast execution can be mistaken for a validated trading strategy. AQTA
carries no actual financial exposure --- the Exchange Simulator replays
a recorded historical trading day (3.4) rather than connecting to any
live market or broker, so no real money or real order ever exists. The
perception risk is controlled at the design level: every EOD-generated
configuration requires explicit operator approval before deployment,
every decision and rejection is logged, and RiskGuard\'s limits apply
regardless of which strategy is active.

## 4.6 Project Timeline

*Figure 6* schedules the project timeline in Gantt Chart with different
group of tasks and dates.

![](media/image6.emf){width="7.389763779527559in"
height="5.090551181102362in"}

*Figure 6: Project Timeline Gantt Chart.*

# References

\[1\] C. Leber, B. Geib and H. Litz, \"High Frequency Trading
Acceleration Using FPGAs,\" *2011 21st International Conference on Field
Programmable Logic and Applications*, Chania, Greece, 2011, pp. 317-322,
doi: 10.1109/FPL.2011.64.

\[2\] Y.-C. Kao, H.-A. Chen and H.-P. Ma, \"An FPGA-Based High-Frequency
Trading System for 10 Gigabit Ethernet with a Latency of 433 ns,\" *2022
International Symposium on VLSI Design, Automation and Test (VLSI-DAT)*,
Hsinchu, Taiwan, 2022, pp. 1-4, doi: 10.1109/VLSI-DAT54769.2022.9768065.

\[3\] Xilinx, \"Zynq-7000 SoC Data Sheet: Overview,\" DS190. \[Online\].
Available: <https://docs.amd.com/v/u/en-US/ds190-Zynq-7000-Overview>
\[Accessed: Jul. 11, 2026\].

\[4\] G. W. Morris, D. B. Thomas and W. Luk, \"FPGA Accelerated
Low-Latency Market Data Feed Processing,\" *2009 17th IEEE Symposium on
High Performance Interconnects*, New York, NY, USA, 2009, pp. 83-89,
doi: 10.1109/HOTI.2009.17.

\[5\] 正点原子 (ALIENTEK), \"领航者 ZYNQ 之嵌入式开发指南 / Navigator
ZYNQ-7020 Development Board User Manual.\" \[Online\]. Available:
<http://www.openedv.com/docs/boards/fpga/zdyz_linhanzhe.html>
\[Accessed: Jul. 10, 2026\].

\[6\] Xilinx, \"Zynq-7000 SoC Technical Reference Manual,\" UG585.
\[Online\]. Available:
[https://docs.amd.com/r/en-US/ug585-zynq-7000-SoC-TRM/Overview](https://www.google.com/search?q=https://docs.amd.com/r/en-US/ug585-zynq-7000-SoC-TRM/Overview)
\[Accessed: Jul. 12, 2026\].

\[7\] J. D. Hamilton, \"A New Approach to the Economic Analysis of
Nonstationary Time Series and the Business Cycle,\" *Econometrica*, vol.
57, no. 2, pp. 357--384, Mar. 1989, doi: 10.2307/1912559.

\[8\] K. Tatsumura, R. Hidaka, J. Nakayama, T. Kashimata, and M.
Yamasaki, \"Real-time Trading System based on Selections of Potentially
Profitable, Uncorrelated, and Balanced Stocks by NP-hard Combinatorial
Optimization,\" Corporate Research and Development Center, Toshiba
Corporation, Japan, 2023.

\[9\] K. Tatsumura, R. Hidaka, J. Nakayama, T. Kashimata, and M.
Yamasaki, \"Pairs-trading System using Quantum-inspired Combinatorial
Optimization Accelerator for Optimal Path Search in Market Graphs,\"
Corporate Research and Development Center, Toshiba Corporation, Japan,
2023.

\[10\] A. Boutros, B. Grady, M. Abbas and P. Chow, \"Build fast, trade
fast: FPGA-based high-frequency trading using high-level synthesis,\"
*2017 International Conference on ReConFigurable Computing and FPGAs
(ReConFig)*, Cancun, Mexico, 2017, pp. 1-6, doi:
10.1109/RECONFIG.2017.8279781.

\[11\] R. Osuna, B. Reponte, and L. G. Ramirez, \"Low-latency Ethernet
communications on FPGA SoC for high frequency trading,\" Kastner
Research Group, University of California, San Diego, San Diego, CA, USA,
Tech. Rep., Jun. 2025. \[Online\]. Available:
<https://kastner.ucsd.edu/wp-content/uploads/2025/06/admin/highfrequencytrading.pdf>

\[12\] Interactive Brokers, \"Market Depth (Level II),\" TWS API v9.72+
Documentation. \[Online\]. Available:
<https://interactivebrokers.github.io/tws-api/market_depth.html>
\[Accessed: Jul. 9, 2026\].

\[13\] C. He, H. Fu, W. Luk, W. Li and G. Yang, \"Exploring the
potential of reconfigurable platforms for order book update,\" *2017
27th International Conference on Field Programmable Logic and
Applications (FPL)*, Ghent, Belgium, 2017, pp. 1-8, doi:
10.23919/FPL.2017.8056862.

\[14\] R. Huang and T. Polak, \"LOBSTER: Limit Order Book Reconstruction
System,\" SSRN Working Paper 1977207, Humboldt-Universität zu Berlin,
Dec. 2011, doi: 10.2139/ssrn.1977207.

\[15\] Y. Zheng, \"FPGA-based Acceleration for High Frequency Trading,\"
M.Phil. thesis, Dept. Electron. Comput. Eng., Hong Kong Univ. Sci.
Technol., Hong Kong, Jan. 2023.

\[16\] LOBSTER, \"Sample Files\" and \"Data Structure,\" LOBSTER
academic data, Humboldt-Universität zu Berlin. \[Online\]. Available:
<https://lobsterdata.com/info/DataSamples.php> ;
<https://lobsterdata.com/info/DataStructure.php> (dataset: AAPL
2012-06-21, levels 1--50; official NASDAQ Historical TotalView-ITCH
sample day). \[Accessed: Jul. 9, 2026\].
